"""
src/application/orchestrator.py
Orchestrator — Tick loop에서 Flow 순서대로 실행 (application layer 통합)

SSOT:
- FLOW.md Section 2: Tick Ordering (Emergency-first)
- FLOW.md Section 4.2: God Object 금지 (책임 분리)
- task_plan.md Phase 6: Tick 순서 고정 (Emergency → Events → Position → Entry)

원칙:
1. Thin wrapper: 각 책임은 이미 구현된 모듈에 위임
2. Tick 순서 고정: Emergency → Events → Position → Entry
3. 상태 관리: transition() 호출로 state 전환

Exports:
- Orchestrator: Tick loop orchestrator
- TickResult: Tick 실행 결과 (state, execution_order, halt_reason 등)
"""

import logging
import time
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from domain.state import State, Position, Direction, StopStatus

logger = logging.getLogger(__name__)
from infrastructure.exchange.market_data_interface import MarketDataInterface
from application.exit_manager import check_stop_hit, create_exit_intent
from domain.intent import ExitIntent

# Phase 11b: Entry Flow imports
from application.entry_allowed import check_entry_allowed, EntryDecision
from application.signal_generator import generate_signal, calculate_grid_spacing, Signal
from application.sizing import calculate_contracts, SizingResult
from application.event_processor import match_pending_order, create_position_from_fill  # Phase 12a-4c: REST API fallback

# Phase 11b: Refactored modules (God Object mitigation)
from application.emergency_checker import check_emergency_status
from application.entry_coordinator import (
    get_stage_params,
    build_signal_context,
    build_sizing_params,
    generate_signal_id,
)
from application.event_processor import (
    verify_state_consistency,
    match_pending_order,
    create_position_from_fill,
)

# Phase 11b: Trade Log Integration
from infrastructure.logging.trade_logger_v1 import TradeLogV1, calculate_market_regime, validate_trade_log_v1
from infrastructure.storage.log_storage import LogStorage

# Stop Manager Integration (Codex Review Fix #1)
from application.stop_manager import should_update_stop, determine_stop_action

# KillSwitch Integration (Codex Review Fix #2)
from infrastructure.safety.killswitch import KillSwitch


@dataclass
class TickResult:
    """Tick 실행 결과"""

    state: State
    execution_order: List[str]
    halt_reason: Optional[str] = None
    entry_blocked: bool = False
    entry_block_reason: Optional[str] = None
    exit_intent: Optional[ExitIntent] = None  # Exit 주문 의도 (Phase 11)


class Orchestrator:
    """
    Orchestrator — Tick loop에서 Flow 순서대로 실행

    FLOW Section 4.2:
        - God Object 금지
        - 책임 분리: emergency/events/position/entry는 별도 모듈에 위임

    task_plan.md Phase 6:
        - Tick 순서 고정: Emergency → Events → Position → Entry
        - degraded/normal 분리, degraded 60s → halt
    """

    def __init__(
        self,
        market_data: MarketDataInterface,
        rest_client=None,  # Phase 11b: Order placement용 (Optional, type: BybitRestClient)
        log_storage: Optional[LogStorage] = None,  # Phase 11b: Trade Log 저장용 (Optional)
        killswitch: Optional[KillSwitch] = None,  # Codex Review Fix #2: Manual halt mechanism
        config_hash: str = "unknown",  # P0 fix: 실제 config hash (safety_limits.yaml 기반)
        git_commit: str = "unknown",  # P0 fix: 실제 git commit hash
    ):
        """
        Orchestrator 초기화

        Args:
            market_data: Market data interface (FakeMarketData or BybitAdapter)
            rest_client: Bybit REST client (Order placement용, Phase 11b)
            log_storage: LogStorage (Trade Log 저장용, Phase 11b)
            killswitch: KillSwitch (Manual halt mechanism, Codex Review Fix #2)
            config_hash: Config 해시 (safety_limits.yaml 기반, 재현성)
            git_commit: Git commit 해시 (코드 버전 추적)
        """
        self.market_data = market_data
        self.rest_client = rest_client
        self.log_storage = log_storage
        self.killswitch = killswitch if killswitch is not None else KillSwitch()
        self.config_hash = config_hash
        self.git_commit = git_commit
        self.tick_counter = 0  # Tick counter (general purpose)

        # Position recovery: 기존 포지션이 있으면 State.IN_POSITION으로 시작
        self.state = State.FLAT
        self.position = None

        if rest_client is not None:
            try:
                pos_response = rest_client.get_position(symbol="BTCUSDT", category="linear")

                if pos_response["retCode"] == 0:
                    positions = pos_response["result"]["list"]

                    if positions and len(positions) > 0:
                        existing_pos = positions[0]
                        size_btc = float(existing_pos.get("size", "0"))

                        if size_btc > 0:
                            # 기존 포지션 발견 → State.IN_POSITION으로 복구
                            qty = int(size_btc * 1000)  # BTC to contracts
                            entry_price = float(existing_pos.get("avgPrice", "0"))
                            side = existing_pos.get("side", "")
                            direction = Direction.LONG if side == "Buy" else Direction.SHORT

                            self.position = Position(
                                qty=qty,
                                entry_price=entry_price,
                                direction=direction,
                                signal_id="recovered",  # Position recovery
                                stop_status=StopStatus.MISSING,  # Force stop recovery
                                stop_price=entry_price,  # Initial stop = entry
                            )
                            self.state = State.IN_POSITION

                            logger.info(f"✅ Position recovered: {side} {qty} contracts @ ${entry_price:.2f}")
                        else:
                            logger.info("✅ No existing position found (size=0)")
                    else:
                        logger.info("✅ No existing position found (empty list)")
                else:
                    logger.warning(f"⚠️ Position recovery API error: {pos_response['retMsg']}")
            except Exception as e:
                logger.warning(f"⚠️ Position recovery failed: {e} - Starting with State.FLAT")
                self.state = State.FLAT
                self.position = None

        # Phase 11b: Entry Flow tracking
        self.pending_order: Optional[dict] = None  # Pending order 정보 (FILL event 매칭용)
        self.pending_order_timestamp: Optional[float] = None  # Phase 12a-4c: Pending order 발주 시각 (timeout 체크용)
        self.current_signal_id: Optional[str] = None  # 현재 Signal ID
        self.grid_spacing: float = 0.0  # Grid spacing (ATR * 2.0)

        # Session Risk Policy 설정 (Phase 9c)
        self.daily_loss_cap_pct = 5.0  # 5% equity
        self.weekly_loss_cap_pct = 12.5  # 12.5% equity
        self.fee_spike_threshold = 1.5  # Fee ratio threshold
        self.slippage_threshold_usd = 2.0  # Slippage threshold ($)
        self.slippage_window_seconds = 600.0  # 10 minutes
        self.current_timestamp = None  # Slippage anomaly용

        # Stop Manager 상태 (Codex Review Fix #1)
        self.last_stop_update_at: float = 0.0  # 마지막 stop 갱신 시각
        self.amend_fail_count: int = 0  # Amend 실패 횟수

    def run_tick(self) -> TickResult:
        """
        Tick 실행 (Emergency → Events → Position → Entry)

        Returns:
            TickResult: Tick 실행 결과

        FLOW Section 2:
            - Emergency check (최우선)
            - Events processing (WS 이벤트)
            - Position management (stop 갱신)
            - Entry decision (signal → gate → sizing)
        """
        import logging
        logger = logging.getLogger(__name__)

        # Tick counter increment
        self.tick_counter += 1

        # Phase 9d: current_timestamp 초기화 (Slippage anomaly 체크용)
        self.current_timestamp = self.market_data.get_timestamp()

        execution_order = []
        halt_reason = None
        entry_blocked = False
        entry_block_reason = None

        # (0a) KillSwitch check (최우선, Codex Review Fix #2)
        if self.killswitch.is_halted():
            self.state = State.HALT
            halt_reason = "manual_halt_killswitch"
            return TickResult(
                state=self.state,
                execution_order=["killswitch_check"],
                halt_reason=halt_reason,
            )

        # (0) Self-healing check (Position vs State 일관성, Phase 11b)
        inconsistency_reason = verify_state_consistency(
            position=self.position,
            state=self.state,
        )
        if inconsistency_reason is not None:
            self.state = State.HALT
            halt_reason = inconsistency_reason
            return TickResult(
                state=self.state,
                execution_order=["self_healing_check"],
                halt_reason=halt_reason,
            )

        # (1) Emergency check (최우선)
        execution_order.append("emergency")
        emergency_result = self._check_emergency()
        if emergency_result["status"] == "HALT":
            self.state = State.HALT
            halt_reason = emergency_result["reason"]
            return TickResult(
                state=self.state,
                execution_order=execution_order,
                halt_reason=halt_reason,
            )

        # (2) Events processing
        execution_order.append("events")
        self._process_events()

        # (3) Position management + Exit decision
        execution_order.append("position")
        exit_intent = self._manage_position()

        # (4) Entry decision
        execution_order.append("entry")
        entry_result = self._decide_entry()
        if entry_result["blocked"]:
            entry_blocked = True
            entry_block_reason = entry_result["reason"]

        return TickResult(
            state=self.state,
            execution_order=execution_order,
            halt_reason=halt_reason,
            entry_blocked=entry_blocked,
            entry_block_reason=entry_block_reason,
            exit_intent=exit_intent,  # Phase 11: Exit intent
        )

    def _log_completed_trade(self, event: Dict[str, Any], position: Optional[Position]) -> None:
        """
        완료된 거래를 Trade Log v1.0으로 기록한다.

        Args:
            event: Exit FILL event
            position: 청산된 Position (Exit FILL 직전 상태)
        """
        if position is None:
            return

        # Exit fill 데이터 추출
        if hasattr(event, 'order_id'):
            # ExecutionEvent dataclass
            order_id = event.order_id or "unknown"
            exec_price = float(event.exec_price)
            exec_qty_btc = float(event.filled_qty) * 0.001
            fee_usd = abs(float(event.fee_paid)) if event.fee_paid is not None else 0.0
            event_timestamp = event.timestamp  # Bybit execTime (ms)
        else:
            # dict (REST API fallback)
            order_id = event.get("orderId", "unknown")
            exec_price = float(event.get("execPrice", 0.0))
            exec_qty_btc = float(event.get("execQty", 0.0))
            fee_usd = abs(float(event.get("execFee", 0.0)))
            event_timestamp = float(event.get("execTime", 0))

        # 거래 결과 계산
        entry_price = position.entry_price
        exit_price = exec_price
        qty_btc = exec_qty_btc
        direction = position.direction.value  # "LONG" or "SHORT"
        exit_side = "Sell" if position.direction == Direction.LONG else "Buy"

        # PnL 계산 (Linear USDT)
        if position.direction == Direction.LONG:
            realized_pnl_usd = (exit_price - entry_price) * qty_btc
        else:
            realized_pnl_usd = (entry_price - exit_price) * qty_btc

        fills = [
            {
                "price": exit_price,
                "qty": int(qty_btc * 1000),
                "fee": fee_usd,
                "timestamp": self.market_data.get_timestamp(),
            }
        ]

        # Market data
        funding_rate = self.market_data.get_funding_rate()
        mark_price = self.market_data.get_mark_price()
        index_price = self.market_data.get_index_price()

        # Market regime
        ma_slope_pct = self.market_data.get_ma_slope_pct()
        atr_percentile = self.market_data.get_atr_percentile()
        market_regime = calculate_market_regime(
            ma_slope_pct=ma_slope_pct,
            atr_percentile=atr_percentile,
        )

        exchange_server_time_offset_ms = self.market_data.get_exchange_server_time_offset_ms()

        # Slippage 계산: 주문 가격(expected) vs 실제 체결 가격
        expected_price = self.pending_order.get("price", 0.0) if self.pending_order else 0.0
        slippage_usd = abs(exec_price - expected_price) * qty_btc if expected_price > 0 else 0.0

        # Latency 계산: 주문 발주 시각 → Bybit 체결 시각 → 우리 수신 시각
        now = time.time()
        if self.pending_order_timestamp and event_timestamp > 0:
            exec_time_sec = event_timestamp / 1000.0 if event_timestamp > 1e12 else event_timestamp
            latency_rest_ms = max(0.0, (exec_time_sec - self.pending_order_timestamp) * 1000.0)
            latency_ws_ms = max(0.0, (now - exec_time_sec) * 1000.0)
            latency_total_ms = (now - self.pending_order_timestamp) * 1000.0
        else:
            latency_rest_ms = 0.0
            latency_ws_ms = 0.0
            latency_total_ms = 0.0

        trade_log = TradeLogV1(
            order_id=order_id,
            fills=fills,
            slippage_usd=slippage_usd,
            latency_rest_ms=latency_rest_ms,
            latency_ws_ms=latency_ws_ms,
            latency_total_ms=latency_total_ms,
            funding_rate=funding_rate,
            mark_price=mark_price,
            index_price=index_price,
            orderbook_snapshot={},
            market_regime=market_regime,
            side=exit_side,
            direction=direction,
            qty_btc=qty_btc,
            entry_price=entry_price,
            exit_price=exit_price,
            realized_pnl_usd=realized_pnl_usd,
            fee_usd=fee_usd,
            schema_version="1.0",
            config_hash=self.config_hash,
            git_commit=self.git_commit,
            exchange_server_time_offset_ms=exchange_server_time_offset_ms,
        )

        validate_trade_log_v1(trade_log)

        log_dict = asdict(trade_log)
        self.log_storage.append_trade_log_v1(log_entry=log_dict, is_critical=False)
        logger.info(f"📝 Trade logged: {direction} {exit_side} {qty_btc:.4f} BTC, entry=${entry_price:,.2f} → exit=${exit_price:,.2f}, PnL=${realized_pnl_usd:,.4f}, fee=${fee_usd:,.4f}")

    def get_state(self) -> State:
        """현재 상태 반환"""
        return self.state

    def _check_emergency(self) -> dict:
        """
        Emergency 체크 (최우선)

        Returns:
            {"status": "PASS" or "HALT", "reason": str}

        FLOW Section 7.1 + Phase 9c Session Risk Policy
        Refactored: Delegates to emergency_checker.check_emergency_status()
        """
        return check_emergency_status(
            market_data=self.market_data,
            daily_loss_cap_pct=self.daily_loss_cap_pct,
            weekly_loss_cap_pct=self.weekly_loss_cap_pct,
            fee_spike_threshold=self.fee_spike_threshold,
            slippage_threshold_usd=self.slippage_threshold_usd,
            slippage_window_seconds=self.slippage_window_seconds,
            current_timestamp=self.current_timestamp,
        )

    def _process_events(self) -> None:
        """
        Events 처리 (FILL → Position update)

        FLOW Section 2.5:
            - FILL event 수신
            - Pending order 매칭 (Dual ID tracking)
            - Position 생성 + State 전환 (atomic)

        Phase 11b: Entry/Exit FILL event 처리
        Phase 12a-4c: REST API polling fallback (WebSocket FILL 이벤트 미수신 시)
        리스크 완화:
        - Atomic state transition (Position + State 동시 전환)
        - Dual ID matching (orderId + orderLinkId)
        - Exception handling (롤백)
        """
        import logging
        logger = logging.getLogger(__name__)

        # Phase 12a-4c: REST API polling fallback (WebSocket timeout 시)
        # EXIT_PENDING 또는 ENTRY_PENDING 상태에서 10초 경과 시 REST API로 주문 조회
        # (5초 → 10초: WS FILL 이벤트 도착 시간 확보, race condition 방지)
        WEBSOCKET_TIMEOUT = 10.0  # seconds
        if (self.state in [State.ENTRY_PENDING, State.EXIT_PENDING] and
            self.pending_order is not None and
            self.pending_order_timestamp is not None):

            elapsed = time.time() - self.pending_order_timestamp
            if elapsed > WEBSOCKET_TIMEOUT:
                logger.warning(f"⚠️ WebSocket FILL event not received after {elapsed:.1f}s, polling REST API...")

                # REST API로 주문 상태 조회
                if self.rest_client is not None:
                    try:
                        order_id = self.pending_order.get("order_id")
                        order_link_id = self.pending_order.get("order_link_id")

                        # Phase 12b Fix: order_id가 None이면 position 확인으로 실제 상태 결정
                        if not order_id:
                            logger.error(f"❌ Invalid pending_order: order_id is None")
                            # Position API로 실제 상태 확인
                            try:
                                pos_response = self.rest_client.get_position(
                                    category="linear",
                                    symbol="BTCUSDT",
                                )
                                positions = pos_response.get("result", {}).get("list", [])
                                has_position = positions and float(positions[0].get("size", "0")) > 0
                            except Exception:
                                has_position = False

                            if self.state == State.EXIT_PENDING and not has_position:
                                # Exit 완료 (포지션 없음)
                                logger.info("✅ No position found, EXIT completed → FLAT")
                                self.state = State.FLAT
                                self.position = None
                            elif self.state == State.ENTRY_PENDING and has_position:
                                # Entry 완료 (포지션 있음)
                                logger.info("✅ Position found, ENTRY completed → IN_POSITION")
                                self.state = State.IN_POSITION
                            else:
                                # 불확실 → FLAT으로 복귀 (안전)
                                logger.warning(f"⚠️ Ambiguous state, resetting to FLAT (had_position={has_position})")
                                self.state = State.FLAT
                                self.position = None
                            self.pending_order = None
                            self.pending_order_timestamp = None
                            return  # Skip fallback

                        # GET /v5/order/realtime (주문 상태 조회)
                        order_response = self.rest_client.get_open_orders(
                            category="linear",
                            symbol="BTCUSDT",
                            orderId=order_id,
                        )

                        # Bybit V5 response: {"result": {"list": [...]}}
                        orders = order_response.get("result", {}).get("list", [])

                        if not orders:
                            # 주문이 open orders에 없음 → 체결(Filled) 또는 취소(Cancelled)
                            logger.info(f"ℹ️ Order {order_id} not in open orders (filled or cancelled)")

                            # Execution list에서 FILL 이벤트 조회
                            exec_response = self.rest_client.get_execution_list(
                                category="linear",
                                symbol="BTCUSDT",
                                orderId=order_id,
                                limit=50,
                            )

                            executions = exec_response.get("result", {}).get("list", [])
                            if executions:
                                # 첫 번째 execution을 FILL 이벤트로 처리
                                fill_event = executions[0]
                                logger.info(f"✅ Got FILL event from REST API: {fill_event}")

                                # FILL 이벤트 처리 (아래 WebSocket 처리 로직과 동일)
                                matched = match_pending_order(event=fill_event, pending_order=self.pending_order)
                                if matched:
                                    position = create_position_from_fill(event=fill_event, pending_order=self.pending_order)

                                    if self.state == State.ENTRY_PENDING:
                                        self.position = position
                                        self.state = State.IN_POSITION
                                        self.pending_order = None
                                        self.pending_order_timestamp = None
                                        logger.info("✅ REST API fallback: ENTRY_PENDING → IN_POSITION")
                                    elif self.state == State.EXIT_PENDING:
                                        if self.log_storage is not None:
                                            self._log_completed_trade(event=fill_event, position=self.position)

                                        self.position = None
                                        self.state = State.FLAT
                                        self.pending_order = None
                                        self.pending_order_timestamp = None
                                        logger.info("✅ REST API fallback: EXIT_PENDING → FLAT")
                            else:
                                # Execution 없음 → order history로 실제 상태 확인
                                # (Race condition: 체결 직후 execution list 미전파 가능)
                                try:
                                    history_response = self.rest_client.get_order_history(
                                        category="linear",
                                        symbol="BTCUSDT",
                                        orderId=order_id,
                                    )
                                    history_orders = history_response.get("result", {}).get("list", [])
                                    if history_orders:
                                        order_status = history_orders[0].get("orderStatus", "Unknown")
                                        logger.info(f"ℹ️ Order history status: {order_status}")

                                        if order_status == "Filled":
                                            # 체결됐지만 execution list 미전파 → 2초 후 재시도
                                            logger.info("⏳ Order Filled but no executions yet, retrying in 2s...")
                                            time.sleep(2)
                                            retry_response = self.rest_client.get_execution_list(
                                                category="linear",
                                                symbol="BTCUSDT",
                                                orderId=order_id,
                                                limit=50,
                                            )
                                            retry_execs = retry_response.get("result", {}).get("list", [])
                                            if retry_execs:
                                                fill_event = retry_execs[0]
                                                logger.info(f"✅ Got FILL event from REST API (retry): {fill_event}")
                                                matched = match_pending_order(event=fill_event, pending_order=self.pending_order)
                                                if matched:
                                                    position = create_position_from_fill(event=fill_event, pending_order=self.pending_order)
                                                    if self.state == State.ENTRY_PENDING:
                                                        self.position = position
                                                        self.state = State.IN_POSITION
                                                        self.pending_order = None
                                                        self.pending_order_timestamp = None
                                                        logger.info("✅ REST API fallback (retry): ENTRY_PENDING → IN_POSITION")
                                                    elif self.state == State.EXIT_PENDING:
                                                        if self.log_storage is not None:
                                                            self._log_completed_trade(event=fill_event, position=self.position)
                                                        self.position = None
                                                        self.state = State.FLAT
                                                        self.pending_order = None
                                                        self.pending_order_timestamp = None
                                                        logger.info("✅ REST API fallback (retry): EXIT_PENDING → FLAT")
                                            else:
                                                # 재시도에도 execution 없음 → position 직접 확인
                                                logger.warning(f"⚠️ Order Filled but no executions after retry, checking position...")
                                                # Position API로 직접 포지션 확인
                                                pos_response = self.rest_client.get_position(
                                                    category="linear",
                                                    symbol="BTCUSDT",
                                                )
                                                positions = pos_response.get("result", {}).get("list", [])
                                                if positions and float(positions[0].get("size", "0")) > 0:
                                                    if self.state == State.ENTRY_PENDING:
                                                        # Entry Filled + position 존재 → Position API에서 직접 복구
                                                        existing_pos = positions[0]
                                                        size_btc = float(existing_pos.get("size", "0"))
                                                        qty = int(size_btc * 1000)  # BTC → contracts
                                                        entry_price = float(existing_pos.get("avgPrice", "0"))
                                                        side = existing_pos.get("side", "")
                                                        direction = Direction.LONG if side == "Buy" else Direction.SHORT
                                                        signal_id = self.pending_order.get("signal_id", "recovered") if self.pending_order else "recovered"

                                                        self.position = Position(
                                                            qty=qty,
                                                            entry_price=entry_price,
                                                            direction=direction,
                                                            signal_id=signal_id,
                                                            stop_status=StopStatus.MISSING,
                                                            stop_price=entry_price,
                                                        )
                                                        self.state = State.IN_POSITION
                                                        self.pending_order = None
                                                        self.pending_order_timestamp = None
                                                        logger.info(f"✅ Position recovered from API: {side} {qty} @ ${entry_price:.2f}, ENTRY_PENDING → IN_POSITION")
                                                    elif self.state == State.EXIT_PENDING:
                                                        # Exit Filled인데 position 아직 존재 → pending 초기화, 다음 tick에서 재시도
                                                        logger.warning(f"⚠️ Exit order Filled but position still exists, clearing pending for retry")
                                                        self.pending_order = None
                                                        self.pending_order_timestamp = None
                                                else:
                                                    logger.warning(f"⚠️ No position found, resetting to FLAT")
                                                    prev_state = self.state
                                                    self.state = State.FLAT
                                                    self.pending_order = None
                                                    self.pending_order_timestamp = None
                                                    logger.info(f"✅ State recovered: {prev_state} → State.FLAT")
                                        elif order_status == "Cancelled":
                                            logger.warning(f"⚠️ Order {order_id} confirmed Cancelled, resetting to FLAT")
                                            prev_state = self.state
                                            self.state = State.FLAT
                                            self.pending_order = None
                                            self.pending_order_timestamp = None
                                            logger.info(f"✅ State recovered: {prev_state} → State.FLAT")
                                        else:
                                            # 예상 외 상태 (PartiallyFilled 등) → position API로 직접 판단
                                            logger.warning(f"⚠️ Order {order_id} status={order_status}, checking position API...")
                                            try:
                                                pos_resp = self.rest_client.get_position(category="linear", symbol="BTCUSDT")
                                                pos_list = pos_resp.get("result", {}).get("list", [])
                                                has_pos = pos_list and float(pos_list[0].get("size", "0")) > 0
                                            except Exception:
                                                has_pos = False
                                            if self.state == State.ENTRY_PENDING and has_pos:
                                                existing = pos_list[0]
                                                size_btc = float(existing.get("size", "0"))
                                                qty = int(size_btc * 1000)
                                                entry_price = float(existing.get("avgPrice", "0"))
                                                side = existing.get("side", "")
                                                direction = Direction.LONG if side == "Buy" else Direction.SHORT
                                                sig_id = self.pending_order.get("signal_id", "recovered") if self.pending_order else "recovered"
                                                self.position = Position(qty=qty, entry_price=entry_price, direction=direction, signal_id=sig_id, stop_status=StopStatus.MISSING, stop_price=entry_price)
                                                self.state = State.IN_POSITION
                                                self.pending_order = None
                                                self.pending_order_timestamp = None
                                                logger.info(f"✅ Position recovered: {side} {qty} @ ${entry_price:.2f}, {order_status} → IN_POSITION")
                                            elif self.state == State.EXIT_PENDING and not has_pos:
                                                self.state = State.FLAT
                                                self.position = None
                                                self.pending_order = None
                                                self.pending_order_timestamp = None
                                                logger.info(f"✅ No position, {order_status} → FLAT")
                                            else:
                                                # 판단 불가 → pending 초기화 (다음 tick에서 재평가)
                                                self.pending_order = None
                                                self.pending_order_timestamp = None
                                                logger.warning(f"⚠️ Ambiguous: state={self.state}, has_pos={has_pos}, clearing pending")
                                    else:
                                        # Order history에도 없음 → position API로 직접 판단
                                        logger.warning(f"⚠️ Order {order_id} not found in history, checking position API...")
                                        try:
                                            pos_resp = self.rest_client.get_position(category="linear", symbol="BTCUSDT")
                                            pos_list = pos_resp.get("result", {}).get("list", [])
                                            has_pos = pos_list and float(pos_list[0].get("size", "0")) > 0
                                        except Exception:
                                            has_pos = False
                                        if self.state == State.ENTRY_PENDING and has_pos:
                                            existing = pos_list[0]
                                            size_btc = float(existing.get("size", "0"))
                                            qty = int(size_btc * 1000)
                                            entry_price = float(existing.get("avgPrice", "0"))
                                            side = existing.get("side", "")
                                            direction = Direction.LONG if side == "Buy" else Direction.SHORT
                                            sig_id = self.pending_order.get("signal_id", "recovered") if self.pending_order else "recovered"
                                            self.position = Position(qty=qty, entry_price=entry_price, direction=direction, signal_id=sig_id, stop_status=StopStatus.MISSING, stop_price=entry_price)
                                            self.state = State.IN_POSITION
                                            self.pending_order = None
                                            self.pending_order_timestamp = None
                                            logger.info(f"✅ Position recovered: {side} {qty} @ ${entry_price:.2f}, ENTRY_PENDING → IN_POSITION")
                                        elif self.state == State.EXIT_PENDING and not has_pos:
                                            self.state = State.FLAT
                                            self.position = None
                                            self.pending_order = None
                                            self.pending_order_timestamp = None
                                            logger.info(f"✅ No position found, EXIT_PENDING → FLAT")
                                        else:
                                            # 판단 불가 → pending 초기화
                                            self.pending_order = None
                                            self.pending_order_timestamp = None
                                            logger.warning(f"⚠️ Order not in history, state={self.state}, has_pos={has_pos}, clearing pending")
                                except Exception as hist_err:
                                    logger.error(f"❌ Order history check failed: {hist_err}")
                                    # Fallback: 기존 동작 (FLAT 복귀)
                                    logger.warning(f"⚠️ Order {order_id} status unknown, resetting to FLAT")
                                    prev_state = self.state
                                    self.state = State.FLAT
                                    self.pending_order = None
                                    self.pending_order_timestamp = None
                                    logger.info(f"✅ State recovered: {prev_state} → State.FLAT")
                        else:
                            # 주문이 여전히 open 상태 (미체결 또는 부분 체결)
                            order_status = orders[0].get("orderStatus")
                            logger.warning(f"⚠️ Order {order_id} still {order_status}, waiting...")

                    except Exception as e:
                        logger.error(f"❌ REST API polling failed: {type(e).__name__}: {e}")

        # WS에서 FILL event 가져오기 (Mock 구현)
        fill_events = self.market_data.get_fill_events()

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        if fill_events:
            logger.info(f">>> Got {len(fill_events)} FILL events from WS")

        for event in fill_events:
            try:
                # Debug logging (support both ExecutionEvent and dict)
                if hasattr(event, 'order_id'):
                    event_order_id = event.order_id
                    event_order_link_id = event.order_link_id
                else:
                    event_order_id = event.get("orderId")
                    event_order_link_id = event.get("orderLinkId")
                logger.info(f">>> Processing FILL event: order_id={event_order_id}, order_link_id={event_order_link_id}")
                logger.info(f">>> Pending order: {self.pending_order}")

                # Step 1: Pending order 매칭 (orderId 또는 orderLinkId)
                matched = match_pending_order(event=event, pending_order=self.pending_order)
                logger.info(f">>> Match result: {matched}")
                if not matched:
                    logger.warning(f">>> FILL event not matched, skipping")
                    continue  # 매칭 실패 → 다음 event

                # Step 2: Position 생성
                position = create_position_from_fill(event=event, pending_order=self.pending_order)

                # Step 3: State 전환 (atomic with Position)
                if self.state == State.ENTRY_PENDING:
                    # Entry FILL → IN_POSITION
                    self.position = position
                    self.state = State.IN_POSITION
                    self.pending_order = None  # Cleanup
                elif self.state == State.EXIT_PENDING:
                    # Exit FILL → FLAT
                    # Phase 11b: Trade Log 생성 및 저장 (DoD: "Trade log 정상 기록")
                    if self.log_storage is not None:
                        self._log_completed_trade(event=event, position=self.position)

                    self.position = None
                    self.state = State.FLAT
                    self.pending_order = None  # Cleanup

                # Step 4: Success (로그는 생략, Exception 발생 시만 처리)

            except Exception as e:
                # Exception 발생 시 State 롤백 (Position은 이미 None 또는 기존 유지)
                # 로그 기록 후 다음 event 처리
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f">>> Exception in _process_events: {type(e).__name__}: {e}")
                import traceback
                logger.error(f">>> Traceback: {traceback.format_exc()}")

    def _manage_position(self) -> Optional[ExitIntent]:
        """
        Position 관리 (stop 갱신 + exit decision)

        FLOW Section 2.5:
            - stop_manager.should_update_stop()
            - stop_manager.determine_stop_action()
            - Phase 11b: Exit decision (stop hit 체크 + Exit order placement)

        Returns:
            ExitIntent: Exit 주문 의도 (stop hit 시)
        """
        # IN_POSITION이 아니면 건너뛰기
        if self.state != State.IN_POSITION or self.position is None:
            return None

        # Phase 11b: Stop hit + Grid take-profit 체크
        current_price = self.market_data.get_current_price()

        should_exit = False
        exit_reason = "stop_loss_hit"

        # 1) Stop loss hit 체크
        if check_stop_hit(current_price=current_price, position=self.position):
            should_exit = True
            exit_reason = "stop_loss_hit"

        # 2) Grid take-profit 체크 (ATR * 2.0 기반)
        if not should_exit:
            atr = self.market_data.get_atr()
            if atr is not None and atr > 0:
                tp_spacing = atr * 1.5  # Take-profit spacing (ATR * 1.5, R:R >= 2:1)
                if self.position.direction == Direction.LONG:
                    take_profit_price = self.position.entry_price + tp_spacing
                    if current_price >= take_profit_price:
                        should_exit = True
                        exit_reason = "take_profit"
                        logger.info(f"🎯 Take profit: ${current_price:,.2f} >= ${take_profit_price:,.2f} (entry + ATR*1.5)")
                elif self.position.direction == Direction.SHORT:
                    take_profit_price = self.position.entry_price - tp_spacing
                    if current_price <= take_profit_price:
                        should_exit = True
                        exit_reason = "take_profit"
                        logger.info(f"🎯 Take profit: ${current_price:,.2f} <= ${take_profit_price:,.2f} (entry - ATR*1.5)")

        if should_exit:
            # Exit intent 생성
            intents = create_exit_intent(position=self.position, reason=exit_reason)

            # Phase 11b: Exit order 발주 (DoD: "Place exit order")
            if self.rest_client is not None:
                try:
                    # Exit order 발주 (Market order for immediate execution)
                    exit_side = "Sell" if self.position.direction == Direction.LONG else "Buy"
                    # Convert contracts to BTC quantity
                    contract_size = 0.001
                    qty_btc = self.position.qty * contract_size

                    exit_order = self.rest_client.place_order(
                        symbol="BTCUSDT",  # Linear USDT Futures
                        side=exit_side,
                        qty=str(qty_btc),  # BTC quantity
                        order_link_id=f"exit_{self.position.signal_id}_{int(time.time())}",
                        order_type="Market",  # Market order (즉시 체결)
                        time_in_force="GTC",
                        price=None,  # Market order: no price
                        category="linear",
                    )

                    # Bybit V5 API response structure: {"result": {"orderId": "...", "orderLinkId": "..."}}
                    ret_code = exit_order.get("retCode", -1)
                    result = exit_order.get("result", {})
                    order_id = result.get("orderId")
                    order_link_id = result.get("orderLinkId")

                    if ret_code != 0 or not order_id:
                        logger.error(f"❌ Exit order failed: retCode={ret_code}, response={exit_order}")
                        # 주문 실패 시 IN_POSITION 유지 (다음 tick에서 재시도)
                        return intents.exit_intent

                    logger.info(f"✅ Exit order placed: orderId={order_id}, side={exit_side}")

                    # State 전이: IN_POSITION → EXIT_PENDING
                    self.state = State.EXIT_PENDING
                    self.pending_order = {
                        "order_id": order_id,
                        "order_link_id": order_link_id,
                        "side": exit_side,
                        "qty": self.position.qty,
                        "price": current_price,  # Market price (참고용)
                        "signal_id": self.position.signal_id,
                    }
                    # Phase 12a-4c: Pending order 발주 시각 기록
                    self.pending_order_timestamp = time.time()
                except Exception as e:
                    # Exit order 실패 → IN_POSITION 유지 (다음 tick에서 재시도)
                    logger.error(f"❌ Exit order exception: {type(e).__name__}: {e}")
                    # HALT 대신 IN_POSITION 유지 → 다음 tick에서 재시도

            return intents.exit_intent

        # Codex Review Fix #1: Stop Manager 통합
        # FLOW Section 2.5: Stop 갱신 정책 (should_update_stop + determine_stop_action)
        current_time = self.market_data.get_timestamp()

        # Step 1: Stop 갱신 필요 여부 판단
        if should_update_stop(
            position_qty=self.position.qty,
            stop_qty=self.position.qty if self.position.stop_order_id else 0,
            last_stop_update_at=self.last_stop_update_at,
            current_time=current_time,
            entry_working=self.position.entry_working,
        ):
            # Step 2: Stop action 결정 (AMEND/CANCEL_AND_PLACE/PLACE)
            action = determine_stop_action(
                stop_status=self.position.stop_status,
                amend_fail_count=self.amend_fail_count,
            )

            # Step 3: Stop 갱신 실행 (rest_client 필요)
            if self.rest_client is not None:
                try:
                    # 새 stop price 계산 (ATR 기반 동적 SL, R:R >= 2:1)
                    atr_for_stop = self.market_data.get_atr()
                    SL_MULTIPLIER = 0.7
                    if atr_for_stop and atr_for_stop > 0:
                        stop_distance_usd = atr_for_stop * SL_MULTIPLIER
                        # Clamp: 최소 0.5%, 최대 2.0% of entry price
                        min_stop = self.position.entry_price * 0.005
                        max_stop = self.position.entry_price * 0.02
                        stop_distance_usd = max(min_stop, min(stop_distance_usd, max_stop))
                    else:
                        stop_distance_usd = self.position.entry_price * 0.01  # Fallback 1%
                    if self.position.direction == Direction.LONG:
                        new_stop_price = self.position.entry_price - stop_distance_usd
                    else:
                        new_stop_price = self.position.entry_price + stop_distance_usd

                    if action == "AMEND" and self.position.stop_order_id:
                        # Amend 시도
                        self.rest_client.amend_order(
                            symbol="BTCUSDT",
                            order_id=self.position.stop_order_id,
                            qty=self.position.qty,
                            trigger_price=new_stop_price,
                        )
                        # Amend 성공 → 상태 업데이트
                        self.position.stop_price = new_stop_price
                        self.position.stop_status = StopStatus.ACTIVE
                        self.amend_fail_count = 0
                        self.last_stop_update_at = current_time

                    elif action == "CANCEL_AND_PLACE" and self.position.stop_order_id:
                        # Cancel 후 Place
                        self.rest_client.cancel_order(
                            symbol="BTCUSDT",
                            order_id=self.position.stop_order_id,
                        )
                        # 새 Stop 주문 발주
                        stop_side = "Sell" if self.position.direction == Direction.LONG else "Buy"
                        stop_order = self.rest_client.place_order(
                            symbol="BTCUSDT",
                            side=stop_side,
                            qty=self.position.qty,
                            order_type="Market",
                            stop_loss=new_stop_price,
                            reduce_only=True,
                            position_idx=0,
                        )
                        # 상태 업데이트
                        self.position.stop_order_id = stop_order["orderId"]
                        self.position.stop_price = new_stop_price
                        self.position.stop_status = StopStatus.ACTIVE
                        self.amend_fail_count = 0
                        self.last_stop_update_at = current_time

                    elif action == "PLACE":
                        # Stop 없음 → 새로 설치 (복구)
                        stop_side = "Sell" if self.position.direction == Direction.LONG else "Buy"
                        stop_order = self.rest_client.place_order(
                            symbol="BTCUSDT",
                            side=stop_side,
                            qty=self.position.qty,
                            order_type="Market",
                            stop_loss=new_stop_price,
                            reduce_only=True,
                            position_idx=0,
                        )
                        # 상태 업데이트
                        self.position.stop_order_id = stop_order["orderId"]
                        self.position.stop_price = new_stop_price
                        self.position.stop_status = StopStatus.ACTIVE
                        self.position.stop_recovery_fail_count = 0
                        self.last_stop_update_at = current_time

                except Exception as e:
                    # Stop 갱신 실패 → amend_fail_count 증가
                    self.amend_fail_count += 1
                    self.position.stop_recovery_fail_count += 1

                    # 3회 실패 → ERROR 상태
                    if self.position.stop_recovery_fail_count >= 3:
                        self.position.stop_status = StopStatus.ERROR
                        # ERROR 상태는 run_tick에서 HALT로 전환됨

        return None

    def _decide_entry(self) -> dict:
        """
        Entry 결정 (signal → gate → sizing → order placement)

        Returns:
            {"blocked": bool, "reason": str}

        FLOW Section 2.4:
            - Step 1: FLAT 상태 확인
            - Step 2: degraded_mode 체크
            - Step 3: Signal generation (Grid-based)
            - Step 4: Entry gates 검증 (8 gates)
            - Step 5: Position sizing (loss budget + margin)
            - Step 6: Order placement (REST API)
            - Step 7: FLAT → ENTRY_PENDING 전환

        Phase 11b: Full Entry Flow 구현
        """

        # Step 1: FLAT 상태 확인
        if self.state != State.FLAT:
            return {"blocked": True, "reason": "state_not_flat"}

        # Step 2: degraded_mode 체크
        ws_degraded = self.market_data.is_ws_degraded()
        if ws_degraded:
            return {"blocked": True, "reason": "degraded_mode"}

        degraded_timeout = self.market_data.is_degraded_timeout()
        if degraded_timeout:
            self.state = State.HALT
            return {"blocked": True, "reason": "degraded_mode_timeout"}

        # Step 3: Signal generation
        # ATR 가져오기 (Grid spacing 계산용)
        atr = self.market_data.get_atr()
        if atr is None:
            return {"blocked": True, "reason": "atr_unavailable"}

        # Grid spacing 계산 (ATR * 0.3 → 재진입 빈도 증가, 더 좁은 그리드)
        self.grid_spacing = calculate_grid_spacing(atr=atr, multiplier=0.3)

        # 현재 가격
        current_price = self.market_data.get_current_price()

        # 마지막 체결 가격 (Grid 기준점)
        last_fill_price = self.market_data.get_last_fill_price()

        # Funding rate + MA slope (첫 진입 방향 결정용, Phase 13c)
        funding_rate = self.market_data.get_funding_rate()
        ma_slope_pct = self.market_data.get_ma_slope_pct()

        # Signal 생성 (Grid up/down, Regime-aware initial direction)
        signal: Optional[Signal] = generate_signal(
            current_price=current_price,
            last_fill_price=last_fill_price,
            grid_spacing=self.grid_spacing,
            qty=0,  # Sizing에서 계산
            funding_rate=funding_rate,
            ma_slope_pct=ma_slope_pct,
        )

        # Signal이 없으면 차단 (Grid spacing 범위 밖)
        if signal is None:
            return {"blocked": True, "reason": "no_signal"}

        # Step 4: Entry gates 검증
        stage = get_stage_params()
        trades_today = self.market_data.get_trades_today()
        atr_pct_24h = self.market_data.get_atr_pct_24h()

        # Sizing 먼저 계산 (EV gate용 qty 필요)
        sizing_params = build_sizing_params(signal=signal, market_data=self.market_data, atr=atr)
        sizing_result: SizingResult = calculate_contracts(params=sizing_params)

        logger.info(f"📐 Sizing: equity=${sizing_params.equity_usdt:.2f}, price=${sizing_params.entry_price_usd:,.2f}, "
                     f"max_loss=${sizing_params.max_loss_usdt:.2f}, lev={sizing_params.leverage}x → "
                     f"contracts={sizing_result.contracts} (reject={sizing_result.reject_reason})")

        if sizing_result.contracts == 0:
            return {"blocked": True, "reason": sizing_result.reject_reason}

        # Signal에 qty 업데이트
        signal.qty = sizing_result.contracts

        # Signal context 생성 (EV gate용)
        signal_context = build_signal_context(signal=signal, grid_spacing=self.grid_spacing)

        winrate = self.market_data.get_winrate()
        position_mode = self.market_data.get_position_mode()
        cooldown_until = None  # COOLDOWN 구현 시 추가
        current_time = self.market_data.get_timestamp()

        # Entry gates 검증
        entry_decision: EntryDecision = check_entry_allowed(
            state=self.state,
            stage=stage,
            trades_today=trades_today,
            atr_pct_24h=atr_pct_24h,
            signal=signal_context,
            winrate=winrate,
            position_mode=position_mode,
            cooldown_until=cooldown_until,
            current_time=current_time,
        )

        # Gate 거절 시 차단
        if not entry_decision.allowed:
            return {"blocked": True, "reason": entry_decision.reject_reason}

        # Step 5: Position sizing (이미 Step 4에서 계산 완료)
        contracts = sizing_result.contracts

        # Step 6: Order placement
        if self.rest_client is None:
            # REST client 없으면 차단 (Unit test에서는 None)
            return {"blocked": True, "reason": "rest_client_unavailable"}

        try:
            # Signal ID 생성
            self.current_signal_id = generate_signal_id()

            # Bybit Linear USDT API: qty는 BTC quantity (계산: contracts * contract_size)
            # 예: contracts=831, contract_size=0.001 → qty_btc=0.831 BTC
            contract_size = 0.001  # Bybit Linear BTCUSDT: 0.001 BTC per contract
            qty_btc = contracts * contract_size

            logger.info(f"📤 Entry order: {signal.side} {contracts} contracts ({qty_btc} BTC) @ ${signal.price:,.2f}")

            # Limit GTC 주문 (현재가 → 즉시 체결 가능, Grid 가격 → 대기 주문)
            # Note: PostOnly는 현재가에서 taker로 취소되므로 GTC 사용
            order_result = self.rest_client.place_order(
                symbol="BTCUSDT",
                side=signal.side,
                order_type="Limit",
                qty=str(qty_btc),
                price=str(signal.price),
                time_in_force="GTC",
                order_link_id=f"entry_{self.current_signal_id}",
                category="linear",
            )

            # Bybit V5 API response structure: {"result": {"orderId": "...", "orderLinkId": "..."}}
            ret_code = order_result.get("retCode", -1)
            result = order_result.get("result", {})
            order_id = result.get("orderId")
            order_link_id = result.get("orderLinkId")

            # Phase 12b Fix: Validate retCode and order_id
            if ret_code != 0 or not order_id:
                raise ValueError(f"Entry order failed: retCode={ret_code}, response={order_result}")

        except Exception as e:
            # Order placement 실패 → 차단
            return {"blocked": True, "reason": f"order_placement_failed: {str(e)}"}

        # Step 7: FLAT → ENTRY_PENDING 전환
        self.state = State.ENTRY_PENDING

        # Pending order 저장 (FILL event 매칭용)
        self.pending_order = {
            "order_id": order_id,
            "order_link_id": order_link_id,
            "side": signal.side,
            "qty": contracts,
            "price": signal.price,
            "signal_id": self.current_signal_id,
        }

        # Phase 12a-4c: Pending order 발주 시각 기록
        self.pending_order_timestamp = time.time()

        return {"blocked": False, "reason": None}

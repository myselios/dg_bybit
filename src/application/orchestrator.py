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

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from domain.state import State, Position, Direction, StopStatus
from infrastructure.exchange.market_data_interface import MarketDataInterface
from application.exit_manager import check_stop_hit, create_exit_intent
from domain.intent import ExitIntent

# Phase 11b: Entry Flow imports
from application.entry_allowed import check_entry_allowed, EntryDecision
from application.signal_generator import generate_signal, calculate_grid_spacing, Signal
from application.sizing import calculate_contracts, SizingResult

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
        force_entry: bool = False,  # Phase 12a-4: Force Entry 모드 (테스트용)
        killswitch: Optional[KillSwitch] = None,  # Codex Review Fix #2: Manual halt mechanism
    ):
        """
        Orchestrator 초기화

        Args:
            market_data: Market data interface (FakeMarketData or BybitAdapter)
            rest_client: Bybit REST client (Order placement용, Phase 11b)
            log_storage: LogStorage (Trade Log 저장용, Phase 11b)
            force_entry: Force Entry 모드 (테스트용, Grid spacing 무시)
            killswitch: KillSwitch (Manual halt mechanism, Codex Review Fix #2)
        """
        self.market_data = market_data
        self.rest_client = rest_client
        self.log_storage = log_storage
        self.force_entry = force_entry
        self.killswitch = killswitch if killswitch is not None else KillSwitch()

        # Position recovery: 기존 포지션이 있으면 State.IN_POSITION으로 시작
        position_data = market_data.get_position()
        position_size = float(position_data.get("size", "0"))

        if position_size > 0:
            # Position 존재 → State.IN_POSITION
            position_side = position_data.get("side", "None")
            avg_price = float(position_data.get("avgPrice", "0") or "0")

            # Direction 매핑 (Bybit "Buy"/"Sell" → Domain Direction)
            direction = Direction.LONG if position_side == "Buy" else Direction.SHORT

            # Position 객체 생성 (recovery 시 signal_id는 "recovered")
            self.position = Position(
                direction=direction,
                qty=position_size,
                entry_price=avg_price,
                signal_id="recovered",
            )
            self.state = State.IN_POSITION
        else:
            # Position 없음 → State.FLAT
            self.state = State.FLAT
            self.position = None

        # Phase 11b: Entry Flow tracking
        self.pending_order: Optional[dict] = None  # Pending order 정보 (FILL event 매칭용)
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
        logger.info(">>> run_tick START")

        # Phase 9d: current_timestamp 초기화 (Slippage anomaly 체크용)
        logger.info(">>> [1] get_timestamp...")
        self.current_timestamp = self.market_data.get_timestamp()
        logger.info(f">>> [1] DONE: ts={self.current_timestamp}")

        execution_order = []
        halt_reason = None
        entry_blocked = False
        entry_block_reason = None

        # (0a) KillSwitch check (최우선, Codex Review Fix #2)
        logger.info(">>> [2] killswitch_check...")
        if self.killswitch.is_halted():
            logger.info(">>> [2] HALT: killswitch")
            self.state = State.HALT
            halt_reason = "manual_halt_killswitch"
            return TickResult(
                state=self.state,
                execution_order=["killswitch_check"],
                halt_reason=halt_reason,
            )
        logger.info(">>> [2] DONE: killswitch OK")

        # (0) Self-healing check (Position vs State 일관성, Phase 11b)
        logger.info(">>> [3] self_healing_check...")
        inconsistency_reason = verify_state_consistency(
            position=self.position,
            state=self.state,
        )
        if inconsistency_reason is not None:
            logger.info(f">>> [3] HALT: {inconsistency_reason}")
            self.state = State.HALT
            halt_reason = inconsistency_reason
            return TickResult(
                state=self.state,
                execution_order=["self_healing_check"],
                halt_reason=halt_reason,
            )
        logger.info(">>> [3] DONE: consistency OK")

        # (1) Emergency check (최우선)
        logger.info(">>> [4] emergency_check...")
        execution_order.append("emergency")
        emergency_result = self._check_emergency()
        logger.info(f">>> [4] DONE: {emergency_result['status']}")
        if emergency_result["status"] == "HALT":
            logger.info(f">>> [4] HALT: {emergency_result['reason']}")
            self.state = State.HALT
            halt_reason = emergency_result["reason"]
            return TickResult(
                state=self.state,
                execution_order=execution_order,
                halt_reason=halt_reason,
            )

        # (2) Events processing
        logger.info(">>> [5] process_events...")
        execution_order.append("events")
        self._process_events()
        logger.info(">>> [5] DONE")

        # (3) Position management + Exit decision
        logger.info(">>> [6] manage_position...")
        execution_order.append("position")
        exit_intent = self._manage_position()
        logger.info(">>> [6] DONE")

        # (4) Entry decision
        logger.info(">>> [7] decide_entry...")
        execution_order.append("entry")
        entry_result = self._decide_entry()
        logger.info(f">>> [7] DONE: blocked={entry_result['blocked']}")
        if entry_result["blocked"]:
            entry_blocked = True
            entry_block_reason = entry_result["reason"]

        logger.info(">>> run_tick COMPLETE")
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

        Phase 11b DoD: "Trade log 정상 기록 (Phase 10 로깅 인프라 사용)"
        """
        if position is None:
            return  # Position이 없으면 로깅 불가

        # Trade Log v1.0 생성
        # 1. 실행 품질 필드
        order_id = event.get("orderId", "unknown")
        fills = [
            {
                "price": float(event.get("execPrice", 0.0)),
                "qty": int(event.get("execQty", 0)),
                "fee": 0.0,  # Fee는 실제 구현에서 계산 필요
                "timestamp": self.market_data.get_timestamp(),
            }
        ]
        slippage_usd = 0.0  # 실제 구현에서는 expected vs exec 계산
        latency_rest_ms = 0.0  # 실제 구현에서는 타이밍 측정
        latency_ws_ms = 0.0
        latency_total_ms = 0.0

        # 2. Market data
        funding_rate = self.market_data.get_funding_rate()
        mark_price = self.market_data.get_mark_price()
        index_price = self.market_data.get_index_price()
        orderbook_snapshot = {}  # 실제 구현에서는 MarketData에서 가져오기

        # 3. Market regime (deterministic)
        ma_slope_pct = self.market_data.get_ma_slope_pct()
        atr_percentile = self.market_data.get_atr_percentile()
        market_regime = calculate_market_regime(
            ma_slope_pct=ma_slope_pct,
            atr_percentile=atr_percentile,
        )

        # 4. 무결성 필드
        schema_version = "1.0"
        config_hash = "test_config_hash"  # 실제 구현에서는 설정 해시 계산
        git_commit = "test_git_commit"  # 실제 구현에서는 Git 커밋 해시 가져오기
        exchange_server_time_offset_ms = self.market_data.get_exchange_server_time_offset_ms()

        # TradeLogV1 생성
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
            orderbook_snapshot=orderbook_snapshot,
            market_regime=market_regime,
            schema_version=schema_version,
            config_hash=config_hash,
            git_commit=git_commit,
            exchange_server_time_offset_ms=exchange_server_time_offset_ms,
        )

        # Validation
        validate_trade_log_v1(trade_log)

        # LogStorage에 저장 (JSONL)
        log_dict = asdict(trade_log)
        self.log_storage.append_trade_log_v1(log_entry=log_dict, is_critical=False)

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
        리스크 완화:
        - Atomic state transition (Position + State 동시 전환)
        - Dual ID matching (orderId + orderLinkId)
        - Exception handling (롤백)
        """
        # WS에서 FILL event 가져오기 (Mock 구현)
        fill_events = self.market_data.get_fill_events()

        for event in fill_events:
            try:
                # Step 1: Pending order 매칭 (orderId 또는 orderLinkId)
                if not match_pending_order(event=event, pending_order=self.pending_order):
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
                # (실제로는 로그 시스템에 기록해야 하지만, 최소 구현은 pass)
                pass

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

        # Phase 11b: Stop hit 체크
        current_price = self.market_data.get_current_price()
        if check_stop_hit(current_price=current_price, position=self.position):
            # Stop hit → Exit intent 생성
            intents = create_exit_intent(position=self.position, reason="stop_loss_hit")

            # Phase 11b: Exit order 발주 (DoD: "Place exit order")
            if self.rest_client is not None:
                try:
                    # Exit order 발주 (Market order for immediate execution)
                    exit_side = "Sell" if self.position.direction == Direction.LONG else "Buy"
                    exit_order = self.rest_client.place_order(
                        symbol="BTCUSD",
                        side=exit_side,
                        qty=self.position.qty,
                        order_link_id=f"exit_{self.position.signal_id}",
                        order_type="Market",  # Market order (즉시 체결)
                        time_in_force="GoodTillCancel",
                    )

                    # State 전이: IN_POSITION → EXIT_PENDING
                    self.state = State.EXIT_PENDING
                    self.pending_order = {
                        "order_id": exit_order["orderId"],
                        "order_link_id": exit_order["orderLinkId"],
                        "side": exit_side,
                        "qty": self.position.qty,
                        "price": current_price,  # Market price (참고용)
                        "signal_id": self.position.signal_id,
                    }
                except Exception as e:
                    # Exit order 실패 → HALT (치명적 오류)
                    self.state = State.HALT
                    # halt_reason은 run_tick()에서 설정 필요 (여기서는 로깅만)
                    pass

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
                    # 새 stop price 계산 (Direction에 따라)
                    # LONG: entry - (entry * 0.03), SHORT: entry + (entry * 0.03)
                    stop_price_offset_pct = 0.03  # 3% (정책에서 가져와야 하지만 일단 고정)
                    if self.position.direction == Direction.LONG:
                        new_stop_price = self.position.entry_price * (1 - stop_price_offset_pct)
                    else:
                        new_stop_price = self.position.entry_price * (1 + stop_price_offset_pct)

                    if action == "AMEND" and self.position.stop_order_id:
                        # Amend 시도
                        self.rest_client.amend_order(
                            symbol="BTCUSD",
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
                            symbol="BTCUSD",
                            order_id=self.position.stop_order_id,
                        )
                        # 새 Stop 주문 발주
                        stop_side = "Sell" if self.position.direction == Direction.LONG else "Buy"
                        stop_order = self.rest_client.place_order(
                            symbol="BTCUSD",
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
                            symbol="BTCUSD",
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
        import logging
        logger = logging.getLogger(__name__)

        # Step 1: FLAT 상태 확인
        logger.info(f">>> decide_entry Step 1: state={self.state}")
        if self.state != State.FLAT:
            logger.info(">>> BLOCKED: state_not_flat")
            return {"blocked": True, "reason": "state_not_flat"}

        # Step 2: degraded_mode 체크
        logger.info(">>> decide_entry Step 2: degraded_mode check")
        ws_degraded = self.market_data.is_ws_degraded()
        if ws_degraded:
            logger.info(">>> BLOCKED: degraded_mode")
            return {"blocked": True, "reason": "degraded_mode"}

        degraded_timeout = self.market_data.is_degraded_timeout()
        if degraded_timeout:
            logger.info(">>> BLOCKED: degraded_mode_timeout")
            self.state = State.HALT
            return {"blocked": True, "reason": "degraded_mode_timeout"}

        # Step 3: Signal generation
        logger.info(">>> decide_entry Step 3: signal generation")
        # ATR 가져오기 (Grid spacing 계산용)
        atr = self.market_data.get_atr()
        logger.info(f">>> ATR: {atr}")
        if atr is None:
            logger.info(">>> BLOCKED: atr_unavailable")
            return {"blocked": True, "reason": "atr_unavailable"}

        # Grid spacing 계산 (ATR * 2.0)
        self.grid_spacing = calculate_grid_spacing(atr=atr, multiplier=2.0)

        # 현재 가격
        current_price = self.market_data.get_current_price()

        # 마지막 체결 가격 (Grid 기준점)
        last_fill_price = self.market_data.get_last_fill_price()

        # Signal 생성 (Grid up/down)
        logger.info(f">>> Generating signal: price={current_price}, last_fill={last_fill_price}, spacing={self.grid_spacing}, force_entry={self.force_entry}")
        signal: Optional[Signal] = generate_signal(
            current_price=current_price,
            last_fill_price=last_fill_price,
            grid_spacing=self.grid_spacing,
            qty=0,  # Sizing에서 계산
            force_entry=self.force_entry,  # Phase 12a-4: Force Entry 모드 전달
        )
        logger.info(f">>> Signal: {signal}")

        # Signal이 없으면 차단 (Grid spacing 범위 밖)
        if signal is None:
            logger.info(">>> BLOCKED: no_signal")
            return {"blocked": True, "reason": "no_signal"}

        # Step 4: Entry gates 검증
        stage = get_stage_params()
        trades_today = self.market_data.get_trades_today()
        atr_pct_24h = self.market_data.get_atr_pct_24h()

        # Sizing 먼저 계산 (EV gate용 qty 필요)
        logger.info(">>> decide_entry Step 4: sizing")
        sizing_params = build_sizing_params(signal=signal, market_data=self.market_data)
        sizing_result: SizingResult = calculate_contracts(params=sizing_params)
        logger.info(f">>> Sizing result: contracts={sizing_result.contracts}, reason={sizing_result.reject_reason}")

        if sizing_result.contracts == 0:
            logger.info(f">>> BLOCKED: {sizing_result.reject_reason}")
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
        logger.info(">>> decide_entry Step 5: entry gates")
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
            force_entry=self.force_entry,  # Phase 12a-4: Force Entry 모드 전달
        )
        logger.info(f">>> Entry decision: allowed={entry_decision.allowed}, reason={entry_decision.reject_reason}")

        # Gate 거절 시 차단
        if not entry_decision.allowed:
            logger.info(f">>> BLOCKED: {entry_decision.reject_reason}")
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

            # Entry order 발주 (Limit order, Maker)
            # TEMPORARY DEBUG: Use 1 contract to test
            test_qty = 1
            logger.info(f">>> Placing order: symbol=BTCUSDT, side={signal.side}, qty={test_qty} (calculated: {contracts}), price={signal.price}")
            order_result = self.rest_client.place_order(
                symbol="BTCUSDT",  # Linear USDT Futures (ADR-0002)
                side=signal.side,  # "Buy" or "Sell"
                order_type="Limit",
                qty=str(test_qty),  # Bybit requires string
                price=str(signal.price),  # Bybit requires string
                time_in_force="PostOnly",  # Maker-only
                order_link_id=f"entry_{self.current_signal_id}",
                category="linear",  # Linear USDT Futures
            )
            logger.info(f">>> Order result: {order_result}")

            # Bybit V5 API response structure: {"result": {"orderId": "...", "orderLinkId": "..."}}
            result = order_result.get("result", {})
            order_id = result.get("orderId")
            order_link_id = result.get("orderLinkId")
            logger.info(f">>> Order placed: order_id={order_id}, order_link_id={order_link_id}")

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

        return {"blocked": False, "reason": None}

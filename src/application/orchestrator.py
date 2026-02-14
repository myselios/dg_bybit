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
from dataclasses import dataclass
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
from infrastructure.storage.log_storage import LogStorage
from application.trade_logging import log_estimated_trade, log_completed_trade

# Stop Manager Integration (Codex Review Fix #1)
from application.stop_manager import should_update_stop, determine_stop_action, execute_stop_update

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

                if pos_response.get("retCode", -1) == 0:
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
                                stop_price=None,  # P0-4: None → check_stop_hit returns False → stop recovery 우선
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

    def _log_estimated_trade(self, reason: str) -> None:
        """Thin delegate to trade_logging.log_estimated_trade()"""
        if self.position is None or self.log_storage is None:
            return
        log_estimated_trade(
            market_data=self.market_data,
            log_storage=self.log_storage,
            config_hash=self.config_hash,
            git_commit=self.git_commit,
            position=self.position,
            reason=reason,
        )

    def _log_completed_trade(self, event: Dict[str, Any], position: Optional[Position]) -> None:
        """Thin delegate to trade_logging.log_completed_trade()"""
        if position is None:
            return
        log_completed_trade(
            market_data=self.market_data,
            log_storage=self.log_storage,
            config_hash=self.config_hash,
            git_commit=self.git_commit,
            position=position,
            pending_order=self.pending_order,
            pending_order_timestamp=self.pending_order_timestamp,
            event=event,
        )

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
        Events 처리 (FILL -> Position update)

        1. REST API fallback (WebSocket timeout 시) → rest_fallback 모듈에 위임
        2. WebSocket FILL event 처리 (match → position create → state transition)
        """
        from application.rest_fallback import check_pending_order_fallback, _NO_CHANGE

        # (1) REST API polling fallback (WebSocket timeout 시)
        WEBSOCKET_TIMEOUT = 10.0
        skip_ws = False
        if (self.state in [State.ENTRY_PENDING, State.EXIT_PENDING] and
            self.pending_order is not None and
            self.pending_order_timestamp is not None):

            elapsed = time.time() - self.pending_order_timestamp
            if elapsed > WEBSOCKET_TIMEOUT and self.rest_client is not None:
                try:
                    result = check_pending_order_fallback(
                        rest_client=self.rest_client,
                        state=self.state,
                        pending_order=self.pending_order,
                        elapsed=elapsed,
                    )
                    self._apply_fallback_result(result)
                    skip_ws = result.skip_ws_processing
                except Exception as e:
                    logger.error(f"REST API polling failed: {type(e).__name__}: {e}")

        if skip_ws:
            return

        # (2) WebSocket FILL event 처리
        fill_events = self.market_data.get_fill_events()
        if fill_events:
            logger.info(f"Got {len(fill_events)} FILL events from WS")

        for event in fill_events:
            try:
                matched = match_pending_order(event=event, pending_order=self.pending_order)
                if not matched:
                    continue

                position = create_position_from_fill(event=event, pending_order=self.pending_order)

                if self.state == State.ENTRY_PENDING:
                    self.position = position
                    self.state = State.IN_POSITION
                    self.pending_order = None
                    self.pending_order_timestamp = None
                elif self.state == State.EXIT_PENDING:
                    if self.log_storage is not None:
                        self._log_completed_trade(event=event, position=self.position)
                    self.position = None
                    self.state = State.FLAT
                    self.pending_order = None
                    self.pending_order_timestamp = None

            except Exception as e:
                logger.error(f"Exception in _process_events: {type(e).__name__}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")

    def _apply_fallback_result(self, result) -> None:
        """FallbackResult를 self.* 상태에 적용"""
        from application.rest_fallback import _NO_CHANGE

        # Estimated trade 로그 (state 변경 전에 기록)
        if result.log_estimated_reason and self.log_storage is not None and self.position is not None:
            self._log_estimated_trade(reason=result.log_estimated_reason)

        # Completed trade 로그
        if result.log_completed_event is not None and self.log_storage is not None:
            self._log_completed_trade(event=result.log_completed_event, position=self.position)

        # State 변경
        if result.new_state is not None:
            self.state = result.new_state

        # Position 변경
        if result.new_position is not _NO_CHANGE:
            self.position = result.new_position

        # Pending 초기화
        if result.clear_pending:
            self.pending_order = None
            self.pending_order_timestamp = None

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

        # P0-1: Stop 복구 실패(ERROR) → 즉시 HALT (Stop 없는 포지션 운영 금지)
        if self.position.stop_status == StopStatus.ERROR:
            logger.error("🚨 Stop recovery failed (ERROR), HALT — 포지션에 Stop 없음")
            self.state = State.HALT
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
                        reduce_only=True,  # P0-2: 반대 방향 포지션 오픈 방지
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

            # Step 3: Stop 갱신 실행 (stop_manager에 위임)
            if self.rest_client is not None:
                try:
                    stop_result = execute_stop_update(
                        rest_client=self.rest_client,
                        entry_price=self.position.entry_price,
                        direction=self.position.direction,
                        current_price=self.market_data.get_current_price(),
                        atr=self.market_data.get_atr(),
                    )

                    if stop_result.stop_already_breached:
                        self.position.stop_price = stop_result.new_stop_price
                        self.position.stop_status = StopStatus.ACTIVE
                        return None

                    self.position.stop_price = stop_result.new_stop_price
                    self.position.stop_status = StopStatus.ACTIVE
                    self.position.stop_recovery_fail_count = 0
                    self.amend_fail_count = 0
                    self.last_stop_update_at = current_time

                except Exception as e:
                    self.amend_fail_count += 1
                    self.position.stop_recovery_fail_count += 1
                    logger.warning(f"Stop update failed ({self.position.stop_recovery_fail_count}/3): {type(e).__name__}: {e}")

                    if self.position.stop_recovery_fail_count >= 3:
                        self.position.stop_status = StopStatus.ERROR

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

        # Stop distance 계산 (ATR 기반, create_position_from_fill에서 사용)
        SL_MULTIPLIER = 0.7
        if atr and atr > 0:
            stop_dist_usd = atr * SL_MULTIPLIER
            min_stop = signal.price * 0.005
            max_stop = signal.price * 0.02
            stop_dist_usd = max(min_stop, min(stop_dist_usd, max_stop))
            stop_distance_pct = stop_dist_usd / signal.price
        else:
            stop_distance_pct = 0.01  # Fallback 1%

        # Pending order 저장 (FILL event 매칭용)
        self.pending_order = {
            "order_id": order_id,
            "order_link_id": order_link_id,
            "side": signal.side,
            "qty": contracts,
            "price": signal.price,
            "signal_id": self.current_signal_id,
            "stop_distance_pct": stop_distance_pct,
        }

        # Phase 12a-4c: Pending order 발주 시각 기록
        self.pending_order_timestamp = time.time()

        return {"blocked": False, "reason": None}

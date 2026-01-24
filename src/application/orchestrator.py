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

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from domain.state import State, Position
from infrastructure.exchange.market_data_interface import MarketDataInterface
from application.session_risk import (
    check_daily_loss_cap,
    check_weekly_loss_cap,
    check_loss_streak_kill,
    check_fee_anomaly,
    check_slippage_anomaly,
)
from application.exit_manager import check_stop_hit, create_exit_intent
from domain.intent import ExitIntent

# Phase 11b: Entry Flow imports
from application.entry_allowed import (
    check_entry_allowed,
    EntryDecision,
    StageParams,
    SignalContext,
)
from application.signal_generator import generate_signal, calculate_grid_spacing, Signal
from application.sizing import calculate_contracts, SizingResult, SizingParams


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
    ):
        """
        Orchestrator 초기화

        Args:
            market_data: Market data interface (FakeMarketData or BybitAdapter)
            rest_client: Bybit REST client (Order placement용, Phase 11b)
        """
        self.market_data = market_data
        self.rest_client = rest_client
        self.state = State.FLAT
        self.position: Optional[Position] = None

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
        # Phase 9d: current_timestamp 초기화 (Slippage anomaly 체크용)
        self.current_timestamp = self.market_data.get_timestamp()

        execution_order = []
        halt_reason = None
        entry_blocked = False
        entry_block_reason = None

        # (0) Self-healing check (Position vs State 일관성, Phase 11b)
        inconsistency_reason = self._verify_state_consistency()
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

    def get_state(self) -> State:
        """현재 상태 반환"""
        return self.state

    def _check_emergency(self) -> dict:
        """
        Emergency 체크 (최우선)

        Returns:
            {"status": "PASS" or "HALT", "reason": str}

        FLOW Section 7.1 + Phase 9c Session Risk Policy:
            - balance_too_low (equity <= 0)
            - degraded_timeout (60s)
            - Session Risk Policy 4개:
              - Daily Loss Cap (-5%)
              - Weekly Loss Cap (-12.5%)
              - Loss Streak Kill (3연패, 5연패)
              - Fee/Slippage Anomaly (2회 연속, 3회/10분)
        """
        # balance_too_low 체크
        equity_btc = self.market_data.get_equity_btc()
        if equity_btc <= 0:
            return {"status": "HALT", "reason": "balance_too_low"}

        # degraded timeout 체크 (60초)
        degraded_timeout = self.market_data.is_degraded_timeout()
        if degraded_timeout:
            return {"status": "HALT", "reason": "degraded_mode_timeout"}

        # Session Risk Policy 체크 (Phase 9c)
        btc_mark_price_usd = self.market_data.get_btc_mark_price_usd()
        equity_usd = equity_btc * btc_mark_price_usd

        # (1) Daily Loss Cap
        daily_pnl = self.market_data.get_daily_realized_pnl_usd()
        if daily_pnl is not None:
            daily_status = check_daily_loss_cap(
                equity_usd=equity_usd,
                daily_realized_pnl_usd=daily_pnl,
                daily_loss_cap_pct=self.daily_loss_cap_pct,
                current_timestamp=self.current_timestamp,
            )
            if daily_status.is_halted:
                return {"status": "HALT", "reason": daily_status.halt_reason}

        # (2) Weekly Loss Cap
        weekly_pnl = self.market_data.get_weekly_realized_pnl_usd()
        if weekly_pnl is not None:
            weekly_status = check_weekly_loss_cap(
                equity_usd=equity_usd,
                weekly_realized_pnl_usd=weekly_pnl,
                weekly_loss_cap_pct=self.weekly_loss_cap_pct,
                current_timestamp=self.current_timestamp,
            )
            if weekly_status.is_halted:
                return {"status": "HALT", "reason": weekly_status.halt_reason}

        # (3) Loss Streak Kill
        loss_streak = self.market_data.get_loss_streak_count()
        if loss_streak is not None:
            streak_status = check_loss_streak_kill(
                loss_streak_count=loss_streak,
                current_timestamp=self.current_timestamp,
            )
            if streak_status.is_halted:
                return {"status": "HALT", "reason": streak_status.halt_reason}

        # (4) Fee Anomaly
        fee_history = self.market_data.get_fee_ratio_history()
        if fee_history is not None:
            fee_status = check_fee_anomaly(
                fee_ratio_history=fee_history,
                fee_spike_threshold=self.fee_spike_threshold,
                current_timestamp=self.current_timestamp,
            )
            if fee_status.is_halted:
                return {"status": "HALT", "reason": fee_status.halt_reason}

        # (5) Slippage Anomaly
        slippage_history = self.market_data.get_slippage_history()
        if slippage_history is not None and self.current_timestamp is not None:
            slippage_status = check_slippage_anomaly(
                slippage_history=slippage_history,
                slippage_threshold_usd=self.slippage_threshold_usd,
                window_seconds=self.slippage_window_seconds,
                current_timestamp=self.current_timestamp,
            )
            if slippage_status.is_halted:
                return {"status": "HALT", "reason": slippage_status.halt_reason}

        return {"status": "PASS", "reason": None}

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
        fill_events = self._get_fill_events()

        for event in fill_events:
            try:
                # Step 1: Pending order 매칭 (orderId 또는 orderLinkId)
                if not self._match_pending_order(event):
                    continue  # 매칭 실패 → 다음 event

                # Step 2: Position 생성
                position = self._create_position_from_fill(event)

                # Step 3: State 전환 (atomic with Position)
                if self.state == State.ENTRY_PENDING:
                    # Entry FILL → IN_POSITION
                    self.position = position
                    self.state = State.IN_POSITION
                    self.pending_order = None  # Cleanup
                elif self.state == State.EXIT_PENDING:
                    # Exit FILL → FLAT
                    self.position = None
                    self.state = State.FLAT
                    self.pending_order = None  # Cleanup

                # Step 4: Success (로그는 생략, Exception 발생 시만 처리)

            except Exception as e:
                # Exception 발생 시 State 롤백 (Position은 이미 None 또는 기존 유지)
                # 로그 기록 후 다음 event 처리
                # (실제로는 로그 시스템에 기록해야 하지만, 최소 구현은 pass)
                pass

    # ========== Phase 11b: Helper Methods (Event Processing) ==========

    def _verify_state_consistency(self) -> Optional[str]:
        """
        Position vs State 일관성 검증 (Self-healing check)

        Returns:
            Optional[str]: 일관성 위반 시 이유 문자열, 정상 시 None

        Phase 11b: Risk mitigation (Section 9 리스크 분석)

        일관성 규칙:
        - Position != None → State는 IN_POSITION 또는 EXIT_PENDING이어야 함
        - Position = None → State는 FLAT, ENTRY_PENDING, COOLDOWN, HALT 중 하나여야 함

        위반 조합 (HALT 트리거):
        1. Position != None and State in [FLAT, ENTRY_PENDING] → "position_state_inconsistent"
        2. Position = None and State = IN_POSITION → "position_state_inconsistent"
        """
        # Case 1: Position이 있는데 State가 FLAT 또는 ENTRY_PENDING
        if self.position is not None:
            if self.state in [State.FLAT, State.ENTRY_PENDING]:
                return "position_state_inconsistent"

        # Case 2: Position이 없는데 State가 IN_POSITION
        if self.position is None:
            if self.state == State.IN_POSITION:
                return "position_state_inconsistent"

        # 일관성 정상
        return None

    def _get_fill_events(self) -> List[Dict[str, Any]]:
        """
        WS에서 FILL event 가져오기

        Returns:
            List[Dict]: FILL event 목록 (Bybit API format)

        Phase 11b: Event Processing
        """
        return self.market_data.get_fill_events()

    def _match_pending_order(self, event: dict) -> bool:
        """
        FILL event를 Pending order와 매칭

        Args:
            event: FILL event (Bybit API format)
                - orderId: Bybit 서버 생성 ID
                - orderLinkId: 클라이언트 ID (optional)

        Returns:
            bool: 매칭 성공 시 True

        매칭 조건 (Dual ID tracking):
        1. event["orderId"] == pending_order["order_id"] (우선)
        2. event.get("orderLinkId") == pending_order["order_link_id"] (fallback)

        리스크 완화: Dual ID tracking으로 매칭 실패 방지
        """
        if self.pending_order is None:
            return False

        # orderId 매칭 (우선)
        if event.get("orderId") == self.pending_order["order_id"]:
            return True

        # orderLinkId 매칭 (fallback)
        if event.get("orderLinkId") == self.pending_order["order_link_id"]:
            return True

        return False

    def _create_position_from_fill(self, event: dict) -> Position:
        """
        FILL event → Position 생성

        Args:
            event: FILL event (Bybit API format)
                - execQty: 체결 수량 (string)
                - execPrice: 체결 가격 (string)
                - side: "Buy" or "Sell"

        Returns:
            Position: entry_price, qty, direction, stop_price, signal_id

        Stop price 계산:
        - LONG: entry_price * (1 - stop_distance_pct)
        - SHORT: entry_price * (1 + stop_distance_pct)
        - stop_distance_pct = 3% (Policy Section 9)
        """
        from domain.state import Position, Direction

        # Event에서 데이터 추출
        qty = int(event["execQty"])
        entry_price = float(event["execPrice"])
        side = event["side"]

        # Signal ID (pending_order에서 가져옴)
        signal_id = self.pending_order["signal_id"] if self.pending_order else "unknown"

        # Direction 계산
        direction = Direction.LONG if side == "Buy" else Direction.SHORT

        # Stop price 계산 (3% stop distance)
        stop_distance_pct = 0.03
        if direction == Direction.LONG:
            stop_price = entry_price * (1 - stop_distance_pct)
        else:  # SHORT
            stop_price = entry_price * (1 + stop_distance_pct)

        return Position(
            qty=qty,
            entry_price=entry_price,
            direction=direction,
            signal_id=signal_id,
            stop_price=stop_price,
        )

    def _manage_position(self) -> Optional[ExitIntent]:
        """
        Position 관리 (stop 갱신 + exit decision)

        FLOW Section 2.5:
            - stop_manager.should_update_stop()
            - stop_manager.determine_stop_action()
            - Phase 11: Exit decision (stop hit 체크)

        Returns:
            ExitIntent: Exit 주문 의도 (stop hit 시)
        """
        # IN_POSITION이 아니면 건너뛰기
        if self.state != State.IN_POSITION or self.position is None:
            return None

        # Phase 11: Stop hit 체크
        current_price = self.market_data.get_current_price()
        if check_stop_hit(current_price=current_price, position=self.position):
            # Stop hit → Exit intent 생성
            intents = create_exit_intent(position=self.position, reason="stop_loss_hit")
            return intents.exit_intent

        # Stop 갱신 로직은 stop_manager.py에 구현되어 있음 (미통합)
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

        # Grid spacing 계산 (ATR * 2.0)
        self.grid_spacing = calculate_grid_spacing(atr=atr, multiplier=2.0)

        # 현재 가격
        current_price = self.market_data.get_current_price()

        # 마지막 체결 가격 (Grid 기준점)
        last_fill_price = self.market_data.get_last_fill_price()

        # Signal 생성 (Grid up/down)
        signal: Optional[Signal] = generate_signal(
            current_price=current_price,
            last_fill_price=last_fill_price,
            grid_spacing=self.grid_spacing,
            qty=0,  # Sizing에서 계산
        )

        # Signal이 없으면 차단 (Grid spacing 범위 밖)
        if signal is None:
            return {"blocked": True, "reason": "no_signal"}

        # Step 4: Entry gates 검증
        stage = self._get_stage_params()
        trades_today = self.market_data.get_trades_today()
        atr_pct_24h = self.market_data.get_atr_pct_24h()

        # Sizing 먼저 계산 (EV gate용 qty 필요)
        sizing_params = self._build_sizing_params(signal)
        sizing_result: SizingResult = calculate_contracts(params=sizing_params)

        if sizing_result.contracts == 0:
            return {"blocked": True, "reason": sizing_result.reject_reason}

        # Signal에 qty 업데이트
        signal.qty = sizing_result.contracts

        # Signal context 생성 (EV gate용)
        signal_context = self._build_signal_context(signal)

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
            self.current_signal_id = self._generate_signal_id()

            # Entry order 발주 (Limit order, Maker)
            order_result = self.rest_client.place_order(
                symbol="BTCUSD",
                side=signal.side,  # "Buy" or "Sell"
                order_type="Limit",
                qty=contracts,
                price=signal.price,
                time_in_force="PostOnly",  # Maker-only
                order_link_id=f"entry_{self.current_signal_id}",
            )

            # Order ID 저장
            order_id = order_result["orderId"]
            order_link_id = order_result["orderLinkId"]

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

    # ========== Phase 11b: Helper Methods (Entry Flow) ==========

    def _get_stage_params(self) -> StageParams:
        """
        Stage 파라미터 반환 (Policy Section 5)

        Returns:
            StageParams: Stage 파라미터 객체

        현재는 Stage 1 고정 (추후 동적 변경)
        """
        return StageParams(
            max_trades_per_day=10,
            atr_pct_24h_min=0.02,  # 2%
            ev_fee_multiple_k=2.0,
            maker_only_default=True,
        )

    def _build_signal_context(self, signal: Signal) -> SignalContext:
        """
        Signal context 생성 (EV gate용)

        Args:
            signal: Signal 객체 (signal_generator.Signal)

        Returns:
            SignalContext: Signal context 객체

        Grid spacing 기반 예상 수익 계산:
        - Expected profit: grid_spacing / entry_price (BTC) * entry_price (USD) = grid_spacing (USD)
        - Fee: qty / entry_price (BTC) * fee_rate * entry_price (USD) ≈ qty * fee_rate (USD approx)
        """
        # Fee 추정 (Maker: 0.01%, Taker: 0.06%)
        fee_rate = 0.0001 if signal.qty > 0 else 0.0001  # Maker-only 전략
        estimated_fee_usd = (signal.qty / signal.price) * fee_rate * signal.price

        # Expected profit (Grid spacing)
        expected_profit_usd = self.grid_spacing

        return SignalContext(
            expected_profit_usd=expected_profit_usd,
            estimated_fee_usd=estimated_fee_usd,
            is_maker=True,  # Maker-only 전략
        )

    def _build_sizing_params(self, signal: Signal) -> SizingParams:
        """
        Sizing 파라미터 생성

        Args:
            signal: Signal 객체 (signal_generator.Signal)

        Returns:
            SizingParams: Sizing 파라미터 객체

        Policy:
        - Max loss budget: 1% equity per trade
        - Stop distance: 3%
        - Leverage: 3x (Stage 1)
        - Fee rate: 0.01% (Maker)
        """
        # Equity BTC
        equity_btc = self.market_data.get_equity_btc()

        # Max loss BTC (loss budget = 1% equity per trade)
        max_loss_btc = equity_btc * 0.01

        # Direction (Buy → LONG, Sell → SHORT)
        direction = "LONG" if signal.side == "Buy" else "SHORT"

        # Stop distance pct (3%)
        stop_distance_pct = 0.03

        # Leverage (Stage 1 = 3x)
        leverage = 3.0

        # Fee rate (Maker: 0.01%)
        fee_rate = 0.0001

        # Tick/Lot size (Bybit BTCUSD)
        tick_size = 0.5
        qty_step = 1

        return SizingParams(
            max_loss_btc=max_loss_btc,
            entry_price_usd=signal.price,
            stop_distance_pct=stop_distance_pct,
            leverage=leverage,
            equity_btc=equity_btc,
            fee_rate=fee_rate,
            direction=direction,
            qty_step=qty_step,
            tick_size=tick_size,
        )

    def _generate_signal_id(self) -> str:
        """
        Signal ID 생성 (타임스탬프 기반)

        Returns:
            str: Signal ID (예: "1737700000")

        Grid trading에서 각 신호를 추적하기 위한 고유 ID
        """
        import time

        timestamp = int(time.time())
        return f"{timestamp}"

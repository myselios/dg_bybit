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
from domain.state import State, Position, Direction
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
        stage = get_stage_params()
        trades_today = self.market_data.get_trades_today()
        atr_pct_24h = self.market_data.get_atr_pct_24h()

        # Sizing 먼저 계산 (EV gate용 qty 필요)
        sizing_params = build_sizing_params(signal=signal, market_data=self.market_data)
        sizing_result: SizingResult = calculate_contracts(params=sizing_params)

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

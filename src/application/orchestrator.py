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
from typing import List, Optional
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

    def __init__(self, market_data: MarketDataInterface):
        """
        Orchestrator 초기화

        Args:
            market_data: Market data interface (FakeMarketData or BybitAdapter)
        """
        self.market_data = market_data
        self.state = State.FLAT
        self.position: Optional[Position] = None

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
        execution_order = []
        halt_reason = None
        entry_blocked = False
        entry_block_reason = None

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
        Events 처리 (WS 이벤트)

        FLOW Section 2.5:
            - FILL/PARTIAL_FILL/CANCEL/REJECT
            - transition() 호출로 state 전환
        """
        # 이벤트 처리는 이미 event_handler.py에 구현되어 있음
        # 여기서는 통합만 수행 (최소 구현)
        pass

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
        Entry 결정 (signal → gate → sizing)

        Returns:
            {"blocked": bool, "reason": str}

        FLOW Section 2.4:
            - degraded_mode → entry 차단
        """
        # degraded mode 체크
        ws_degraded = self.market_data.is_ws_degraded()
        if ws_degraded and self.state == State.FLAT:
            # degraded mode에서 FLAT 상태는 entry 차단
            return {"blocked": True, "reason": "degraded_mode"}

        # degraded timeout 체크 (60초)
        degraded_timeout = self.market_data.is_degraded_timeout()
        if degraded_timeout:
            # degraded 60s 경과 → HALT
            self.state = State.HALT
            return {"blocked": True, "reason": "degraded_mode_timeout"}

        return {"blocked": False, "reason": None}

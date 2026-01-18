"""State Machine 구현"""

from ..interfaces.state_machine import IStateMachine
from ..models.trading_context import TradingContext, TradingState, EVDecision


class StateMachine(IStateMachine):
    """
    State Machine 구현

    핵심 규칙:
    - MONITORING → ENTRY 전환 시 EV_FRAMEWORK가 PASS를 내야 함
    - EV가 REJECT를 내면 ENTRY로 절대 진입하지 않음
    """

    def __init__(self):
        self._current_state = TradingState.INIT

    def get_current_state(self) -> TradingState:
        """현재 상태 반환"""
        return self._current_state

    def transition(self, context: TradingContext) -> TradingState:
        """
        상태 전환 로직

        Phase 0 버전: INIT → IDLE → MONITORING → ENTRY만 구현
        """
        current = self._current_state

        if current == TradingState.INIT:
            # 초기화 완료 후 IDLE로
            self._current_state = TradingState.IDLE
            return self._current_state

        if current == TradingState.IDLE:
            # 시장 조건 충족 시 MONITORING으로
            if context.market_data:
                self._current_state = TradingState.MONITORING
            return self._current_state

        if current == TradingState.MONITORING:
            # CRITICAL: EV_FRAMEWORK 검증
            if context.strategy_signal and context.strategy_signal.entry_valid:
                if context.ev_result and context.ev_result.decision == EVDecision.PASS:
                    # EV 통과 → ENTRY 허용
                    self._current_state = TradingState.ENTRY
                else:
                    # EV 미달 → MONITORING 유지 (진입 차단)
                    print(
                        f"[STATE_MACHINE] EV_FRAMEWORK REJECTED: "
                        f"{context.ev_result.rejection_reason if context.ev_result else 'No EV result'}"
                    )
                    # MONITORING 유지
                    pass
            return self._current_state

        if current == TradingState.ENTRY:
            # Phase 0에서는 ENTRY 상태에서 즉시 IDLE로 복귀 (단순 검증용)
            print("[STATE_MACHINE] ENTRY 상태 진입 성공! IDLE로 복귀")
            self._current_state = TradingState.IDLE
            return self._current_state

        # 기타 상태는 현재 상태 유지
        return self._current_state

    def can_enter_trade(self) -> bool:
        """현재 상태에서 진입 가능한지 확인"""
        return self._current_state in [
            TradingState.MONITORING,
            TradingState.ENTRY,
        ]

"""
Event Router — Stateless Thin Wrapper

책임:
1. 이벤트 정규화 (raw event → ExecutionEvent)
2. transition() 호출
3. 결과 전달

⚠️ 금지:
- 상태 전환 분기 (if state == ...) — transition()에만 존재해야 함
- stateful 필드 (self.state 등) — 인자로만 전달
"""

from typing import Optional, Tuple

from src.domain.state import (
    State,
    ExecutionEvent,
    Position,
    PendingOrder
)
from src.domain.intent import TransitionIntents
from src.application.transition import transition


class EventRouter:
    """
    Execution Event Router (Stateless Thin Wrapper)

    역할:
    - 이벤트 정규화
    - transition() 호출 (전이 로직은 transition에만 존재)
    - 결과 전달

    ⚠️ 이 클래스는 전이 로직을 포함하지 않는다.
    """

    def handle_event(
        self,
        current_state: State,
        current_position: Optional[Position],
        event: ExecutionEvent,
        pending_order: Optional[PendingOrder] = None
    ) -> Tuple[State, Optional[Position], TransitionIntents]:
        """
        Execution Event 처리 → State Transition

        Args:
            current_state: 현재 상태
            current_position: 현재 포지션
            event: Execution event
            pending_order: 대기 중인 주문

        Returns:
            (new_state, new_position, intents)

        ⚠️ 전이 로직은 transition()에 위임
        """
        # 이벤트 정규화 (필요 시)
        normalized_event = self._normalize_event(event)

        # transition() 호출 (전이 로직의 유일한 진실)
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            normalized_event,
            pending_order
        )

        return new_state, new_position, intents

    def _normalize_event(self, event: ExecutionEvent) -> ExecutionEvent:
        """
        이벤트 정규화 (필요 시)

        예: raw exchange event → ExecutionEvent 변환
        지금은 이미 정규화된 상태라고 가정
        """
        return event

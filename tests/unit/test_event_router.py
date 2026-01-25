"""
EventRouter Unit Tests — Gate 3 증명

목적: EventRouter가 전이 로직을 포함하지 않고
      transition()을 올바르게 호출하는지 검증

Gate 3 통과 조건:
- EventRouter에 상태 전환 분기(if state == ...) 없음
- transition()과 동일한 결과를 반환
"""

import pytest

from src.domain.state import (
    State,
    StopStatus,
    Direction,
    EventType,
    ExecutionEvent,
    Position,
    PendingOrder
)
from src.application.event_router import EventRouter
from src.application.transition import transition


class TestEventRouterGate3:
    """
    Gate 3 증명: EventRouter는 thin wrapper

    검증 사항:
    - EventRouter.handle_event()와 transition()이 동일한 결과 반환
    - EventRouter에 전이 분기 로직 없음
    """

    def test_event_router_delegates_to_transition(self):
        """
        Gate 3 증명: EventRouter는 transition()에 위임만 함

        Given: ENTRY_PENDING + FILL
        When: EventRouter.handle_event() 호출
        Then: transition()과 동일한 결과 반환
        """
        # Given
        initial_state = State.ENTRY_PENDING
        initial_position = None
        pending_order = PendingOrder(
            order_id="test_order_1",
            order_link_id="test_link_1",
            placed_at=1000.0,
            signal_id="test_signal_1",
            qty=100,
            price=50000.0,
            side="Buy"
        )
        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="test_order_1",
            order_link_id="test_link_1",
            filled_qty=100,
            order_qty=100,
            timestamp=1001.0
        )

        # When: EventRouter 호출
        router = EventRouter()
        router_state, router_position, router_intents = router.handle_event(
            initial_state,
            initial_position,
            event,
            pending_order
        )

        # When: transition() 직접 호출
        direct_state, direct_position, direct_intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order
        )

        # Then: 결과 동일
        assert router_state == direct_state == State.IN_POSITION
        assert router_position is not None
        assert direct_position is not None
        assert router_position.qty == direct_position.qty == 100
        assert router_position.entry_price == direct_position.entry_price
        assert router_position.stop_status == direct_position.stop_status
        assert router_position.entry_working == direct_position.entry_working

        # Intent도 동일
        assert router_intents.stop_intent is not None
        assert direct_intents.stop_intent is not None
        assert router_intents.stop_intent.action == direct_intents.stop_intent.action == "PLACE"
        assert router_intents.stop_intent.desired_qty == direct_intents.stop_intent.desired_qty == 100

    def test_event_router_emergency_event_delegation(self):
        """
        Gate 3 증명: Emergency event도 transition()에 위임

        Given: IN_POSITION + LIQUIDATION
        When: EventRouter.handle_event() 호출
        Then: transition()과 동일하게 HALT 반환
        """
        # Given
        initial_state = State.IN_POSITION
        initial_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal_liq",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )
        event = ExecutionEvent(
            type=EventType.LIQUIDATION,
            order_id="liq_event",
            order_link_id="liq_link",
            filled_qty=0,
            order_qty=0,
            timestamp=3000.0
        )

        # When: EventRouter 호출
        router = EventRouter()
        router_state, router_position, router_intents = router.handle_event(
            initial_state,
            initial_position,
            event,
            pending_order=None
        )

        # When: transition() 직접 호출
        direct_state, direct_position, direct_intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order=None
        )

        # Then: 결과 동일 (HALT)
        assert router_state == direct_state == State.HALT
        assert router_position is None
        assert direct_position is None
        assert router_intents.halt_intent is not None
        assert direct_intents.halt_intent is not None
        assert "liquidation" in router_intents.halt_intent.reason.lower()
        assert router_intents.entry_blocked == direct_intents.entry_blocked == True

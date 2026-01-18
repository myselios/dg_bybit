"""
Unit Tests — State Transition (Pure Function)

FLOW.md Section 2.5 기반 상태 전환 Oracle Tests

원칙:
1. transition() 순수 함수 테스트
2. 36케이스 전부 실제 assert (Placeholder 금지)
3. intents 검증 (행동 규칙 명시)
"""

import pytest
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from domain.state import (
    State,
    StopStatus,
    Direction,
    EventType,
    ExecutionEvent,
    PendingOrder,
    Position
)
from application.services.state_transition import (
    transition,
    StopIntent,
    HaltIntent,
    TransitionIntents,
    is_entry_allowed
)


class TestEntryPendingTransitions:
    """
    ENTRY_PENDING 상태 전환 Tests (Unit)

    Given-When-Then 구조, 실제 assert (Placeholder 금지)
    """

    def test_entry_pending_fill_transitions_to_in_position(self):
        """
        Case 1: ENTRY_PENDING + FILL → IN_POSITION

        Given:
          - state = ENTRY_PENDING
          - pending_order.qty = 100
        When: FILL event (filled_qty=100)
        Then:
          - new_state = IN_POSITION
          - position.qty = 100
          - position.entry_working = False
          - stop_intent.action = "PLACE"
          - stop_intent.desired_qty = 100
        """
        # Given
        current_state = State.ENTRY_PENDING
        current_position = None
        pending_order = PendingOrder(
            order_id="entry_1",
            order_link_id="entry_link_1",
            placed_at=1000.0,
            signal_id="signal_1",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="entry_1",
            order_link_id="entry_link_1",
            filled_qty=100,
            order_qty=100,
            timestamp=1001.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            pending_order
        )

        # Then: State transition
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 100
        assert new_position.entry_price == 50000.0
        assert new_position.direction == Direction.LONG
        assert new_position.stop_status == StopStatus.PENDING
        assert new_position.entry_working is False

        # Then: Intents
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "PLACE"
        assert intents.stop_intent.desired_qty == 100
        assert "stop" in intents.stop_intent.reason.lower()
        assert intents.halt_intent is None
        assert intents.entry_blocked is False

    def test_entry_pending_partial_fill_transitions_to_in_position_with_entry_working(self):
        """
        Case 2: ENTRY_PENDING + PARTIAL_FILL → IN_POSITION (entry_working=True)

        Given:
          - state = ENTRY_PENDING
          - pending_order.qty = 100
        When: PARTIAL_FILL event (filled_qty=20)
        Then:
          - new_state = IN_POSITION
          - position.qty = 20
          - position.entry_working = True (잔량 활성)
          - stop_intent.action = "PLACE"
          - stop_intent.desired_qty = 20
          - stop_intent.reason = "first_partial_fill_requires_immediate_stop_install"
        """
        # Given
        current_state = State.ENTRY_PENDING
        pending_order = PendingOrder(
            order_id="entry_2",
            order_link_id="entry_link_2",
            placed_at=1000.0,
            signal_id="signal_2",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        event = ExecutionEvent(
            type=EventType.PARTIAL_FILL,
            order_id="entry_2",
            order_link_id="entry_link_2",
            filled_qty=20,
            order_qty=100,
            timestamp=1001.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            None,
            event,
            pending_order
        )

        # Then: State transition
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 20
        assert new_position.entry_working is True  # 치명적 규칙
        assert new_position.stop_status == StopStatus.PENDING
        assert new_position.entry_order_id == "entry_2"

        # Then: Intents
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "PLACE"
        assert intents.stop_intent.desired_qty == 20
        assert intents.stop_intent.reason == "first_partial_fill_requires_immediate_stop_install"

    def test_entry_pending_reject_transitions_to_flat(self):
        """
        Case 3: ENTRY_PENDING + REJECT → FLAT

        Given: state = ENTRY_PENDING
        When: REJECT event
        Then:
          - new_state = FLAT
          - position = None
          - no intents
        """
        # Given
        current_state = State.ENTRY_PENDING
        pending_order = PendingOrder(
            order_id="entry_3",
            order_link_id="entry_link_3",
            placed_at=1000.0,
            signal_id="signal_3",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        event = ExecutionEvent(
            type=EventType.REJECT,
            order_id="entry_3",
            order_link_id="entry_link_3",
            filled_qty=0,
            order_qty=100,
            timestamp=1001.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            None,
            event,
            pending_order
        )

        # Then
        assert new_state == State.FLAT
        assert new_position is None
        assert intents.stop_intent is None
        assert intents.halt_intent is None

    def test_entry_pending_cancel_zero_fill_transitions_to_flat(self):
        """
        Case 4: ENTRY_PENDING + CANCEL (filled_qty=0) → FLAT

        Given: state = ENTRY_PENDING
        When: CANCEL event with filled_qty=0
        Then:
          - new_state = FLAT
          - position = None
        """
        # Given
        current_state = State.ENTRY_PENDING
        pending_order = PendingOrder(
            order_id="entry_4",
            order_link_id="entry_link_4",
            placed_at=1000.0,
            signal_id="signal_4",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        event = ExecutionEvent(
            type=EventType.CANCEL,
            order_id="entry_4",
            order_link_id="entry_link_4",
            filled_qty=0,
            order_qty=100,
            timestamp=1001.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            None,
            event,
            pending_order
        )

        # Then
        assert new_state == State.FLAT
        assert new_position is None
        assert intents.stop_intent is None

    def test_entry_pending_cancel_partial_fill_transitions_to_in_position(self):
        """
        Case 5: ENTRY_PENDING + CANCEL (filled_qty>0) → IN_POSITION

        Given: state = ENTRY_PENDING
        When: CANCEL event with filled_qty=30 (부분체결 후 취소)
        Then:
          - new_state = IN_POSITION
          - position.qty = 30
          - position.entry_working = False (잔량 취소됨)
          - stop_intent.action = "PLACE"
        """
        # Given
        current_state = State.ENTRY_PENDING
        pending_order = PendingOrder(
            order_id="entry_5",
            order_link_id="entry_link_5",
            placed_at=1000.0,
            signal_id="signal_5",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        event = ExecutionEvent(
            type=EventType.CANCEL,
            order_id="entry_5",
            order_link_id="entry_link_5",
            filled_qty=30,
            order_qty=100,
            timestamp=1001.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            None,
            event,
            pending_order
        )

        # Then
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 30
        assert new_position.entry_working is False  # 잔량 취소됨
        assert new_position.stop_status == StopStatus.PENDING

        # Stop PLACE intent
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "PLACE"
        assert intents.stop_intent.desired_qty == 30


class TestExitPendingTransitions:
    """
    EXIT_PENDING 상태 전환 Tests
    """

    def test_exit_pending_fill_transitions_to_flat(self):
        """
        Case 6: EXIT_PENDING + FILL → FLAT

        Given:
          - state = EXIT_PENDING
          - position.qty = 100 (청산 대기 중)
        When: FILL event (exit order 완전 체결)
        Then:
          - new_state = FLAT
          - position = None
          - no intents
        """
        # Given
        current_state = State.EXIT_PENDING
        current_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="signal_exit",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="exit_1",
            order_link_id="exit_link_1",
            filled_qty=100,
            order_qty=100,
            timestamp=2000.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            None
        )

        # Then
        assert new_state == State.FLAT
        assert new_position is None
        assert intents.stop_intent is None
        assert intents.halt_intent is None
        assert intents.entry_blocked is False

    def test_exit_pending_reject_stays_in_exit_pending(self):
        """
        Case 7: EXIT_PENDING + REJECT → stay (재시도)

        Given: state = EXIT_PENDING
        When: REJECT event (exit order 거절)
        Then:
          - new_state = EXIT_PENDING (재시도 필요)
          - position = 유지
          - no intents
        """
        # Given
        current_state = State.EXIT_PENDING
        current_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="signal_exit",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.REJECT,
            order_id="exit_2",
            order_link_id="exit_link_2",
            filled_qty=0,
            order_qty=100,
            timestamp=2000.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            None
        )

        # Then
        assert new_state == State.EXIT_PENDING
        assert new_position is not None
        assert new_position.qty == 100
        assert intents.stop_intent is None
        assert intents.halt_intent is None

    def test_exit_pending_cancel_stays_in_exit_pending(self):
        """
        Case 8: EXIT_PENDING + CANCEL → stay (재시도)

        Given: state = EXIT_PENDING
        When: CANCEL event (exit order 취소)
        Then:
          - new_state = EXIT_PENDING (재시도 필요)
          - position = 유지
          - no intents
        """
        # Given
        current_state = State.EXIT_PENDING
        current_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="signal_exit",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.CANCEL,
            order_id="exit_3",
            order_link_id="exit_link_3",
            filled_qty=0,
            order_qty=100,
            timestamp=2000.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            None
        )

        # Then
        assert new_state == State.EXIT_PENDING
        assert new_position is not None
        assert new_position.qty == 100
        assert intents.stop_intent is None
        assert intents.halt_intent is None


class TestExitPendingPartialFills:
    """
    EXIT_PENDING 부분체결 및 과체결 안전장치 Tests
    """

    def test_exit_pending_partial_fill_reduces_position_qty_and_stays_exit_pending(self):
        """
        Case 22: EXIT_PENDING + PARTIAL_FILL → EXIT_PENDING 유지 + qty 감소

        Given:
          - state = EXIT_PENDING
          - position.qty = 100
        When: PARTIAL_FILL (filled_qty=30)
        Then:
          - new_state = EXIT_PENDING (유지)
          - position.qty = 70 (100 - 30)
          - no intents
        """
        # Given
        current_state = State.EXIT_PENDING
        current_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="signal_exit_partial",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.PARTIAL_FILL,
            order_id="exit_partial_1",
            order_link_id="exit_partial_link_1",
            filled_qty=30,
            order_qty=100,
            timestamp=2100.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            None
        )

        # Then
        assert new_state == State.EXIT_PENDING
        assert new_position is not None
        assert new_position.qty == 70
        assert intents.stop_intent is None
        assert intents.halt_intent is None

    def test_exit_pending_fill_after_partial_should_flat(self):
        """
        Case 23: EXIT_PENDING + FILL → FLAT (최종 청산 완료)

        Given:
          - state = EXIT_PENDING
          - position.qty = 70 (이전 partial 이후)
        When: FILL (filled_qty=70)
        Then:
          - new_state = FLAT
          - position = None
          - no intents
        """
        # Given
        current_state = State.EXIT_PENDING
        current_position = Position(
            qty=70,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="signal_exit_final",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="exit_final",
            order_link_id="exit_final_link",
            filled_qty=70,
            order_qty=100,
            timestamp=2200.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            None
        )

        # Then
        assert new_state == State.FLAT
        assert new_position is None
        assert intents.stop_intent is None
        assert intents.halt_intent is None

    def test_exit_pending_overfill_should_halt(self):
        """
        Case 24: EXIT_PENDING + FILL over position qty → HALT

        Given:
          - state = EXIT_PENDING
          - position.qty = 50
        When: FILL arrives with filled_qty=80 (과체결)
        Then:
          - new_state = HALT
          - position = None
          - halt_intent.reason = "exit_fill_exceeded_position_qty"
          - entry_blocked = True
        """
        # Given
        current_state = State.EXIT_PENDING
        current_position = Position(
            qty=50,
            entry_price=50000.0,
            direction=Direction.SHORT,
            signal_id="signal_overfill",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="exit_overfill",
            order_link_id="exit_overfill_link",
            filled_qty=80,
            order_qty=100,
            timestamp=2300.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            None
        )

        # Then
        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert intents.halt_intent.reason == "exit_fill_exceeded_position_qty"
        assert intents.entry_blocked is True


class TestUnexpectedEvents:
    """
    예상치 못한 이벤트 Tests (HALT 트리거)
    """

    def test_flat_unexpected_fill_should_halt(self):
        """
        Case 16: FLAT + FILL → HALT (유령 체결)

        Given: state = FLAT
        When: FILL event arrives (filled_qty>0)
        Then:
          - new_state = HALT
          - halt_intent.reason = "unexpected_fill_while_flat"
          - entry_blocked = True
        """
        # Given
        current_state = State.FLAT
        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="ghost_fill",
            order_link_id="ghost",
            filled_qty=10,
            order_qty=10,
            timestamp=1000.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            None,
            event,
            None
        )

        # Then
        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert intents.halt_intent.reason == "unexpected_fill_while_flat"
        assert intents.entry_blocked is True


class TestEmergencyEvents:
    """
    Emergency Events Tests (LIQUIDATION, ADL)

    모든 상태에서 최우선 처리 → HALT
    """

    def test_liquidation_from_in_position_should_halt(self):
        """
        Case 19: LIQUIDATION (IN_POSITION) → HALT

        Given:
          - state = IN_POSITION
          - position.qty = 100
        When: LIQUIDATION event
        Then:
          - new_state = HALT
          - position = None (청산됨)
          - halt_intent.reason = "liquidation_event_requires_immediate_halt"
          - entry_blocked = True
        """
        # Given
        current_state = State.IN_POSITION
        current_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="signal_liq",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.LIQUIDATION,
            order_id="liquidation_order",
            order_link_id="liq_link",
            filled_qty=100,
            order_qty=100,
            timestamp=3000.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            None
        )

        # Then
        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert intents.halt_intent.reason == "liquidation_event_requires_immediate_halt"
        assert intents.entry_blocked is True
        assert intents.stop_intent is None

    def test_adl_from_in_position_should_halt(self):
        """
        Case 20: ADL (IN_POSITION) → HALT

        Given:
          - state = IN_POSITION
          - position.qty = 50
        When: ADL event
        Then:
          - new_state = HALT
          - position = None (청산됨)
          - halt_intent.reason = "adl_event_requires_immediate_halt"
          - entry_blocked = True
        """
        # Given
        current_state = State.IN_POSITION
        current_position = Position(
            qty=50,
            entry_price=51000.0,
            direction=Direction.SHORT,
            signal_id="signal_adl",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.ADL,
            order_id="adl_order",
            order_link_id="adl_link",
            filled_qty=50,
            order_qty=50,
            timestamp=3500.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            None
        )

        # Then
        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert intents.halt_intent.reason == "adl_event_requires_immediate_halt"
        assert intents.entry_blocked is True

    def test_liquidation_from_flat_should_halt(self):
        """
        Case 21: Emergency event는 모든 상태에서 최우선 처리

        Given:
          - state = FLAT (포지션 없음)
        When: LIQUIDATION event (예상치 못한 상황)
        Then:
          - new_state = HALT
          - position = None
          - halt_intent 생성
          - entry_blocked = True
        """
        # Given
        current_state = State.FLAT
        current_position = None

        event = ExecutionEvent(
            type=EventType.LIQUIDATION,
            order_id="unexpected_liq",
            order_link_id="liq_flat",
            filled_qty=0,
            order_qty=0,
            timestamp=4000.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            None
        )

        # Then
        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert "liquidation" in intents.halt_intent.reason.lower()
        assert intents.entry_blocked is True


class TestInPositionAdditionalFills:
    """
    IN_POSITION 상태에서 추가 체결 Tests

    entry_working=True → 잔량 주문 활성 상태
    """

    def test_in_position_additional_partial_fill_increases_qty_and_amends_stop(self):
        """
        Case 17: IN_POSITION (entry_working=True) + PARTIAL_FILL → qty 증가 + AMEND intent

        Given:
          - state = IN_POSITION
          - position.qty = 20 (첫 부분체결)
          - position.entry_working = True (잔량 활성)
          - position.entry_order_id = "entry_2"
        When: PARTIAL_FILL event (추가 체결 +10)
        Then:
          - new_state = IN_POSITION (유지)
          - position.qty = 30 (20 + 10)
          - position.entry_working = True (여전히 활성)
          - stop_intent.action = "AMEND"
          - stop_intent.desired_qty = 30
          - stop_intent.reason = "additional_partial_fill_requires_stop_qty_update"
        """
        # Given
        current_state = State.IN_POSITION
        current_position = Position(
            qty=20,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="signal_add",
            stop_status=StopStatus.ACTIVE,
            entry_working=True,
            entry_order_id="entry_2"
        )

        event = ExecutionEvent(
            type=EventType.PARTIAL_FILL,
            order_id="entry_2",
            order_link_id="entry_link_2",
            filled_qty=10,
            order_qty=100,
            timestamp=1500.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            None
        )

        # Then: State transition
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 30
        assert new_position.entry_working is True
        assert new_position.entry_order_id == "entry_2"
        assert new_position.stop_status == StopStatus.ACTIVE

        # Then: Intents
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "AMEND"
        assert intents.stop_intent.desired_qty == 30
        assert intents.stop_intent.reason == "additional_partial_fill_requires_stop_qty_update"
        assert intents.halt_intent is None

    def test_in_position_entry_fill_complete_sets_entry_working_false(self):
        """
        Case 18: IN_POSITION (entry_working=True) + FILL → qty 증가 + entry_working=False

        Given:
          - state = IN_POSITION
          - position.qty = 30 (이전 체결)
          - position.entry_working = True
          - position.entry_order_id = "entry_2"
        When: FILL event (잔량 완전 체결 +70)
        Then:
          - new_state = IN_POSITION (유지)
          - position.qty = 100 (30 + 70)
          - position.entry_working = False (완전 체결)
          - position.entry_order_id = None
          - stop_intent.action = "AMEND"
          - stop_intent.desired_qty = 100
          - stop_intent.reason = "entry_fill_complete_final_stop_qty_update"
        """
        # Given
        current_state = State.IN_POSITION
        current_position = Position(
            qty=30,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="signal_complete",
            stop_status=StopStatus.ACTIVE,
            entry_working=True,
            entry_order_id="entry_2"
        )

        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="entry_2",
            order_link_id="entry_link_2",
            filled_qty=70,
            order_qty=100,
            timestamp=2000.0
        )

        # When
        new_state, new_position, intents = transition(
            current_state,
            current_position,
            event,
            None
        )

        # Then: State transition
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 100
        assert new_position.entry_working is False
        assert new_position.entry_order_id is None
        assert new_position.stop_status == StopStatus.ACTIVE

        # Then: Intents
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "AMEND"
        assert intents.stop_intent.desired_qty == 100
        assert intents.stop_intent.reason == "entry_fill_complete_final_stop_qty_update"
        assert intents.halt_intent is None


class TestEntryBlocking:
    """
    HALT/COOLDOWN 진입 차단 규칙 Tests

    Cases 25-27: 진입 허용 여부 검증
    """

    def test_halt_blocks_new_entry(self):
        """
        Case 25: HALT 상태 → 진입 차단

        Given: state = HALT
        When: is_entry_allowed() called
        Then: returns False
        """
        assert is_entry_allowed(State.HALT) is False

    def test_cooldown_blocks_new_entry(self):
        """
        Case 26: COOLDOWN 상태 → 진입 차단

        Given: state = COOLDOWN
        When: is_entry_allowed() called
        Then: returns False
        """
        assert is_entry_allowed(State.COOLDOWN) is False

    def test_flat_allows_entry(self):
        """
        Case 27: FLAT 상태 → 진입 허용

        Given: state = FLAT
        When: is_entry_allowed() called
        Then: returns True
        """
        assert is_entry_allowed(State.FLAT) is True

    def test_other_states_allow_entry(self):
        """
        기타 상태 (ENTRY_PENDING, IN_POSITION, EXIT_PENDING) → 진입 허용

        Note: 실제로는 이들 상태에서 진입 시도가 없지만, is_entry_allowed는 True 반환
        """
        assert is_entry_allowed(State.ENTRY_PENDING) is True
        assert is_entry_allowed(State.IN_POSITION) is True
        assert is_entry_allowed(State.EXIT_PENDING) is True

    def test_halt_state_persists_on_unexpected_events(self):
        """
        HALT 상태는 예상치 못한 이벤트에도 유지

        Given: state = HALT
        When: FILL event arrives (예상치 못한 이벤트)
        Then: state remains HALT
        """
        current_state = State.HALT
        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="unexpected",
            order_link_id="unexpected_link",
            filled_qty=10,
            order_qty=10,
            timestamp=5000.0
        )

        new_state, new_position, intents = transition(
            current_state,
            None,
            event,
            None
        )

        # HALT 유지 (변경 없음)
        assert new_state == State.HALT

"""
tests/unit/test_event_handler.py
Unit tests for event handler (FLOW Section 2.5)

Purpose:
- ExecutionEvent → transition() 호출 → intents 실행
- PARTIAL_FILL → IN_POSITION + Stop 즉시 설치 (safety rule)
- CANCEL 처리 (filled_qty 확인)
- REJECT → FLAT
- Intents 실행 (Stop, Halt, Cancel)

SSOT:
- FLOW.md Section 2.5: Execution Events

Test Coverage:
1. handle_fill_event_entry_pending_to_in_position (FILL → Stop 설치)
2. handle_partial_fill_stop_immediately_placed (PARTIAL_FILL → Stop 즉시)
3. handle_cancel_with_filled_qty_becomes_in_position (filled_qty > 0)
4. handle_cancel_with_zero_filled_becomes_flat (filled_qty = 0)
5. handle_reject_returns_to_flat (REJECT → FLAT)
6. execute_intents_stop_amend (StopIntent.AMEND)
7. execute_intents_halt_cancels_all_orders (HaltIntent + cancel)
"""

from application.event_handler import (
    handle_execution_event,
    execute_intents,
)
from domain.state import State, Position, PendingOrder, StopStatus, Direction
from domain.events import ExecutionEvent, EventType
from domain.intent import (
    TransitionIntents,
    StopIntent,
    HaltIntent,
    CancelOrderIntent,
)


def test_handle_fill_event_entry_pending_to_in_position():
    """
    FILL → IN_POSITION + Stop 설치 (FLOW Section 2.5)

    FLOW Section 2.5:
        - FILL 이벤트 → ENTRY_PENDING → IN_POSITION
        - Position 생성 (filled_qty)
        - Stop 즉시 설치 (StopIntent.PLACE)

    Example:
        state=ENTRY_PENDING
        event=FILL(filled_qty=100)

    Expected:
        new_state=IN_POSITION
        position.qty=100, stop_status=PENDING
        StopIntent(action="PLACE", desired_qty=100)
    """
    # Preconditions
    current_state = State.ENTRY_PENDING
    current_position = None
    pending_order = PendingOrder(
        order_id="order_1",
        signal_id="test_1",
        order_link_id="test_1_Buy",
        side="Buy",
        qty=100,
        price=50000.0,
        placed_at=1705593600.0,
    )

    event = ExecutionEvent(
        type=EventType.FILL,
        order_id="order_1",
        order_link_id="test_1_Buy",
        filled_qty=100,
        order_qty=100,
        timestamp=1705593600.0,
        exec_price=50000.0,
    )

    # When
    result = handle_execution_event(
        event=event,
        current_state=current_state,
        current_position=current_position,
        pending_order=pending_order,
    )

    # Then
    assert result.new_state == State.IN_POSITION
    assert result.new_position is not None
    assert result.new_position.qty == 100
    assert result.new_position.stop_status == StopStatus.PENDING

    # StopIntent 확인
    assert result.intents.stop_intent is not None
    assert result.intents.stop_intent.action == "PLACE"
    assert result.intents.stop_intent.desired_qty == 100


def test_handle_partial_fill_stop_immediately_placed():
    """
    PARTIAL_FILL → IN_POSITION + Stop 즉시 설치 (FLOW Section 2.5 Safety Rule)

    FLOW Section 2.5:
        Critical Safety Rule:
        - filled_qty > 0 → 즉시 IN_POSITION + Stop 설치
        - entry_working=True (추가 체결 가능)

    Example:
        state=ENTRY_PENDING
        event=PARTIAL_FILL(filled_qty=50, order_qty=100)

    Expected:
        new_state=IN_POSITION
        position.qty=50, entry_working=True
        StopIntent(action="PLACE", desired_qty=50)
    """
    # Preconditions
    current_state = State.ENTRY_PENDING
    current_position = None
    pending_order = PendingOrder(
        order_id="order_1",
        signal_id="test_1",
        order_link_id="test_1_Buy",
        side="Buy",
        qty=100,
        price=50000.0,
        placed_at=1705593600.0,
    )

    event = ExecutionEvent(
        type=EventType.PARTIAL_FILL,
        order_id="order_1",
        order_link_id="test_1_Buy",
        filled_qty=50,
        order_qty=100,
        timestamp=1705593600.0,
        exec_price=50000.0,
    )

    # When
    result = handle_execution_event(
        event=event,
        current_state=current_state,
        current_position=current_position,
        pending_order=pending_order,
    )

    # Then
    assert result.new_state == State.IN_POSITION
    assert result.new_position is not None
    assert result.new_position.qty == 50
    assert result.new_position.entry_working is True

    # StopIntent 확인 (즉시 설치)
    assert result.intents.stop_intent is not None
    assert result.intents.stop_intent.action == "PLACE"
    assert result.intents.stop_intent.desired_qty == 50


def test_handle_cancel_with_filled_qty_becomes_in_position():
    """
    CANCEL (filled_qty > 0) → IN_POSITION (FLOW Section 2.5)

    FLOW Section 2.5:
        - CANCEL 이벤트 → filled_qty 확인
        - filled_qty > 0 → IN_POSITION (부분 체결 후 취소)

    Example:
        state=ENTRY_PENDING
        event=CANCEL(filled_qty=50, order_qty=100)

    Expected:
        new_state=IN_POSITION
        position.qty=50
    """
    # Preconditions
    current_state = State.ENTRY_PENDING
    current_position = None
    pending_order = PendingOrder(
        order_id="order_1",
        signal_id="test_1",
        order_link_id="test_1_Buy",
        side="Buy",
        qty=100,
        price=50000.0,
        placed_at=1705593600.0,
    )

    event = ExecutionEvent(
        type=EventType.CANCEL,
        order_id="order_1",
        order_link_id="test_1_Buy",
        filled_qty=50,
        order_qty=100,
        timestamp=1705593600.0,
    )

    # When
    result = handle_execution_event(
        event=event,
        current_state=current_state,
        current_position=current_position,
        pending_order=pending_order,
    )

    # Then
    assert result.new_state == State.IN_POSITION
    assert result.new_position is not None
    assert result.new_position.qty == 50


def test_handle_cancel_with_zero_filled_becomes_flat():
    """
    CANCEL (filled_qty = 0) → FLAT (FLOW Section 2.5)

    FLOW Section 2.5:
        - filled_qty = 0 → FLAT (체결 없음)

    Example:
        state=ENTRY_PENDING
        event=CANCEL(filled_qty=0)

    Expected:
        new_state=FLAT
        position=None
    """
    # Preconditions
    current_state = State.ENTRY_PENDING
    current_position = None
    pending_order = PendingOrder(
        order_id="order_1",
        signal_id="test_1",
        order_link_id="test_1_Buy",
        side="Buy",
        qty=100,
        price=50000.0,
        placed_at=1705593600.0,
    )

    event = ExecutionEvent(
        type=EventType.CANCEL,
        order_id="order_1",
        order_link_id="test_1_Buy",
        filled_qty=0,
        order_qty=100,
        timestamp=1705593600.0,
    )

    # When
    result = handle_execution_event(
        event=event,
        current_state=current_state,
        current_position=current_position,
        pending_order=pending_order,
    )

    # Then
    assert result.new_state == State.FLAT
    assert result.new_position is None


def test_handle_reject_returns_to_flat():
    """
    REJECT → FLAT (FLOW Section 2.5)

    FLOW Section 2.5:
        - REJECT 이벤트 → FLAT (주문 거절)

    Example:
        state=ENTRY_PENDING
        event=REJECT

    Expected:
        new_state=FLAT
        position=None
    """
    # Preconditions
    current_state = State.ENTRY_PENDING
    current_position = None
    pending_order = PendingOrder(
        order_id="order_1",
        signal_id="test_1",
        order_link_id="test_1_Buy",
        side="Buy",
        qty=100,
        price=50000.0,
        placed_at=1705593600.0,
    )

    event = ExecutionEvent(
        type=EventType.REJECT,
        order_id="order_1",
        order_link_id="test_1_Buy",
        filled_qty=0,
        order_qty=100,
        timestamp=1705593600.0,
    )

    # When
    result = handle_execution_event(
        event=event,
        current_state=current_state,
        current_position=current_position,
        pending_order=pending_order,
    )

    # Then
    assert result.new_state == State.FLAT
    assert result.new_position is None


def test_execute_intents_stop_amend():
    """
    StopIntent.AMEND → order_executor.amend_stop_loss() 호출

    Example:
        StopIntent(action="AMEND", desired_qty=150)

    Expected:
        order_executor.amend_stop_loss() 호출
    """
    # Preconditions
    position = Position(
        direction=Direction.LONG,
        qty=100,
        entry_price=50000.0,
        signal_id="test_1",
        stop_price=49000.0,
        stop_status=StopStatus.ACTIVE,
        stop_order_id="stop_1",
        entry_working=False,
    )

    intents = TransitionIntents(
        stop_intent=StopIntent(action="AMEND", desired_qty=150, reason="qty_increased")
    )

    # When
    results = execute_intents(intents=intents, position=position)

    # Then
    assert len(results) > 0
    # Amend intent 실행 확인 (Fake implementation에서는 success=True)
    amend_result = results[0]
    assert amend_result.intent_type == "STOP_AMEND"
    assert amend_result.success is True


def test_execute_intents_halt_cancels_all_orders():
    """
    HaltIntent + pending_order → order_executor.cancel_order() 호출

    Example:
        HaltIntent(reason="balance_too_low")
        pending_order 존재

    Expected:
        order_executor.cancel_order() 호출
        entry_blocked=True
    """
    # Preconditions
    pending_order = PendingOrder(
        order_id="order_1",
        signal_id="test_1",
        order_link_id="test_1_Buy",
        side="Buy",
        qty=100,
        price=50000.0,
        placed_at=1705593600.0,
    )

    intents = TransitionIntents(
        halt_intent=HaltIntent(reason="balance_too_low"),
        cancel_intent=CancelOrderIntent(order_link_id="test_1_Buy"),
        entry_blocked=True,
    )

    # When
    results = execute_intents(intents=intents, position=None)

    # Then
    assert len(results) >= 2  # HALT + CANCEL
    # HALT intent 실행 확인
    halt_result = next((r for r in results if r.intent_type == "HALT"), None)
    assert halt_result is not None
    assert halt_result.success is True

    # CANCEL intent 실행 확인
    cancel_result = next((r for r in results if r.intent_type == "CANCEL"), None)
    assert cancel_result is not None
    assert cancel_result.success is True

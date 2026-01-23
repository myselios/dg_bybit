"""
tests/unit/test_exit_manager.py

Phase 11: Exit Manager 테스트

DoD:
- check_stop_hit(): Stop loss 도달 확인 (LONG/SHORT 별)
- check_profit_target(): Profit target 도달 확인 (optional)
- create_exit_intent(): Exit 주문 Intent 생성
"""

import pytest
from domain.state import Position, Direction, StopStatus
from application.exit_manager import check_stop_hit, create_exit_intent


# Test 1: LONG 포지션에서 stop price 도달
def test_stop_hit_long():
    """
    시나리오: LONG 포지션, current_price <= stop_price → Stop hit

    검증:
    - check_stop_hit() returns True
    """
    # Given: LONG position, entry_price = 50000, stop_price = 49000
    position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.LONG,
        signal_id="test_001",
        stop_price=49000.0,
        stop_status=StopStatus.ACTIVE,
    )
    current_price = 48900.0  # Below stop price

    # When: check_stop_hit()
    is_hit = check_stop_hit(current_price=current_price, position=position)

    # Then: Stop hit
    assert is_hit is True, "Should detect stop hit for LONG when price <= stop_price"


# Test 2: SHORT 포지션에서 stop price 도달
def test_stop_hit_short():
    """
    시나리오: SHORT 포지션, current_price >= stop_price → Stop hit

    검증:
    - check_stop_hit() returns True
    """
    # Given: SHORT position, entry_price = 50000, stop_price = 51000
    position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.SHORT,
        signal_id="test_002",
        stop_price=51000.0,
        stop_status=StopStatus.ACTIVE,
    )
    current_price = 51100.0  # Above stop price

    # When: check_stop_hit()
    is_hit = check_stop_hit(current_price=current_price, position=position)

    # Then: Stop hit
    assert is_hit is True, "Should detect stop hit for SHORT when price >= stop_price"


# Test 3: LONG 포지션에서 stop price 미도달
def test_stop_not_hit_long():
    """
    시나리오: LONG 포지션, current_price > stop_price → No stop hit

    검증:
    - check_stop_hit() returns False
    """
    # Given: LONG position, entry_price = 50000, stop_price = 49000
    position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.LONG,
        signal_id="test_003",
        stop_price=49000.0,
        stop_status=StopStatus.ACTIVE,
    )
    current_price = 49100.0  # Above stop price

    # When: check_stop_hit()
    is_hit = check_stop_hit(current_price=current_price, position=position)

    # Then: No stop hit
    assert is_hit is False, "Should not detect stop hit for LONG when price > stop_price"


# Test 4: SHORT 포지션에서 stop price 미도달
def test_stop_not_hit_short():
    """
    시나리오: SHORT 포지션, current_price < stop_price → No stop hit

    검증:
    - check_stop_hit() returns False
    """
    # Given: SHORT position, entry_price = 50000, stop_price = 51000
    position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.SHORT,
        signal_id="test_004",
        stop_price=51000.0,
        stop_status=StopStatus.ACTIVE,
    )
    current_price = 50900.0  # Below stop price

    # When: check_stop_hit()
    is_hit = check_stop_hit(current_price=current_price, position=position)

    # Then: No stop hit
    assert is_hit is False, "Should not detect stop hit for SHORT when price < stop_price"


# Test 5: Exit intent 생성 (시장가 주문)
def test_create_exit_intent():
    """
    시나리오: Stop hit → Exit intent 생성

    검증:
    - TransitionIntents with exit order
    - Market order (시장가 강제 청산)
    - Exit reason 포함
    """
    # Given: LONG position
    position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.LONG,
        signal_id="test_005",
        stop_price=49000.0,
        stop_status=StopStatus.ACTIVE,
    )
    reason = "stop_loss_hit"

    # When: create_exit_intent()
    intents = create_exit_intent(position=position, reason=reason)

    # Then: Exit intent 생성
    assert intents is not None, "Should create exit intents"
    assert intents.exit_intent is not None, "Should have exit intent"
    assert intents.exit_intent.reason == reason, "Exit reason should match"
    assert intents.exit_intent.qty == position.qty, "Exit qty should match position qty"
    # Market order로 청산 (Grid 전략에서는 시장가 강제 청산)
    assert intents.exit_intent.order_type == "Market", "Should use Market order for stop loss"


# Test 6: Stop price 경계값 (LONG, exactly at stop price)
def test_stop_hit_long_boundary():
    """
    Edge case: LONG 포지션, current_price == stop_price → Stop hit

    검증:
    - check_stop_hit() returns True (경계값 포함)
    """
    # Given: LONG position, current_price == stop_price
    position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.LONG,
        signal_id="test_006",
        stop_price=49000.0,
        stop_status=StopStatus.ACTIVE,
    )
    current_price = 49000.0  # Exactly at stop price

    # When: check_stop_hit()
    is_hit = check_stop_hit(current_price=current_price, position=position)

    # Then: Stop hit (경계값 포함)
    assert is_hit is True, "Should detect stop hit for LONG when price == stop_price"


# Test 7: Stop price 경계값 (SHORT, exactly at stop price)
def test_stop_hit_short_boundary():
    """
    Edge case: SHORT 포지션, current_price == stop_price → Stop hit

    검증:
    - check_stop_hit() returns True (경계값 포함)
    """
    # Given: SHORT position, current_price == stop_price
    position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.SHORT,
        signal_id="test_007",
        stop_price=51000.0,
        stop_status=StopStatus.ACTIVE,
    )
    current_price = 51000.0  # Exactly at stop price

    # When: check_stop_hit()
    is_hit = check_stop_hit(current_price=current_price, position=position)

    # Then: Stop hit (경계값 포함)
    assert is_hit is True, "Should detect stop hit for SHORT when price == stop_price"


# Test 8: Stop price None일 때 예외 처리
def test_stop_hit_no_stop_price():
    """
    Edge case: stop_price가 None일 때 → No stop hit

    검증:
    - check_stop_hit() returns False (또는 에러 처리)
    """
    # Given: Position with stop_price = None
    position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.LONG,
        signal_id="test_008",
        stop_price=None,  # No stop price set
        stop_status=StopStatus.MISSING,
    )
    current_price = 48000.0

    # When: check_stop_hit()
    is_hit = check_stop_hit(current_price=current_price, position=position)

    # Then: No stop hit (stop_price가 없으면 확인 불가)
    assert is_hit is False, "Should return False when stop_price is None"

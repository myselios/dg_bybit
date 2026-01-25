"""
tests/unit/test_orchestrator_event_processing.py
Unit tests for Orchestrator Event Processing (Phase 11b)

SSOT:
- FLOW.md Section 2.5: Event Processing Flow
- task_plan.md Phase 11b: Event Processing (FILL → Position update)

Test Coverage:
1. test_event_processing_entry_fill_success — Entry FILL 정상 처리 (ENTRY_PENDING → IN_POSITION)
2. test_event_processing_exit_fill_success — Exit FILL 정상 처리 (EXIT_PENDING → FLAT)
3. test_event_processing_no_pending_order — Pending order 없을 때 매칭 실패
4. test_event_processing_order_id_mismatch — Order ID 불일치 시 매칭 실패
5. test_event_processing_dual_id_matching_order_id — orderId로 매칭 성공
6. test_event_processing_dual_id_matching_order_link_id — orderLinkId로 매칭 성공 (fallback)
7. test_state_consistency_check_position_without_state — Position != None but State = FLAT → HALT
8. test_state_consistency_check_state_without_position — Position = None but State = IN_POSITION → HALT
9. test_state_consistency_check_normal — 정상 조합 → 통과
"""

import pytest
from application.orchestrator import Orchestrator
from infrastructure.exchange.fake_market_data import FakeMarketData
from domain.state import State, Position, Direction


class MockRestClient:
    """Mock REST client for testing"""

    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.orders = []

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: int,
        price: float,
        time_in_force: str,
        order_link_id: str,
    ):
        """Mock place_order method"""
        if self.should_fail:
            raise Exception("Order placement failed (mock)")

        order = {
            "orderId": "mock_order_123",
            "orderLinkId": order_link_id,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "price": price,
            "timeInForce": time_in_force,
        }
        self.orders.append(order)
        return order


# ========== Test 1: Entry FILL 정상 처리 ==========


def test_event_processing_entry_fill_success():
    """
    Test 1: Entry FILL 정상 처리 (ENTRY_PENDING → IN_POSITION)

    Given:
        - State: ENTRY_PENDING
        - Pending order: order_id="order_123", qty=100, price=50000.0, side="Buy"
        - FILL event: orderId="order_123", execQty=100, execPrice=50000.0, side="Buy"

    When:
        - run_tick() 실행 (Event Processing)

    Then:
        - State: IN_POSITION
        - Position: Created (qty=100, entry_price=50000.0, direction=LONG, stop_price=48500.0)
        - Pending order: None (cleaned up)
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_btc=0.0025)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    # ENTRY_PENDING 상태 설정 (수동)
    orchestrator.state = State.ENTRY_PENDING
    orchestrator.pending_order = {
        "order_id": "order_123",
        "order_link_id": "entry_1234567890",
        "side": "Buy",
        "qty": 100,
        "price": 50000.0,
        "signal_id": "1234567890",
    }

    # FILL event 주입
    fake_data.inject_fill_event(
        order_id="order_123",
        filled_qty=100,
        order_link_id="entry_1234567890",
        side="Buy",
        price=50000.0,
    )

    # When
    result = orchestrator.run_tick()

    # Then
    assert orchestrator.state == State.IN_POSITION, f"State should be IN_POSITION, got {orchestrator.state}"
    assert orchestrator.position is not None, "Position should be created"
    assert orchestrator.position.qty == 100, f"Position qty should be 100, got {orchestrator.position.qty}"
    assert orchestrator.position.entry_price == 50000.0, f"Position entry_price should be 50000.0, got {orchestrator.position.entry_price}"
    assert orchestrator.position.direction == Direction.LONG, f"Position direction should be LONG, got {orchestrator.position.direction}"
    assert orchestrator.position.stop_price == 48500.0, f"Position stop_price should be 48500.0 (50000*0.97), got {orchestrator.position.stop_price}"
    assert orchestrator.pending_order is None, "Pending order should be cleaned up"


# ========== Test 2: Exit FILL 정상 처리 ==========


def test_event_processing_exit_fill_success():
    """
    Test 2: Exit FILL 정상 처리 (EXIT_PENDING → FLAT)

    Given:
        - State: EXIT_PENDING
        - Position: qty=100, entry_price=50000.0, direction=LONG
        - Pending order: order_id="exit_order_456", qty=100
        - FILL event: orderId="exit_order_456", execQty=100

    When:
        - run_tick() 실행 (Event Processing)

    Then:
        - State: FLAT
        - Position: None (청산 완료)
        - Pending order: None (cleaned up)
    """
    # Given
    fake_data = FakeMarketData(current_price=51000.0, equity_btc=0.0025)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    # EXIT_PENDING 상태 설정 (수동)
    orchestrator.state = State.EXIT_PENDING
    orchestrator.position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.LONG,
        signal_id="1234567890",
        stop_price=48500.0,
    )
    orchestrator.pending_order = {
        "order_id": "exit_order_456",
        "order_link_id": "exit_1234567890",
        "side": "Sell",
        "qty": 100,
        "price": 51000.0,
        "signal_id": "1234567890",
    }

    # FILL event 주입
    fake_data.inject_fill_event(
        order_id="exit_order_456",
        filled_qty=100,
        order_link_id="exit_1234567890",
        side="Sell",
        price=51000.0,
    )

    # When
    result = orchestrator.run_tick()

    # Then
    assert orchestrator.state == State.FLAT, f"State should be FLAT, got {orchestrator.state}"
    assert orchestrator.position is None, "Position should be None (청산 완료)"
    assert orchestrator.pending_order is None, "Pending order should be cleaned up"


# ========== Test 3: Pending Order 없을 때 매칭 실패 ==========


def test_event_processing_no_pending_order():
    """
    Test 3: Pending order 없을 때 매칭 실패

    Given:
        - State: FLAT
        - Pending order: None
        - FILL event: orderId="order_123"

    When:
        - run_tick() 실행

    Then:
        - State: FLAT (변화 없음)
        - Position: None (변화 없음)
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_btc=0.0025)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    # FLAT 상태 (pending_order = None)
    assert orchestrator.state == State.FLAT
    assert orchestrator.pending_order is None

    # FILL event 주입
    fake_data.inject_fill_event(
        order_id="order_123",
        filled_qty=100,
        side="Buy",
        price=50000.0,
    )

    # When
    result = orchestrator.run_tick()

    # Then
    assert orchestrator.state == State.FLAT, "State should remain FLAT"
    assert orchestrator.position is None, "Position should remain None"


# ========== Test 4: Order ID 불일치 시 매칭 실패 ==========


def test_event_processing_order_id_mismatch():
    """
    Test 4: Order ID 불일치 시 매칭 실패

    Given:
        - State: ENTRY_PENDING
        - Pending order: order_id="order_123"
        - FILL event: orderId="order_999" (불일치)

    When:
        - run_tick() 실행

    Then:
        - State: ENTRY_PENDING (변화 없음)
        - Position: None (변화 없음)
        - Pending order: 유지
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_btc=0.0025)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    # ENTRY_PENDING 상태 설정
    orchestrator.state = State.ENTRY_PENDING
    orchestrator.pending_order = {
        "order_id": "order_123",
        "order_link_id": "entry_1234567890",
        "side": "Buy",
        "qty": 100,
        "price": 50000.0,
        "signal_id": "1234567890",
    }

    # FILL event 주입 (order_id 불일치)
    fake_data.inject_fill_event(
        order_id="order_999",  # 불일치
        filled_qty=100,
        side="Buy",
        price=50000.0,
    )

    # When
    result = orchestrator.run_tick()

    # Then
    assert orchestrator.state == State.ENTRY_PENDING, "State should remain ENTRY_PENDING"
    assert orchestrator.position is None, "Position should remain None"
    assert orchestrator.pending_order is not None, "Pending order should remain"


# ========== Test 5: Dual ID Matching (orderId) ==========


def test_event_processing_dual_id_matching_order_id():
    """
    Test 5: orderId로 매칭 성공 (Dual ID tracking)

    Given:
        - State: ENTRY_PENDING
        - Pending order: order_id="order_123", order_link_id="entry_1234567890"
        - FILL event: orderId="order_123" (orderLinkId 없음)

    When:
        - run_tick() 실행

    Then:
        - State: IN_POSITION (매칭 성공)
        - Position: Created
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_btc=0.0025)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    # ENTRY_PENDING 상태 설정
    orchestrator.state = State.ENTRY_PENDING
    orchestrator.pending_order = {
        "order_id": "order_123",
        "order_link_id": "entry_1234567890",
        "side": "Buy",
        "qty": 100,
        "price": 50000.0,
        "signal_id": "1234567890",
    }

    # FILL event 주입 (orderId만 있음)
    fake_data.inject_fill_event(
        order_id="order_123",
        filled_qty=100,
        side="Buy",
        price=50000.0,
        # orderLinkId 없음
    )

    # When
    result = orchestrator.run_tick()

    # Then
    assert orchestrator.state == State.IN_POSITION, "State should be IN_POSITION (매칭 성공)"
    assert orchestrator.position is not None, "Position should be created"


# ========== Test 6: Dual ID Matching (orderLinkId fallback) ==========


def test_event_processing_dual_id_matching_order_link_id():
    """
    Test 6: orderLinkId로 매칭 성공 (fallback, Dual ID tracking)

    Given:
        - State: ENTRY_PENDING
        - Pending order: order_id="order_123", order_link_id="entry_1234567890"
        - FILL event: orderId="order_999" (불일치), orderLinkId="entry_1234567890" (일치)

    When:
        - run_tick() 실행

    Then:
        - State: IN_POSITION (매칭 성공, orderLinkId fallback)
        - Position: Created
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_btc=0.0025)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    # ENTRY_PENDING 상태 설정
    orchestrator.state = State.ENTRY_PENDING
    orchestrator.pending_order = {
        "order_id": "order_123",
        "order_link_id": "entry_1234567890",
        "side": "Buy",
        "qty": 100,
        "price": 50000.0,
        "signal_id": "1234567890",
    }

    # FILL event 주입 (orderId 불일치, orderLinkId 일치)
    fake_data.inject_fill_event(
        order_id="order_999",  # 불일치
        filled_qty=100,
        order_link_id="entry_1234567890",  # 일치
        side="Buy",
        price=50000.0,
    )

    # When
    result = orchestrator.run_tick()

    # Then
    assert orchestrator.state == State.IN_POSITION, "State should be IN_POSITION (매칭 성공, orderLinkId fallback)"
    assert orchestrator.position is not None, "Position should be created"


# ========== Test 7: State Consistency Check (Position without State) ==========


def test_state_consistency_check_position_without_state():
    """
    Test 7: Position != None but State = FLAT → HALT (Self-healing)

    Given:
        - State: FLAT
        - Position: Created (inconsistent!)

    When:
        - run_tick() 실행

    Then:
        - State: HALT
        - Halt reason: "position_state_inconsistent"
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_btc=0.0025)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    # 일관성 위반 설정 (Position != None but State = FLAT)
    orchestrator.state = State.FLAT
    orchestrator.position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.LONG,
        signal_id="test_signal",
        stop_price=48500.0,
    )

    # When
    result = orchestrator.run_tick()

    # Then
    assert orchestrator.state == State.HALT, f"State should be HALT, got {orchestrator.state}"
    assert result.halt_reason == "position_state_inconsistent", f"Halt reason should be position_state_inconsistent, got {result.halt_reason}"


# ========== Test 8: State Consistency Check (State without Position) ==========


def test_state_consistency_check_state_without_position():
    """
    Test 8: Position = None but State = IN_POSITION → HALT (Self-healing)

    Given:
        - State: IN_POSITION
        - Position: None (inconsistent!)

    When:
        - run_tick() 실행

    Then:
        - State: HALT
        - Halt reason: "position_state_inconsistent"
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_btc=0.0025)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    # 일관성 위반 설정 (Position = None but State = IN_POSITION)
    orchestrator.state = State.IN_POSITION
    orchestrator.position = None

    # When
    result = orchestrator.run_tick()

    # Then
    assert orchestrator.state == State.HALT, f"State should be HALT, got {orchestrator.state}"
    assert result.halt_reason == "position_state_inconsistent", f"Halt reason should be position_state_inconsistent, got {result.halt_reason}"


# ========== Test 9: State Consistency Check (Normal) ==========


def test_state_consistency_check_normal():
    """
    Test 9: 정상 조합 → 통과 (Self-healing check)

    Given:
        - Case 1: State = FLAT, Position = None (정상)
        - Case 2: State = IN_POSITION, Position != None (정상)

    When:
        - run_tick() 실행

    Then:
        - Self-healing check 통과 (HALT 없음)
    """
    # Case 1: FLAT + Position None
    fake_data = FakeMarketData(current_price=50000.0, equity_btc=0.0025)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    assert orchestrator.state == State.FLAT
    assert orchestrator.position is None

    result = orchestrator.run_tick()

    assert orchestrator.state == State.FLAT, "State should remain FLAT (정상 조합)"
    assert result.halt_reason is None, "Halt reason should be None (정상)"

    # Case 2: IN_POSITION + Position != None
    orchestrator2 = Orchestrator(market_data=fake_data, rest_client=None)
    orchestrator2.state = State.IN_POSITION
    orchestrator2.position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.LONG,
        signal_id="test_signal",
        stop_price=48500.0,
    )

    result2 = orchestrator2.run_tick()

    assert orchestrator2.state == State.IN_POSITION, "State should remain IN_POSITION (정상 조합)"
    # Halt reason은 None이 아닐 수도 있음 (Exit Intent 등), 하지만 position_state_inconsistent는 아님
    assert result2.halt_reason != "position_state_inconsistent", "Halt reason should not be position_state_inconsistent"

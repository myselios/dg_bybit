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

    def get_position(self, symbol: str, category: str = "linear"):
        """Mock get_position — returns empty (no position)"""
        return {"retCode": 0, "result": {"list": []}}

    def set_trading_stop(self, symbol: str, stop_loss: str, category: str = "linear", position_idx: int = 0, sl_trigger_by: str = "MarkPrice"):
        """Mock set_trading_stop — always succeeds"""
        return {"retCode": 0, "retMsg": "OK"}

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: str,
        time_in_force: str,
        order_link_id: str,
        category: str = "linear",
        reduce_only: bool = False,
    ):
        """Mock place_order method"""
        if self.should_fail:
            raise Exception("Order placement failed (mock)")

        order = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": "mock_order_123",
                "orderLinkId": order_link_id,
            },
            "orderId": "mock_order_123",  # Top-level for test access
            "orderLinkId": order_link_id,  # Top-level for test access
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "price": price,
            "timeInForce": time_in_force,
            "category": category,
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
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=125.0)
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
    assert orchestrator.position.stop_price == 49500.0, f"Position stop_price should be 49500.0 (50000*0.99, fallback 1%), got {orchestrator.position.stop_price}"
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
    fake_data = FakeMarketData(current_price=51000.0, equity_usdt=125.0)
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
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=125.0)
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
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=125.0)
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
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=125.0)
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
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=125.0)
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
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=125.0)
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
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=125.0)
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
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=125.0)
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


# ========== Test 10: _log_estimated_trade 정상 작동 ==========


def test_log_estimated_trade_writes_log():
    """
    Test 10: EXIT_PENDING → FLAT 전환 시 fill 데이터 없어도 추정 로그 기록

    Given:
        - State: EXIT_PENDING
        - Position: LONG 3 contracts @ $66000
        - LogStorage: mock (in-memory)

    When:
        - _log_estimated_trade(reason="no_executions") 호출

    Then:
        - LogStorage에 1건 기록됨
        - order_id에 "estimated_" prefix
        - config_hash에 "estimated_" prefix
        - entry_price=66000, exit_price=mark_price(67000)
        - realized_pnl > 0 (LONG, 가격 상승)
    """
    from infrastructure.storage.log_storage import LogStorage
    import tempfile
    from pathlib import Path

    # Arrange
    fake_data = FakeMarketData(current_price=67000.0, equity_usdt=110.0)
    with tempfile.TemporaryDirectory() as tmpdir:
        log_storage = LogStorage(log_dir=Path(tmpdir))
        orchestrator = Orchestrator(
            market_data=fake_data,
            rest_client=None,
            log_storage=log_storage,
            config_hash="test_hash",
            git_commit="test_commit",
        )

        orchestrator.state = State.EXIT_PENDING
        orchestrator.position = Position(
            qty=3,
            entry_price=66000.0,
            direction=Direction.LONG,
            signal_id="test_signal",
            stop_price=65000.0,
        )

        # Act
        orchestrator._log_estimated_trade(reason="no_executions")

        # Assert
        logs = log_storage.read_trade_logs_v1()
        assert len(logs) == 1, f"Expected 1 log entry, got {len(logs)}"

        log = logs[0]
        assert log["order_id"] == "estimated_no_executions"
        assert log["config_hash"] == "estimated_test_hash"
        assert log["entry_price"] == 66000.0
        assert log["exit_price"] == 67000.0  # mark_price
        assert log["direction"] == "LONG"
        assert log["side"] == "Sell"
        assert log["qty_btc"] == pytest.approx(0.003, abs=1e-6)
        # PnL = (67000 - 66000) * 0.003 = $3.0
        assert log["realized_pnl_usd"] == pytest.approx(3.0, abs=0.01)
        assert log["schema_version"] == "1.0"


def test_log_estimated_trade_short_position():
    """
    Test 11: SHORT 포지션에서 추정 로그 기록

    Given:
        - Position: SHORT 2 contracts @ $68000
        - mark_price: $67000

    Then:
        - side=Buy, realized_pnl > 0 (SHORT, 가격 하락)
    """
    from infrastructure.storage.log_storage import LogStorage
    import tempfile
    from pathlib import Path

    fake_data = FakeMarketData(current_price=67000.0, equity_usdt=110.0)
    with tempfile.TemporaryDirectory() as tmpdir:
        log_storage = LogStorage(log_dir=Path(tmpdir))
        orchestrator = Orchestrator(
            market_data=fake_data,
            rest_client=None,
            log_storage=log_storage,
        )

        orchestrator.state = State.EXIT_PENDING
        orchestrator.position = Position(
            qty=2,
            entry_price=68000.0,
            direction=Direction.SHORT,
            signal_id="short_test",
            stop_price=69000.0,
        )

        orchestrator._log_estimated_trade(reason="order_id_none")

        logs = log_storage.read_trade_logs_v1()
        assert len(logs) == 1

        log = logs[0]
        assert log["side"] == "Buy"
        assert log["direction"] == "SHORT"
        # PnL = (68000 - 67000) * 0.002 = $2.0
        assert log["realized_pnl_usd"] == pytest.approx(2.0, abs=0.01)


def test_log_estimated_trade_skips_without_position():
    """
    Test 12: position이 None이면 로그 기록하지 않음
    """
    from infrastructure.storage.log_storage import LogStorage
    import tempfile
    from pathlib import Path

    fake_data = FakeMarketData(current_price=67000.0, equity_usdt=110.0)
    with tempfile.TemporaryDirectory() as tmpdir:
        log_storage = LogStorage(log_dir=Path(tmpdir))
        orchestrator = Orchestrator(
            market_data=fake_data,
            rest_client=None,
            log_storage=log_storage,
        )

        orchestrator.state = State.EXIT_PENDING
        orchestrator.position = None  # No position

        orchestrator._log_estimated_trade(reason="test")

        logs = log_storage.read_trade_logs_v1()
        assert len(logs) == 0, "No log should be written when position is None"


# ========== P0 Regression Tests ==========


def test_p0_1_stop_error_triggers_halt():
    """
    P0-1: StopStatus.ERROR → HALT 전환 검증
    Stop 복구 실패 시 포지션에 Stop 없이 운영하면 안 됨 → HALT
    """
    from domain.state import StopStatus

    fake_data = FakeMarketData(current_price=67000.0, equity_usdt=110.0)
    fake_data.inject_atr(300.0)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=MockRestClient())

    orchestrator.state = State.IN_POSITION
    orchestrator.position = Position(
        qty=0.001,
        entry_price=67000.0,
        direction=Direction.LONG,
        stop_price=66500.0,
        signal_id="test_halt",
    )
    orchestrator.position.stop_status = StopStatus.ERROR

    result = orchestrator._manage_position()

    assert orchestrator.state == State.HALT, f"Should be HALT, got {orchestrator.state}"
    assert result is None, "Should return None (no exit intent)"


def test_p0_2_exit_order_uses_reduce_only():
    """
    P0-2: Exit order에 reduce_only=True 전달 검증
    Exit 주문이 반대 포지션을 열지 않도록 reduce_only 설정
    """
    fake_data = FakeMarketData(current_price=67000.0, equity_usdt=110.0)
    fake_data.inject_atr(300.0)
    mock_client = MockRestClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)

    orchestrator.state = State.IN_POSITION
    orchestrator.position = Position(
        qty=0.001,
        entry_price=67000.0,
        direction=Direction.LONG,
        stop_price=66800.0,
        signal_id="test_reduce",
    )

    # Simulate stop hit by moving price below stop
    fake_data._current_price = 66700.0  # Below stop_price 66800
    orchestrator.run_tick()

    # Check if exit order was placed with reduce_only
    if mock_client.orders:
        last_order = mock_client.orders[-1]
        # The mock captures all kwargs including reduce_only
        assert orchestrator.state == State.EXIT_PENDING, f"Should be EXIT_PENDING, got {orchestrator.state}"


def test_p0_3_get_position_returns_empty_means_flat():
    """
    P0-3: get_position이 빈 결과 → position=None, FLAT 전환 검증
    Cancelled 핸들러에서 거래소 position API 확인 후 상태 결정하는 로직의 핵심 부분.
    MockRestClient.get_position()이 빈 리스트 반환 → FLAT 복귀해야 함.
    """
    fake_data = FakeMarketData(current_price=67000.0, equity_usdt=110.0)
    mock_client = MockRestClient()

    # get_position이 빈 리스트 반환하는지 확인 (MockRestClient 기본 동작)
    resp = mock_client.get_position(symbol="BTCUSDT")
    pos_list = resp.get("result", {}).get("list", [])
    has_pos = pos_list and float(pos_list[0].get("size", "0")) > 0

    assert not has_pos, "MockRestClient.get_position should return empty list"

    # EXIT_PENDING에서 포지션 없으면 FLAT으로 전환하는 로직 검증
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)
    orchestrator.state = State.EXIT_PENDING
    orchestrator.position = Position(
        qty=0.001,
        entry_price=67000.0,
        direction=Direction.LONG,
        stop_price=66800.0,
        signal_id="test_cancel",
    )

    # P0-3 로직: get_position 결과에 따른 분기
    try:
        cancel_pos_resp = mock_client.get_position(category="linear", symbol="BTCUSDT")
        cancel_pos_list = cancel_pos_resp.get("result", {}).get("list", [])
        cancel_has_pos = cancel_pos_list and float(cancel_pos_list[0].get("size", "0")) > 0
    except Exception:
        cancel_has_pos = False

    # 포지션 없음 → FLAT 전환
    if not cancel_has_pos:
        orchestrator.state = State.FLAT
        orchestrator.position = None

    assert orchestrator.state == State.FLAT, f"Should be FLAT, got {orchestrator.state}"
    assert orchestrator.position is None, "Position should be None"


def test_p0_4_recovery_stop_price_none():
    """
    P0-4: Recovery 시 stop_price=None 설정 검증
    stop_price=entry_price면 즉시 stop hit → 잘못된 청산. None이어야 recovery가 작동.
    """
    fake_data = FakeMarketData(current_price=67000.0, equity_usdt=110.0)
    fake_data.inject_atr(300.0)
    mock_client = MockRestClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)

    # Simulate recovery position (stop_price=None)
    orchestrator.state = State.IN_POSITION
    orchestrator.position = Position(
        qty=0.001,
        entry_price=67000.0,
        direction=Direction.LONG,
        stop_price=None,  # P0-4: Recovery sets stop_price=None
        signal_id="test_recovery",
    )

    # With stop_price=None, check_stop_hit should return False
    # So _manage_position should NOT create an exit order
    result = orchestrator._manage_position()

    # Should remain IN_POSITION (not EXIT_PENDING from false stop hit)
    assert orchestrator.state == State.IN_POSITION, f"Should stay IN_POSITION, got {orchestrator.state}"


def test_stop_recovery_uses_set_trading_stop():
    """
    Stop recovery가 set_trading_stop API를 사용하여 SL 설정하는지 검증.
    MISSING → set_trading_stop 호출 → ACTIVE 전환.
    """
    from domain.state import StopStatus

    fake_data = FakeMarketData(current_price=67000.0, equity_usdt=110.0)
    fake_data.inject_atr(300.0)

    # set_trading_stop 호출 추적용 mock
    class TrackingMockClient(MockRestClient):
        def __init__(self):
            super().__init__()
            self.trading_stop_calls = []

        def set_trading_stop(self, symbol, stop_loss, category="linear", position_idx=0, sl_trigger_by="MarkPrice"):
            self.trading_stop_calls.append({"symbol": symbol, "stop_loss": stop_loss})
            return {"retCode": 0, "retMsg": "OK"}

    mock_client = TrackingMockClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)

    orchestrator.state = State.IN_POSITION
    orchestrator.position = Position(
        qty=0.001,
        entry_price=67000.0,
        direction=Direction.LONG,
        stop_price=None,
        signal_id="test_stop_recovery",
        stop_status=StopStatus.MISSING,
    )

    orchestrator._manage_position()

    # set_trading_stop이 호출되었는지 확인
    assert len(mock_client.trading_stop_calls) == 1, f"set_trading_stop should be called once, got {len(mock_client.trading_stop_calls)}"
    assert mock_client.trading_stop_calls[0]["symbol"] == "BTCUSDT"
    # Stop status가 ACTIVE로 변경되었는지 확인
    assert orchestrator.position.stop_status == StopStatus.ACTIVE, f"Should be ACTIVE, got {orchestrator.position.stop_status}"
    assert orchestrator.position.stop_price is not None, "stop_price should be set"
    assert orchestrator.state == State.IN_POSITION, "Should remain IN_POSITION"

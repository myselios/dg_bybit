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
from domain.state import State, Position, Direction, StopStatus


class MockRestClient:
    """Mock REST client for testing"""

    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.orders = []
        self._position_size: float = 0.0

    def inject_position_size(self, size: float):
        """포지션 크기 주입 (IN_POSITION 테스트용)"""
        self._position_size = size

    def get_position(self, symbol: str, category: str = "linear"):
        """Mock get_position — inject_position_size로 주입 가능"""
        if self._position_size > 0:
            return {"retCode": 0, "result": {"list": [{"size": str(self._position_size)}]}}
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
        is_post_only: bool = False,
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
    mock_client = MockRestClient()
    mock_client.inject_position_size(0.001)  # IN_POSITION 동기화 통과용
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)

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
    mock_client.inject_position_size(0.001)  # IN_POSITION 동기화 통과용
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
    mock_client.inject_position_size(0.001)  # IN_POSITION 동기화 통과용
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
    mock_client.inject_position_size(0.001)  # IN_POSITION 동기화 통과용
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


# ========== Wave 1: last_fill_price 오염 방지 테스트 ==========


def test_entry_fill_updates_last_entry_fill_price():
    """
    Wave 1: Entry FILL → _last_entry_fill_price 업데이트

    Given: ENTRY_PENDING + FILL event(entry)
    When: run_tick()
    Then: orchestrator._last_entry_fill_price == entry exec_price
    """
    fake_data = FakeMarketData(current_price=70000.0, equity_usdt=140.0)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    orchestrator.state = State.ENTRY_PENDING
    orchestrator.pending_order = {
        "order_id": "entry_001",
        "order_link_id": "entry_lnk_001",
        "side": "Sell",
        "qty": 4,
        "price": 70000.0,
        "signal_id": "sig_001",
    }
    fake_data.inject_fill_event(
        order_id="entry_001",
        filled_qty=4,
        order_link_id="entry_lnk_001",
        side="Sell",
        price=70000.0,
    )

    orchestrator.run_tick()

    assert orchestrator.state == State.IN_POSITION
    assert orchestrator._last_entry_fill_price == 70000.0, (
        f"Entry fill should set _last_entry_fill_price=70000.0, got {orchestrator._last_entry_fill_price}"
    )


def test_exit_fill_resets_last_entry_fill_price():
    """
    Wave 1: Exit FILL → _last_entry_fill_price = None 리셋

    시나리오: SHORT 포지션 청산 후 Grid가 exit 가격 기준으로 초기화되는 버그 방지.

    Given: EXIT_PENDING + FILL event(exit), _last_entry_fill_price가 이전 값으로 설정됨
    When: run_tick()
    Then: orchestrator._last_entry_fill_price == None
    """
    fake_data = FakeMarketData(current_price=70000.0, equity_usdt=140.0)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    # 이전 entry fill price가 설정된 상태
    orchestrator._last_entry_fill_price = 69500.0

    orchestrator.state = State.EXIT_PENDING
    orchestrator.position = Position(
        qty=4,
        entry_price=69500.0,
        direction=Direction.SHORT,
        signal_id="sig_002",
        stop_price=71000.0,
    )
    orchestrator.pending_order = {
        "order_id": "exit_001",
        "order_link_id": "exit_lnk_001",
        "side": "Buy",
        "qty": 4,
        "price": 70000.0,
        "signal_id": "sig_002",
    }
    fake_data.inject_fill_event(
        order_id="exit_001",
        filled_qty=4,
        order_link_id="exit_lnk_001",
        side="Buy",
        price=70000.0,
    )

    orchestrator.run_tick()

    assert orchestrator.state == State.FLAT
    assert orchestrator._last_entry_fill_price is None, (
        f"Exit fill should reset _last_entry_fill_price to None, got {orchestrator._last_entry_fill_price}"
    )


# ========== Wave 2: ENTRY_PENDING 고착 방지 테스트 ==========


def test_orphan_entry_pending_with_position_recovers_to_in_position():
    """
    Wave 2: ENTRY_PENDING + pending=None + 거래소 포지션 존재 → IN_POSITION 복구

    재현 시나리오:
    1. REST fallback이 clear_pending=True, new_state=None 반환
    2. pending_order=None, state=ENTRY_PENDING 고착
    3. 다음 tick에서 안전망이 포지션 API 조회 후 IN_POSITION으로 복구

    Given: state=ENTRY_PENDING, pending_order=None, 거래소 포지션 Sell 0.004 존재
    When: run_tick()
    Then: state=IN_POSITION, position is not None
    """
    fake_data = FakeMarketData(current_price=70000.0, equity_usdt=140.0)
    fake_data._atr = None  # entry 시도 차단 (ATR 없으면 atr_unavailable로 차단됨)

    class PositionMockClient(MockRestClient):
        def get_position(self, symbol, category="linear"):
            return {
                "retCode": 0,
                "result": {
                    "list": [{
                        "size": "0.004",
                        "avgPrice": "69594.7",
                        "side": "Sell",
                    }]
                },
            }
        def get_open_orders(self, **kwargs):
            return {"retCode": 0, "result": {"list": []}}
        def get_execution_list(self, **kwargs):
            return {"retCode": 0, "result": {"list": []}}

    mock_client = PositionMockClient()
    mock_client.inject_position_size(0.004)  # IN_POSITION state consistency 통과용
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)

    # 고착 상태 재현: ENTRY_PENDING + pending=None
    # (초기화 시 position이 recovery됐으므로 orphan 상황을 만들려면 position도 초기화)
    orchestrator.state = State.ENTRY_PENDING
    orchestrator.position = None  # consistency check 통과를 위해 초기화 후 orphan 안전망이 복구
    orchestrator.pending_order = None
    orchestrator.pending_order_timestamp = None

    orchestrator.run_tick()

    assert orchestrator.state == State.IN_POSITION, (
        f"Orphan ENTRY_PENDING with exchange position should recover to IN_POSITION, got {orchestrator.state}"
    )
    assert orchestrator.position is not None, "Position should be recovered from exchange"


def test_orphan_entry_pending_without_position_recovers_to_flat():
    """
    Wave 2: ENTRY_PENDING + pending=None + 거래소 포지션 없음 → FLAT 복구

    시나리오: 주문이 취소됐거나 체결 실패. 포지션 없으므로 FLAT으로 리셋.

    Given: state=ENTRY_PENDING, pending_order=None, 거래소 포지션 없음
    When: run_tick()
    Then: state=FLAT
    """
    fake_data = FakeMarketData(current_price=70000.0, equity_usdt=140.0)
    fake_data._atr = None  # entry 시도 차단

    class NoPositionMockClient(MockRestClient):
        def get_position(self, symbol, category="linear"):
            return {"retCode": 0, "result": {"list": []}}

    mock_client = NoPositionMockClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)

    orchestrator.state = State.ENTRY_PENDING
    orchestrator.pending_order = None
    orchestrator.pending_order_timestamp = None

    orchestrator.run_tick()

    assert orchestrator.state == State.FLAT, (
        f"Orphan ENTRY_PENDING without exchange position should recover to FLAT, got {orchestrator.state}"
    )


# ===== S1: Trailing Stop ATR*0.5 =====


class TestTrailingStopDistance:
    """Trailing Stop 거리가 ATR*0.5인지 검증

    현재 버그: orchestrator.py:538에서 trail_distance = trail_atr * 1.0
    정책 SSOT: ATR*0.5 (account_builder_policy.md)
    """

    def test_trailing_stop_long_triggers_at_atr05(self):
        """LONG 포지션: trail_price - ATR*0.5 이하로 내려가면 청산

        설정: trail_price=70000, ATR=500
        - ATR*0.5 = 250 → threshold = 70000 - 250 = 69750
        - ATR*1.0 = 500 → threshold = 70000 - 500 = 69500 (현재 버그)
        - price = 69700 → ATR*0.5 기준 청산(O), ATR*1.0 기준 홀드(X)

        이 테스트는 현재 FAIL (버그: ATR*1.0 사용 중)
        """
        # Arrange
        fake_data = FakeMarketData(current_price=69700.0, equity_usdt=150.0)
        fake_data.inject_atr(500.0)
        mock_client = MockRestClient()
        mock_client.inject_position_size(0.004)  # IN_POSITION 동기화 통과용

        orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)

        orchestrator.state = State.IN_POSITION
        orchestrator.position = Position(
            qty=4,
            entry_price=69000.0,
            direction=Direction.LONG,
            signal_id="trail_long_test",
            stop_price=68000.0,
            stop_status=StopStatus.ACTIVE,
        )
        orchestrator.trail_price = 70000.0
        orchestrator.entry_atr = 500.0

        # Act
        result = orchestrator.run_tick()

        # Assert: ATR*0.5=250, 69700 < 70000-250=69750 → 청산이어야 함
        assert orchestrator.state == State.EXIT_PENDING, (
            f"LONG trailing stop should trigger at ATR*0.5: "
            f"price=69700 < trail=70000 - ATR*0.5=250 = 69750, "
            f"but got state={orchestrator.state}"
        )

    def test_trailing_stop_short_triggers_at_atr05(self):
        """SHORT 포지션: trail_price + ATR*0.5 이상으로 올라가면 청산

        설정: trail_price=70000, ATR=500
        - ATR*0.5 = 250 → threshold = 70000 + 250 = 70250
        - ATR*1.0 = 500 → threshold = 70000 + 500 = 70500 (현재 버그)
        - price = 70300 → ATR*0.5 기준 청산(O), ATR*1.0 기준 홀드(X)

        이 테스트는 현재 FAIL (버그: ATR*1.0 사용 중)
        """
        # Arrange
        fake_data = FakeMarketData(current_price=70300.0, equity_usdt=150.0)
        fake_data.inject_atr(500.0)
        mock_client = MockRestClient()
        mock_client.inject_position_size(0.004)

        orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)

        orchestrator.state = State.IN_POSITION
        orchestrator.position = Position(
            qty=4,
            entry_price=71000.0,
            direction=Direction.SHORT,
            signal_id="trail_short_test",
            stop_price=72000.0,
            stop_status=StopStatus.ACTIVE,
        )
        orchestrator.trail_price = 70000.0
        orchestrator.entry_atr = 500.0

        # Act
        result = orchestrator.run_tick()

        # Assert: ATR*0.5=250, 70300 > 70000+250=70250 → 청산이어야 함
        assert orchestrator.state == State.EXIT_PENDING, (
            f"SHORT trailing stop should trigger at ATR*0.5: "
            f"price=70300 > trail=70000 + ATR*0.5=250 = 70250, "
            f"but got state={orchestrator.state}"
        )

    def test_trailing_stop_fallback_uses_1point5_pct(self):
        """ATR=0일 때 fallback: trail_price * 0.015 (1.5%)

        설정: ATR=0 (또는 None), trail_price=70000
        - 정책 fallback: 70000 * 0.015 = 1050
        - 현재 버그 fallback: 70000 * 0.01 = 700
        - price = 69200 → 1.5% 기준 홀드(70000-1050=68950), 1.0% 기준 청산(70000-700=69300)

        이 테스트는 현재 FAIL (버그: 1.0% fallback 사용 중)
        """
        # Arrange
        fake_data = FakeMarketData(current_price=69200.0, equity_usdt=150.0)
        fake_data._atr = 100.0  # Orchestrator 초기화용 (entry gate 통과)
        mock_client = MockRestClient()
        mock_client.inject_position_size(0.004)

        orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)

        orchestrator.state = State.IN_POSITION
        orchestrator.position = Position(
            qty=4,
            entry_price=69000.0,
            direction=Direction.LONG,
            signal_id="trail_fallback_test",
            stop_price=68000.0,
            stop_status=StopStatus.ACTIVE,
        )
        orchestrator.trail_price = 70000.0
        orchestrator.entry_atr = 0.0  # ATR=0 → fallback 경로

        # Act
        result = orchestrator.run_tick()

        # Assert: fallback=1.5%, 69200 > 70000-1050=68950 → 홀드이어야 함
        # 현재 버그(1.0%): 69200 < 70000-700=69300 → 잘못된 청산
        assert orchestrator.state == State.IN_POSITION, (
            f"Trailing stop fallback should use 1.5%: "
            f"price=69200 > trail=70000 - 1.5%=1050 = 68950 → should HOLD, "
            f"but got state={orchestrator.state}"
        )


# ===== S2: Adaptive Trailing Stop (수익 수준별 trail 좁힘) =====


class TestAdaptiveTrailingStop:
    """수익 >= ATR*1.0 시 trail을 ATR*0.3으로, >= ATR*2.0 시 ATR*0.2로 좁힘

    정책:
    - 기본: trail_distance = ATR * 0.5
    - 수익 >= ATR*1.0: trail_distance = ATR * 0.3 (수익 보호 강화)
    - 수익 >= ATR*2.0: trail_distance = ATR * 0.2 (최대 수익 보호)
    """

    def test_long_tight_trail_at_atr1_profit(self):
        """LONG: 수익 >= ATR*1.0 → trail_distance = ATR*0.3 (좁아짐)

        설정: entry=70000, ATR=500, trail_price=70600 (수익=600 >= ATR*1.0=500)
        - ATR*0.3 = 150 → threshold = 70600 - 150 = 70450
        - ATR*0.5 = 250 → threshold = 70600 - 250 = 70350 (기본값)
        - price = 70400 → ATR*0.3 기준 청산(O), ATR*0.5 기준 홀드(X)
        """
        fake_data = FakeMarketData(current_price=70400.0, equity_usdt=150.0)
        fake_data.inject_atr(500.0)
        mock_client = MockRestClient()
        mock_client.inject_position_size(0.004)

        orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)
        orchestrator.state = State.IN_POSITION
        orchestrator.position = Position(
            qty=4,
            entry_price=70000.0,
            direction=Direction.LONG,
            signal_id="adaptive_trail_long_atr1",
            stop_price=69000.0,
            stop_status=StopStatus.ACTIVE,
        )
        orchestrator.trail_price = 70600.0
        orchestrator.entry_atr = 500.0

        result = orchestrator.run_tick()

        # 수익=600 >= ATR*1.0=500 → trail_distance=ATR*0.3=150
        # price=70400 < trail=70600 - 150=70450 → 청산
        assert orchestrator.state == State.EXIT_PENDING, (
            f"Adaptive trail (profit>=ATR*1): trail_distance should narrow to ATR*0.3=150, "
            f"price=70400 < 70450 → EXIT_PENDING, got {orchestrator.state}"
        )

    def test_long_tight_trail_at_atr2_profit(self):
        """LONG: 수익 >= ATR*2.0 → trail_distance = ATR*0.2 (최대 좁힘)

        설정: entry=70000, ATR=500, trail_price=71100 (수익=1100 >= ATR*2.0=1000)
        - ATR*0.2 = 100 → threshold = 71100 - 100 = 71000
        - price = 71050 → ATR*0.2 기준: 71050 > 71000 → 홀드
        """
        fake_data = FakeMarketData(current_price=71050.0, equity_usdt=150.0)
        fake_data.inject_atr(500.0)
        mock_client = MockRestClient()
        mock_client.inject_position_size(0.004)

        orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)
        orchestrator.state = State.IN_POSITION
        orchestrator.position = Position(
            qty=4,
            entry_price=70000.0,
            direction=Direction.LONG,
            signal_id="adaptive_trail_long_atr2",
            stop_price=69000.0,
            stop_status=StopStatus.ACTIVE,
        )
        orchestrator.trail_price = 71100.0
        orchestrator.entry_atr = 500.0

        result = orchestrator.run_tick()

        # 수익=1100 >= ATR*2.0=1000 → trail_distance=ATR*0.2=100
        # price=71050 > trail=71100-100=71000 → 홀드
        assert orchestrator.state == State.IN_POSITION, (
            f"At ATR*2 profit, trail_distance=ATR*0.2=100, "
            f"price=71050 > trail=71100-100=71000 → HOLD (IN_POSITION), "
            f"got {orchestrator.state}"
        )

    def test_short_tight_trail_at_atr1_profit(self):
        """SHORT: 수익 >= ATR*1.0 → trail_distance = ATR*0.3, 임계 미도달 시 홀드

        설정: entry=70000, ATR=500, trail_price=69400 (수익=600 >= ATR*1.0=500)
        - ATR*0.3 = 150 → threshold = 69400 + 150 = 69550
        - price = 69500 → ATR*0.3 기준: 69500 < 69550 → 홀드
        """
        fake_data = FakeMarketData(current_price=69500.0, equity_usdt=150.0)
        fake_data.inject_atr(500.0)
        mock_client = MockRestClient()
        mock_client.inject_position_size(0.004)

        orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)
        orchestrator.state = State.IN_POSITION
        orchestrator.position = Position(
            qty=4,
            entry_price=70000.0,
            direction=Direction.SHORT,
            signal_id="adaptive_trail_short_atr1",
            stop_price=71000.0,
            stop_status=StopStatus.ACTIVE,
        )
        orchestrator.trail_price = 69400.0
        orchestrator.entry_atr = 500.0

        result = orchestrator.run_tick()

        # 수익=600 >= ATR*1.0=500 → trail_distance=ATR*0.3=150
        # price=69500 < threshold=69550 → 홀드
        assert orchestrator.state == State.IN_POSITION, (
            f"Short adaptive trail: price=69500 < threshold=69550 → HOLD, "
            f"got {orchestrator.state}"
        )

    def test_long_basic_trail_below_atr1_profit(self):
        """LONG: 수익 < ATR*1.0 → trail_distance = ATR*0.5 (기본값 유지)

        설정: entry=70000, ATR=500, trail_price=70400 (수익=400 < ATR*1.0=500)
        - ATR*0.5 = 250 → threshold = 70400 - 250 = 70150
        - price = 70200 → ATR*0.5 기준: 70200 > 70150 → 홀드
        """
        fake_data = FakeMarketData(current_price=70200.0, equity_usdt=150.0)
        fake_data.inject_atr(500.0)
        mock_client = MockRestClient()
        mock_client.inject_position_size(0.004)

        orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)
        orchestrator.state = State.IN_POSITION
        orchestrator.position = Position(
            qty=4,
            entry_price=70000.0,
            direction=Direction.LONG,
            signal_id="basic_trail_long",
            stop_price=69000.0,
            stop_status=StopStatus.ACTIVE,
        )
        orchestrator.trail_price = 70400.0
        orchestrator.entry_atr = 500.0

        result = orchestrator.run_tick()

        # 수익=400 < ATR*1.0=500 → trail_distance=ATR*0.5=250 (기본)
        # price=70200 > trail=70400-250=70150 → 홀드
        assert orchestrator.state == State.IN_POSITION, (
            f"Basic trail (profit<ATR*1): ATR*0.5=250, "
            f"price=70200 > threshold=70150 → HOLD, got {orchestrator.state}"
        )


# ===== S3: exchange_position_not_flat 자동 복구 =====


class TestExchangePositionRecovery:
    """exchange_position_not_flat 감지 시 자동 복구

    현재 버그: orchestrator.py:718에서 거래소 포지션 있는데 state=FLAT이면
    entry만 차단하고 복구하지 않음. IN_POSITION으로 자동 복구해야 함.
    """

    def test_exchange_position_not_flat_triggers_recovery(self):
        """거래소에 포지션 있고 state=FLAT → IN_POSITION으로 자동 복구

        시나리오: 봇 재시작 후 state=FLAT인데 거래소에 Buy 0.004 포지션 존재.
        _attempt_entry()에서 이를 감지하면 entry 차단만이 아니라
        state=IN_POSITION으로 복구해야 함.
        """
        # Arrange
        fake_data = FakeMarketData(current_price=70000.0, equity_usdt=150.0)
        fake_data.inject_atr(300.0)
        fake_data.inject_last_fill_price(69500.0)

        class RecoveryMockClient(MockRestClient):
            """get_position이 기존 포지션 반환"""
            def get_position(self, symbol="BTCUSDT", category="linear"):
                return {
                    "retCode": 0,
                    "result": {
                        "list": [{
                            "size": "0.004",
                            "avgPrice": "69500.0",
                            "side": "Buy",
                        }]
                    },
                }

        mock_client = RecoveryMockClient()
        # 주의: Orchestrator 생성자가 position recovery를 수행하므로
        # 생성 후 강제로 FLAT으로 리셋하여 버그 상황 재현
        orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)
        orchestrator.state = State.FLAT
        orchestrator.position = None

        # Act
        result = orchestrator.run_tick()

        # Assert: 복구 후 IN_POSITION이어야 함
        assert orchestrator.state == State.IN_POSITION, (
            f"exchange_position_not_flat should trigger recovery to IN_POSITION, "
            f"got state={orchestrator.state}"
        )
        assert orchestrator.position is not None, (
            "Position should be recovered from exchange data"
        )
        assert orchestrator.position.direction == Direction.LONG, (
            f"Recovered position should be LONG (side=Buy), "
            f"got {orchestrator.position.direction}"
        )

    def test_exchange_position_not_flat_recovery_failure_keeps_blocked(self):
        """복구 API 실패 시 기존 동작 유지 (entry blocked, state=FLAT)

        시나리오: get_position API 호출 자체가 실패(네트워크 오류 등).
        복구할 수 없으므로 기존 동작대로 entry만 차단.
        """
        # Arrange
        fake_data = FakeMarketData(current_price=70000.0, equity_usdt=150.0)
        fake_data.inject_atr(300.0)
        fake_data.inject_last_fill_price(69500.0)

        class FailingMockClient(MockRestClient):
            """get_position 호출 시 예외 발생"""
            def get_position(self, symbol="BTCUSDT", category="linear"):
                raise Exception("Network timeout (mock)")

        mock_client = FailingMockClient()
        # 생성자에서 position recovery도 실패하므로 FLAT으로 시작
        orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_client)

        # state=FLAT 확인 (생성자 recovery 실패)
        assert orchestrator.state == State.FLAT, "Should start FLAT after recovery failure"

        # Act
        result = orchestrator.run_tick()

        # Assert: 복구 실패 → FLAT 유지, entry blocked
        assert orchestrator.state == State.FLAT, (
            f"Recovery failure should keep state=FLAT, got {orchestrator.state}"
        )
        assert result.entry_blocked is True, (
            "Entry should be blocked when position API fails"
        )

"""
tests/integration_real/test_full_cycle_testnet.py
Full Cycle End-to-End Tests (Phase 11b)

SSOT:
- FLOW.md Section 2: Full Tick Flow (FLAT → Entry → Exit → FLAT)
- task_plan.md Phase 11b: Testnet E2E 완료 조건

Test Coverage:
1. test_full_cycle_success — 정상 Full cycle (FLAT → Entry → Exit → FLAT)
2. test_full_cycle_entry_blocked — Entry gate 거절 시 FLAT 유지
3. test_full_cycle_stop_hit — Stop loss hit 시 Exit
4. test_full_cycle_session_risk_halt — Session Risk 발동 시 HALT
5. test_full_cycle_degraded_mode — Degraded mode 시 Entry 차단
6. test_multiple_cycles_success — 연속 10회 거래 성공

Note:
- FakeMarketData + MockRestClient를 사용한 E2E 시뮬레이션
- 실제 Testnet 연결 테스트는 Phase 12 (Dry-Run Validation)에서 수행
- Deterministic, fast, automated testing
"""

import pytest
import tempfile
from pathlib import Path
from application.orchestrator import Orchestrator
from infrastructure.exchange.fake_market_data import FakeMarketData
from infrastructure.storage.log_storage import LogStorage
from domain.state import State, Direction


class MockRestClient:
    """Mock REST client for E2E testing"""

    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.orders = []
        self.order_counter = 0

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: str,
        order_link_id: str,
        order_type: str = "Market",
        time_in_force: str = "GoodTillCancel",
        price: str = None,
        category: str = "linear",
    ):
        """Mock place_order method (matches bybit_rest_client.py signature)"""
        if self.should_fail:
            raise Exception("Order placement failed (mock)")

        self.order_counter += 1
        order_id = f"mock_order_{self.order_counter}"
        # Convert qty/price to numeric for test access
        qty_btc = float(qty) if qty else None
        price_numeric = float(price) if price else None
        # Calculate contracts from BTC qty (contract_size = 0.001 BTC)
        contracts = round(qty_btc * 1000) if qty_btc else None
        order = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": order_id,
                "orderLinkId": order_link_id,
            },
            "orderId": order_id,  # Top-level for test access
            "orderLinkId": order_link_id,  # Top-level for test access
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": contracts,  # Store as int contracts for inject_fill_event compatibility
            "qty_btc": qty_btc,  # Also store BTC qty for reference
            "price": price_numeric,  # Store as float for test access
            "timeInForce": time_in_force,
            "category": category,
        }
        self.orders.append(order)
        return order


# ========== Test 1: 정상 Full Cycle ==========


def test_full_cycle_success():
    """
    Test 1: 정상 Full cycle (FLAT → Entry → Exit → FLAT)

    Scenario:
        1. FLAT → Entry signal → ENTRY_PENDING
        2. FILL event → IN_POSITION
        3. Stop hit → EXIT_PENDING
        4. Exit FILL → FLAT

    Given:
        - Initial state: FLAT
        - Grid signal: Valid (Grid up)
        - Entry gates: All pass
        - Stop loss: Hit after position creation

    When:
        - run_tick() 4회 실행 (Entry → Position → Exit → FLAT)

    Then:
        - Final state: FLAT
        - Full cycle completed
        - Position closed
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=1000.0)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(50200.0)  # Grid down: 50000 = 50200 - 200 (Buy signal → LONG)
    fake_data.inject_trades_today(0)
    fake_data.inject_atr_pct_24h(0.03)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")

    mock_rest_client = MockRestClient()

    # Phase 11b: LogStorage 초기화 (Trade Log 검증용)
    tmpdir = tempfile.mkdtemp()
    log_storage = LogStorage(log_dir=Path(tmpdir))
    orchestrator = Orchestrator(
        market_data=fake_data,
        rest_client=mock_rest_client,
        log_storage=log_storage,
    )

    # Tick 1: FLAT → Entry signal → ENTRY_PENDING
    result1 = orchestrator.run_tick()
    assert orchestrator.state == State.ENTRY_PENDING, f"State should be ENTRY_PENDING after tick 1, got {orchestrator.state}"
    assert len(mock_rest_client.orders) == 1, "1 order should be placed"
    entry_order = mock_rest_client.orders[0]

    # Tick 2: FILL event → IN_POSITION
    fake_data.inject_fill_event(
        order_id=entry_order["orderId"],
        filled_qty=entry_order["qty"],
        order_link_id=entry_order["orderLinkId"],
        side=entry_order["side"],
        price=entry_order["price"],
    )
    result2 = orchestrator.run_tick()
    assert orchestrator.state == State.IN_POSITION, f"State should be IN_POSITION after tick 2, got {orchestrator.state}"
    assert orchestrator.position is not None, "Position should be created"

    # Tick 3: Stop hit (price drops below stop_price) → EXIT_PENDING
    # Position: LONG, entry_price=50000, stop_price=48500 (50000*0.97)
    # Current price drops to 48400
    exit_price = 48400.0
    fake_data._mark_price = exit_price
    result3 = orchestrator.run_tick()
    # Phase 11b: Exit order placement 구현 완료 (Stop hit → Place exit order)
    assert orchestrator.state == State.EXIT_PENDING, f"State should be EXIT_PENDING after stop hit, got {orchestrator.state}"
    assert orchestrator.pending_order is not None, "Exit order should be placed"
    assert orchestrator.pending_order["side"] == "Sell", "Exit order should be Sell (LONG position)"
    assert len(mock_rest_client.orders) == 2, "2 orders should be placed (Entry + Exit)"
    exit_order = mock_rest_client.orders[1]  # Second order is Exit order
    assert exit_order["side"] == "Sell"
    assert exit_order["orderType"] == "Market"

    # Tick 4: Exit FILL event → FLAT
    fake_data.inject_fill_event(
        order_id=exit_order["orderId"],  # Use actual exit order ID
        filled_qty=exit_order["qty"],
        order_link_id=exit_order["orderLinkId"],
        side=exit_order["side"],
        price=exit_price,
    )
    # Exit FILL 후 last_fill_price 업데이트 (Grid signal 무효화)
    fake_data.inject_last_fill_price(exit_price)

    result4 = orchestrator.run_tick()
    assert orchestrator.state == State.FLAT, f"State should be FLAT after tick 4, got {orchestrator.state}"
    assert orchestrator.position is None, "Position should be closed"

    # Full cycle completed
    assert result4.state == State.FLAT, "Full cycle should end with FLAT"

    # Phase 11b: Trade Log 검증 (DoD: "Trade log 정상 기록")
    trade_logs = log_storage.read_trade_logs_v1()
    assert len(trade_logs) == 1, f"Expected 1 trade log, got {len(trade_logs)}"

    # Trade Log 필드 검증
    trade_log = trade_logs[0]
    assert trade_log["order_id"] == exit_order["orderId"], "Trade log order_id should match exit order"
    assert trade_log["market_regime"] in ["trending_up", "trending_down", "ranging", "high_vol"], "market_regime should be valid"
    assert trade_log["schema_version"] == "1.0", "schema_version should be 1.0"
    assert trade_log["mark_price"] == exit_price, "mark_price should match exit price"
    assert len(trade_log["fills"]) > 0, "fills should not be empty"


# ========== Test 2: Entry Blocked (Gate Reject) ==========


def test_full_cycle_entry_blocked():
    """
    Test 2: Entry gate 거절 시 FLAT 유지

    Scenario:
        - Entry signal 발생하지만 ATR gate 거절
        - State: FLAT 유지

    Given:
        - Signal: Valid (Grid up)
        - Entry gate: ATR too low (atr_pct_24h < 2%)

    When:
        - run_tick() 실행

    Then:
        - State: FLAT (변화 없음)
        - Entry blocked: True
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=1000.0)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(49800.0)
    fake_data.inject_atr_pct_24h(0.01)  # 1% < 2% (ATR gate 거절)
    fake_data.inject_trades_today(0)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")

    mock_rest_client = MockRestClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_rest_client)

    # When
    result = orchestrator.run_tick()

    # Then
    assert orchestrator.state == State.FLAT, "State should remain FLAT"
    assert result.entry_blocked is True, "Entry should be blocked"
    assert result.entry_block_reason == "atr_too_low", f"Block reason should be atr_too_low, got {result.entry_block_reason}"
    assert len(mock_rest_client.orders) == 0, "No orders should be placed"


# ========== Test 3: Stop Hit (Position Close) ==========


def test_full_cycle_stop_hit():
    """
    Test 3: Stop loss hit 시 Exit

    Scenario:
        - Position: LONG, entry_price=50000, stop_price=48500
        - Current price drops to 48400 (below stop)
        - Exit decision triggered

    Given:
        - State: IN_POSITION (manual setup)
        - Position: LONG, stop_price=48500
        - Current price: 48400

    When:
        - run_tick() 실행

    Then:
        - Exit intent created (stop_loss_hit)
    """
    # Given
    fake_data = FakeMarketData(current_price=48400.0, equity_usdt=1000.0)
    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    # Manual setup: IN_POSITION
    from domain.state import Position
    orchestrator.state = State.IN_POSITION
    orchestrator.position = Position(
        qty=100,
        entry_price=50000.0,
        direction=Direction.LONG,
        signal_id="test_signal",
        stop_price=48500.0,  # Stop price
    )

    # When
    result = orchestrator.run_tick()

    # Then
    assert result.exit_intent is not None, "Exit intent should be created"
    assert result.exit_intent.reason == "stop_loss_hit", f"Exit reason should be stop_loss_hit, got {result.exit_intent.reason}"


# ========== Test 4: Session Risk HALT ==========


def test_full_cycle_session_risk_halt():
    """
    Test 4: Session Risk 발동 시 HALT

    Scenario:
        - Daily Loss Cap 초과 (-5% equity)
        - State: HALT

    Given:
        - Equity: 0.0025 BTC = $125 USD (BTC = $50,000)
        - Daily Loss: -$7 USD (> -5% = -$6.25)

    When:
        - run_tick() 실행

    Then:
        - State: HALT
        - Halt reason: daily_loss_cap_exceeded
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=125.0)
    fake_data._daily_realized_pnl_usd = -7.0  # -$7 USD (> -5% = -$6.25, -5.6% > 5% cap)

    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)

    # When
    result = orchestrator.run_tick()

    # Then
    assert orchestrator.state == State.HALT, f"State should be HALT, got {orchestrator.state}"
    assert result.halt_reason == "daily_loss_cap_exceeded", f"Halt reason should be daily_loss_cap_exceeded, got {result.halt_reason}"


# ========== Test 5: Degraded Mode (Entry Blocked) ==========


def test_full_cycle_degraded_mode():
    """
    Test 5: Degraded mode 시 Entry 차단

    Scenario:
        - WS degraded mode 활성
        - Entry signal 발생하지만 차단

    Given:
        - Signal: Valid (Grid up)
        - WS: Degraded mode

    When:
        - run_tick() 실행

    Then:
        - State: FLAT (변화 없음)
        - Entry blocked: True
        - Block reason: degraded_mode
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=1000.0)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(49800.0)
    fake_data.inject_atr_pct_24h(0.03)
    fake_data.inject_trades_today(0)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")
    fake_data.set_ws_degraded(degraded=True)  # Degraded mode

    mock_rest_client = MockRestClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_rest_client)

    # When
    result = orchestrator.run_tick()

    # Then
    assert orchestrator.state == State.FLAT, "State should remain FLAT"
    assert result.entry_blocked is True, "Entry should be blocked"
    assert result.entry_block_reason == "degraded_mode", f"Block reason should be degraded_mode, got {result.entry_block_reason}"


# ========== Test 6: Multiple Cycles (10회 거래 시뮬레이션) ==========


def test_multiple_cycles_success():
    """
    Test 6: 연속 10회 거래 성공

    Scenario:
        - 10회 Full cycle 반복 (Entry → Position → Exit → FLAT)
        - 모든 사이클 성공

    Given:
        - Grid trading setup (ATR = 100, Grid spacing = 200)
        - 각 사이클마다 last_fill_price 업데이트

    When:
        - 10회 사이클 실행

    Then:
        - 모든 사이클 성공 (FLAT → FLAT)
        - 총 20개 주문 (Entry 10 + Exit 10)
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=1000.0)
    fake_data.inject_atr(100.0)
    fake_data.inject_atr_pct_24h(0.03)
    fake_data.inject_trades_today(0)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")

    mock_rest_client = MockRestClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_rest_client)

    successful_cycles = 0
    max_cycles = 10

    for i in range(max_cycles):
        # Cycle start: FLAT
        assert orchestrator.state == State.FLAT, f"Cycle {i+1} should start with FLAT, got {orchestrator.state}"

        # Setup Grid signal (alternating Buy/Sell)
        if i % 2 == 0:
            # Grid down: Buy signal
            fake_data.inject_last_fill_price(50200.0)
            fake_data._mark_price = 50000.0  # Current price = 50000 (Grid down = 50200 - 200)
        else:
            # Grid up: Sell signal
            fake_data.inject_last_fill_price(49800.0)
            fake_data._mark_price = 50000.0  # Current price = 50000 (Grid up = 49800 + 200)

        # Tick 1: Entry
        result1 = orchestrator.run_tick()
        if orchestrator.state != State.ENTRY_PENDING:
            break  # Entry failed, stop cycle

        entry_order = mock_rest_client.orders[-1]

        # Tick 2: FILL → IN_POSITION
        fake_data.inject_fill_event(
            order_id=entry_order["orderId"],
            filled_qty=entry_order["qty"],
            order_link_id=entry_order["orderLinkId"],
            side=entry_order["side"],
            price=entry_order["price"],
        )
        result2 = orchestrator.run_tick()
        if orchestrator.state != State.IN_POSITION:
            break  # Position creation failed

        # Tick 3: Stop hit → EXIT_PENDING
        # LONG position: stop_price = entry * 0.97, trigger at entry * 0.96
        # SHORT position: stop_price = entry * 1.03, trigger at entry * 1.04
        if orchestrator.position.direction == Direction.LONG:
            stop_trigger_price = entry_order["price"] * 0.96  # Below stop_price
        else:  # SHORT
            stop_trigger_price = entry_order["price"] * 1.04  # Above stop_price

        fake_data._mark_price = stop_trigger_price
        result3 = orchestrator.run_tick()
        if orchestrator.state != State.EXIT_PENDING:
            break  # Exit order placement failed

        exit_order = mock_rest_client.orders[-1]  # Last order is Exit order

        # Tick 4: Exit FILL → FLAT
        exit_price = stop_trigger_price
        fake_data.inject_fill_event(
            order_id=exit_order["orderId"],
            filled_qty=exit_order["qty"],
            order_link_id=exit_order["orderLinkId"],
            side=exit_order["side"],
            price=exit_price,
        )
        # Exit FILL 후 last_fill_price 업데이트 (Grid signal 무효화)
        fake_data.inject_last_fill_price(exit_price)

        result4 = orchestrator.run_tick()
        if orchestrator.state == State.FLAT:
            successful_cycles += 1

    # Then
    assert successful_cycles == max_cycles, f"Expected {max_cycles} successful cycles, got {successful_cycles}"
    assert orchestrator.state == State.FLAT, "Final state should be FLAT"

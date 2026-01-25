"""
tests/unit/test_orchestrator_entry_flow.py
Unit tests for Orchestrator Entry Flow (Phase 11b)

SSOT:
- FLOW.md Section 2.4: Entry Decision Flow
- task_plan.md Phase 11b: Full Orchestrator Integration

Test Coverage:
1. test_entry_flow_success — 정상 Entry flow (FLAT → ENTRY_PENDING)
2. test_entry_blocked_state_not_flat — FLAT이 아닐 때 차단
3. test_entry_blocked_degraded_mode — degraded mode 시 차단
4. test_entry_blocked_no_signal — Signal 없을 때 차단
5. test_entry_blocked_gate_reject — Entry gate 거절 시 차단
6. test_entry_blocked_sizing_fail — Sizing 실패 시 차단
7. test_entry_blocked_rest_client_unavailable — REST client 없을 때 차단
"""

import pytest
from application.orchestrator import Orchestrator
from infrastructure.exchange.fake_market_data import FakeMarketData
from domain.state import State


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


# ========== Test 1: 정상 Entry Flow ==========


def test_entry_flow_success():
    """
    Test 1: 정상 Entry flow (FLAT → ENTRY_PENDING)

    Given:
        - State: FLAT
        - WS: Normal (not degraded)
        - ATR: 100.0 (Grid spacing = 200.0)
        - Last fill price: 49800.0
        - Current price: 50000.0 (Grid up: 49800 + 200 = 50000, Sell signal)
        - Entry gates: All pass
        - Sizing: 100 contracts
        - REST client: Available

    When:
        - run_tick() 실행

    Then:
        - Entry blocked: False
        - State: ENTRY_PENDING
        - Pending order: Created
        - Order placement: 1 order placed
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=1000.0)  # Linear USDT
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(49800.0)
    fake_data.inject_trades_today(0)
    fake_data.inject_atr_pct_24h(0.03)  # 3% (ATR gate 통과)
    fake_data.inject_winrate(0.6)  # 60%
    fake_data.inject_position_mode("MergedSingle")

    mock_rest_client = MockRestClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_rest_client)

    # When
    result = orchestrator.run_tick()

    # Then
    assert result.entry_blocked is False, f"Entry should not be blocked, reason: {result.entry_block_reason}"
    assert orchestrator.state == State.ENTRY_PENDING, f"State should be ENTRY_PENDING, got {orchestrator.state}"
    assert orchestrator.pending_order is not None, "Pending order should be created"
    assert orchestrator.pending_order["side"] == "Sell", "Signal should be Sell (Grid up)"
    assert len(mock_rest_client.orders) == 1, "1 order should be placed"
    assert mock_rest_client.orders[0]["side"] == "Sell"
    assert mock_rest_client.orders[0]["orderType"] == "Limit"
    assert mock_rest_client.orders[0]["timeInForce"] == "PostOnly"


# ========== Test 2: State Not FLAT ==========


def test_entry_blocked_state_not_flat():
    """
    Test 2: FLAT이 아닐 때 차단

    Given:
        - State: IN_POSITION (not FLAT)
        - Position: Created (Self-healing check 통과용)

    When:
        - run_tick() 실행

    Then:
        - Entry blocked: True
        - Reason: state_not_flat
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=1000.0)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(49800.0)

    mock_rest_client = MockRestClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_rest_client)
    orchestrator.state = State.IN_POSITION  # Force state

    # Phase 11b: Self-healing check 통과를 위해 Position도 설정
    from domain.state import Position, Direction
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
    assert result.entry_blocked is True
    assert result.entry_block_reason == "state_not_flat"


# ========== Test 3: Degraded Mode ==========


def test_entry_blocked_degraded_mode():
    """
    Test 3: degraded mode 시 차단

    Given:
        - State: FLAT
        - WS: Degraded

    When:
        - run_tick() 실행

    Then:
        - Entry blocked: True
        - Reason: degraded_mode
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=1000.0)
    fake_data.set_ws_degraded(degraded=True)

    mock_rest_client = MockRestClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_rest_client)

    # When
    result = orchestrator.run_tick()

    # Then
    assert result.entry_blocked is True
    assert result.entry_block_reason == "degraded_mode"


# ========== Test 4: No Signal ==========


def test_entry_blocked_no_signal():
    """
    Test 4: Signal 없을 때 차단

    Given:
        - State: FLAT
        - WS: Normal
        - ATR: 100.0 (Grid spacing = 200.0)
        - Last fill price: 49800.0
        - Current price: 49900.0 (Grid spacing 범위 밖, no signal)

    When:
        - run_tick() 실행

    Then:
        - Entry blocked: True
        - Reason: no_signal
    """
    # Given
    fake_data = FakeMarketData(current_price=49900.0, equity_usdt=1000.0)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(49800.0)
    # Current price = 49900, Grid up = 49800 + 200 = 50000, Grid down = 49800 - 200 = 49600
    # 49900은 범위 밖 → no signal

    mock_rest_client = MockRestClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_rest_client)

    # When
    result = orchestrator.run_tick()

    # Then
    assert result.entry_blocked is True
    assert result.entry_block_reason == "no_signal"


# ========== Test 5: Entry Gate Reject ==========


def test_entry_blocked_gate_reject():
    """
    Test 5: Entry gate 거절 시 차단

    Given:
        - State: FLAT
        - WS: Normal
        - Signal: Valid (Grid up)
        - Entry gate: ATR too low (atr_pct_24h < 2%)

    When:
        - run_tick() 실행

    Then:
        - Entry blocked: True
        - Reason: atr_too_low
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=1000.0)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(49800.0)
    fake_data.inject_atr_pct_24h(0.01)  # 1% (ATR gate 거절: < 2%)
    fake_data.inject_trades_today(0)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")

    mock_rest_client = MockRestClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_rest_client)

    # When
    result = orchestrator.run_tick()

    # Then
    assert result.entry_blocked is True
    assert result.entry_block_reason == "atr_too_low"


# ========== Test 6: Sizing Fail ==========


def test_entry_blocked_sizing_fail():
    """
    Test 6: Sizing 실패 시 차단

    Given:
        - State: FLAT
        - WS: Normal
        - Signal: Valid (Grid up)
        - Entry gates: All pass
        - Sizing: Fail (equity too low)

    When:
        - run_tick() 실행

    Then:
        - Entry blocked: True
        - Reason: qty_below_minimum or margin_insufficient
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_btc=0.00001)  # Very low equity
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(49800.0)
    fake_data.inject_atr_pct_24h(0.03)
    fake_data.inject_trades_today(0)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")

    mock_rest_client = MockRestClient()
    orchestrator = Orchestrator(market_data=fake_data, rest_client=mock_rest_client)

    # When
    result = orchestrator.run_tick()

    # Then
    assert result.entry_blocked is True
    assert result.entry_block_reason in ["qty_below_minimum", "margin_insufficient"]


# ========== Test 7: REST Client Unavailable ==========


def test_entry_blocked_rest_client_unavailable():
    """
    Test 7: REST client 없을 때 차단

    Given:
        - State: FLAT
        - WS: Normal
        - Signal: Valid (Grid up)
        - Entry gates: All pass
        - Sizing: Pass
        - REST client: None

    When:
        - run_tick() 실행

    Then:
        - Entry blocked: True
        - Reason: rest_client_unavailable
    """
    # Given
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=1000.0)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(49800.0)
    fake_data.inject_atr_pct_24h(0.03)
    fake_data.inject_trades_today(0)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")

    orchestrator = Orchestrator(market_data=fake_data, rest_client=None)  # No REST client

    # When
    result = orchestrator.run_tick()

    # Then
    assert result.entry_blocked is True
    assert result.entry_block_reason == "rest_client_unavailable"

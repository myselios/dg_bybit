"""
tests/unit/test_rest_fallback.py
REST fallback module tests — check_pending_order_fallback
"""

import pytest
from unittest.mock import MagicMock
from domain.state import State, Position, Direction, StopStatus
from application.rest_fallback import (
    check_pending_order_fallback,
    FallbackResult,
    _NO_CHANGE,
    _check_has_position,
    _recover_position_from_api,
)


def _mock_rest_client(**overrides):
    """테스트용 REST client mock"""
    client = MagicMock()

    # get_position default: no position
    pos_response = overrides.get("pos_response", {
        "result": {"list": [{"size": "0", "avgPrice": "0", "side": "None"}]}
    })
    client.get_position.return_value = pos_response

    # get_open_orders default: empty (order not open)
    open_orders = overrides.get("open_orders", {"result": {"list": []}})
    client.get_open_orders.return_value = open_orders

    # get_execution_list default: empty
    executions = overrides.get("executions", {"result": {"list": []}})
    client.get_execution_list.return_value = executions

    # get_order_history default: empty
    history = overrides.get("history", {"result": {"list": []}})
    client.get_order_history.return_value = history

    return client


class TestCheckHasPosition:
    def test_has_position_true(self):
        client = _mock_rest_client(pos_response={
            "result": {"list": [{"size": "0.003", "avgPrice": "50000", "side": "Buy"}]}
        })
        assert _check_has_position(client) is True

    def test_has_position_false_zero_size(self):
        client = _mock_rest_client()
        assert _check_has_position(client) is False

    def test_has_position_false_on_exception(self):
        client = MagicMock()
        client.get_position.side_effect = Exception("API error")
        assert _check_has_position(client) is False


class TestRecoverPositionFromApi:
    def test_recovers_long_position(self):
        client = _mock_rest_client(pos_response={
            "result": {"list": [{"size": "0.003", "avgPrice": "50000.0", "side": "Buy"}]}
        })
        pos = _recover_position_from_api(client, {"signal_id": "sig1"})

        assert pos is not None
        assert pos.qty == 3
        assert pos.entry_price == 50000.0
        assert pos.direction == Direction.LONG
        assert pos.signal_id == "sig1"
        assert pos.stop_status == StopStatus.MISSING

    def test_returns_none_when_no_position(self):
        client = _mock_rest_client()
        pos = _recover_position_from_api(client, None)
        assert pos is None


class TestCheckPendingOrderFallback:
    def test_order_still_open_returns_no_change(self):
        """주문이 아직 open 상태이면 변경 없음"""
        client = _mock_rest_client(open_orders={
            "result": {"list": [{"orderStatus": "New"}]}
        })
        pending = {"order_id": "ord123", "order_link_id": "link123"}

        result = check_pending_order_fallback(
            rest_client=client, state=State.ENTRY_PENDING,
            pending_order=pending, elapsed=15.0,
        )

        assert result.new_state is None
        assert result.clear_pending is False

    def test_order_id_none_exit_pending_no_position_goes_flat(self):
        """order_id=None + EXIT_PENDING + position 없음 → FLAT"""
        client = _mock_rest_client()
        pending = {"order_id": None}

        result = check_pending_order_fallback(
            rest_client=client, state=State.EXIT_PENDING,
            pending_order=pending, elapsed=15.0,
        )

        assert result.new_state == State.FLAT
        assert result.new_position is None
        assert result.clear_pending is True
        assert result.log_estimated_reason == "order_id_none"
        assert result.skip_ws_processing is True

    def test_order_filled_with_executions_entry(self):
        """주문 체결 + execution 존재 → ENTRY_PENDING → IN_POSITION"""
        client = _mock_rest_client(
            executions={"result": {"list": [{
                "orderId": "ord123",
                "orderLinkId": "link123",
                "execPrice": "50000.0",
                "execQty": "0.003",
                "execFee": "0.01",
                "execTime": "1700000000000",
                "side": "Buy",
            }]}}
        )
        pending = {
            "order_id": "ord123",
            "order_link_id": "link123",
            "side": "Buy",
            "qty": 3,
            "price": 50000.0,
            "signal_id": "sig1",
            "stop_distance_pct": 0.01,
        }

        result = check_pending_order_fallback(
            rest_client=client, state=State.ENTRY_PENDING,
            pending_order=pending, elapsed=15.0,
        )

        assert result.new_state == State.IN_POSITION
        assert result.new_position is not _NO_CHANGE
        assert result.clear_pending is True

    def test_order_cancelled_exit_pending_has_position(self):
        """주문 취소 + EXIT_PENDING + position 존재 → IN_POSITION"""
        client = _mock_rest_client(
            history={"result": {"list": [{"orderStatus": "Cancelled"}]}},
            pos_response={"result": {"list": [{"size": "0.003", "avgPrice": "50000", "side": "Buy"}]}},
        )
        pending = {"order_id": "ord123"}

        result = check_pending_order_fallback(
            rest_client=client, state=State.EXIT_PENDING,
            pending_order=pending, elapsed=15.0,
        )

        assert result.new_state == State.IN_POSITION
        assert result.clear_pending is True

    def test_order_cancelled_entry_pending_no_position(self):
        """주문 취소 + ENTRY_PENDING + position 없음 → FLAT"""
        client = _mock_rest_client(
            history={"result": {"list": [{"orderStatus": "Cancelled"}]}},
        )
        pending = {"order_id": "ord123"}

        result = check_pending_order_fallback(
            rest_client=client, state=State.ENTRY_PENDING,
            pending_order=pending, elapsed=15.0,
        )

        assert result.new_state == State.FLAT
        assert result.new_position is None
        assert result.clear_pending is True


class TestStopUpdateResult:
    def test_no_change_sentinel(self):
        """_NO_CHANGE sentinel이 None과 다른지 확인"""
        result = FallbackResult()
        assert result.new_position is _NO_CHANGE
        assert result.new_position is not None

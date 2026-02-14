"""
tests/unit/test_trade_logging.py
Trade logging module tests — log_estimated_trade, log_completed_trade
"""

import pytest
from unittest.mock import MagicMock, patch
from domain.state import Position, Direction, StopStatus
from application.trade_logging import log_estimated_trade, log_completed_trade


def _make_market_data(**overrides):
    """테스트용 MarketData mock 생성"""
    md = MagicMock()
    md.get_mark_price.return_value = overrides.get("mark_price", 50000.0)
    md.get_funding_rate.return_value = overrides.get("funding_rate", 0.0001)
    md.get_index_price.return_value = overrides.get("index_price", 50001.0)
    md.get_timestamp.return_value = overrides.get("timestamp", 1700000000.0)
    md.get_ma_slope_pct.return_value = overrides.get("ma_slope_pct", 0.5)
    md.get_atr_percentile.return_value = overrides.get("atr_percentile", 50.0)
    md.get_exchange_server_time_offset_ms.return_value = overrides.get("offset_ms", 10.0)
    return md


def _make_position(**overrides):
    """테스트용 Position 생성"""
    return Position(
        qty=overrides.get("qty", 3),
        entry_price=overrides.get("entry_price", 49000.0),
        direction=overrides.get("direction", Direction.LONG),
        signal_id=overrides.get("signal_id", "test_signal"),
        stop_status=overrides.get("stop_status", StopStatus.ACTIVE),
        stop_price=overrides.get("stop_price", 48500.0),
    )


class TestLogEstimatedTrade:
    def test_logs_estimated_trade_long(self):
        md = _make_market_data(mark_price=50000.0)
        log_storage = MagicMock()
        position = _make_position(direction=Direction.LONG, entry_price=49000.0, qty=3)

        log_estimated_trade(
            market_data=md,
            log_storage=log_storage,
            config_hash="abc123",
            git_commit="def456",
            position=position,
            reason="test_reason",
        )

        log_storage.append_trade_log_v1.assert_called_once()
        log_entry = log_storage.append_trade_log_v1.call_args[1]["log_entry"]

        assert log_entry["order_id"] == "estimated_test_reason"
        assert log_entry["config_hash"] == "estimated_abc123"
        assert log_entry["direction"] == "LONG"
        assert log_entry["side"] == "Sell"
        assert log_entry["entry_price"] == 49000.0
        assert log_entry["exit_price"] == 50000.0
        # PnL: (50000 - 49000) * 0.003 = 3.0
        assert abs(log_entry["realized_pnl_usd"] - 3.0) < 0.01

    def test_logs_estimated_trade_short(self):
        md = _make_market_data(mark_price=48000.0)
        log_storage = MagicMock()
        position = _make_position(direction=Direction.SHORT, entry_price=49000.0, qty=2)

        log_estimated_trade(
            market_data=md,
            log_storage=log_storage,
            config_hash="hash",
            git_commit="commit",
            position=position,
            reason="exit_no_fill",
        )

        log_entry = log_storage.append_trade_log_v1.call_args[1]["log_entry"]
        assert log_entry["side"] == "Buy"
        assert log_entry["direction"] == "SHORT"
        # PnL: (49000 - 48000) * 0.002 = 2.0
        assert abs(log_entry["realized_pnl_usd"] - 2.0) < 0.01


class TestLogCompletedTrade:
    def test_logs_completed_trade_from_dict_event(self):
        md = _make_market_data(mark_price=51000.0)
        log_storage = MagicMock()
        position = _make_position(direction=Direction.LONG, entry_price=49000.0, qty=3)
        pending_order = {"price": 49100.0}

        event = {
            "orderId": "order123",
            "execPrice": "51000.0",
            "execQty": "0.003",
            "execFee": "0.05",
            "execTime": "1700000010000",
        }

        log_completed_trade(
            market_data=md,
            log_storage=log_storage,
            config_hash="hash",
            git_commit="commit",
            position=position,
            pending_order=pending_order,
            pending_order_timestamp=1700000000.0,
            event=event,
        )

        log_storage.append_trade_log_v1.assert_called_once()
        log_entry = log_storage.append_trade_log_v1.call_args[1]["log_entry"]

        assert log_entry["order_id"] == "order123"
        assert log_entry["exit_price"] == 51000.0
        assert log_entry["direction"] == "LONG"
        assert log_entry["side"] == "Sell"
        # PnL: (51000 - 49000) * 0.003 = 6.0
        assert abs(log_entry["realized_pnl_usd"] - 6.0) < 0.01
        assert log_entry["fee_usd"] == 0.05

    def test_logs_completed_trade_from_execution_event(self):
        md = _make_market_data()
        log_storage = MagicMock()
        position = _make_position(direction=Direction.SHORT, entry_price=50000.0, qty=2)

        event = MagicMock()
        event.order_id = "order456"
        event.exec_price = 49000.0
        event.filled_qty = 2
        event.fee_paid = 0.03
        event.timestamp = 1700000005000

        log_completed_trade(
            market_data=md,
            log_storage=log_storage,
            config_hash="hash",
            git_commit="commit",
            position=position,
            pending_order={"price": 49100.0},
            pending_order_timestamp=1700000000.0,
            event=event,
        )

        log_entry = log_storage.append_trade_log_v1.call_args[1]["log_entry"]
        assert log_entry["order_id"] == "order456"
        assert log_entry["side"] == "Buy"
        # PnL: (50000 - 49000) * 0.002 = 2.0
        assert abs(log_entry["realized_pnl_usd"] - 2.0) < 0.01

"""
tests/unit/test_stop_manager_execute.py
Stop manager execute_stop_update tests
"""

import pytest
from unittest.mock import MagicMock
from domain.state import Direction
from application.stop_manager import (
    calculate_stop_price,
    is_stop_breached,
    execute_stop_update,
)


class TestCalculateStopPrice:
    def test_long_stop_below_entry(self):
        price = calculate_stop_price(entry_price=50000.0, direction=Direction.LONG, atr=400.0)
        # ATR*0.7 = 280, clamped to [250, 1000]
        assert price < 50000.0
        assert price == 50000.0 - 280.0

    def test_short_stop_above_entry(self):
        price = calculate_stop_price(entry_price=50000.0, direction=Direction.SHORT, atr=400.0)
        assert price > 50000.0
        assert price == 50000.0 + 280.0

    def test_fallback_1pct_when_no_atr(self):
        price = calculate_stop_price(entry_price=50000.0, direction=Direction.LONG, atr=None)
        assert price == 50000.0 - 500.0  # 1% of 50000

    def test_clamp_min(self):
        # ATR very small → clamp to 0.5%
        price = calculate_stop_price(entry_price=50000.0, direction=Direction.LONG, atr=1.0)
        expected = 50000.0 - 250.0  # min = 0.5% of 50000
        assert price == expected

    def test_clamp_max(self):
        # ATR very large → clamp to 2.0%
        price = calculate_stop_price(entry_price=50000.0, direction=Direction.LONG, atr=5000.0)
        expected = 50000.0 - 1000.0  # max = 2.0% of 50000
        assert price == expected


class TestIsStopBreached:
    def test_long_breached(self):
        assert is_stop_breached(49000.0, 49500.0, Direction.LONG) is True

    def test_long_not_breached(self):
        assert is_stop_breached(50000.0, 49500.0, Direction.LONG) is False

    def test_short_breached(self):
        assert is_stop_breached(51000.0, 50500.0, Direction.SHORT) is True

    def test_short_not_breached(self):
        assert is_stop_breached(50000.0, 50500.0, Direction.SHORT) is False

    def test_zero_price_not_breached(self):
        assert is_stop_breached(0.0, 50000.0, Direction.LONG) is False


class TestExecuteStopUpdate:
    def test_success_sets_stop(self):
        client = MagicMock()
        client.set_trading_stop.return_value = {"retCode": 0, "retMsg": "OK"}

        result = execute_stop_update(
            rest_client=client,
            entry_price=50000.0,
            direction=Direction.LONG,
            current_price=50500.0,
            atr=400.0,
        )

        assert result.success is True
        assert result.new_stop_price == 50000.0 - 280.0
        assert result.stop_already_breached is False
        client.set_trading_stop.assert_called_once()

    def test_not_modified_34040_treated_as_success(self):
        client = MagicMock()
        client.set_trading_stop.return_value = {"retCode": 34040, "retMsg": "not modified"}

        result = execute_stop_update(
            rest_client=client,
            entry_price=50000.0,
            direction=Direction.LONG,
            current_price=50500.0,
            atr=400.0,
        )

        assert result.success is True

    def test_api_error_raises(self):
        client = MagicMock()
        client.set_trading_stop.return_value = {"retCode": 10001, "retMsg": "params error"}

        with pytest.raises(ValueError, match="set_trading_stop failed"):
            execute_stop_update(
                rest_client=client,
                entry_price=50000.0,
                direction=Direction.LONG,
                current_price=50500.0,
                atr=400.0,
            )

    def test_stop_already_breached_skips_api(self):
        client = MagicMock()

        result = execute_stop_update(
            rest_client=client,
            entry_price=50000.0,
            direction=Direction.LONG,
            current_price=49000.0,  # Below stop price
            atr=400.0,
        )

        assert result.success is True
        assert result.stop_already_breached is True
        client.set_trading_stop.assert_not_called()

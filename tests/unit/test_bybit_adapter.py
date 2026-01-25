"""
tests/unit/test_bybit_adapter.py
BybitAdapter Unit Tests

Purpose:
- REST API 응답 → MarketDataInterface 변환 검증
- WebSocket event → ExecutionEvent 변환 검증
- Caching 동작 검증
- DEGRADED 모드 전환 검증

SSOT:
- docs/plans/task_plan.md Phase 12a-1
- src/infrastructure/exchange/market_data_interface.py (Protocol)
"""

import time
import pytest
from unittest.mock import Mock, MagicMock, call
from typing import Dict, Any, List, Optional

from infrastructure.exchange.bybit_adapter import BybitAdapter
from infrastructure.exchange.bybit_rest_client import BybitRestClient
from infrastructure.exchange.bybit_ws_client import BybitWsClient
from domain.events import ExecutionEvent, EventType


class TestBybitAdapterRestIntegration:
    """REST API 응답 → MarketDataInterface 변환"""

    def test_get_mark_price_from_rest_tickers(self):
        """GET /v5/market/tickers → get_mark_price()"""
        # Arrange
        rest_client = MagicMock()  # ✅ Mock spec → MagicMock
        ws_client = MagicMock()    # ✅ Mock spec → MagicMock

        # Bybit REST 응답 (실제 구조)
        rest_client.get_tickers.return_value = {
            "result": {
                "list": [{
                    "symbol": "BTCUSD",
                    "markPrice": "50000.50",
                    "indexPrice": "50001.00",
                    "fundingRate": "0.0001"
                }]
            }
        }

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        adapter.update_market_data()
        mark_price = adapter.get_mark_price()

        # Assert
        assert mark_price == 50000.50
        rest_client.get_tickers.assert_called_once_with(category="inverse", symbol="BTCUSD")

    def test_get_equity_btc_from_wallet_balance(self):
        """GET /v5/account/wallet-balance → get_equity_btc()"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        # Bybit REST 응답
        rest_client.get_wallet_balance.return_value = {
            "result": {
                "list": [{
                    "coin": [{
                        "coin": "BTC",
                        "equity": "0.0025",
                        "walletBalance": "0.0024",
                        "unrealisedPnl": "0.0001"
                    }]
                }]
            }
        }

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        adapter.update_market_data()
        equity_btc = adapter.get_equity_btc()

        # Assert
        assert equity_btc == 0.0025
        rest_client.get_wallet_balance.assert_called_once_with(accountType="CONTRACT", coin="BTC")

    def test_get_index_price_and_funding_rate(self):
        """GET /v5/market/tickers → get_index_price(), get_funding_rate()"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        rest_client.get_tickers.return_value = {
            "result": {
                "list": [{
                    "symbol": "BTCUSD",
                    "markPrice": "50000.00",
                    "indexPrice": "50001.50",
                    "fundingRate": "0.00015"
                }]
            }
        }

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        adapter.update_market_data()

        # Assert
        assert adapter.get_index_price() == 50001.50
        assert adapter.get_funding_rate() == 0.00015

    def test_get_current_position_from_rest(self):
        """GET /v5/position/list → Position tracking"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        rest_client.get_position.return_value = {
            "result": {
                "list": [{
                    "symbol": "BTCUSD",
                    "side": "Buy",
                    "size": "100",
                    "avgPrice": "49500.00",
                    "unrealisedPnl": "0.00020"
                }]
            }
        }

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        adapter.update_market_data()
        position = adapter._current_position

        # Assert
        assert position is not None
        assert position["side"] == "Buy"
        assert float(position["size"]) == 100.0
        assert float(position["avgPrice"]) == 49500.00


class TestBybitAdapterWebSocketIntegration:
    """WebSocket event → ExecutionEvent 변환"""

    def test_fill_event_conversion_from_ws(self):
        """WS execution.inverse → ExecutionEvent(FILL)"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        # WebSocket FILL event (Bybit execution.inverse 구조)
        ws_fill_event = {
            "topic": "execution.inverse",
            "data": [{
                "symbol": "BTCUSD",
                "orderId": "abc123",
                "orderLinkId": "grid_xyz_l",
                "side": "Buy",
                "execType": "Trade",
                "execQty": "100",
                "execPrice": "49800.00",
                "orderQty": "100",
                "execFee": "0.00001",
                "execTime": "1706000000000"
            }]
        }

        ws_client.get_execution_events.return_value = [ws_fill_event["data"][0]]

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        fill_events = adapter.get_fill_events()

        # Assert
        assert len(fill_events) == 1
        event = fill_events[0]
        assert isinstance(event, ExecutionEvent)
        assert event.type == EventType.FILL  # ✅ event_type → type
        assert event.order_id == "abc123"
        assert event.order_link_id == "grid_xyz_l"
        assert event.filled_qty == 100  # ✅ executed_qty → filled_qty
        assert event.exec_price == 49800.00  # ✅ executed_price → exec_price

    def test_partial_fill_event_conversion(self):
        """WS execution → ExecutionEvent(PARTIAL_FILL)"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        ws_partial_event = {
            "symbol": "BTCUSD",
            "orderId": "def456",
            "orderLinkId": "grid_abc_s",
            "side": "Sell",
            "execType": "Trade",
            "execQty": "30",
            "execPrice": "50200.00",
            "orderQty": "100",  # Partial: 30/100
            "execFee": "0.000003",
            "execTime": "1706000010000"
        }

        ws_client.get_execution_events.return_value = [ws_partial_event]

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        fill_events = adapter.get_fill_events()

        # Assert
        assert len(fill_events) == 1
        event = fill_events[0]
        assert event.type == EventType.PARTIAL_FILL  # ✅ event_type → type
        assert event.filled_qty == 30  # ✅ executed_qty → filled_qty
        assert event.order_qty == 100


class TestBybitAdapterStateCaching:
    """State caching 동작 검증"""

    def test_caching_mark_price_between_updates(self):
        """mark_price 캐싱 (update 없으면 이전 값 유지)"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        rest_client.get_tickers.return_value = {
            "result": {"list": [{"symbol": "BTCUSD", "markPrice": "50000.00"}]}
        }

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        adapter.update_market_data()
        price1 = adapter.get_mark_price()

        # 캐시된 값 반환 (REST 호출 안 함)
        price2 = adapter.get_mark_price()

        # Assert
        assert price1 == 50000.00
        assert price2 == 50000.00
        assert rest_client.get_tickers.call_count == 1  # 1번만 호출

    def test_last_fill_price_tracking(self):
        """last_fill_price 업데이트 (FILL event 시)"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        ws_fill = {
            "orderId": "xyz789",
            "orderLinkId": "grid_test",
            "side": "Buy",
            "execType": "Trade",
            "execQty": "100",
            "execPrice": "49900.00",
            "orderQty": "100"
        }

        ws_client.get_execution_events.return_value = [ws_fill]

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        initial_price = adapter.get_last_fill_price()
        assert initial_price is None

        adapter.get_fill_events()  # 내부에서 last_fill_price 업데이트
        updated_price = adapter.get_last_fill_price()

        # Assert
        assert updated_price == 49900.00

    def test_trades_today_counter_increment(self):
        """trades_today 카운터 증가"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        initial_count = adapter.get_trades_today()
        assert initial_count == 0

        adapter.increment_trades_today()
        adapter.increment_trades_today()

        # Assert
        assert adapter.get_trades_today() == 2


class TestBybitAdapterDegradedMode:
    """DEGRADED 모드 전환 검증"""

    def test_degraded_mode_on_ws_heartbeat_timeout(self):
        """WS heartbeat timeout → DEGRADED 모드"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # WS healthy 초기 상태
        assert adapter.is_ws_degraded() is False

        # Act
        adapter.set_ws_degraded(True)

        # Assert
        assert adapter.is_ws_degraded() is True

    def test_degraded_timeout_after_60_seconds(self):
        """DEGRADED 60초 timeout 검증"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        adapter.set_ws_degraded(True)

        # 60초 이전
        assert adapter.is_degraded_timeout() is False

        # 60초 경과 시뮬레이션 (시간 주입 필요하면 Clock 사용)
        adapter._degraded_entered_at = time.time() - 61.0

        # Assert
        assert adapter.is_degraded_timeout() is True

    def test_degraded_exit_clears_timeout(self):
        """DEGRADED 모드 해제 시 timeout 리셋"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        adapter.set_ws_degraded(True)
        assert adapter._degraded_entered_at is not None

        adapter.set_ws_degraded(False)

        # Assert
        assert adapter.is_ws_degraded() is False
        assert adapter._degraded_entered_at is None


class TestBybitAdapterSessionRiskTracking:
    """Session Risk tracking (Phase 9 통합)"""

    def test_get_daily_realized_pnl_from_trade_history(self):
        """GET /v5/execution/list → Daily realized PnL 계산"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        # 현재 시간 (ms)
        current_time_ms = time.time() * 1000

        # Trade history (2 trades, +5 USD, -3 USD)
        rest_client.get_execution_list.return_value = {
            "result": {
                "list": [
                    {"closedPnl": "5.0", "symbol": "BTCUSD", "execTime": str(int(current_time_ms - 1000))},
                    {"closedPnl": "-3.0", "symbol": "BTCUSD", "execTime": str(int(current_time_ms - 500))}
                ]
            }
        }

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        adapter.update_market_data()
        daily_pnl = adapter.get_daily_realized_pnl_usd()

        # Assert
        assert daily_pnl == 2.0  # 5.0 + (-3.0) = 2.0

    def test_loss_streak_calculation(self):
        """Loss streak 계산 (연속 손실 카운트)"""
        # Arrange
        rest_client = MagicMock()
        ws_client = MagicMock()

        # 현재 시간 (ms)
        current_time_ms = time.time() * 1000

        # 3 consecutive losses
        rest_client.get_execution_list.return_value = {
            "result": {
                "list": [
                    {"closedPnl": "-2.0", "execTime": str(int(current_time_ms - 3000))},
                    {"closedPnl": "-1.5", "execTime": str(int(current_time_ms - 2000))},
                    {"closedPnl": "-3.0", "execTime": str(int(current_time_ms - 1000))}
                ]
            }
        }

        adapter = BybitAdapter(rest_client, ws_client, testnet=True)

        # Act
        adapter.update_market_data()
        loss_streak = adapter.get_loss_streak_count()

        # Assert
        assert loss_streak == 3

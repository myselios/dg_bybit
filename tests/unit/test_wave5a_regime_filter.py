"""
tests/unit/test_wave5a_regime_filter.py
Wave 5A: Regime 방향 필터 + signal_score 보존 테스트

커버:
1. trending_down 레짐에서 Buy(LONG) 신호 차단
2. trending_up 레짐에서 Sell(SHORT) 신호 차단
3. ranging 레짐에서 양방향 허용
4. high_vol 레짐에서 양방향 허용
5. signal_score가 entry pending_order에서 보존되어 _entry_signal_score에 저장됨
6. _classify_regime 로직 단위 검증
"""

import pytest
from application.orchestrator import Orchestrator
from infrastructure.exchange.fake_market_data import FakeMarketData
from domain.state import State


class MockRestClient:
    """Mock REST client for regime filter tests"""

    def __init__(self):
        self.orders = []

    def get_position(self, symbol: str = "BTCUSDT", category: str = "linear"):
        return {"retCode": 0, "result": {"list": []}}

    def set_trading_stop(self, symbol: str, stop_loss: str, category: str = "linear",
                         position_idx: int = 0, sl_trigger_by: str = "MarkPrice"):
        return {"retCode": 0, "retMsg": "OK"}

    def place_order(self, symbol: str, side: str, order_type: str, qty: str,
                    price: str, time_in_force: str, order_link_id: str,
                    category: str = "linear", reduce_only: bool = False, **kwargs):
        order = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": f"mock_{side}_123",
                "orderLinkId": order_link_id,
            },
        }
        self.orders.append(order)
        return order


def _make_orchestrator_for_sell_signal(ma_slope_pct: float, atr_percentile: float) -> Orchestrator:
    """
    Sell(SHORT) 신호가 발생하는 조건으로 Orchestrator 생성.
    current_price=50000, last_fill=49800 → grid_up → Sell signal
    """
    fake_data = FakeMarketData(current_price=50000.0, equity_usdt=1000.0)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(49800.0)
    fake_data.inject_trades_today(0)
    fake_data.inject_atr_pct_24h(0.03)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")
    fake_data.inject_ma_slope_pct(ma_slope_pct)
    fake_data.inject_atr_percentile(atr_percentile)
    return Orchestrator(market_data=fake_data, rest_client=MockRestClient())


def _make_orchestrator_for_buy_signal(ma_slope_pct: float, atr_percentile: float) -> Orchestrator:
    """
    Buy(LONG) 신호가 발생하는 조건으로 Orchestrator 생성.
    current_price=49600, last_fill=49800 → grid_down → Buy signal
    """
    fake_data = FakeMarketData(current_price=49600.0, equity_usdt=1000.0)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(49800.0)
    fake_data.inject_trades_today(0)
    fake_data.inject_atr_pct_24h(0.03)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")
    fake_data.inject_ma_slope_pct(ma_slope_pct)
    fake_data.inject_atr_percentile(atr_percentile)
    return Orchestrator(market_data=fake_data, rest_client=MockRestClient())


# ========== Test 1: _classify_regime 단위 검증 ==========

class TestClassifyRegime:
    """Orchestrator._classify_regime 정적 메서드 단위 테스트"""

    def test_high_vol_takes_priority(self):
        """ATR percentile >= 80이면 high_vol (우선순위 최고)"""
        result = Orchestrator._classify_regime(ma_slope_pct=0.5, atr_percentile=80.0)
        assert result == "high_vol"

    def test_trending_up_below_50_percentile(self):
        """ma_slope > 0.1% + atr_percentile < 50 → trending_up"""
        result = Orchestrator._classify_regime(ma_slope_pct=0.15, atr_percentile=40.0)
        assert result == "trending_up"

    def test_trending_down_below_50_percentile(self):
        """ma_slope < -0.1% + atr_percentile < 50 → trending_down"""
        result = Orchestrator._classify_regime(ma_slope_pct=-0.15, atr_percentile=30.0)
        assert result == "trending_down"

    def test_ranging_when_slope_small(self):
        """|ma_slope| <= 0.1% → ranging"""
        result = Orchestrator._classify_regime(ma_slope_pct=0.05, atr_percentile=40.0)
        assert result == "ranging"

    def test_ranging_when_atr_percentile_50_to_79(self):
        """ATR percentile 50-79: slope가 커도 ranging (trending 판단 안 함)"""
        result = Orchestrator._classify_regime(ma_slope_pct=0.5, atr_percentile=60.0)
        assert result == "ranging"

    def test_boundary_ma_slope_exactly_01(self):
        """ma_slope = 0.1 경계: trending_up 아님 → ranging"""
        result = Orchestrator._classify_regime(ma_slope_pct=0.1, atr_percentile=40.0)
        assert result == "ranging"

    def test_boundary_ma_slope_just_above_01(self):
        """ma_slope = 0.101: trending_up"""
        result = Orchestrator._classify_regime(ma_slope_pct=0.101, atr_percentile=40.0)
        assert result == "trending_up"


# ========== Test 2: trending_down에서 Buy 차단 ==========

class TestTrendingDownBlocksBuy:
    """trending_down 레짐에서 LONG(Buy) 진입 차단 테스트"""

    def test_trending_down_blocks_buy_signal(self):
        """
        Given: trending_down 레짐 (ma_slope=-0.3%, atr_pct=30)
        When: Buy 신호 발생 (grid_down → price < last_fill - spacing)
        Then: entry_blocked=True, reason="regime_direction_filter"
        """
        orchestrator = _make_orchestrator_for_buy_signal(
            ma_slope_pct=-0.3, atr_percentile=30.0
        )
        result = orchestrator.run_tick()

        assert result.entry_blocked is True
        assert result.entry_block_reason == "regime_direction_filter"
        assert orchestrator.state == State.FLAT

    def test_trending_down_allows_sell_signal(self):
        """
        Given: trending_down 레짐 (ma_slope=-0.3%, atr_pct=30)
        When: Sell 신호 발생 (grid_up → price > last_fill + spacing)
        Then: entry_blocked=False (Sell은 허용)
        """
        orchestrator = _make_orchestrator_for_sell_signal(
            ma_slope_pct=-0.3, atr_percentile=30.0
        )
        result = orchestrator.run_tick()

        assert result.entry_blocked is False
        assert orchestrator.state == State.ENTRY_PENDING


# ========== Test 3: trending_up에서 Sell 차단 ==========

class TestTrendingUpBlocksSell:
    """trending_up 레짐에서 SHORT(Sell) 진입 차단 테스트"""

    def test_trending_up_blocks_sell_signal(self):
        """
        Given: trending_up 레짐 (ma_slope=0.3%, atr_pct=30)
        When: Sell 신호 발생 (grid_up → price > last_fill + spacing)
        Then: entry_blocked=True, reason="regime_direction_filter"
        """
        orchestrator = _make_orchestrator_for_sell_signal(
            ma_slope_pct=0.3, atr_percentile=30.0
        )
        result = orchestrator.run_tick()

        assert result.entry_blocked is True
        assert result.entry_block_reason == "regime_direction_filter"
        assert orchestrator.state == State.FLAT

    def test_trending_up_allows_buy_signal(self):
        """
        Given: trending_up 레짐 (ma_slope=0.3%, atr_pct=30)
        When: Buy 신호 발생 (grid_down → price < last_fill - spacing)
        Then: entry_blocked=False (Buy는 허용)
        """
        orchestrator = _make_orchestrator_for_buy_signal(
            ma_slope_pct=0.3, atr_percentile=30.0
        )
        result = orchestrator.run_tick()

        assert result.entry_blocked is False
        assert orchestrator.state == State.ENTRY_PENDING


# ========== Test 4: ranging/high_vol은 양방향 허용 ==========

class TestRangingAllowsBothDirections:
    """ranging / high_vol 레짐에서 양방향 허용"""

    def test_ranging_allows_sell(self):
        """ranging 레짐: Sell 허용"""
        orchestrator = _make_orchestrator_for_sell_signal(
            ma_slope_pct=0.05, atr_percentile=40.0
        )
        result = orchestrator.run_tick()

        assert result.entry_blocked is False
        assert orchestrator.state == State.ENTRY_PENDING

    def test_ranging_allows_buy(self):
        """ranging 레짐: Buy 허용"""
        orchestrator = _make_orchestrator_for_buy_signal(
            ma_slope_pct=0.05, atr_percentile=40.0
        )
        result = orchestrator.run_tick()

        assert result.entry_blocked is False
        assert orchestrator.state == State.ENTRY_PENDING

    def test_high_vol_allows_sell(self):
        """high_vol 레짐: Sell 허용 (양방향) — ma_slope 중립으로 신호 보장"""
        orchestrator = _make_orchestrator_for_sell_signal(
            ma_slope_pct=0.0, atr_percentile=85.0
        )
        result = orchestrator.run_tick()

        assert result.entry_blocked is False
        assert orchestrator.state == State.ENTRY_PENDING

    def test_high_vol_allows_buy(self):
        """high_vol 레짐: Buy 허용 (양방향) — ma_slope 중립으로 신호 보장"""
        orchestrator = _make_orchestrator_for_buy_signal(
            ma_slope_pct=0.0, atr_percentile=85.0
        )
        result = orchestrator.run_tick()

        assert result.entry_blocked is False
        assert orchestrator.state == State.ENTRY_PENDING


# ========== Test 5: signal_score 보존 검증 ==========

class TestEntrySignalScorePreserved:
    """
    Wave 5A: _entry_signal_score가 pending_order와 별도로 저장되는지 검증.
    signal.score가 None이 아닌 경우에도 _entry_signal_score에 동일값이 복사되어야 함.
    """

    def test_entry_signal_score_stored_in_instance_variable(self):
        """
        Entry 성공 시 _entry_signal_score가 pending_order["signal_score"]와 동일한지 검증.
        """
        orchestrator = _make_orchestrator_for_sell_signal(
            ma_slope_pct=0.05, atr_percentile=40.0
        )
        result = orchestrator.run_tick()

        assert result.entry_blocked is False
        assert orchestrator.pending_order is not None
        # _entry_signal_score는 pending_order의 signal_score와 동일해야 함
        pending_score = orchestrator.pending_order.get("signal_score")
        assert orchestrator._entry_signal_score == pending_score

    def test_entry_signal_components_stored_in_instance_variable(self):
        """
        Entry 성공 시 _entry_signal_components가 pending_order["signal_components"]와 동일한지 검증.
        """
        orchestrator = _make_orchestrator_for_sell_signal(
            ma_slope_pct=0.05, atr_percentile=40.0
        )
        result = orchestrator.run_tick()

        assert result.entry_blocked is False
        pending_components = orchestrator.pending_order.get("signal_components")
        assert orchestrator._entry_signal_components == pending_components

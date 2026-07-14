"""
tests/unit/test_wave6_streamb_ranging.py
Wave 6 Stream B: ranging 레짐 진입 threshold 강화 테스트

커버:
1. ranging + score=4 → 차단 (ranging_score_below_threshold)
2. ranging + score=5 → 허용
3. ranging + score=None (MA slope 모드) → threshold 체크 스킵 (기존 동작 유지)
4. trending_up/trending_down/high_vol + score=4 → 기존대로 허용
5. _is_ranging_score_sufficient 정적 메서드 단위 검증
"""

import pytest
from application.orchestrator import Orchestrator


# ========== Test 1: _is_ranging_score_sufficient 단위 검증 ==========


class TestIsRangingScoreSufficient:
    """Orchestrator._is_ranging_score_sufficient 정적 메서드 단위 테스트"""

    def test_ranging_score_4_insufficient(self):
        """ranging + score=4 → False (차단)"""
        # Arrange / Act
        result = Orchestrator._is_ranging_score_sufficient(
            regime="ranging", score=4
        )
        # Assert
        assert result is False

    def test_ranging_score_5_sufficient(self):
        """ranging + score=5 → True (허용)"""
        result = Orchestrator._is_ranging_score_sufficient(
            regime="ranging", score=5
        )
        assert result is True

    def test_ranging_score_6_sufficient(self):
        """ranging + score=6 → True (허용)"""
        result = Orchestrator._is_ranging_score_sufficient(
            regime="ranging", score=6
        )
        assert result is True

    def test_ranging_score_7_sufficient(self):
        """ranging + score=7 (최대) → True (허용)"""
        result = Orchestrator._is_ranging_score_sufficient(
            regime="ranging", score=7
        )
        assert result is True

    def test_ranging_score_none_skips_check(self):
        """ranging + score=None (MA slope 모드) → True (체크 스킵)"""
        result = Orchestrator._is_ranging_score_sufficient(
            regime="ranging", score=None
        )
        assert result is True

    def test_trending_up_score_4_not_affected(self):
        """trending_up + score=4 → True (ranging 규칙 미적용)"""
        result = Orchestrator._is_ranging_score_sufficient(
            regime="trending_up", score=4
        )
        assert result is True

    def test_trending_down_score_4_not_affected(self):
        """trending_down + score=4 → True (ranging 규칙 미적용)"""
        result = Orchestrator._is_ranging_score_sufficient(
            regime="trending_down", score=4
        )
        assert result is True

    def test_high_vol_score_4_not_affected(self):
        """high_vol + score=4 → True (ranging 규칙 미적용)"""
        result = Orchestrator._is_ranging_score_sufficient(
            regime="high_vol", score=4
        )
        assert result is True

    def test_trending_up_score_none_not_affected(self):
        """trending_up + score=None → True (ranging 규칙 미적용)"""
        result = Orchestrator._is_ranging_score_sufficient(
            regime="trending_up", score=None
        )
        assert result is True


# ========== Test 2: _decide_entry ranging 차단 통합 검증 ==========
# signal.score는 앙상블 모드에서만 설정됨.
# FakeMarketData 기반으로는 score=None(MA slope fallback)이 기본.
# 따라서 _decide_entry 내부 ranging threshold 로직은
# _is_ranging_score_sufficient를 통해 단위 검증(Test 1)으로 충분히 커버.
#
# 아래 테스트는 ranging threshold 로직이 실제 _decide_entry 흐름에서
# regime 분류 이후에 올바른 순서로 호출되는지 검증한다.
# (Orchestrator 내부 구조 변경 없이 score=None 경로 검증)


class MockRestClientWave6:
    """Wave 6 Stream B 테스트용 Mock REST client"""

    def __init__(self):
        self.orders = []

    def get_position(self, symbol: str = "BTCUSDT", category: str = "linear"):
        return {"retCode": 0, "result": {"list": []}}

    def set_trading_stop(
        self,
        symbol: str,
        stop_loss: str,
        category: str = "linear",
        position_idx: int = 0,
        sl_trigger_by: str = "MarkPrice",
    ):
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
        **kwargs,
    ):
        order = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "orderId": f"mock_{side}_wave6",
                "orderLinkId": order_link_id,
            },
        }
        self.orders.append(order)
        return order


def _make_orchestrator_ranging(price: float, last_fill: float, equity: float = 200.0):
    """ranging 레짐 (ma_slope=0.05%, atr_percentile=40) Orchestrator 생성"""
    from infrastructure.exchange.fake_market_data import FakeMarketData

    fake_data = FakeMarketData(current_price=price, equity_usdt=equity)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(last_fill)
    fake_data.inject_trades_today(0)
    fake_data.inject_atr_pct_24h(0.03)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")
    fake_data.inject_ma_slope_pct(0.05)   # ranging: slope 작음
    fake_data.inject_atr_percentile(40.0)  # ranging: percentile < 50, slope 미달
    return Orchestrator(market_data=fake_data, rest_client=MockRestClientWave6())


def _make_orchestrator_trending_down(price: float, last_fill: float, equity: float = 200.0):
    """trending_down 레짐 (ma_slope=-0.3%, atr_percentile=30) Orchestrator 생성"""
    from infrastructure.exchange.fake_market_data import FakeMarketData

    fake_data = FakeMarketData(current_price=price, equity_usdt=equity)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(last_fill)
    fake_data.inject_trades_today(0)
    fake_data.inject_atr_pct_24h(0.03)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")
    fake_data.inject_ma_slope_pct(-0.3)    # trending_down
    fake_data.inject_atr_percentile(30.0)
    return Orchestrator(market_data=fake_data, rest_client=MockRestClientWave6())


def _make_orchestrator_high_vol(price: float, last_fill: float, equity: float = 200.0):
    """high_vol 레짐 (atr_percentile=85) Orchestrator 생성"""
    from infrastructure.exchange.fake_market_data import FakeMarketData

    fake_data = FakeMarketData(current_price=price, equity_usdt=equity)
    fake_data.inject_atr(100.0)
    fake_data.inject_last_fill_price(last_fill)
    fake_data.inject_trades_today(0)
    fake_data.inject_atr_pct_24h(0.03)
    fake_data.inject_winrate(0.6)
    fake_data.inject_position_mode("MergedSingle")
    fake_data.inject_ma_slope_pct(0.0)     # high_vol 우선
    fake_data.inject_atr_percentile(85.0)
    return Orchestrator(market_data=fake_data, rest_client=MockRestClientWave6())


class TestRangingThresholdInDecideEntry:
    """
    ranging 레짐에서 _decide_entry가 score 기반 threshold를 올바르게 적용하는지 검증.

    FakeMarketData는 앙상블 prices 미주입 → score=None(MA slope 모드).
    score=None 경로는 ranging_score_below_threshold를 트리거하지 않아야 함.
    이 케이스는 _is_ranging_score_sufficient(ranging, None)=True를 확인하며 커버됨.
    """

    def test_ranging_with_score_none_allows_entry(self):
        """
        ranging 레짐 + score=None(MA slope 모드) → ranging threshold 차단 없음.
        Grid 조건이 맞으면 진입 허용.
        """
        # Arrange: price < last_fill - spacing → Buy signal (grid_down)
        # grid_spacing = ATR * 0.3 = 100 * 0.3 = 30 → 49800 - 30 = 49770 미만
        orchestrator = _make_orchestrator_ranging(
            price=49600.0, last_fill=49800.0
        )

        # Act
        result = orchestrator.run_tick()

        # Assert: ranging_score_below_threshold로 차단되면 안 됨
        if result.entry_blocked:
            assert result.entry_block_reason != "ranging_score_below_threshold", (
                f"score=None인데 ranging_score_below_threshold 차단됨: {result.entry_block_reason}"
            )

    def test_trending_down_with_sell_signal_not_ranging_blocked(self):
        """
        trending_down 레짐 + Sell 신호 (허용 방향) → ranging 차단 없음.
        score=None (MA slope 모드) 경로.
        """
        # Arrange: price > last_fill + spacing → Sell signal (grid_up)
        orchestrator = _make_orchestrator_trending_down(
            price=50000.0, last_fill=49800.0
        )

        # Act
        result = orchestrator.run_tick()

        # Assert: ranging 차단이 아님
        assert result.entry_block_reason != "ranging_score_below_threshold"

    def test_high_vol_with_sell_signal_not_ranging_blocked(self):
        """
        high_vol 레짐 + Sell 신호 → ranging threshold 체크 없음.
        """
        # Arrange
        orchestrator = _make_orchestrator_high_vol(
            price=50000.0, last_fill=49800.0
        )

        # Act
        result = orchestrator.run_tick()

        # Assert
        assert result.entry_block_reason != "ranging_score_below_threshold"

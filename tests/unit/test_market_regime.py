"""
tests/unit/test_market_regime.py
Market Regime Analyzer Unit Tests

Purpose:
- Kline 데이터 → MA slope 계산 검증
- Regime 분류 검증 (trending_up/down/ranging/high_vol)

SSOT:
- docs/plans/task_plan.md Phase 12a-2
- docs/specs/account_builder_policy.md (Entry Flow - Market Regime)
"""

import pytest
from typing import List

from application.market_regime import MarketRegimeAnalyzer, Kline


class TestMarketRegimeMASlope:
    """MA slope 계산"""

    def test_calculate_ma_slope_uptrend(self):
        """MA slope 계산 (상승 추세)"""
        # Arrange
        analyzer = MarketRegimeAnalyzer(ma_period=5)

        # 상승 추세 (50000 → 50400)
        klines = [
            Kline(close=50000.0),
            Kline(close=50100.0),
            Kline(close=50200.0),
            Kline(close=50300.0),
            Kline(close=50400.0),
        ]

        # Act
        ma_slope_pct = analyzer.calculate_ma_slope(klines)

        # Assert
        # MA(5) = (50000 + 50100 + 50200 + 50300 + 50400) / 5 = 50200
        # Previous MA(4) = (50000 + 50100 + 50200 + 50300) / 4 = 50150
        # Slope = (50200 - 50150) / 50150 * 100 ≈ 0.1% (positive)
        assert ma_slope_pct > 0
        assert 0.05 < ma_slope_pct < 0.15  # ~0.1%

    def test_calculate_ma_slope_downtrend(self):
        """MA slope 계산 (하락 추세)"""
        # Arrange
        analyzer = MarketRegimeAnalyzer(ma_period=5)

        # 하락 추세 (50400 → 50000)
        klines = [
            Kline(close=50400.0),
            Kline(close=50300.0),
            Kline(close=50200.0),
            Kline(close=50100.0),
            Kline(close=50000.0),
        ]

        # Act
        ma_slope_pct = analyzer.calculate_ma_slope(klines)

        # Assert
        assert ma_slope_pct < 0  # Negative slope

    def test_calculate_ma_slope_flat(self):
        """MA slope 계산 (횡보)"""
        # Arrange
        analyzer = MarketRegimeAnalyzer(ma_period=5)

        # 횡보 (동일 가격)
        klines = [
            Kline(close=50000.0),
            Kline(close=50000.0),
            Kline(close=50000.0),
            Kline(close=50000.0),
            Kline(close=50000.0),
        ]

        # Act
        ma_slope_pct = analyzer.calculate_ma_slope(klines)

        # Assert
        assert ma_slope_pct == pytest.approx(0.0, abs=1e-6)  # ~0%


class TestMarketRegimeClassification:
    """Market regime 분류"""

    def test_classify_regime_trending_up(self):
        """Regime 분류: trending_up"""
        # Arrange
        analyzer = MarketRegimeAnalyzer()

        # Act
        regime = analyzer.classify_regime(ma_slope_pct=0.5, atr_percentile=40.0)

        # Assert
        # ma_slope > 0.2% → trending_up
        assert regime == "trending_up"

    def test_classify_regime_trending_down(self):
        """Regime 분류: trending_down"""
        # Arrange
        analyzer = MarketRegimeAnalyzer()

        # Act
        regime = analyzer.classify_regime(ma_slope_pct=-0.5, atr_percentile=40.0)

        # Assert
        # ma_slope < -0.2% → trending_down
        assert regime == "trending_down"

    def test_classify_regime_ranging(self):
        """Regime 분류: ranging"""
        # Arrange
        analyzer = MarketRegimeAnalyzer()

        # Act
        regime = analyzer.classify_regime(ma_slope_pct=0.05, atr_percentile=30.0)

        # Assert
        # |ma_slope| < 0.2% and atr_percentile < 70 → ranging
        assert regime == "ranging"

    def test_classify_regime_high_vol(self):
        """Regime 분류: high_vol"""
        # Arrange
        analyzer = MarketRegimeAnalyzer()

        # Act
        regime = analyzer.classify_regime(ma_slope_pct=0.05, atr_percentile=80.0)

        # Assert
        # atr_percentile > 70 → high_vol (ATR 기준 우선)
        assert regime == "high_vol"

    def test_classify_regime_boundary(self):
        """Regime 분류: 경계값 테스트"""
        # Arrange
        analyzer = MarketRegimeAnalyzer()

        # Act & Assert
        # ma_slope = 0.2% (경계)
        regime1 = analyzer.classify_regime(ma_slope_pct=0.2, atr_percentile=50.0)
        assert regime1 in ["trending_up", "ranging"]  # 구현에 따라 다를 수 있음

        # atr_percentile = 70% (경계)
        regime2 = analyzer.classify_regime(ma_slope_pct=0.1, atr_percentile=70.0)
        assert regime2 in ["ranging", "high_vol"]  # 구현에 따라 다를 수 있음

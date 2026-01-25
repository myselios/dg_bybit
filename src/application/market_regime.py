"""
src/application/market_regime.py
Market Regime Analyzer — Kline → Regime Classification

Purpose:
- Kline 데이터를 받아 MA slope 계산
- Market regime 분류 (trending_up/down/ranging/high_vol)

Design:
- MA slope: SMA 기반 추세 강도 계산
- Regime 분류: MA slope + ATR percentile 조합
- Stateless calculator (입력 데이터 → 분류 결과)

SSOT:
- docs/plans/task_plan.md Phase 12a-2
- docs/specs/account_builder_policy.md Section 11 (Entry Flow)
"""

from dataclasses import dataclass
from typing import List


@dataclass
class Kline:
    """
    Kline 정보 (캔들스틱)

    Attributes:
        close: 종가 (USD)
        high: 고가 (USD, optional)
        low: 저가 (USD, optional)
    """
    close: float
    high: float = 0.0
    low: float = 0.0


class MarketRegimeAnalyzer:
    """
    Market Regime Analyzer — Kline → Regime classification

    역할:
    - MA slope 계산 (SMA 기반 추세 강도)
    - Market regime 분류 (trending_up/down/ranging/high_vol)

    Regime 분류 규칙:
    - trending_up: ma_slope > 0.2%
    - trending_down: ma_slope < -0.2%
    - high_vol: atr_percentile > 70
    - ranging: |ma_slope| <= 0.2% and atr_percentile <= 70
    """

    def __init__(
        self,
        ma_period: int = 20,
        trend_threshold_pct: float = 0.2,
        high_vol_threshold_percentile: float = 70.0
    ):
        """
        Market Regime Analyzer 초기화

        Args:
            ma_period: MA 계산 기간 (default: 20)
            trend_threshold_pct: 추세 판단 임계값 (%, default: 0.2)
            high_vol_threshold_percentile: 고변동성 판단 임계값 (percentile, default: 70.0)
        """
        self.ma_period = ma_period
        self.trend_threshold_pct = trend_threshold_pct
        self.high_vol_threshold_percentile = high_vol_threshold_percentile

    def calculate_ma_slope(self, klines: List[Kline]) -> float:
        """
        MA slope 계산 (SMA 기반)

        계산 방식:
        1. 최근 N개 kline으로 현재 MA 계산
        2. 최근 N-1개 kline으로 이전 MA 계산
        3. Slope = (current_ma - previous_ma) / previous_ma * 100 (%)

        Args:
            klines: Kline 리스트 (최소 ma_period개 필요)

        Returns:
            float: MA slope (%, 양수=상승, 음수=하락, 0=횡보)

        Raises:
            ValueError: klines 데이터가 부족한 경우
        """
        if len(klines) < self.ma_period:
            raise ValueError(
                f"Insufficient kline data: {len(klines)} < {self.ma_period}"
            )

        # 현재 MA (최근 N개)
        current_closes = [kline.close for kline in klines[-self.ma_period:]]
        current_ma = sum(current_closes) / len(current_closes)

        # 이전 MA (최근 N-1개, 1개 이전부터)
        previous_closes = [kline.close for kline in klines[-(self.ma_period + 1):-1]]
        previous_ma = sum(previous_closes) / len(previous_closes)

        # Slope 계산 (%)
        if previous_ma == 0:
            return 0.0

        slope_pct = (current_ma - previous_ma) / previous_ma * 100.0

        return slope_pct

    def classify_regime(
        self,
        ma_slope_pct: float,
        atr_percentile: float
    ) -> str:
        """
        Market regime 분류

        분류 규칙:
        1. atr_percentile > high_vol_threshold → "high_vol" (우선순위 1)
        2. ma_slope > trend_threshold → "trending_up"
        3. ma_slope < -trend_threshold → "trending_down"
        4. 그 외 → "ranging"

        Args:
            ma_slope_pct: MA slope (%)
            atr_percentile: ATR percentile (0~100)

        Returns:
            str: Regime 분류 ("trending_up", "trending_down", "ranging", "high_vol")
        """
        # 1. ATR 기준 고변동성 판단 (우선순위 1)
        if atr_percentile > self.high_vol_threshold_percentile:
            return "high_vol"

        # 2. MA slope 기준 추세 판단
        if ma_slope_pct > self.trend_threshold_pct:
            return "trending_up"
        elif ma_slope_pct < -self.trend_threshold_pct:
            return "trending_down"
        else:
            return "ranging"

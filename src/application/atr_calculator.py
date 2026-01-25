"""
src/application/atr_calculator.py
ATR (Average True Range) Calculator

Purpose:
- Kline 데이터 → ATR 계산
- ATR percentile 계산 (rolling 100-period)
- Grid spacing 계산 (Entry signal generation용)

SSOT:
- docs/plans/task_plan.md Phase 12a-2 (ATR Calculator)
- Grid Trading 전략: ATR 기반 동적 Grid spacing
"""

from dataclasses import dataclass
from typing import List


@dataclass
class Kline:
    """
    Kline (Candlestick) 데이터

    Fields:
        high: 최고가
        low: 최저가
        close: 종가
    """
    high: float
    low: float
    close: float


class ATRCalculator:
    """
    ATR Calculator

    역할:
    - 14-period ATR 계산 (True Range의 EMA)
    - ATR percentile 계산 (rolling 100-period)
    - Grid spacing 계산 (ATR * multiplier)
    """

    def __init__(self, period: int = 14, default_multiplier: float = 0.5):
        """
        ATR Calculator 초기화

        Args:
            period: ATR period (기본: 14)
            default_multiplier: Grid spacing 기본 multiplier (기본: 0.5)
        """
        self.period = period
        self.default_multiplier = default_multiplier

    def calculate_true_range(self, current_kline: Kline, previous_close: float) -> float:
        """
        True Range 계산

        TR = max(H-L, |H-PC|, |PC-L|)
        where H=High, L=Low, PC=Previous Close

        Args:
            current_kline: 현재 Kline
            previous_close: 이전 종가

        Returns:
            float: True Range
        """
        high_low = current_kline.high - current_kline.low
        high_prev_close = abs(current_kline.high - previous_close)
        prev_close_low = abs(previous_close - current_kline.low)

        return max(high_low, high_prev_close, prev_close_low)

    def calculate_atr(self, klines: List[Kline]) -> float:
        """
        14-period ATR 계산

        ATR = EMA of True Range (14-period)

        Args:
            klines: Kline 데이터 리스트 (최소 period+1개 필요)

        Returns:
            float: ATR 값

        Raises:
            ValueError: Kline 데이터 부족
        """
        if len(klines) < self.period + 1:
            raise ValueError(
                f"Insufficient kline data: {len(klines)} < {self.period + 1}"
            )

        # True Range 계산
        true_ranges = []
        for i in range(1, len(klines)):
            tr = self.calculate_true_range(klines[i], klines[i-1].close)
            true_ranges.append(tr)

        # ATR 계산 (EMA of True Range)
        # 첫 번째 ATR = 첫 period개의 평균
        first_atr = sum(true_ranges[:self.period]) / self.period
        atr = first_atr

        # 나머지는 EMA 방식으로 계산
        multiplier = 2.0 / (self.period + 1)
        for i in range(self.period, len(true_ranges)):
            atr = (true_ranges[i] * multiplier) + (atr * (1 - multiplier))

        return atr

    def calculate_atr_percentile(
        self, current_atr: float, atr_history: List[float]
    ) -> float:
        """
        ATR percentile 계산 (rolling 100-period)

        현재 ATR이 과거 ATR history에서 몇 percentile에 위치하는지 계산

        Args:
            current_atr: 현재 ATR 값
            atr_history: 과거 ATR 값 리스트 (최대 100개)

        Returns:
            float: Percentile (0~100)
        """
        if not atr_history:
            return 50.0  # Default

        # current_atr보다 작은 ATR 개수 계산
        count_below = sum(1 for atr in atr_history if atr < current_atr)

        # Percentile 계산
        percentile = (count_below / len(atr_history)) * 100.0

        return percentile

    def calculate_grid_spacing(
        self, atr: float, multiplier: float = None
    ) -> float:
        """
        Grid spacing 계산

        Grid spacing = ATR * multiplier

        Args:
            atr: ATR 값
            multiplier: Multiplier (기본: self.default_multiplier)

        Returns:
            float: Grid spacing (USD)
        """
        if multiplier is None:
            multiplier = self.default_multiplier

        return atr * multiplier

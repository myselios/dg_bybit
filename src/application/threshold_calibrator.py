"""
src/application/threshold_calibrator.py
동적 T_TREND 임계값 보정 — 실제 ma_slope 분포 기반

Purpose:
- 하드코딩된 T_TREND(0.4%)가 실제 ma_slope 분포보다 지나치게 높아 진입 신호 영구 차단
- 실제 kline 데이터의 ma_slope 분포를 측정하여 적절한 T_TREND 산출
- T_RANGE_ENTRY = T_TREND * 0.25 (Range regime 진입 허용 임계값)

Design:
- 500개 kline 기준 ma_slope 절댓값의 85th percentile → T_TREND
- MIN_T_TREND = 0.005% clamp (과잉 진입 방지)
"""

from dataclasses import dataclass
from typing import List

from application.market_regime import Kline, MarketRegimeAnalyzer


@dataclass(frozen=True)
class ThresholdConfig:
    """동적 임계값 설정"""
    t_trend: float        # MA slope >= t_trend → Trend regime
    t_range_entry: float  # MA slope >= t_range_entry → Range 진입 허용


MIN_T_TREND = 0.005  # 최소 clamp (과잉 진입 방지, 단위: %)

# kline 데이터 없이 calibration 불가 시 사용하는 안전 기본값
# 실측 ma_slope P99 = 0.04% 기반 → 0.05%로 설정 (T_TREND=0.4% 대비 8배 낮음)
DEFAULT_THRESHOLD_CONFIG = ThresholdConfig(t_trend=0.05, t_range_entry=0.0125)


class ThresholdCalibrator:
    """
    동적 임계값 보정기

    실제 ma_slope 분포에서 percentile 기반으로 T_TREND를 산출한다.

    Args:
        ma_period: MA 계산 기간 (default: 20)
        percentile: T_TREND 기준 percentile (default: 85.0)
    """

    def __init__(self, ma_period: int = 20, percentile: float = 85.0):
        self._ma_period = ma_period
        self._percentile = percentile
        self._analyzer = MarketRegimeAnalyzer(ma_period=ma_period)

    def calibrate(self, klines: List[Kline]) -> ThresholdConfig:
        """
        kline 데이터 기반 임계값 보정

        Args:
            klines: Kline 리스트 (최소 ma_period + 1개 필요)

        Returns:
            ThresholdConfig: 보정된 임계값 (t_trend, t_range_entry)

        Raises:
            ValueError: klines 데이터가 부족한 경우
        """
        slopes = self._compute_slopes(klines)
        if not slopes:
            raise ValueError("klines 데이터가 부족합니다")

        abs_slopes = sorted(abs(s) for s in slopes)
        idx = int(len(abs_slopes) * self._percentile / 100.0)
        idx = min(idx, len(abs_slopes) - 1)

        t_trend = max(abs_slopes[idx], MIN_T_TREND)
        t_range_entry = t_trend * 0.25

        return ThresholdConfig(t_trend=t_trend, t_range_entry=t_range_entry)

    def _compute_slopes(self, klines: List[Kline]) -> List[float]:
        """
        kline 윈도우별 ma_slope 계산

        Args:
            klines: Kline 리스트

        Returns:
            List[float]: MA slope 목록

        Raises:
            ValueError: 최소 kline 수 미달
        """
        required = self._ma_period + 1
        if len(klines) < required:
            raise ValueError(
                f"Insufficient klines: 최소 {required}개 필요, {len(klines)}개 제공"
            )

        slopes = []
        for i in range(required, len(klines) + 1):
            window = klines[:i]
            try:
                slope = self._analyzer.calculate_ma_slope(window)
                slopes.append(slope)
            except ValueError:
                continue

        return slopes

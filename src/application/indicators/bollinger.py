"""
src/application/indicators/bollinger.py

Bollinger Bands 계산기.
외부 라이브러리 없이 stdlib math만 사용.
"""

import math
from typing import Optional


def calculate_bollinger(
    prices: list[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> Optional[dict]:
    """
    Bollinger Bands 계산.

    Args:
        prices: 종가 리스트 (최소 period개 필요)
        period: 이동 평균 기간 (기본 20)
        std_dev: 표준편차 배수 (기본 2.0)

    Returns:
        dict: {"upper": float, "middle": float, "lower": float, "bandwidth": float}
        None: 데이터 부족 시
    """
    if len(prices) < period:
        return None

    window = prices[-period:]
    middle = sum(window) / period

    variance = sum((p - middle) ** 2 for p in window) / period
    sigma = math.sqrt(variance)

    upper = middle + std_dev * sigma
    lower = middle - std_dev * sigma
    bandwidth = upper - lower

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "bandwidth": bandwidth,
    }

"""
src/application/indicators/rsi.py

Wilder RSI (Relative Strength Index) 계산기.
외부 라이브러리 없이 stdlib만 사용.
"""

from typing import Optional


def calculate_rsi(prices: list[float], period: int = 14) -> Optional[float]:
    """
    Wilder RSI 계산.

    Args:
        prices: 종가 리스트 (최소 period+1개 필요)
        period: RSI 계산 기간 (기본 14)

    Returns:
        0~100 사이 RSI 값. 데이터 부족 시 None.
    """
    if len(prices) < period + 1:
        return None

    # 변화량 계산
    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

    # 첫 avg_gain, avg_loss: 첫 period개 변화량 단순 평균
    first_gains = [c for c in changes[:period] if c > 0]
    first_losses = [-c for c in changes[:period] if c < 0]

    avg_gain = sum(first_gains) / period
    avg_loss = sum(first_losses) / period

    # 이후 Wilder 지수이동평균 적용
    for change in changes[period:]:
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

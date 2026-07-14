"""
src/application/indicators/macd.py

MACD (Moving Average Convergence/Divergence) 계산기.
외부 라이브러리 없이 stdlib만 사용.
"""

from typing import Optional


def _ema(prices: list[float], period: int) -> list[float]:
    """지수이동평균(EMA) 계산. 최소 period개 필요."""
    if len(prices) < period:
        return []

    k = 2.0 / (period + 1)
    ema_values = []
    # 첫 번째 EMA는 첫 period개의 단순 평균
    first_ema = sum(prices[:period]) / period
    ema_values.append(first_ema)

    for price in prices[period:]:
        ema_values.append(price * k + ema_values[-1] * (1.0 - k))

    return ema_values


def calculate_macd(
    prices: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Optional[dict]:
    """
    MACD 계산.

    Args:
        prices: 종가 리스트 (최소 slow+signal개 필요)
        fast: 단기 EMA 기간 (기본 12)
        slow: 장기 EMA 기간 (기본 26)
        signal: 시그널 라인 기간 (기본 9)

    Returns:
        dict: {"macd": float, "signal": float, "histogram": float, "crossover": str}
              crossover: "bullish" | "bearish" | "none"
        None: 데이터 부족 시
    """
    if len(prices) < slow + signal:
        return None

    fast_ema = _ema(prices, fast)
    slow_ema = _ema(prices, slow)

    if not fast_ema or not slow_ema:
        return None

    # MACD line = fast_ema - slow_ema (같은 시점 기준으로 정렬)
    # fast_ema는 prices[fast-1:]부터, slow_ema는 prices[slow-1:]부터 시작
    offset = slow - fast
    if offset >= len(fast_ema):
        return None

    macd_line = [fast_ema[i + offset] - slow_ema[i] for i in range(len(slow_ema))]

    if len(macd_line) < signal:
        return None

    signal_line = _ema(macd_line, signal)
    if not signal_line:
        return None

    # 현재(마지막) 값
    current_macd = macd_line[-1]
    current_signal = signal_line[-1]
    current_histogram = current_macd - current_signal

    # Crossover 판정: 이전 값과 비교
    crossover = "none"
    if len(signal_line) >= 2 and len(macd_line) >= 2:
        # signal_line의 인덱스와 macd_line 정렬
        sl_offset = len(macd_line) - len(signal_line)
        if sl_offset >= 1:
            prev_macd = macd_line[-(len(signal_line) + 1)]
            prev_signal = signal_line[-2] if len(signal_line) >= 2 else current_signal

            prev_diff = prev_macd - prev_signal
            curr_diff = current_macd - current_signal

            if prev_diff <= 0 and curr_diff > 0:
                crossover = "bullish"
            elif prev_diff >= 0 and curr_diff < 0:
                crossover = "bearish"

    return {
        "macd": current_macd,
        "signal": current_signal,
        "histogram": current_histogram,
        "crossover": crossover,
    }

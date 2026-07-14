"""
src/application/indicators/breakout.py

Wave 4 Stream C: Breakout 신호 지표.
최근 N개 캔들의 highest high / lowest low 돌파 + 거래량 확인.

거짓 돌파 필터: volume > avg_volume * VOLUME_MULTIPLIER 조건 필수.
"""

_LOOKBACK = 20
_VOLUME_MULTIPLIER = 1.5
_MIN_DATA = _LOOKBACK + 1  # highs/lows 20개 + 현재 가격 1개


def calculate_breakout(
    prices: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    lookback: int = _LOOKBACK,
    volume_multiplier: float = _VOLUME_MULTIPLIER,
) -> dict:
    """
    Breakout 신호 계산.

    Args:
        prices: 종가 리스트. prices[-1]이 현재 종가.
        highs: 캔들 고가 리스트. 최근 lookback개 사용.
        lows: 캔들 저가 리스트. 최근 lookback개 사용.
        volumes: 거래량 리스트. volumes[-1]이 현재 거래량.
        lookback: 레인지 계산에 사용할 캔들 수 (기본 20).
        volume_multiplier: 거래량 확인 배수 (기본 1.5).

    Returns:
        dict with keys:
            long_breakout: bool — LONG 돌파 신호
            short_breakout: bool — SHORT 돌파 신호
            long_score: int — 0 또는 1
            short_score: int — 0 또는 1
            highest_high: float | None
            lowest_low: float | None
    """
    _empty = {
        "long_breakout": False,
        "short_breakout": False,
        "long_score": 0,
        "short_score": 0,
        "highest_high": None,
        "lowest_low": None,
    }

    # 데이터 유효성 검사
    if (
        not prices
        or not highs
        or not lows
        or not volumes
        or len(highs) < lookback
        or len(lows) < lookback
        or len(prices) < 1
        or len(volumes) < lookback + 1
    ):
        return _empty

    current_close = prices[-1]
    current_volume = volumes[-1]

    # 최근 lookback개 캔들 레인지 (현재 캔들 제외: 돌파 판단 기준)
    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]
    highest_high = max(recent_highs)
    lowest_low = min(recent_lows)

    # 거래량 필터: 현재 volume > 직전 lookback개 평균 * multiplier
    hist_volumes = volumes[-(lookback + 1):-1]
    avg_volume = sum(hist_volumes) / lookback
    volume_ok = current_volume > avg_volume * volume_multiplier

    long_breakout = current_close > highest_high and volume_ok
    short_breakout = current_close < lowest_low and volume_ok

    return {
        "long_breakout": long_breakout,
        "short_breakout": short_breakout,
        "long_score": 1 if long_breakout else 0,
        "short_score": 1 if short_breakout else 0,
        "highest_high": highest_high,
        "lowest_low": lowest_low,
    }

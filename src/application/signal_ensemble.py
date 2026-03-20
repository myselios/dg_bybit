"""
src/application/signal_ensemble.py

Signal Intelligence Stream A: 6지표 앙상블 신호 엔진.

6지표:
  1. RSI (Wilder, period=14): 과매수/과매도 감지
  2. MACD (12/26/9): 모멘텀 방향 전환 감지
  3. Bollinger Bands (period=20, std=2): 가격 위치
  4. Volume Confirmation (period=20): 거래량 확인
  5. MA Slope: 추세 방향
  6. Breakout (period=20, vol_multiplier=1.5): 레인지 돌파 + 거래량 확인

점수 체계 (Wave 4 Stream A 완화):
  LONG  조건: rsi<35(+2), macd bullish cross or hist 3연속 양수(+1),
              price<=bb_lower*1.003(+1), volume(+1),
              ma_slope>t_trend(+1), breakout_long(+1) → 최대 7점
  SHORT 조건: rsi>65(+2), macd bearish cross or hist 3연속 음수(+1),
              price>=bb_upper*0.997(+1), volume(+1),
              ma_slope<-t_trend(+1), breakout_short(+1) → 최대 7점
  score >= 4 → 진입. 동점 처리: LONG 우선 (BTC 상승 바이어스).
  highs/lows 없으면 breakout_score=0으로 graceful fallback.
"""

from dataclasses import dataclass
from typing import Optional

from application.indicators.bollinger import calculate_bollinger
from application.indicators.breakout import calculate_breakout
from application.indicators.macd import calculate_macd
from application.indicators.rsi import calculate_rsi
from application.indicators.volume import is_volume_confirmed


def _macd_histogram_consecutive_direction(prices: list[float], n: int = 3) -> str:
    """MACD 히스토그램 최근 n개의 연속 방향 판정.

    Args:
        prices: 종가 리스트 (최소 35+n개 필요)
        n: 연속 방향 확인 개수 (기본 3)

    Returns:
        "positive" | "negative" | "mixed"
    """
    min_len = 35 + n
    if len(prices) < min_len:
        return "mixed"

    histograms = []
    for offset in range(n - 1, -1, -1):
        end = len(prices) - offset if offset > 0 else len(prices)
        result = calculate_macd(prices[:end])
        if result is None:
            return "mixed"
        histograms.append(result["histogram"])

    if all(h > 0 for h in histograms):
        return "positive"
    if all(h < 0 for h in histograms):
        return "negative"
    return "mixed"


@dataclass
class EnsembleSignal:
    """앙상블 신호 결과.

    Attributes:
        side: "Buy" | "Sell" | None
        score: 0~7 합산 점수
        components: 각 지표별 점수
            {"rsi": int, "macd": int, "bb": int, "volume": int, "ma_slope": int, "breakout": int}
        confidence: score / 7.0
    """

    side: Optional[str]
    score: int
    components: dict
    confidence: float


def calculate_ensemble_score(
    prices: list[float],
    volumes: list[float],
    ma_slope_pct: float,
    t_trend: float = 0.05,
    highs: Optional[list[float]] = None,
    lows: Optional[list[float]] = None,
) -> EnsembleSignal:
    """
    6지표 앙상블 점수 계산.

    Args:
        prices: 종가 리스트 (최소 26개 권장, 부족해도 crash 없음)
        volumes: 거래량 리스트 (최소 21개 권장)
        ma_slope_pct: MA slope % 값 (예: -0.5 = -0.5%)
        t_trend: 추세 판단 임계값 (기본 0.05%)
        highs: 캔들 고가 리스트 (None이면 breakout_score=0 graceful fallback)
        lows: 캔들 저가 리스트 (None이면 breakout_score=0 graceful fallback)

    Returns:
        EnsembleSignal: side/score/components/confidence
    """
    # 현재 가격 (마지막 값)
    current_price = prices[-1] if prices else 0.0

    # ── 1. RSI (완화: LONG < 35, SHORT > 65) ─────────────────
    rsi_val = calculate_rsi(prices, period=14) if len(prices) >= 15 else None
    long_rsi = 2 if (rsi_val is not None and rsi_val < 35) else 0
    short_rsi = 2 if (rsi_val is not None and rsi_val > 65) else 0

    # ── 2. MACD (크로스오버 or 히스토그램 3연속 방향) ──────────
    macd_result = calculate_macd(prices) if len(prices) >= 35 else None
    long_macd = 0
    short_macd = 0
    if macd_result:
        crossover = macd_result["crossover"]
        if crossover == "bullish":
            long_macd = 1
        elif crossover == "bearish":
            short_macd = 1
        else:
            # 보완 조건: histogram 3개 연속 같은 방향 (크로스오버 없어도 점수 부여)
            hist_dir = _macd_histogram_consecutive_direction(prices)
            if hist_dir == "positive":
                long_macd = 1
            elif hist_dir == "negative":
                short_macd = 1

    # ── 3. Bollinger Bands (완화: ±0.3% 이내 포함) ───────────
    bb_result = calculate_bollinger(prices, period=20) if len(prices) >= 20 else None
    long_bb = 0
    short_bb = 0
    if bb_result and current_price > 0:
        long_bb = 1 if current_price <= bb_result["lower"] * 1.003 else 0
        short_bb = 1 if current_price >= bb_result["upper"] * 0.997 else 0

    # ── 4. Volume ────────────────────────────────────────────
    vol_confirmed = is_volume_confirmed(volumes) if len(volumes) >= 21 else False
    vol_score = 1 if vol_confirmed else 0

    # ── 5. MA Slope ──────────────────────────────────────────
    long_slope = 1 if ma_slope_pct > t_trend else 0
    short_slope = 1 if ma_slope_pct < -t_trend else 0

    # ── 6. Breakout (highs/lows 없으면 0으로 graceful fallback) ──
    long_breakout_score = 0
    short_breakout_score = 0
    if highs is not None and lows is not None:
        bo = calculate_breakout(prices, highs, lows, volumes)
        long_breakout_score = bo["long_score"]
        short_breakout_score = bo["short_score"]

    # ── 합산 ─────────────────────────────────────────────────
    long_score = long_rsi + long_macd + long_bb + vol_score + long_slope + long_breakout_score
    short_score = short_rsi + short_macd + short_bb + vol_score + short_slope + short_breakout_score

    # ── 진입 결정 (score >= 4) ────────────────────────────────
    # 2026-03-20: backtest 결과 T=4 최적 (승률 12.05%, PnL -$6.51 vs T=3 -$19.07)
    # Wave 4 Stream C: 최대 점수 6→7 (breakout +1), ENTRY_THRESHOLD=4 유지
    entry_threshold = 4
    max_score = 7

    if long_score >= entry_threshold and long_score >= short_score:
        # 동점이면 LONG 우선 (BTC 상승 바이어스)
        side = "Buy"
        final_score = long_score
        components = {
            "rsi": long_rsi,
            "macd": long_macd,
            "bb": long_bb,
            "volume": vol_score,
            "ma_slope": long_slope,
            "breakout": long_breakout_score,
        }
    elif short_score >= entry_threshold:
        side = "Sell"
        final_score = short_score
        components = {
            "rsi": short_rsi,
            "macd": short_macd,
            "bb": short_bb,
            "volume": vol_score,
            "ma_slope": short_slope,
            "breakout": short_breakout_score,
        }
    else:
        # 어느 쪽도 임계값 미달
        side = None
        final_score = max(long_score, short_score)
        # components는 더 높은 쪽 기준
        if long_score >= short_score:
            components = {
                "rsi": long_rsi,
                "macd": long_macd,
                "bb": long_bb,
                "volume": vol_score,
                "ma_slope": long_slope,
                "breakout": long_breakout_score,
            }
        else:
            components = {
                "rsi": short_rsi,
                "macd": short_macd,
                "bb": short_bb,
                "volume": vol_score,
                "ma_slope": short_slope,
                "breakout": short_breakout_score,
            }

    confidence = final_score / max_score

    return EnsembleSignal(
        side=side,
        score=final_score,
        components=components,
        confidence=confidence,
    )

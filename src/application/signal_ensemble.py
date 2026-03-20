"""
src/application/signal_ensemble.py

Signal Intelligence Stream A: 5지표 앙상블 신호 엔진.

5지표:
  1. RSI (Wilder, period=14): 과매수/과매도 감지
  2. MACD (12/26/9): 모멘텀 방향 전환 감지
  3. Bollinger Bands (period=20, std=2): 가격 위치
  4. Volume Confirmation (period=20): 거래량 확인
  5. MA Slope: 추세 방향

점수 체계:
  LONG  조건: rsi<30(+2), macd bullish cross(+1), price<=bb_lower(+1), volume(+1), ma_slope>t_trend(+1) → 최대 6점
  SHORT 조건: rsi>70(+2), macd bearish cross(+1), price>=bb_upper(+1), volume(+1), ma_slope<-t_trend(+1) → 최대 6점
  score >= 3 → 진입. 동점 처리: LONG 우선 (BTC 상승 바이어스).
"""

from dataclasses import dataclass
from typing import Optional

from application.indicators.rsi import calculate_rsi
from application.indicators.macd import calculate_macd
from application.indicators.bollinger import calculate_bollinger
from application.indicators.volume import is_volume_confirmed


@dataclass
class EnsembleSignal:
    """앙상블 신호 결과.

    Attributes:
        side: "Buy" | "Sell" | None
        score: 0~6 합산 점수
        components: 각 지표별 점수 {"rsi": int, "macd": int, "bb": int, "volume": int, "ma_slope": int}
        confidence: score / 6.0
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
) -> EnsembleSignal:
    """
    5지표 앙상블 점수 계산.

    Args:
        prices: 종가 리스트 (최소 26개 권장, 부족해도 crash 없음)
        volumes: 거래량 리스트 (최소 21개 권장)
        ma_slope_pct: MA slope % 값 (예: -0.5 = -0.5%)
        t_trend: 추세 판단 임계값 (기본 0.05%)

    Returns:
        EnsembleSignal: side/score/components/confidence
    """
    # 현재 가격 (마지막 값)
    current_price = prices[-1] if prices else 0.0

    # ── 1. RSI ──────────────────────────────────────────────
    rsi_val = calculate_rsi(prices, period=14) if len(prices) >= 15 else None
    long_rsi = 2 if (rsi_val is not None and rsi_val < 30) else 0
    short_rsi = 2 if (rsi_val is not None and rsi_val > 70) else 0

    # ── 2. MACD ─────────────────────────────────────────────
    macd_result = calculate_macd(prices) if len(prices) >= 35 else None
    crossover = macd_result["crossover"] if macd_result else "none"
    long_macd = 1 if crossover == "bullish" else 0
    short_macd = 1 if crossover == "bearish" else 0

    # ── 3. Bollinger Bands ───────────────────────────────────
    bb_result = calculate_bollinger(prices, period=20) if len(prices) >= 20 else None
    long_bb = 0
    short_bb = 0
    if bb_result and current_price > 0:
        long_bb = 1 if current_price <= bb_result["lower"] else 0
        short_bb = 1 if current_price >= bb_result["upper"] else 0

    # ── 4. Volume ────────────────────────────────────────────
    vol_confirmed = is_volume_confirmed(volumes) if len(volumes) >= 21 else False
    vol_score = 1 if vol_confirmed else 0

    # ── 5. MA Slope ──────────────────────────────────────────
    long_slope = 1 if ma_slope_pct > t_trend else 0
    short_slope = 1 if ma_slope_pct < -t_trend else 0

    # ── 합산 ─────────────────────────────────────────────────
    long_score = long_rsi + long_macd + long_bb + vol_score + long_slope
    short_score = short_rsi + short_macd + short_bb + vol_score + short_slope

    # ── 진입 결정 (score >= 3) ────────────────────────────────
    ENTRY_THRESHOLD = 3

    if long_score >= ENTRY_THRESHOLD and long_score >= short_score:
        # 동점이면 LONG 우선 (BTC 상승 바이어스)
        side = "Buy"
        final_score = long_score
        components = {
            "rsi": long_rsi,
            "macd": long_macd,
            "bb": long_bb,
            "volume": vol_score,
            "ma_slope": long_slope,
        }
    elif short_score >= ENTRY_THRESHOLD:
        side = "Sell"
        final_score = short_score
        components = {
            "rsi": short_rsi,
            "macd": short_macd,
            "bb": short_bb,
            "volume": vol_score,
            "ma_slope": short_slope,
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
            }
        else:
            components = {
                "rsi": short_rsi,
                "macd": short_macd,
                "bb": short_bb,
                "volume": vol_score,
                "ma_slope": short_slope,
            }

    confidence = final_score / 6.0

    return EnsembleSignal(
        side=side,
        score=final_score,
        components=components,
        confidence=confidence,
    )

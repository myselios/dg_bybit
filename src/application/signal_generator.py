"""
src/application/signal_generator.py

Phase 11: Signal Generator (Grid 전략)
Phase 13c: Regime-Aware Entry (Trend vs Range)

DoD:
- Grid-based signal generation (간단한 구현)
- ATR 기반 grid spacing 계산
- Last fill price 기반 grid level 결정
- Regime-aware initial entry (MA slope + Funding)
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from application.threshold_calibrator import ThresholdConfig

logger = logging.getLogger(__name__)

# ========== SSOT: 임계값 정의 (Phase 13c) ==========
# 단위 명확화: ma_slope_pct는 % 단위 (예: -0.5 = -0.5%)
T_TREND = 0.4  # MA slope >= 0.4% → Trend regime (2026-03-15: 0.5→0.4로 완화, 하루 이상 거래 0건으로 진입 빈도 확보)
T_RANGE_ENTRY = 0.4  # T_TREND와 동일 유지 = ranging 진입 차단
F_EXTREME = 0.01  # abs(funding) >= 0.01 (1%) → 극단 과열
# Conflict는 Range에서만 보류, Trend에서는 size 조절
# =================================================


@dataclass
class Signal:
    """
    거래 신호

    Attributes:
        side: Buy 또는 Sell
        price: 신호 발생 시점 가격
        qty: 거래 수량 (contracts)
        score: 앙상블 합산 점수 (0~6, None=MA slope 모드)
        components: 지표별 점수 {"rsi":int, "macd":int, "bb":int, "volume":int, "ma_slope":int}
    """

    side: str  # "Buy" or "Sell"
    price: float
    qty: int = 0
    score: Optional[int] = None
    components: Optional[dict] = None


def _determine_regime_with_threshold(ma_slope_pct: float, t_trend: float) -> Tuple[str, str]:
    """
    threshold 파라미터를 받는 내부 regime 판정 함수

    Args:
        ma_slope_pct: MA slope (% 단위)
        t_trend: 추세 판단 임계값

    Returns:
        (regime, direction)
    """
    if abs(ma_slope_pct) >= t_trend:
        direction = "up" if ma_slope_pct > 0 else "down"
        return ("trend", direction)
    return ("range", "neutral")


def determine_regime(ma_slope_pct: float) -> Tuple[str, str]:
    """
    Market regime 판정 (Trend vs Range)

    Args:
        ma_slope_pct: MA slope (% 단위, 예: -0.5 = -0.5%)

    Returns:
        (regime, direction):
        - ("trend", "up") if ma_slope_pct >= T_TREND
        - ("trend", "down") if ma_slope_pct <= -T_TREND
        - ("range", "neutral") otherwise
    """
    if abs(ma_slope_pct) >= T_TREND:
        direction = "up" if ma_slope_pct > 0 else "down"
        return ("trend", direction)
    else:
        return ("range", "neutral")


def calculate_grid_spacing(atr: float, multiplier: float = 2.0) -> float:
    """
    ATR 기반 grid spacing 계산

    Grid spacing = ATR * multiplier

    Args:
        atr: Average True Range
        multiplier: Grid spacing multiplier (기본 2.0)

    Returns:
        float: Grid spacing (USD)
    """
    return atr * multiplier


def generate_signal(
    current_price: float,
    last_fill_price: Optional[float],
    grid_spacing: float,
    qty: int = 0,
    funding_rate: float = 0.0001,
    ma_slope_pct: float = 0.0,
    threshold_config: Optional["ThresholdConfig"] = None,
    prices: Optional[list] = None,
    volumes: Optional[list] = None,
) -> Optional[Signal]:
    """
    Grid 전략 기반 신호 생성 (Phase 13c: Regime-Aware)

    규칙:
    - **앙상블 모드 (last_fill_price=None AND prices >= 26개)**: 5지표 앙상블로 첫 진입 결정
      - score >= 3 → 진입 (LONG/SHORT)
      - score 1~2 → Near-miss (DEBUG 로그 기록), 진입 없음
      - score 0 → 진입 없음
    - **Legacy 모드 (last_fill_price=None, prices 미제공)**: Regime-aware 방향 결정
      - Trend regime (abs(ma_slope) >= threshold_config.t_trend): MA slope 방향 우선
      - Range regime: Funding 극단값 참고 → 약한 방향성 → 완전 무방향(보류)
      - 충돌 처리: Range에서만 보류, Trend에서는 진입
    - Grid up: current_price >= last_fill_price + grid_spacing → Sell
    - Grid down: current_price <= last_fill_price - grid_spacing → Buy
    - 그 외: No signal

    Args:
        current_price: 현재 가격
        last_fill_price: 마지막 체결 가격 (None이면 FLAT 상태)
        grid_spacing: Grid 간격 (USD)
        qty: 거래 수량 (contracts, 기본 0)
        funding_rate: Funding rate (기본 0.0001 = 0.01%)
        ma_slope_pct: MA slope (% 단위, 기본 0.0)
        threshold_config: 동적 임계값 설정 (None이면 모듈 상수 T_TREND/T_RANGE_ENTRY 사용)
        prices: 앙상블용 종가 리스트 (26개 이상이면 앙상블 모드 활성화)
        volumes: 앙상블용 거래량 리스트

    Returns:
        Optional[Signal]: 신호 (없으면 None)
    """
    logger.debug(f"generate_signal: price={current_price}, lfp={last_fill_price}, gs={grid_spacing:.2f}, ma={ma_slope_pct}, fr={funding_rate}")

    # threshold_config 적용: 제공되면 동적 값 사용, 없으면 모듈 상수 fallback
    t_trend = threshold_config.t_trend if threshold_config is not None else T_TREND
    t_range_entry = threshold_config.t_range_entry if threshold_config is not None else T_RANGE_ENTRY

    # 앙상블 모드: prices >= 26개 제공 시 5지표 앙상블 신호로 첫 진입 결정
    _ENSEMBLE_MIN_PRICES = 26
    if (
        last_fill_price is None
        and prices is not None
        and len(prices) >= _ENSEMBLE_MIN_PRICES
    ):
        from application.signal_ensemble import calculate_ensemble_score

        ensemble = calculate_ensemble_score(
            prices=prices,
            volumes=volumes if volumes is not None else [],
            ma_slope_pct=ma_slope_pct,
            t_trend=t_trend,
        )
        logger.debug(
            f"Ensemble mode: side={ensemble.side}, score={ensemble.score}, "
            f"components={ensemble.components}"
        )
        if ensemble.side is not None:
            return Signal(
                side=ensemble.side,
                price=current_price,
                qty=qty,
                score=ensemble.score,
                components=ensemble.components,
            )
        # Near-miss logging: score > 0 but < 3 → diagnose why no trade fires
        if 0 < ensemble.score < 3:
            long_score = sum(v for v in ensemble.components.values() if v > 0)
            short_score = sum(abs(v) for v in ensemble.components.values() if v < 0)
            side_attempt = "Buy" if long_score >= short_score else "Sell"
            logger.debug(
                f"[Ensemble] Near-miss: score={ensemble.score}/6, "
                f"components={ensemble.components}, side_candidate={side_attempt}, "
                f"ma_slope={ma_slope_pct:.4f}%"
            )
        return None

    # 첫 진입: Regime-aware 방향 결정 (기존 legacy 모드)
    if last_fill_price is None:
        regime, direction = _determine_regime_with_threshold(ma_slope_pct, t_trend)

        if regime == "trend":
            # Trend regime: MA slope 방향 우선
            side = "Buy" if direction == "up" else "Sell"
            return Signal(side=side, price=current_price, qty=qty)

        else:
            # Range regime: 3단계 진입 판정
            # 1) Extreme funding → 역추세 진입 (최우선)
            if abs(funding_rate) >= F_EXTREME:
                side = "Sell" if funding_rate > 0 else "Buy"
                return Signal(side=side, price=current_price, qty=qty)

            # 2) 약한 방향성 → MA 방향 진입 (Grid 시작점 설정)
            if abs(ma_slope_pct) >= t_range_entry:
                side = "Buy" if ma_slope_pct > 0 else "Sell"
                return Signal(side=side, price=current_price, qty=qty)

            # 3) 완전 무방향 → 진입 보류
            return None

    # Grid up: 가격 상승 → Sell 신호 (강한 상승 추세에서는 SHORT 역추세 진입 차단)
    # 차단 기준은 하드코딩 T_TREND 사용 (동적 임계값은 첫 진입에만 적용)
    if current_price >= last_fill_price + grid_spacing:
        if ma_slope_pct >= T_TREND:
            logger.debug(f"Grid Sell blocked: strong uptrend ma_slope={ma_slope_pct:.4f}%")
            return None
        return Signal(side="Sell", price=current_price, qty=qty)

    # Grid down: 가격 하락 → Buy 신호 (강한 하락 추세에서는 LONG 역추세 진입 차단)
    # 차단 기준은 하드코딩 T_TREND 사용 (동적 임계값은 첫 진입에만 적용)
    if current_price <= last_fill_price - grid_spacing:
        if ma_slope_pct <= -T_TREND:
            logger.debug(f"Grid Buy blocked: strong downtrend ma_slope={ma_slope_pct:.4f}%")
            return None
        return Signal(side="Buy", price=current_price, qty=qty)

    # Grid 범위 내 → 신호 없음
    return None

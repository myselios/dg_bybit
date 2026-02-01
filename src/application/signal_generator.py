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

from dataclasses import dataclass
from typing import Optional, Tuple

# ========== SSOT: 임계값 정의 (Phase 13c) ==========
# 단위 명확화: ma_slope_pct는 % 단위 (예: -0.5 = -0.5%)
T_TREND = 0.5  # MA slope >= 0.5% → Trend regime
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
    """

    side: str  # "Buy" or "Sell"
    price: float
    qty: int = 0


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
) -> Optional[Signal]:
    """
    Grid 전략 기반 신호 생성 (Phase 13c: Regime-Aware)

    규칙:
    - **첫 진입 (last_fill_price=None)**: Regime-aware 방향 결정
      - Trend regime (abs(ma_slope) >= 0.5%): MA slope 방향 우선
      - Range regime (abs(ma_slope) < 0.5%): Funding 극단값 참고
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

    Returns:
        Optional[Signal]: 신호 (없으면 None)
    """
    # 첫 진입: Regime-aware 방향 결정
    if last_fill_price is None:
        regime, direction = determine_regime(ma_slope_pct)

        if regime == "trend":
            # Trend regime: MA slope 방향 우선
            side = "Buy" if direction == "up" else "Sell"
            return Signal(side=side, price=current_price, qty=qty)

        else:
            # Range regime: Funding 극단값만 허용
            if abs(funding_rate) < F_EXTREME:
                return None  # 과열 아님, 진입 보류

            # Funding 극단 → 역추세 진입
            side = "Sell" if funding_rate > 0 else "Buy"
            return Signal(side=side, price=current_price, qty=qty)

    # Grid up: 가격 상승 → Sell 신호
    if current_price >= last_fill_price + grid_spacing:
        return Signal(side="Sell", price=current_price, qty=qty)

    # Grid down: 가격 하락 → Buy 신호
    if current_price <= last_fill_price - grid_spacing:
        return Signal(side="Buy", price=current_price, qty=qty)

    # Grid 범위 내 → 신호 없음
    return None

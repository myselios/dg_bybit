"""
src/application/signal_generator.py

Phase 11: Signal Generator (Grid 전략)

DoD:
- Grid-based signal generation (간단한 구현)
- ATR 기반 grid spacing 계산
- Last fill price 기반 grid level 결정
"""

from dataclasses import dataclass
from typing import Optional


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
) -> Optional[Signal]:
    """
    Grid 전략 기반 신호 생성

    규칙:
    - Grid up: current_price >= last_fill_price + grid_spacing → Sell
    - Grid down: current_price <= last_fill_price - grid_spacing → Buy
    - 그 외: No signal

    Args:
        current_price: 현재 가격
        last_fill_price: 마지막 체결 가격 (None이면 FLAT 상태)
        grid_spacing: Grid 간격 (USD)
        qty: 거래 수량 (contracts, 기본 0)

    Returns:
        Optional[Signal]: 신호 (없으면 None)
    """
    # FLAT 상태 (last_fill_price가 None)면 grid 신호 생성 불가
    if last_fill_price is None:
        return None

    # Grid up: 가격 상승 → Sell 신호
    if current_price >= last_fill_price + grid_spacing:
        return Signal(side="Sell", price=current_price, qty=qty)

    # Grid down: 가격 하락 → Buy 신호
    if current_price <= last_fill_price - grid_spacing:
        return Signal(side="Buy", price=current_price, qty=qty)

    # Grid 범위 내 → 신호 없음
    return None

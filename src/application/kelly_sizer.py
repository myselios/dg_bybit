"""
src/application/kelly_sizer.py
Kelly Criterion position sizing (Adaptive Engine Stream B)

Purpose:
- Kelly formula 기반 최적 포지션 비율 계산
- 손실 중 / 데이터 부족 시 fallback 처리
- sizing.py의 loss_budget과 min() 취하여 보수적 선택

Formula:
  f = (p * b - q) / b
  where:
    b = avg_win_usd / avg_loss_usd  (payoff ratio)
    p = win_rate
    q = 1 - win_rate

SSOT:
- account_builder_policy.md: Stage params, max loss
- sizing.py: loss_budget 기반 sizing (kelly는 optional override)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class KellyParams:
    """
    Kelly Criterion 계산 입력 파라미터

    Attributes:
        win_rate: 승률 (0~1)
        avg_win_usd: 평균 수익 (USD, 양수)
        avg_loss_usd: 평균 손실 (USD, 양수)
        equity_usdt: 현재 자산 (USDT)
        max_fraction: Kelly 최대 비율 cap (기본 0.25 = 25%)
    """
    win_rate: float
    avg_win_usd: float
    avg_loss_usd: float
    equity_usdt: float
    max_fraction: float = 0.25


@dataclass(frozen=True)
class KellyResult:
    """
    Kelly Criterion 계산 결과 (불변)

    Attributes:
        fraction: Kelly 분수 (0~max_fraction)
        position_usdt: 권장 포지션 크기 (USDT) = equity * fraction
        mode: "kelly" | "fallback"
    """
    fraction: float
    position_usdt: float
    mode: str


def calculate_kelly(params: KellyParams) -> KellyResult:
    """
    Kelly Criterion 기반 최적 포지션 비율 계산

    Args:
        params: KellyParams

    Returns:
        KellyResult: fraction, position_usdt, mode

    Fallback 조건 (mode="fallback"):
    - win_rate < 0.1 → 불충분한 데이터 → fraction=0.1
    - avg_loss_usd = 0 → division by zero 방지 → fraction=0.1
    - Kelly < 0 (손실 중) → fraction=0.05 (최소 포지션)

    Cap:
    - fraction > max_fraction → max_fraction으로 클램프
    """
    # Fallback: 데이터 불충분 (승률 < 10%)
    if params.win_rate < 0.1:
        fraction = 0.1
        return KellyResult(
            fraction=fraction,
            position_usdt=params.equity_usdt * fraction,
            mode="fallback",
        )

    # Fallback: avg_loss = 0 (division by zero 방지)
    if params.avg_loss_usd <= 0:
        fraction = 0.1
        return KellyResult(
            fraction=fraction,
            position_usdt=params.equity_usdt * fraction,
            mode="fallback",
        )

    # Kelly formula
    b = params.avg_win_usd / params.avg_loss_usd  # payoff ratio
    p = params.win_rate
    q = 1.0 - p

    kelly_fraction = (p * b - q) / b

    # Negative Kelly → minimum position (손실 중)
    if kelly_fraction <= 0:
        fraction = 0.05
        return KellyResult(
            fraction=fraction,
            position_usdt=params.equity_usdt * fraction,
            mode="fallback",
        )

    # Cap at max_fraction (기본 25%)
    fraction = min(kelly_fraction, params.max_fraction)

    return KellyResult(
        fraction=fraction,
        position_usdt=params.equity_usdt * fraction,
        mode="kelly",
    )

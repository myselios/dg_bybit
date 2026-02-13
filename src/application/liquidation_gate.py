"""
src/application/liquidation_gate.py
Liquidation Distance Gate (FLOW Section 7.5)

Purpose:
- Sizing 완료 후 청산거리 검증 (Stop loss 전 청산 방지)
- 동적 기준: max(stop × multiplier, min_absolute)
- Fallback: API 실패 시 보수적 haircut

SSOT:
- FLOW.md Section 7.5: Liquidation Distance Gate
- Policy.md Section 5: Stage Parameters (liq_distance_min_pct)

Exports:
- calculate_liquidation_distance(): 청산거리 계산 (보수적 근사)
- check_liquidation_gate(): Gate 검증 + Fallback 규칙
"""

from dataclasses import dataclass


@dataclass
class LiquidationGateResult:
    """Liquidation gate 검증 결과"""
    allowed: bool
    reject_reason: str | None = None
    adjusted_contracts: int | None = None  # Haircut 적용 시 조정된 contracts
    haircut_applied: bool = False


# Stage별 동적 기준 (FLOW Section 7.5)
LIQ_DISTANCE_MULTIPLIER = {
    1: 4.0,  # Stage 1: stop × 4
    2: 3.5,  # Stage 2: stop × 3.5
    3: 3.0,  # Stage 3: stop × 3
}

MIN_ABSOLUTE_LIQ_DISTANCE = {
    1: 0.15,  # Stage 1: 최소 15%
    2: 0.15,  # Stage 2: 최소 15%
    3: 0.12,  # Stage 3: 최소 12%
}


def calculate_liquidation_distance(
    entry_price: float,
    contracts: int,
    leverage: float,
    direction: str,
    equity_usdt: float,
) -> float:
    """
    Liquidation distance 계산 (Bybit Linear USDT, 보수적 근사)

    FLOW Section 7.5:
        Bankruptcy Price (Simplified):
          LONG:  liq_price ≈ entry × leverage / (leverage + 1)
          SHORT: liq_price ≈ entry × leverage / (leverage - 1)

        Liquidation Distance:
          LONG:  (entry - liq_price) / entry
          SHORT: (liq_price - entry) / entry

    Args:
        entry_price: 진입가 (USDT)
        contracts: 계약 수량
        leverage: 레버리지
        direction: "LONG" or "SHORT"
        equity_usdt: 계좌 잔고 (USDT)

    Returns:
        liq_distance_pct: 청산거리 (0.0~1.0)
    """
    if direction == "LONG":
        # LONG: 청산가는 entry보다 낮음
        liq_price_approx = entry_price * leverage / (leverage + 1)
        liq_distance_pct = (entry_price - liq_price_approx) / entry_price
    elif direction == "SHORT":
        # SHORT: 청산가는 entry보다 높음
        liq_price_approx = entry_price * leverage / (leverage - 1)
        liq_distance_pct = (liq_price_approx - entry_price) / entry_price
    else:
        raise ValueError(f"Invalid direction: {direction}")

    return liq_distance_pct


def check_liquidation_gate(params, api_failure: bool = False) -> LiquidationGateResult:
    """
    Liquidation gate 검증 (FLOW Section 7.5)

    Gate 규칙:
        1. liq_distance 계산 (또는 API 조회)
        2. min_required = max(stop × multiplier, min_absolute)
        3. if liq_distance < min_required → REJECT
        4. Fallback (API 실패 시):
           - leverage > 3 → REJECT
           - stop > 5% → contracts × 0.8 (haircut)

    Args:
        params: LiquidationParams (entry, contracts, leverage, direction, equity, stop, stage)
        api_failure: API 실패 시뮬레이션 (테스트용)

    Returns:
        LiquidationGateResult (allowed, reject_reason, adjusted_contracts, haircut_applied)
    """
    # 1. Liquidation distance 계산 (API 실패가 아니면 계산)
    if api_failure:
        liq_distance_pct = None
    else:
        liq_distance_pct = calculate_liquidation_distance(
            entry_price=params.entry_price_usd,
            contracts=params.contracts,
            leverage=params.leverage,
            direction=params.direction,
            equity_usdt=params.equity_usdt,
        )

    # 2. 동적 기준 계산
    multiplier = LIQ_DISTANCE_MULTIPLIER.get(params.stage_id, 3.5)
    min_absolute = MIN_ABSOLUTE_LIQ_DISTANCE.get(params.stage_id, 0.15)
    min_required = max(params.stop_distance_pct * multiplier, min_absolute)

    # 3. Fallback 처리 (API 실패 시)
    if liq_distance_pct is None:
        # Fallback Rule 1: leverage > 3 → REJECT
        if params.leverage > 3.0:
            return LiquidationGateResult(
                allowed=False,
                reject_reason="leverage_too_high_without_liq_check",
            )

        # Fallback Rule 2: stop > 5% → haircut
        if params.stop_distance_pct > 0.05:
            adjusted_contracts = int(params.contracts * 0.8)
            return LiquidationGateResult(
                allowed=True,
                adjusted_contracts=adjusted_contracts,
                haircut_applied=True,
            )

        # Fallback Rule 3: 그 외는 PASS
        return LiquidationGateResult(allowed=True)

    # 4. Gate 검증 (liq_distance < min_required → REJECT)
    if liq_distance_pct < min_required:
        return LiquidationGateResult(
            allowed=False,
            reject_reason="liquidation_too_close",
        )

    # 5. PASS
    return LiquidationGateResult(allowed=True)

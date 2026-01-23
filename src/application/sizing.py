"""
src/application/sizing.py
Position sizing (FLOW Section 3.4, Policy Section 10)

Purpose:
- Contracts 계산 (loss budget 기반, Direction별 정확한 공식)
- Margin feasibility 검증 (BTC-denominated)
- Tick/Lot size 보정 + 재검증
- Min contracts 검증

SSOT:
- FLOW.md Section 3.4: Position Sizing (Direction별 정확한 공식)
- FLOW.md Section 3.4: Margin Calculation (BTC-denominated)
- FLOW.md Section 3.4: Tick/Lot Size 준수
- FLOW.md Section 7: Sizing Double-Check (Margin vs Loss)

Design Decisions:
- Direction별 정확한 공식 사용 (stop_distance >= 3%)
- 근사 공식은 사용하지 않음 (정확성 우선)
- Margin vs Loss budget: 둘 중 작은 값 선택
- Tick/Lot 보정 후 재검증 필수
"""

from dataclasses import dataclass
import math


@dataclass
class SizingResult:
    """
    Sizing 결과

    Attributes:
        contracts: 계산된 contracts (0이면 실패)
        reject_reason: 거절 사유 (contracts=0일 때만)
    """
    contracts: int
    reject_reason: str | None = None


def calculate_contracts(params) -> SizingResult:
    """
    Position sizing (loss budget + margin 제약)

    Args:
        params: SizingParams (test에서 정의)
            - max_loss_btc: 최대 손실 (BTC)
            - entry_price_usd: 진입가 (USD)
            - stop_distance_pct: Stop 거리 (pct, 예: 0.03 = 3%)
            - leverage: 레버리지 (예: 3.0)
            - equity_btc: 현재 equity (BTC)
            - fee_rate: 수수료율 (예: 0.0001)
            - direction: "LONG" or "SHORT"
            - qty_step: Lot size (예: 1)
            - tick_size: Tick size (예: 0.5)

    Returns:
        SizingResult: contracts + reject_reason

    Steps:
        1. Loss budget 기준 contracts 계산 (Direction별 정확한 공식)
        2. Margin 기준 contracts 계산
        3. min(loss_based, margin_based)
        4. Tick/Lot size 보정
        5. 보정 후 재검증 (margin feasibility)
        6. 최소 수량 검증

    FLOW Section 3.4, 7
    """
    # Step 1: Loss budget 기준 contracts 계산
    if params.direction == "LONG":
        # LONG: contracts = (max_loss_btc × entry × (1 - d)) / d
        contracts_from_loss = (
            params.max_loss_btc
            * params.entry_price_usd
            * (1 - params.stop_distance_pct)
        ) / params.stop_distance_pct
    else:  # SHORT
        # SHORT: contracts = (max_loss_btc × entry × (1 + d)) / d
        contracts_from_loss = (
            params.max_loss_btc
            * params.entry_price_usd
            * (1 + params.stop_distance_pct)
        ) / params.stop_distance_pct

    # Step 2: Margin 기준 contracts 계산
    # available_btc = equity_btc * 0.8 (80%만 사용, buffer)
    # max_position_value_btc = available_btc * leverage
    # contracts_from_margin = max_position_value_btc * entry_price
    available_btc = params.equity_btc * 0.8
    max_position_value_btc = available_btc * params.leverage
    contracts_from_margin = max_position_value_btc * params.entry_price_usd

    # Step 3: 둘 중 작은 값
    contracts = min(contracts_from_loss, contracts_from_margin)
    contracts = int(contracts)  # floor

    # Step 4: Tick/Lot size 보정
    contracts = int(contracts / params.qty_step) * params.qty_step

    # Step 5: 최소 수량 검증
    if contracts < params.qty_step:
        return SizingResult(contracts=0, reject_reason="qty_below_minimum")

    # Step 6: 보정 후 재검증 (margin feasibility)
    position_value_btc = contracts / params.entry_price_usd
    required_margin_btc = position_value_btc / params.leverage
    fee_buffer_btc = position_value_btc * params.fee_rate * 2

    if required_margin_btc + fee_buffer_btc > params.equity_btc:
        return SizingResult(contracts=0, reject_reason="margin_insufficient")

    # 성공
    return SizingResult(contracts=contracts, reject_reason=None)

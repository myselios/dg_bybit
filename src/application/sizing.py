"""
src/application/sizing.py
Position sizing (FLOW Section 3.4, Policy Section 10) — Linear USDT

Purpose:
- Qty/Contracts 계산 (loss budget 기반, Linear 공식)
- Margin feasibility 검증 (USDT-denominated)
- Tick/Lot size 보정 + 재검증
- Min contracts 검증

SSOT:
- FLOW.md Section 3.4: Position Sizing (Linear 공식)
- account_builder_policy.md Section 10: Position Sizing (Bybit Linear USDT)
- ADR-0002: Inverse to Linear USDT Migration

Design Decisions:
- Linear 공식: loss_usdt = qty * price * stop_distance_pct
- Bybit Linear BTCUSDT contract size: 0.001 BTC per contract
- USDT-denominated (환산 불필요)
- Margin vs Loss budget: 둘 중 작은 값 선택
- Tick/Lot 보정 후 재검증 필수
"""

from dataclasses import dataclass
import math


@dataclass
class SizingParams:
    """
    Sizing 파라미터 (Linear USDT)

    Attributes:
        max_loss_usdt: 최대 손실 (USDT)
        entry_price_usd: 진입가 (USD)
        stop_distance_pct: Stop 거리 (pct, 예: 0.03 = 3%)
        leverage: 레버리지 (예: 3.0)
        equity_usdt: 현재 equity (USDT)
        fee_rate: 수수료율 (예: 0.0001)
        direction: "LONG" or "SHORT" (Linear에서는 영향 없음, 호환성 유지)
        qty_step: Lot size (예: 1 contract)
        tick_size: Tick size (예: 0.5 USD)
        contract_size: Contract size in BTC (Bybit Linear BTCUSDT: 0.001 BTC)
    """
    max_loss_usdt: float
    entry_price_usd: float
    stop_distance_pct: float
    leverage: float
    equity_usdt: float
    fee_rate: float
    direction: str
    qty_step: int
    tick_size: float
    contract_size: float = 0.001  # Bybit Linear BTCUSDT default


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


def calculate_contracts(params: SizingParams) -> SizingResult:
    """
    Position sizing (loss budget + margin 제약) — Linear USDT

    Args:
        params: SizingParams
            - max_loss_usdt: 최대 손실 (USDT)
            - entry_price_usd: 진입가 (USD)
            - stop_distance_pct: Stop 거리 (pct, 예: 0.03 = 3%)
            - leverage: 레버리지 (예: 3.0)
            - equity_usdt: 현재 equity (USDT)
            - fee_rate: 수수료율 (예: 0.0001)
            - direction: "LONG" or "SHORT" (Linear에서는 영향 없음)
            - qty_step: Lot size (예: 1)
            - tick_size: Tick size (예: 0.5)
            - contract_size: Contract size in BTC (기본: 0.001)

    Returns:
        SizingResult: contracts + reject_reason

    Steps:
        1. Loss budget 기준 qty 계산 (Linear 공식)
        2. Margin 기준 qty 계산
        3. min(loss_based, margin_based)
        4. Qty → Contracts 변환 (contract_size 기준)
        5. Tick/Lot size 보정
        6. 보정 후 재검증 (margin feasibility)
        7. 최소 수량 검증

    Linear Formula:
        loss_usdt_at_stop = qty * entry_price * stop_distance_pct
        qty = max_loss_usdt / (entry_price * stop_distance_pct)

    SSOT: account_builder_policy.md Section 10, ADR-0002
    """
    # Step 1: Loss budget 기준 qty 계산 (Linear 공식)
    # loss_usdt = qty * entry_price * stop_distance_pct
    # qty = max_loss_usdt / (entry_price * stop_distance_pct)
    qty_from_loss = params.max_loss_usdt / (
        params.entry_price_usd * params.stop_distance_pct
    )

    # Step 2: Margin 기준 qty 계산
    # available_usdt = equity_usdt * 0.8 (80%만 사용, buffer)
    # max_notional_usdt = available_usdt * leverage
    # qty_from_margin = max_notional_usdt / entry_price
    available_usdt = params.equity_usdt * 0.8
    max_notional_usdt = available_usdt * params.leverage
    qty_from_margin = max_notional_usdt / params.entry_price_usd

    # Step 3: 둘 중 작은 값
    qty = min(qty_from_loss, qty_from_margin)

    # Step 4: Qty → Contracts 변환 (Bybit Linear BTCUSDT: 1 contract = 0.001 BTC)
    contracts = int(qty / params.contract_size)

    # Step 5: Tick/Lot size 보정
    contracts = int(contracts / params.qty_step) * params.qty_step

    # Step 6: 최소 수량 검증
    if contracts < params.qty_step:
        return SizingResult(contracts=0, reject_reason="qty_below_minimum")

    # Step 7: 보정 후 재검증 (margin feasibility, USDT-denominated)
    actual_qty = contracts * params.contract_size
    notional_usdt = actual_qty * params.entry_price_usd
    required_margin_usdt = notional_usdt / params.leverage
    fee_buffer_usdt = notional_usdt * params.fee_rate * 2  # entry + exit

    if required_margin_usdt + fee_buffer_usdt > params.equity_usdt:
        return SizingResult(contracts=0, reject_reason="margin_insufficient")

    # 성공
    return SizingResult(contracts=contracts, reject_reason=None)

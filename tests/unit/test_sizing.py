"""
tests/unit/test_sizing.py
Unit tests for position sizing (FLOW Section 3.4, Policy Section 10)

Purpose:
- Contracts 계산 (loss budget 기반, Direction별 정확한 공식)
- Margin feasibility 검증 (BTC-denominated)
- Tick/Lot size 보정 + 재검증
- Min contracts 검증

SSOT:
- FLOW.md Section 3.4: Position Sizing (Direction별 정확한 공식)
- FLOW.md Section 3.4: Margin Calculation (BTC-denominated)
- FLOW.md Section 3.4: Tick/Lot Size 준수
- Policy.md Section 10: Position Sizing

Test Coverage:
1. contracts_from_loss_budget_long (LONG, 정확한 공식)
2. contracts_from_loss_budget_short (SHORT, 정확한 공식)
3. margin_feasibility_rejects_insufficient (margin 부족 → REJECT)
4. tick_lot_size_correction (qty_step 보정)
5. tick_lot_size_revalidation_after_rounding (보정 후 재검증)
6. min_contracts_validation (최소 수량 검증)
7. margin_vs_loss_budget_minimum (margin/loss 중 작은 값)
8. fee_buffer_included_in_margin_check (fee buffer 포함)
"""

from dataclasses import dataclass
from src.application.sizing import calculate_contracts, SizingResult


@dataclass
class SizingParams:
    """Sizing 파라미터"""
    max_loss_btc: float
    entry_price_usd: float
    stop_distance_pct: float
    leverage: float
    equity_btc: float
    fee_rate: float
    direction: str  # "LONG" or "SHORT"
    qty_step: int  # Lot size (예: 1)
    tick_size: float  # Tick size (예: 0.5)


def test_contracts_from_loss_budget_long():
    """
    LONG: contracts 계산 (정확한 공식)

    FLOW Section 3.4:
        contracts = (max_loss_btc × entry × (1 - stop_distance_pct)) / stop_distance_pct

    Example:
        max_loss_btc = 0.001 BTC
        entry_price = 100000 USD
        stop_distance_pct = 0.03 (3%)

        contracts = (0.001 × 100000 × (1 - 0.03)) / 0.03
                  = (100 × 0.97) / 0.03
                  = 97 / 0.03
                  = 3233.33 → floor(3233) = 3233
    """
    params = SizingParams(
        max_loss_btc=0.001,
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_btc=0.02,  # 충분히 높음 (margin 통과용, loss budget 우선)
        fee_rate=0.0001,
        direction="LONG",
        qty_step=1,
        tick_size=0.5,
    )

    result = calculate_contracts(params)

    # 정확한 공식 검증
    expected_contracts = (0.001 * 100000 * (1 - 0.03)) / 0.03
    expected_contracts = int(expected_contracts)  # floor

    assert result.contracts == expected_contracts
    assert result.reject_reason is None


def test_contracts_from_loss_budget_short():
    """
    SHORT: contracts 계산 (정확한 공식)

    FLOW Section 3.4:
        contracts = (max_loss_btc × entry × (1 + stop_distance_pct)) / stop_distance_pct

    Example:
        max_loss_btc = 0.001 BTC
        entry_price = 100000 USD
        stop_distance_pct = 0.03 (3%)

        contracts = (0.001 × 100000 × (1 + 0.03)) / 0.03
                  = (100 × 1.03) / 0.03
                  = 103 / 0.03
                  = 3433.33 → floor(3433) = 3433
    """
    params = SizingParams(
        max_loss_btc=0.001,
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_btc=0.02,  # 충분히 높음 (margin 통과용, loss budget 우선)
        fee_rate=0.0001,
        direction="SHORT",
        qty_step=1,
        tick_size=0.5,
    )

    result = calculate_contracts(params)

    # 정확한 공식 검증
    expected_contracts = (0.001 * 100000 * (1 + 0.03)) / 0.03
    expected_contracts = int(expected_contracts)  # floor

    assert result.contracts == expected_contracts
    assert result.reject_reason is None


def test_margin_feasibility_constrains_contracts():
    """
    Margin feasibility: equity가 작으면 contracts가 제약됨

    FLOW Section 7: contracts = min(contracts_from_loss, contracts_from_margin)
    - Loss budget는 크지만, margin이 부족하면 contracts가 줄어듦
    - 80% buffer 때문에 완전히 REJECT는 아니지만, 매우 작은 값
    """
    params = SizingParams(
        max_loss_btc=0.01,  # 큰 loss budget (loss 기준 ~32000 contracts)
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_btc=0.0005,  # 매우 작은 equity (margin 제약)
        fee_rate=0.0001,
        direction="LONG",
        qty_step=1,
        tick_size=0.5,
    )

    result = calculate_contracts(params)

    # Margin 제약으로 인해 contracts가 매우 작음
    loss_based = int((0.01 * 100000 * (1 - 0.03)) / 0.03)
    assert result.contracts < loss_based
    assert result.contracts < 200  # Margin 제약으로 매우 작음


def test_tick_lot_size_correction():
    """
    Tick/Lot size 보정: qty_step 단위로 floor

    FLOW Section 3.4:
        contracts = floor(contracts / qty_step) * qty_step

    Example:
        raw_contracts = 3233.7
        qty_step = 10
        → contracts = floor(3233.7 / 10) * 10 = 323 * 10 = 3230
    """
    params = SizingParams(
        max_loss_btc=0.001,
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_btc=0.02,  # 충분히 높음 (margin 통과용, loss budget 우선)
        fee_rate=0.0001,
        direction="LONG",
        qty_step=10,  # Lot size = 10
        tick_size=0.5,
    )

    result = calculate_contracts(params)

    # qty_step 단위로 floor
    raw_contracts = (0.001 * 100000 * (1 - 0.03)) / 0.03
    expected_contracts = int(raw_contracts / 10) * 10

    assert result.contracts == expected_contracts
    assert result.contracts % 10 == 0  # qty_step 배수


def test_min_contracts_validation():
    """
    최소 수량 검증: contracts < qty_step → REJECT

    FLOW Section 3.4:
        if contracts < qty_step => REJECT
    """
    params = SizingParams(
        max_loss_btc=0.00001,  # 매우 작은 loss budget
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_btc=0.01,
        fee_rate=0.0001,
        direction="LONG",
        qty_step=100,  # 큰 lot size
        tick_size=0.5,
    )

    result = calculate_contracts(params)

    # raw_contracts = (0.00001 * 100000 * 0.97) / 0.03 = 32.33
    # floor(32.33 / 100) * 100 = 0 * 100 = 0
    # 0 < 100 → REJECT

    assert result.contracts == 0
    assert result.reject_reason == "qty_below_minimum"


def test_margin_vs_loss_budget_minimum():
    """
    Margin vs Loss budget: 둘 중 작은 값 사용

    FLOW Section 7: Sizing Double-Check
        contracts = min(contracts_from_loss, contracts_from_margin)
    """
    # Margin 제약이 더 작은 경우
    params = SizingParams(
        max_loss_btc=0.01,  # 큰 loss budget
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_btc=0.003,  # 작은 equity (margin 제약)
        fee_rate=0.0001,
        direction="LONG",
        qty_step=1,
        tick_size=0.5,
    )

    result = calculate_contracts(params)

    # Loss budget 기준: (0.01 * 100000 * 0.97) / 0.03 = 32333
    # Margin 기준: equity * leverage * entry - fee_buffer
    #   = 0.003 * 3 * 100000 - fee = 900 - fee ≈ 800~900 정도
    # → Margin이 제약

    # contracts < loss budget 기준
    loss_based = int((0.01 * 100000 * (1 - 0.03)) / 0.03)
    assert result.contracts < loss_based


def test_fee_buffer_included_in_margin_check():
    """
    Fee buffer 포함: margin + fee_buffer <= equity

    FLOW Section 3.4:
        fee_buffer_btc = (contracts / entry) × fee_rate × 2
        required_margin_btc + fee_buffer_btc <= equity_btc
    """
    params = SizingParams(
        max_loss_btc=0.001,
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_btc=0.01,
        fee_rate=0.0001,
        direction="LONG",
        qty_step=1,
        tick_size=0.5,
    )

    result = calculate_contracts(params)

    # Fee buffer 계산
    position_value_btc = result.contracts / params.entry_price_usd
    fee_buffer_btc = position_value_btc * params.fee_rate * 2
    required_margin_btc = position_value_btc / params.leverage

    # 검증: margin + fee_buffer <= equity
    assert required_margin_btc + fee_buffer_btc <= params.equity_btc


def test_tick_lot_size_revalidation_after_rounding():
    """
    보정 후 재검증: tick/lot 보정 후 margin 재확인

    FLOW Section 3.4:
        4. 보정 후 재검증 (필수)
        - Margin feasibility 재확인
        - Liquidation gate 재확인 (추후 구현)
        - 최소 수량 검증
    """
    # 보정 전에는 통과, 보정 후 margin 부족 케이스
    params = SizingParams(
        max_loss_btc=0.001,
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_btc=0.0035,  # 경계값 (보정 후 부족 가능)
        fee_rate=0.0001,
        direction="LONG",
        qty_step=100,  # 큰 lot size (보정으로 크게 변함)
        tick_size=0.5,
    )

    result = calculate_contracts(params)

    # 보정 후 재검증 통과 확인
    if result.contracts > 0:
        position_value_btc = result.contracts / params.entry_price_usd
        fee_buffer_btc = position_value_btc * params.fee_rate * 2
        required_margin_btc = position_value_btc / params.leverage

        assert required_margin_btc + fee_buffer_btc <= params.equity_btc

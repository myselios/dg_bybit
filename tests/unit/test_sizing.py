"""
tests/unit/test_sizing.py
Unit tests for position sizing (Linear USDT) — ADR-0002

Purpose:
- Qty/Contracts 계산 (loss budget 기반, Linear 공식)
- Margin feasibility 검증 (USDT-denominated)
- Tick/Lot size 보정 + 재검증
- Min contracts 검증

SSOT:
- account_builder_policy.md Section 10: Position Sizing (Bybit Linear USDT)
- ADR-0002: Inverse to Linear USDT Migration
- sizing.py: Linear 공식 구현

Test Coverage:
1. contracts_from_loss_budget (Linear 공식)
2. margin_feasibility_rejects_insufficient (margin 부족 → REJECT)
3. tick_lot_size_correction (qty_step 보정)
4. tick_lot_size_revalidation_after_rounding (보정 후 재검증)
5. min_contracts_validation (최소 수량 검증)
6. margin_vs_loss_budget_minimum (margin/loss 중 작은 값)
7. fee_buffer_included_in_margin_check (fee buffer 포함)
8. contract_size_conversion (qty → contracts 변환)
"""

from application.sizing import calculate_contracts, SizingParams, SizingResult


def test_contracts_from_loss_budget():
    """
    Linear USDT: contracts 계산

    Linear Formula (ADR-0002):
        loss_usdt_at_stop = qty * entry_price * stop_distance_pct
        qty = max_loss_usdt / (entry_price * stop_distance_pct)
        contracts = floor(qty / contract_size)

    Example:
        max_loss_usdt = $100 USDT
        entry_price = $100,000 USD
        stop_distance_pct = 0.03 (3%)
        contract_size = 0.001 BTC

        qty = 100 / (100000 * 0.03)
            = 100 / 3000
            = 0.03333 BTC

        contracts = floor(0.03333 / 0.001)
                  = floor(33.33)
                  = 33 contracts
    """
    params = SizingParams(
        max_loss_usdt=100.0,
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_usdt=10000.0,  # 충분히 높음 (margin 통과용, loss budget 우선)
        fee_rate=0.0001,
        direction="LONG",
        qty_step=1,
        tick_size=0.5,
        contract_size=0.001,
    )

    result = calculate_contracts(params)

    # Linear 공식 검증
    qty = 100.0 / (100000.0 * 0.03)  # 0.03333 BTC
    expected_contracts = int(qty / 0.001)  # floor(33.33) = 33
    expected_contracts = int(expected_contracts / params.qty_step) * params.qty_step  # Lot size 보정

    assert result.contracts == expected_contracts
    assert result.reject_reason is None


def test_margin_feasibility_constrains_contracts():
    """
    Margin 부족 → contracts 제한 또는 REJECT

    Example:
        equity_usdt = $1000 USDT
        leverage = 3.0
        available_usdt = 1000 * 0.8 = 800 USDT (80% buffer)
        max_notional_usdt = 800 * 3 = 2400 USDT
        qty_from_margin = 2400 / 100000 = 0.024 BTC
        contracts_from_margin = floor(0.024 / 0.001) = 24 contracts

        하지만 loss budget은 더 크게 설정 (margin이 제한 요인)
    """
    params = SizingParams(
        max_loss_usdt=1000.0,  # 큰 loss budget (margin 제한 유도)
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_usdt=1000.0,  # 작은 equity (margin 제한)
        fee_rate=0.0001,
        direction="LONG",
        qty_step=1,
        tick_size=0.5,
        contract_size=0.001,
    )

    result = calculate_contracts(params)

    # Margin 제한 검증
    available_usdt = 1000.0 * 0.8  # 800
    max_notional_usdt = available_usdt * 3.0  # 2400
    qty_from_margin = max_notional_usdt / 100000.0  # 0.024 BTC
    expected_contracts = int(qty_from_margin / 0.001)  # floor(24) = 24

    # contracts는 margin으로 제한됨
    assert result.contracts <= expected_contracts
    assert result.contracts > 0  # REJECT는 아님 (일부 가능)


def test_tick_lot_size_correction():
    """
    Tick/Lot size 보정 (qty_step)

    Example:
        qty_step = 5 contracts
        계산 결과 = 33 contracts
        보정 후 = 30 contracts (floor(33 / 5) * 5 = 30)
    """
    params = SizingParams(
        max_loss_usdt=100.0,
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_usdt=10000.0,
        fee_rate=0.0001,
        direction="LONG",
        qty_step=5,  # 5 contracts씩만 거래 가능
        tick_size=0.5,
        contract_size=0.001,
    )

    result = calculate_contracts(params)

    # Lot size 보정 검증
    assert result.contracts % params.qty_step == 0  # 5의 배수
    assert result.reject_reason is None


def test_min_contracts_validation():
    """
    최소 수량 검증 (qty_step 미만 → REJECT)

    Example:
        max_loss_usdt = 0.1 USDT (매우 작음)
        계산 결과 = 0.000033 BTC = 0.033 contracts
        floor(0.033) = 0 contracts
        → qty_below_minimum REJECT
    """
    params = SizingParams(
        max_loss_usdt=0.1,  # 매우 작은 loss budget
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_usdt=10000.0,
        fee_rate=0.0001,
        direction="LONG",
        qty_step=1,
        tick_size=0.5,
        contract_size=0.001,
    )

    result = calculate_contracts(params)

    # 최소 수량 미달 → REJECT
    assert result.contracts == 0
    assert result.reject_reason == "qty_below_minimum"


def test_margin_vs_loss_budget_minimum():
    """
    Loss budget vs Margin: 둘 중 작은 값 선택

    Example:
        loss budget → 33 contracts
        margin → 24 contracts
        → min(33, 24) = 24 contracts
    """
    params = SizingParams(
        max_loss_usdt=100.0,  # Loss budget → 33 contracts
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_usdt=1000.0,  # Margin → 24 contracts (제한 요인)
        fee_rate=0.0001,
        direction="LONG",
        qty_step=1,
        tick_size=0.5,
        contract_size=0.001,
    )

    result = calculate_contracts(params)

    # Margin이 제한 요인 → contracts < loss budget 기준
    qty_from_loss = 100.0 / (100000.0 * 0.03)  # 0.03333 BTC
    contracts_from_loss = int(qty_from_loss / 0.001)  # 33 contracts

    assert result.contracts < contracts_from_loss  # Margin 제한
    assert result.contracts > 0


def test_fee_buffer_included_in_margin_check():
    """
    Fee buffer 포함 (entry + exit)

    Example:
        notional_usdt = qty * entry_price
        fee_buffer_usdt = notional_usdt * fee_rate * 2
        required_margin_usdt + fee_buffer_usdt <= equity_usdt
    """
    params = SizingParams(
        max_loss_usdt=100.0,
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_usdt=1000.0,
        fee_rate=0.0001,  # 0.01%
        direction="LONG",
        qty_step=1,
        tick_size=0.5,
        contract_size=0.001,
    )

    result = calculate_contracts(params)

    # Fee buffer 검증
    actual_qty = result.contracts * 0.001
    notional_usdt = actual_qty * 100000.0
    required_margin_usdt = notional_usdt / 3.0
    fee_buffer_usdt = notional_usdt * 0.0001 * 2

    # 마진 + 수수료 버퍼 <= equity
    assert required_margin_usdt + fee_buffer_usdt <= params.equity_usdt


def test_tick_lot_size_revalidation_after_rounding():
    """
    보정 후 재검증 (margin feasibility 재확인)

    보정 전 contracts가 margin을 통과해도,
    보정 후 contracts가 margin을 초과하면 REJECT

    Example:
        보정 전 = 24.8 contracts → floor(24) = 24 (margin 통과)
        Lot size 보정 = 20 contracts (qty_step=5)
        재검증 → 통과
    """
    params = SizingParams(
        max_loss_usdt=75.0,  # 약 25 contracts
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_usdt=1000.0,
        fee_rate=0.0001,
        direction="LONG",
        qty_step=5,  # Lot size 보정
        tick_size=0.5,
        contract_size=0.001,
    )

    result = calculate_contracts(params)

    # 보정 후에도 margin 통과 검증
    assert result.contracts % params.qty_step == 0  # Lot size 준수
    assert result.reject_reason is None  # 재검증 통과


def test_contract_size_conversion():
    """
    Qty → Contracts 변환 (contract_size 기준)

    Example:
        qty = 0.05 BTC
        contract_size = 0.001 BTC per contract
        contracts = floor(0.05 / 0.001) = 50 contracts
    """
    params = SizingParams(
        max_loss_usdt=150.0,
        entry_price_usd=100000.0,
        stop_distance_pct=0.03,
        leverage=3.0,
        equity_usdt=10000.0,
        fee_rate=0.0001,
        direction="LONG",
        qty_step=1,
        tick_size=0.5,
        contract_size=0.001,  # 1 contract = 0.001 BTC
    )

    result = calculate_contracts(params)

    # Contracts 변환 검증
    qty = 150.0 / (100000.0 * 0.03)  # 0.05 BTC
    expected_contracts = int(qty / 0.001)  # floor(50) = 50

    assert result.contracts == expected_contracts
    assert result.reject_reason is None

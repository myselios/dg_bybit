"""
tests/unit/test_liquidation_gate.py
Unit tests for liquidation distance gate (FLOW Section 7.5)

Purpose:
- Liquidation distance 계산 (Bybit Inverse, 보수적 근사)
- 동적 기준 검증 (stop_distance × multiplier + min_absolute)
- REJECT 이유코드 반환 검증
- Fallback 규칙 (API 실패 시)

SSOT:
- FLOW.md Section 7.5: Liquidation Distance Gate (강제 안전장치)
- Policy.md Section 5: Stage Parameters (liq_distance_min_pct)

Test Coverage:
1. calculate_liquidation_distance_long (LONG, leverage 3x)
2. calculate_liquidation_distance_short (SHORT, leverage 3x)
3. gate_rejects_too_close (liq_distance < min_required)
4. gate_passes_sufficient_distance (liq_distance >= min_required)
5. dynamic_criteria_stage1 (stop × 4, 최소 15%)
6. dynamic_criteria_stage3 (stop × 3, 최소 12%)
7. fallback_api_failure_high_leverage (leverage > 3 → REJECT)
8. fallback_api_failure_large_stop (stop > 5% → haircut)
"""

from dataclasses import dataclass
from application.liquidation_gate import (
    calculate_liquidation_distance,
    check_liquidation_gate,
    LiquidationGateResult,
)


@dataclass
class LiquidationParams:
    """Liquidation gate 파라미터"""
    entry_price_usd: float
    contracts: int
    leverage: float
    direction: str  # "LONG" or "SHORT"
    equity_btc: float
    stop_distance_pct: float
    stage_id: int


def test_calculate_liquidation_distance_long():
    """
    LONG: liquidation distance 계산 (보수적 근사)

    FLOW Section 7.5:
        liq_price ≈ entry × leverage / (leverage + 1)
        liq_distance = (entry - liq_price) / entry

    Example:
        entry = 100000 USD
        leverage = 3x
        liq_price ≈ 100000 × 3 / (3 + 1) = 75000
        liq_distance = (100000 - 75000) / 100000 = 0.25 (25%)
    """
    liq_distance = calculate_liquidation_distance(
        entry_price=100000.0,
        contracts=1000,  # contracts는 근사에 영향 없음 (simplified)
        leverage=3.0,
        direction="LONG",
        equity_btc=0.01,  # equity_btc도 근사에 영향 없음 (simplified)
    )

    # LONG, leverage 3x → liq_distance ≈ 25%
    expected = 0.25
    assert abs(liq_distance - expected) < 0.01, f"Expected {expected}, got {liq_distance}"


def test_calculate_liquidation_distance_short():
    """
    SHORT: liquidation distance 계산 (보수적 근사)

    FLOW Section 7.5:
        liq_price ≈ entry × leverage / (leverage - 1)
        liq_distance = (liq_price - entry) / entry

    Example:
        entry = 100000 USD
        leverage = 3x
        liq_price ≈ 100000 × 3 / (3 - 1) = 150000
        liq_distance = (150000 - 100000) / 100000 = 0.50 (50%)
    """
    liq_distance = calculate_liquidation_distance(
        entry_price=100000.0,
        contracts=1000,
        leverage=3.0,
        direction="SHORT",
        equity_btc=0.01,
    )

    # SHORT, leverage 3x → liq_distance ≈ 50%
    expected = 0.50
    assert abs(liq_distance - expected) < 0.01, f"Expected {expected}, got {liq_distance}"


def test_gate_rejects_too_close():
    """
    Gate REJECT: liq_distance < min_required

    FLOW Section 7.5:
        if liq_distance < min_required → REJECT
    """
    params = LiquidationParams(
        entry_price_usd=100000.0,
        contracts=1000,
        leverage=5.0,  # 높은 leverage (liq_distance 감소)
        direction="LONG",
        equity_btc=0.01,
        stop_distance_pct=0.02,  # 2%
        stage_id=1,
    )

    result = check_liquidation_gate(params)

    # leverage 5x LONG → liq_distance ≈ 20% (5/(5+1) = 0.833, 1-0.833 = 16.7%)
    # min_required = max(2% × 4, 15%) = 15%
    # 16.7% > 15% → PASS가 예상되지만...
    # 더 정확히는 leverage 5x는 매우 위험 (Policy에서 Stage 1은 3x max)
    # → 테스트 조정 필요

    # leverage 4x로 재조정
    params.leverage = 4.0
    result = check_liquidation_gate(params)

    # leverage 4x LONG → liq_distance = 1 - 4/5 = 20%
    # min_required = max(2% × 4, 15%) = 15%
    # 20% > 15% → PASS

    # stop_distance를 5%로 늘려서 REJECT 유도
    params.stop_distance_pct = 0.05  # 5%
    result = check_liquidation_gate(params)

    # min_required = max(5% × 4, 15%) = 20%
    # liq_distance = 20%
    # 20% >= 20% → 경계값 (PASS)

    # stop_distance를 6%로 늘려서 REJECT 확정
    params.stop_distance_pct = 0.06  # 6%
    result = check_liquidation_gate(params)

    # min_required = max(6% × 4, 15%) = 24%
    # liq_distance = 20%
    # 20% < 24% → REJECT

    assert result.allowed is False
    assert result.reject_reason == "liquidation_too_close"


def test_gate_passes_sufficient_distance():
    """
    Gate PASS: liq_distance >= min_required

    FLOW Section 7.5:
        if liq_distance >= min_required → PASS
    """
    params = LiquidationParams(
        entry_price_usd=100000.0,
        contracts=1000,
        leverage=3.0,
        direction="LONG",
        equity_btc=0.01,
        stop_distance_pct=0.02,  # 2%
        stage_id=1,
    )

    result = check_liquidation_gate(params)

    # leverage 3x LONG → liq_distance = 25%
    # min_required = max(2% × 4, 15%) = 15%
    # 25% > 15% → PASS

    assert result.allowed is True
    assert result.reject_reason is None


def test_dynamic_criteria_stage1():
    """
    Stage 1: 동적 기준 (stop × 4, 최소 15%)

    FLOW Section 7.5:
        liq_distance_multiplier[1] = 4.0
        min_absolute_liq_distance[1] = 0.15 (15%)
        min_required = max(stop × 4, 15%)
    """
    params = LiquidationParams(
        entry_price_usd=100000.0,
        contracts=1000,
        leverage=3.0,
        direction="LONG",
        equity_btc=0.01,
        stop_distance_pct=0.03,  # 3%
        stage_id=1,
    )

    result = check_liquidation_gate(params)

    # min_required = max(3% × 4, 15%) = max(12%, 15%) = 15%
    # liq_distance = 25%
    # 25% > 15% → PASS

    assert result.allowed is True

    # stop_distance를 4%로 늘림
    params.stop_distance_pct = 0.04  # 4%
    result = check_liquidation_gate(params)

    # min_required = max(4% × 4, 15%) = max(16%, 15%) = 16%
    # liq_distance = 25%
    # 25% > 16% → PASS

    assert result.allowed is True


def test_dynamic_criteria_stage3():
    """
    Stage 3: 동적 기준 (stop × 3, 최소 12%)

    FLOW Section 7.5:
        liq_distance_multiplier[3] = 3.0
        min_absolute_liq_distance[3] = 0.12 (12%)
        min_required = max(stop × 3, 12%)
    """
    params = LiquidationParams(
        entry_price_usd=100000.0,
        contracts=1000,
        leverage=2.0,  # Stage 3는 2x leverage
        direction="LONG",
        equity_btc=0.01,
        stop_distance_pct=0.05,  # 5%
        stage_id=3,
    )

    result = check_liquidation_gate(params)

    # leverage 2x LONG → liq_distance = 1 - 2/3 = 33%
    # min_required = max(5% × 3, 12%) = max(15%, 12%) = 15%
    # 33% > 15% → PASS

    assert result.allowed is True


def test_fallback_api_failure_high_leverage():
    """
    Fallback: API 실패 + leverage > 3 → REJECT

    FLOW Section 7.5:
        if liq_distance is None and leverage > 3 → REJECT
    """
    params = LiquidationParams(
        entry_price_usd=100000.0,
        contracts=1000,
        leverage=4.0,  # leverage > 3
        direction="LONG",
        equity_btc=0.01,
        stop_distance_pct=0.02,
        stage_id=1,
    )

    result = check_liquidation_gate(params, api_failure=True)

    # API 실패 + leverage 4 > 3 → REJECT

    assert result.allowed is False
    assert result.reject_reason == "leverage_too_high_without_liq_check"


def test_fallback_api_failure_large_stop():
    """
    Fallback: API 실패 + stop > 5% → contracts × 0.8 (haircut)

    FLOW Section 7.5:
        if liq_distance is None and stop > 5% → contracts × 0.8
    """
    params = LiquidationParams(
        entry_price_usd=100000.0,
        contracts=1000,
        leverage=3.0,  # leverage <= 3 (PASS)
        direction="LONG",
        equity_btc=0.01,
        stop_distance_pct=0.06,  # 6% > 5%
        stage_id=1,
    )

    result = check_liquidation_gate(params, api_failure=True)

    # API 실패 + stop 6% > 5% → contracts × 0.8 = 800
    # haircut 적용 (PASS, but reduced)

    assert result.allowed is True
    assert result.adjusted_contracts == 800  # 1000 × 0.8
    assert result.haircut_applied is True

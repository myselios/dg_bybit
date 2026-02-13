"""
tests/unit/test_fee_verification.py
Unit tests for fee verification (FLOW Section 6.2)

Purpose:
- Fee spike 감지 (actual / estimated > 1.5)
- Tightening 규칙 (24시간 지속, EV gate K × 1.5)
- Linear USDT Fee 계산 (fee = qty × price × fee_rate, 단위: USDT)

SSOT:
- FLOW.md Section 6.2: Fee Post-Trade Verification
- ADR-0002: Inverse → Linear USDT 마이그레이션 완료

Test Coverage:
1. estimate_fee_usdt_linear_formula (Linear: qty × price × fee_rate)
2. verify_fee_post_trade_no_spike (ratio < 1.5)
3. verify_fee_post_trade_spike_detected (ratio > 1.5)
4. apply_fee_spike_tightening_increases_ev_multiplier (×1.5)
5. apply_fee_spike_tightening_no_change_when_inactive (no change)
"""

from application.fee_verification import (
    estimate_fee_usdt,
    verify_fee_post_trade,
    apply_fee_spike_tightening,
)


def test_estimate_fee_usdt_linear_formula():
    """
    Linear USDT Fee 계산: fee = qty × price × fee_rate

    Example:
        qty = 0.001 BTC
        price = 100000 USDT/BTC
        fee_rate = 0.00055 (0.055% taker)
        fee_usdt = 0.001 × 100000 × 0.00055 = 0.055 USDT
    """
    qty = 0.001
    price = 100000.0
    fee_rate = 0.00055

    fee_usdt = estimate_fee_usdt(qty, price, fee_rate)

    expected_fee = 0.001 * 100000.0 * 0.00055  # 0.055
    assert abs(fee_usdt - expected_fee) < 1e-6, f"Expected {expected_fee}, got {fee_usdt}"


def test_verify_fee_post_trade_no_spike():
    """
    No spike: actual / estimated <= 1.5

    Linear USDT:
        fee_ratio = actual_fee_usdt / estimated_fee_usdt
        spike_detected = fee_ratio > 1.5

    Example:
        estimated_fee = 0.055 USDT
        actual_fee = 0.055 USDT (동일)
        fee_ratio = 1.0 (< 1.5) → no spike
    """
    estimated_fee_usdt = 0.055
    actual_fee_usdt = 0.055
    estimated_fee_rate = 0.00055

    result = verify_fee_post_trade(
        estimated_fee_usdt, actual_fee_usdt, estimated_fee_rate
    )

    assert result.spike_detected is False
    assert abs(result.fee_ratio - 1.0) < 0.1  # ~1.0
    assert result.tightening_required is False
    assert result.tighten_until_ts is None


def test_verify_fee_post_trade_spike_detected():
    """
    Spike detected: actual / estimated > 1.5

    Example:
        estimated_fee = 0.055 USDT
        actual_fee = 0.11 USDT (2배)
        fee_ratio = 0.11 / 0.055 = 2.0 (> 1.5) → spike detected

    Tightening:
        - fee_spike_mode = True
        - tighten_until = now() + 24 hours (86400 seconds)
    """
    estimated_fee_usdt = 0.055
    actual_fee_usdt = 0.11
    estimated_fee_rate = 0.00055

    result = verify_fee_post_trade(
        estimated_fee_usdt, actual_fee_usdt, estimated_fee_rate
    )

    # actual = 0.11, estimated = 0.055, ratio = 2.0
    assert result.spike_detected is True
    assert abs(result.fee_ratio - 2.0) < 0.1  # ~2.0
    assert result.tightening_required is True
    assert result.tighten_until_ts is not None  # now() + 86400


def test_apply_fee_spike_tightening_increases_ev_multiplier():
    """
    Fee spike mode → EV gate 배수 증가 (×1.5)

    Example:
        base_ev_multiplier = 2.0
        fee_spike_mode = True
        adjusted_multiplier = 2.0 × 1.5 = 3.0
    """
    base_ev_multiplier = 2.0
    fee_spike_mode = True

    adjusted_multiplier = apply_fee_spike_tightening(base_ev_multiplier, fee_spike_mode)

    expected_multiplier = 2.0 * 1.5
    assert (
        abs(adjusted_multiplier - expected_multiplier) < 1e-6
    ), f"Expected {expected_multiplier}, got {adjusted_multiplier}"


def test_apply_fee_spike_tightening_no_change_when_inactive():
    """
    No fee spike mode → EV gate 배수 유지

    Example:
        base_ev_multiplier = 2.0
        fee_spike_mode = False
        adjusted_multiplier = 2.0
    """
    base_ev_multiplier = 2.0
    fee_spike_mode = False

    adjusted_multiplier = apply_fee_spike_tightening(base_ev_multiplier, fee_spike_mode)

    assert (
        abs(adjusted_multiplier - base_ev_multiplier) < 1e-6
    ), f"Expected {base_ev_multiplier}, got {adjusted_multiplier}"

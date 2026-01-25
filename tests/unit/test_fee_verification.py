"""
tests/unit/test_fee_verification.py
Unit tests for fee verification (FLOW Section 6.2)

Purpose:
- Fee spike 감지 (actual / estimated > 1.5)
- Tightening 규칙 (24시간 지속, EV gate K × 1.5)
- Inverse Fee 계산 (contracts = USD notional)

SSOT:
- FLOW.md Section 6.2: Fee Post-Trade Verification

Test Coverage:
1. estimate_fee_usd_inverse_formula (Inverse: contracts = USD)
2. verify_fee_post_trade_no_spike (ratio < 1.5)
3. verify_fee_post_trade_spike_detected (ratio > 1.5)
4. apply_fee_spike_tightening_increases_ev_multiplier (×1.5)
5. apply_fee_spike_tightening_no_change_when_inactive (no change)
"""

from src.application.fee_verification import (
    estimate_fee_usd,
    verify_fee_post_trade,
    apply_fee_spike_tightening,
)


def test_estimate_fee_usd_inverse_formula():
    """
    Inverse Fee 계산: contracts = USD notional

    FLOW Section 6.2:
        fee_usd = contracts × fee_rate

    Example:
        contracts = 100 (= 100 USD notional)
        fee_rate = 0.0001 (0.01%)
        fee_usd = 100 × 0.0001 = 0.01 USD
    """
    contracts = 100
    fee_rate = 0.0001

    fee_usd = estimate_fee_usd(contracts, fee_rate)

    expected_fee = 100 * 0.0001
    assert abs(fee_usd - expected_fee) < 1e-6, f"Expected {expected_fee}, got {fee_usd}"


def test_verify_fee_post_trade_no_spike():
    """
    No spike: actual / estimated <= 1.5

    FLOW Section 6.2:
        actual_fee_usd = actual_fee_btc × exec_price
        fee_ratio = actual_fee_usd / estimated_fee_usd
        spike_detected = fee_ratio > 1.5

    Example:
        estimated_fee = 0.01 USD
        actual_fee_btc = 0.0000002 BTC
        exec_price = 50000 USD/BTC
        actual_fee_usd = 0.0000002 × 50000 = 0.01 USD
        fee_ratio = 0.01 / 0.01 = 1.0 (< 1.5) → no spike
    """
    estimated_fee_usd = 0.01
    actual_fee_btc = 0.0000002
    exec_price = 50000.0
    estimated_fee_rate = 0.0001

    result = verify_fee_post_trade(
        estimated_fee_usd, actual_fee_btc, exec_price, estimated_fee_rate
    )

    assert result.spike_detected is False
    assert abs(result.fee_ratio - 1.0) < 0.1  # ~1.0
    assert result.tightening_required is False
    assert result.tighten_until_ts is None


def test_verify_fee_post_trade_spike_detected():
    """
    Spike detected: actual / estimated > 1.5

    FLOW Section 6.2:
        actual_fee_usd = actual_fee_btc × exec_price
        fee_ratio = actual_fee_usd / estimated_fee_usd
        if fee_ratio > 1.5 → spike_detected = True

    Example:
        estimated_fee = 0.01 USD
        actual_fee_btc = 0.0000004 BTC
        exec_price = 50000 USD/BTC
        actual_fee_usd = 0.0000004 × 50000 = 0.02 USD
        fee_ratio = 0.02 / 0.01 = 2.0 (> 1.5) → spike detected

    Tightening:
        - fee_spike_mode = True
        - tighten_until = now() + 24 hours (86400 seconds)
    """
    estimated_fee_usd = 0.01
    actual_fee_btc = 0.0000004
    exec_price = 50000.0
    estimated_fee_rate = 0.0001

    result = verify_fee_post_trade(
        estimated_fee_usd, actual_fee_btc, exec_price, estimated_fee_rate
    )

    # actual_fee_usd = 0.02, ratio = 2.0
    assert result.spike_detected is True
    assert abs(result.fee_ratio - 2.0) < 0.1  # ~2.0
    assert result.tightening_required is True
    assert result.tighten_until_ts is not None  # now() + 86400


def test_apply_fee_spike_tightening_increases_ev_multiplier():
    """
    Fee spike mode → EV gate 배수 증가 (×1.5)

    FLOW Section 6.2:
        if fee_spike_mode:
            adjusted_multiplier = base_ev_multiplier × 1.5

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

    FLOW Section 6.2:
        if not fee_spike_mode:
            adjusted_multiplier = base_ev_multiplier (unchanged)

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

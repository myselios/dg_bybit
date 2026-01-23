"""
src/application/fee_verification.py
Fee spike detection and tightening logic (FLOW Section 6.2)

Purpose:
- Fee spike 감지 (actual / estimated > 1.5)
- Tightening 규칙 (24시간 지속, EV gate K × 1.5)
- Inverse Fee 계산 (contracts = USD notional)

SSOT:
- FLOW.md Section 6.2: Fee Post-Trade Verification

Exports:
- estimate_fee_usd(): Fee 예상 (USD 기준)
- verify_fee_post_trade(): Fee spike 감지 + tightening
- apply_fee_spike_tightening(): EV gate 배수 조정
"""

from dataclasses import dataclass
from time import time


@dataclass
class FeeVerificationResult:
    """Fee verification 결과"""

    spike_detected: bool
    fee_ratio: float
    tightening_required: bool
    tighten_until_ts: float | None = None


def estimate_fee_usd(contracts: int, fee_rate: float) -> float:
    """
    Fee 예상 (Bybit Inverse, USD 기준)

    FLOW Section 6.2:
        Inverse: contracts = USD notional
        fee_usd = contracts × fee_rate

    Args:
        contracts: 계약 수량 (Inverse: 1 contract = 1 USD notional)
        fee_rate: 수수료율 (예: 0.0001 = 0.01%)

    Returns:
        estimated_fee_usd: 예상 수수료 (USD)
    """
    return contracts * fee_rate


def verify_fee_post_trade(
    estimated_fee_usd: float,
    actual_fee_btc: float,
    exec_price: float,
    estimated_fee_rate: float,
) -> FeeVerificationResult:
    """
    Fee spike 감지 (FLOW Section 6.2)

    FLOW Section 6.2:
        actual_fee_usd = actual_fee_btc × exec_price
        fee_ratio = actual_fee_usd / estimated_fee_usd
        if fee_ratio > 1.5 → spike_detected = True

    Tightening:
        - fee_spike_mode = True
        - tighten_until = now() + 24 hours (86400 seconds)
        - EV gate K × 1.5

    Args:
        estimated_fee_usd: 예상 수수료 (USD)
        actual_fee_btc: 실제 수수료 (BTC)
        exec_price: 체결가 (USD/BTC)
        estimated_fee_rate: 예상 수수료율 (디버깅용)

    Returns:
        FeeVerificationResult(spike_detected, fee_ratio, tightening_required, tighten_until_ts)
    """
    # Actual fee 계산 (BTC → USD)
    actual_fee_usd = actual_fee_btc * exec_price

    # Fee ratio 계산
    if estimated_fee_usd > 0:
        fee_ratio = actual_fee_usd / estimated_fee_usd
    else:
        fee_ratio = 0.0

    # Spike 감지 (1.5x 초과)
    spike_detected = fee_ratio > 1.5

    # Tightening 설정 (24시간)
    if spike_detected:
        tightening_required = True
        tighten_until_ts = time() + 86400  # 24 hours
    else:
        tightening_required = False
        tighten_until_ts = None

    return FeeVerificationResult(
        spike_detected=spike_detected,
        fee_ratio=fee_ratio,
        tightening_required=tightening_required,
        tighten_until_ts=tighten_until_ts,
    )


def apply_fee_spike_tightening(
    base_ev_multiplier: float, fee_spike_mode: bool
) -> float:
    """
    Fee spike mode → EV gate 배수 증가

    FLOW Section 6.2:
        if fee_spike_mode:
            adjusted_multiplier = base_ev_multiplier × 1.5
        else:
            adjusted_multiplier = base_ev_multiplier

    Args:
        base_ev_multiplier: 기본 EV gate 배수 (Policy.md Section 5)
        fee_spike_mode: Fee spike 모드 활성화 여부

    Returns:
        adjusted_multiplier: 조정된 EV gate 배수
    """
    if fee_spike_mode:
        return base_ev_multiplier * 1.5
    else:
        return base_ev_multiplier

"""
src/application/fee_verification.py
Fee spike detection and tightening logic (FLOW Section 6.2)

Purpose:
- Fee spike 감지 (actual / estimated > 1.5)
- Tightening 규칙 (24시간 지속, EV gate K × 1.5)
- Linear USDT Fee 계산 (fee = qty × price × fee_rate, 단위: USDT)

SSOT:
- FLOW.md Section 6.2: Fee Post-Trade Verification
- ADR-0002: Inverse → Linear USDT 마이그레이션 완료

Exports:
- estimate_fee_usdt(): Fee 예상 (USDT 기준)
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


def estimate_fee_usdt(qty: float, price: float, fee_rate: float) -> float:
    """
    Fee 예상 (Bybit Linear USDT 기준)

    Linear USDT:
        fee_usdt = qty × price × fee_rate

    Args:
        qty: 수량 (BTC, 예: 0.001)
        price: 체결가 (USDT/BTC)
        fee_rate: 수수료율 (예: 0.00055 = 0.055% taker)

    Returns:
        estimated_fee_usdt: 예상 수수료 (USDT)
    """
    return qty * price * fee_rate


def verify_fee_post_trade(
    estimated_fee_usdt: float,
    actual_fee_usdt: float,
    estimated_fee_rate: float,
) -> FeeVerificationResult:
    """
    Fee spike 감지 (FLOW Section 6.2)

    Linear USDT:
        fee_ratio = actual_fee_usdt / estimated_fee_usdt
        if fee_ratio > 1.5 → spike_detected = True

    Tightening:
        - fee_spike_mode = True
        - tighten_until = now() + 24 hours (86400 seconds)
        - EV gate K × 1.5

    Args:
        estimated_fee_usdt: 예상 수수료 (USDT)
        actual_fee_usdt: 실제 수수료 (USDT, Bybit Linear에서 직접 USDT로 지급)
        estimated_fee_rate: 예상 수수료율 (디버깅용)

    Returns:
        FeeVerificationResult(spike_detected, fee_ratio, tightening_required, tighten_until_ts)
    """
    # Fee ratio 계산 (둘 다 USDT 단위이므로 직접 비교)
    if estimated_fee_usdt > 0:
        fee_ratio = actual_fee_usdt / estimated_fee_usdt
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

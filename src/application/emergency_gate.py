"""
Emergency Gate (FLOW.md Section 1.5 준수)

FLOW_REF: docs/constitution/FLOW.md#1.5 (Emergency Check, 최우선, 항상)
Last verified: 2026-01-19

Priority 0 (Signal보다 먼저 실행):
- price_drop_1m <= -10% → State.COOLDOWN (auto-recovery 가능)
- price_drop_5m <= -20% → State.COOLDOWN (auto-recovery 가능)
- balance anomaly (equity <= 0 OR stale timestamp > 30s) → State.HALT (manual reset)
- latency_rest >= 5.0s → emergency_block=True (State 변경 없음)

Implementation Status: Phase 0.5 골격 (Phase 1에서 완전 구현 예정)
"""

from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class EmergencyStatus:
    """
    Emergency 평가 결과

    Attributes:
        is_halt: True이면 State.HALT (manual reset 필요)
        is_cooldown: True이면 State.COOLDOWN (auto-recovery 가능)
        is_blocked: True이면 emergency_block=True (진입 차단, State 변경 없음)
        reason: Emergency 사유 (로그/디버깅용)
    """
    is_halt: bool
    is_cooldown: bool
    is_blocked: bool
    reason: str


def evaluate(snapshot: Dict[str, Any]) -> EmergencyStatus:
    """
    Emergency 평가 (순수 함수)

    Args:
        snapshot: {
            "price_drop_1m": float,  # -0.10 = -10%
            "price_drop_5m": float,  # -0.20 = -20%
            "equity_btc": float,
            "latency_rest_p95": float,  # seconds
            "timestamp": float,
            "last_balance_ts": float
        }

    Returns:
        EmergencyStatus

    Implementation:
        Phase 1에서 완전 구현 예정.
        현재는 최소 골격 (항상 safe 반환).
    """
    # TODO: Phase 1 구현
    # - price_drop 게이트 (Policy Section 7.2)
    # - balance anomaly 게이트 (Policy Section 7.1)
    # - latency 게이트 (Policy Section 7.2)
    # - auto-recovery 조건 (Policy Section 7.3)

    return EmergencyStatus(
        is_halt=False,
        is_cooldown=False,
        is_blocked=False,
        reason=""
    )

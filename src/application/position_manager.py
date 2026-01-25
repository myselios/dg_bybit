"""
Position Manager — Stop Status 강제 루프

FLOW.md Section 1 IN_POSITION 서브상태 기반
FLOW_REF: docs/constitution/FLOW.md#1 (Last verified: 2026-01-23)

책임:
1. IN_POSITION일 때 매 tick마다 stop_status 확인
2. MISSING → 복구 시도 (최대 3회)
3. ERROR → 즉시 HALT

⚠️ 핵심 규칙 (FLOW Section 1):
- stop_status == MISSING: 최대 10초 허용 (복구 중)
- stop_recovery_fail_count >= 3: ERROR → HALT
"""

from typing import Optional
import time

from src.domain.state import State, Position, StopStatus
from src.domain.intent import TransitionIntents, StopIntent, HaltIntent


def manage_stop_status(
    current_state: State,
    current_position: Optional[Position]
) -> TransitionIntents:
    """
    Stop Status 강제 감시 (IN_POSITION only)

    Args:
        current_state: 현재 상태
        current_position: 현재 포지션 (IN_POSITION만)

    Returns:
        TransitionIntents (Stop 복구 또는 HALT)

    FLOW 규칙:
    - IN_POSITION + stop_status == MISSING → PLACE_STOP intent
    - stop_recovery_fail_count >= 3 → HALT
    - stop_status == ERROR → HALT
    """
    intents = TransitionIntents()

    # IN_POSITION 아니면 건너뛰기
    if current_state != State.IN_POSITION:
        return intents

    # Position 없으면 불일치 (HALT)
    if current_position is None:
        intents.halt_intent = HaltIntent(
            reason="state_position_mismatch: IN_POSITION but no position object"
        )
        intents.entry_blocked = True
        return intents

    # Stop Status 확인
    if current_position.stop_status == StopStatus.MISSING:
        # MISSING: 복구 시도 (최대 3회)
        if current_position.stop_recovery_fail_count >= 3:
            # 3회 실패 → ERROR → HALT
            intents.halt_intent = HaltIntent(
                reason=f"stop_loss_unrecoverable: Stop recovery failed {current_position.stop_recovery_fail_count} times"
            )
            intents.entry_blocked = True
        else:
            # 복구 시도: PLACE_STOP intent
            intents.stop_intent = StopIntent(
                action="PLACE",
                desired_qty=current_position.qty,
                stop_price=_calculate_stop_price(current_position),
                reason="stop_missing_recovery"
            )

    elif current_position.stop_status == StopStatus.ERROR:
        # ERROR: 즉시 HALT
        intents.halt_intent = HaltIntent(
            reason="stop_status_error: Stop status is ERROR (복구 불가)"
        )
        intents.entry_blocked = True

    # ACTIVE/PENDING: 정상, 아무 것도 안 함

    return intents


def _calculate_stop_price(position: Position) -> float:
    """
    Stop price 계산 (FLOW Section 3.2)

    Direction별:
    - LONG: entry_price × (1 - stop_distance_pct)
    - SHORT: entry_price × (1 + stop_distance_pct)
    """
    if position.direction.value == "LONG":
        return position.entry_price * (1 - position.stop_distance_pct)
    else:  # SHORT
        return position.entry_price * (1 + position.stop_distance_pct)

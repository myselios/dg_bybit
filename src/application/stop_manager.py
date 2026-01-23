"""
src/application/stop_manager.py
Stop Manager — Stop Loss 갱신 정책 (FLOW Section 2.5 + Oracle PF-2~PF-6)

SSOT:
- FLOW.md Section 2.5: Stop Update Policy
- Oracle Backlog PF-2~PF-6: Stop Update 시나리오

원칙:
1. Amend 우선 (공백 방지)
2. Debounce: 20% threshold + 2초 간격
3. stop_status 복구 (MISSING → PLACE intent)
4. entry_working=True → stop 갱신 금지

Exports:
- should_update_stop(): delta threshold + debounce 체크
- determine_stop_action(): stop_status + amend_fail_count 기반 action 결정
- recover_missing_stop(): stop_status=MISSING 복구
"""

from typing import Tuple
from domain.state import StopStatus


def should_update_stop(
    position_qty: int,
    stop_qty: int,
    last_stop_update_at: float,
    current_time: float,
    threshold_pct: float = 0.20,
    debounce_seconds: float = 2.0,
    entry_working: bool = False,
) -> bool:
    """
    Stop 갱신 필요 여부 판단 (FLOW Section 2.5 + Oracle PF-2/PF-3)

    Args:
        position_qty: 현재 포지션 수량
        stop_qty: 현재 stop 수량
        last_stop_update_at: 마지막 stop 갱신 시각 (timestamp)
        current_time: 현재 시각 (timestamp)
        threshold_pct: Delta threshold (기본 20%)
        debounce_seconds: Debounce 간격 (기본 2초)
        entry_working: Entry order 활성 여부 (True면 stop 갱신 금지)

    Returns:
        True: stop 갱신 필요
        False: stop 갱신 불필요

    FLOW Section 2.5:
        - Delta >= 20% → stop 갱신 필요
        - Delta < 20% → stop 유지
        - Debounce: 최소 2초 간격
        - entry_working=True → stop 갱신 금지
    """
    # (1) entry_working=True → 갱신 차단
    if entry_working:
        return False

    # (2) Delta 계산
    if stop_qty == 0:
        # stop_qty=0이면 갱신 필요 (초기 상태)
        return True

    delta = abs(position_qty - stop_qty)
    delta_pct = delta / stop_qty if stop_qty > 0 else 0.0

    # (3) Delta threshold 체크
    if delta_pct < threshold_pct:
        # Delta < 20% → 갱신 불필요
        return False

    # (4) Debounce 체크
    time_since_last_update = current_time - last_stop_update_at
    if time_since_last_update < debounce_seconds:
        # Debounce 2초 이내 → 차단
        return False

    # (5) Delta >= 20% + Debounce 통과 → 갱신 필요
    return True


def determine_stop_action(
    stop_status: StopStatus,
    amend_fail_count: int,
) -> str:
    """
    Stop 갱신 action 결정 (FLOW Section 2.5 + Oracle PF-3/PF-5/PF-6)

    Args:
        stop_status: stop_status (ACTIVE/PENDING/MISSING/ERROR)
        amend_fail_count: Amend 실패 횟수

    Returns:
        "AMEND": Amend 우선
        "CANCEL_AND_PLACE": Amend 재시도 한계 or stop_status=MISSING
        "PLACE": stop_status=MISSING (복구)

    FLOW Section 2.5:
        - stop_status=ACTIVE, amend_fail_count=0 → AMEND 우선
        - amend_fail_count=1 → AMEND 재시도
        - amend_fail_count=2 → CANCEL_AND_PLACE (재시도 한계)
        - stop_status=MISSING → PLACE (복구)
    """
    # (1) stop_status=MISSING → PLACE (복구)
    if stop_status == StopStatus.MISSING:
        return "PLACE"

    # (2) stop_status=ERROR → CANCEL_AND_PLACE (복구 실패)
    if stop_status == StopStatus.ERROR:
        return "CANCEL_AND_PLACE"

    # (3) amend_fail_count >= 2 → CANCEL_AND_PLACE (재시도 한계)
    if amend_fail_count >= 2:
        return "CANCEL_AND_PLACE"

    # (4) stop_status=ACTIVE, amend_fail_count < 2 → AMEND 우선
    return "AMEND"


def recover_missing_stop(
    stop_status: StopStatus,
    position_qty: int,
) -> Tuple[bool, str]:
    """
    stop_status=MISSING 복구 (SSOT: Phase 0.5)

    Args:
        stop_status: stop_status
        position_qty: 포지션 수량

    Returns:
        (recovery_needed, action)
        - recovery_needed: True (복구 필요)
        - action: "PLACE" (stop 설치)

    Phase 0.5:
        - stop_status=MISSING → PlaceStop intent
    """
    if stop_status == StopStatus.MISSING and position_qty > 0:
        return True, "PLACE"

    return False, "NONE"

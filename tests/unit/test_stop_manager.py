"""
tests/unit/test_stop_manager.py
Unit tests for stop manager (FLOW Section 2.5 + Oracle Backlog PF-2~PF-6)

Purpose:
- Stop 갱신 정책 (20% threshold + 2초 debounce)
- Amend 우선 (공백 방지), cancel+place는 최후
- stop_status 복구 (MISSING → PLACE intent)

SSOT:
- FLOW.md Section 2.5: Stop Update Policy
- Oracle Backlog PF-2~PF-6: Stop Update 시나리오

Test Coverage:
1. should_update_stop_below_threshold_no_update (delta < 20%)
2. should_update_stop_at_threshold_triggers_update (delta >= 20%)
3. should_update_stop_debounce_blocks_update (2초 이내)
4. should_update_stop_debounce_passed_allows_update (2초 경과)
5. determine_stop_action_amend_priority (stop_status=ACTIVE, amend_fail_count=0)
6. determine_stop_action_retry_amend_after_reject (amend_fail_count=1)
7. determine_stop_action_cancel_place_after_retry_limit (amend_fail_count=2)
8. determine_stop_action_missing_stop_requires_place (stop_status=MISSING)
9. recover_missing_stop_emits_place_intent (stop_status=MISSING 복구)
10. entry_working_blocks_stop_update (entry_working=True → stop 갱신 금지)
"""

from time import time
from src.application.stop_manager import (
    should_update_stop,
    determine_stop_action,
    recover_missing_stop,
)
from src.domain.state import StopStatus


def test_should_update_stop_below_threshold_no_update():
    """
    Delta < 20% → stop 갱신 안 함 (SSOT: Oracle PF-2)

    Oracle PF-2:
        position.qty=20, stop.qty=20
        PARTIAL_FILL +3 (delta 15% < 20%)
        → stop.qty 유지

    Example:
        position_qty=100
        stop_qty=100
        delta=10 (10% < 20%)

    Expected:
        should_update=False
    """
    position_qty = 100
    stop_qty = 100
    last_stop_update_at = time() - 10.0  # 10초 전
    current_time = time()

    should_update = should_update_stop(
        position_qty=position_qty,
        stop_qty=stop_qty,
        last_stop_update_at=last_stop_update_at,
        current_time=current_time,
        threshold_pct=0.20,  # 20%
        debounce_seconds=2.0,
    )

    # Delta 10% < 20% threshold → 갱신 안 함
    assert should_update is False


def test_should_update_stop_at_threshold_triggers_update():
    """
    Delta >= 20% → stop 갱신 필요 (SSOT: Oracle PF-3)

    Oracle PF-3:
        position.qty=20, stop.qty=20
        PARTIAL_FILL +4 (delta 20% == threshold)
        → AMEND

    Example:
        position_qty=120
        stop_qty=100
        delta=20 (20% == 20%)

    Expected:
        should_update=True
    """
    position_qty = 120
    stop_qty = 100
    last_stop_update_at = time() - 10.0  # 10초 전 (debounce 통과)
    current_time = time()

    should_update = should_update_stop(
        position_qty=position_qty,
        stop_qty=stop_qty,
        last_stop_update_at=last_stop_update_at,
        current_time=current_time,
        threshold_pct=0.20,  # 20%
        debounce_seconds=2.0,
    )

    # Delta 20% >= 20% threshold → 갱신 필요
    assert should_update is True


def test_should_update_stop_debounce_blocks_update():
    """
    Debounce 2초 이내 → stop 갱신 차단 (공백 방지)

    FLOW Section 2.5:
        - Stop 갱신은 최소 2초 간격
        - 2초 이내 재시도 차단 (공백 방지)

    Example:
        position_qty=120
        stop_qty=100 (delta 20%)
        last_stop_update_at = now() - 1.0초 (2초 미만)

    Expected:
        should_update=False (debounce 차단)
    """
    position_qty = 120
    stop_qty = 100
    current_time = time()
    last_stop_update_at = current_time - 1.0  # 1초 전 (2초 미만)

    should_update = should_update_stop(
        position_qty=position_qty,
        stop_qty=stop_qty,
        last_stop_update_at=last_stop_update_at,
        current_time=current_time,
        threshold_pct=0.20,
        debounce_seconds=2.0,
    )

    # Debounce 2초 이내 → 차단
    assert should_update is False


def test_should_update_stop_debounce_passed_allows_update():
    """
    Debounce 2초 경과 + delta >= 20% → stop 갱신 허용

    Example:
        position_qty=120
        stop_qty=100 (delta 20%)
        last_stop_update_at = now() - 3.0초 (2초 경과)

    Expected:
        should_update=True
    """
    position_qty = 120
    stop_qty = 100
    current_time = time()
    last_stop_update_at = current_time - 3.0  # 3초 전 (2초 경과)

    should_update = should_update_stop(
        position_qty=position_qty,
        stop_qty=stop_qty,
        last_stop_update_at=last_stop_update_at,
        current_time=current_time,
        threshold_pct=0.20,
        debounce_seconds=2.0,
    )

    # Debounce 통과 + delta 20% → 갱신 허용
    assert should_update is True


def test_determine_stop_action_amend_priority():
    """
    Amend 우선 (SSOT: FLOW Section 2.5 + Oracle PF-3)

    FLOW Section 2.5:
        - Stop 갱신은 Amend 우선 (공백 방지)
        - stop_status=ACTIVE, amend_fail_count=0 → AMEND

    Example:
        stop_status=ACTIVE
        amend_fail_count=0

    Expected:
        action="AMEND"
    """
    stop_status = StopStatus.ACTIVE
    amend_fail_count = 0

    action = determine_stop_action(
        stop_status=stop_status,
        amend_fail_count=amend_fail_count,
    )

    # Amend 우선
    assert action == "AMEND"


def test_determine_stop_action_retry_amend_after_reject():
    """
    Amend 거절 → 재시도 (SSOT: Oracle PF-5)

    Oracle PF-5:
        AMEND 거절, amend_fail_count=1
        → next_intent.action="AMEND" (재시도)

    Example:
        stop_status=ACTIVE
        amend_fail_count=1 (1회 실패)

    Expected:
        action="AMEND" (재시도)
    """
    stop_status = StopStatus.ACTIVE
    amend_fail_count = 1

    action = determine_stop_action(
        stop_status=stop_status,
        amend_fail_count=amend_fail_count,
    )

    # Amend 재시도 (1회 실패 후)
    assert action == "AMEND"


def test_determine_stop_action_cancel_place_after_retry_limit():
    """
    Amend 재시도 한계 → CANCEL_AND_PLACE (SSOT: Oracle PF-6)

    Oracle PF-6:
        amend_fail_count=2
        → stop_intent.action="CANCEL_AND_PLACE"

    Example:
        stop_status=ACTIVE
        amend_fail_count=2 (2회 실패, 재시도 한계)

    Expected:
        action="CANCEL_AND_PLACE"
    """
    stop_status = StopStatus.ACTIVE
    amend_fail_count = 2

    action = determine_stop_action(
        stop_status=stop_status,
        amend_fail_count=amend_fail_count,
    )

    # Amend 재시도 한계 → CANCEL_AND_PLACE
    assert action == "CANCEL_AND_PLACE"


def test_determine_stop_action_missing_stop_requires_place():
    """
    stop_status=MISSING → PLACE (SSOT: Oracle PF-6)

    Oracle PF-6:
        (A) stop_status=MISSING
        → stop_intent.action="CANCEL_AND_PLACE" (or PLACE)

    Example:
        stop_status=MISSING

    Expected:
        action="PLACE" (복구)
    """
    stop_status = StopStatus.MISSING
    amend_fail_count = 0

    action = determine_stop_action(
        stop_status=stop_status,
        amend_fail_count=amend_fail_count,
    )

    # stop_status=MISSING → PLACE
    assert action == "PLACE"


def test_recover_missing_stop_emits_place_intent():
    """
    stop_status=MISSING 복구 (SSOT: Phase 0.5)

    Phase 0.5:
        stop_status=MISSING → PlaceStop intent

    Example:
        stop_status=MISSING
        position_qty=100

    Expected:
        recovery_needed=True
        action="PLACE"
    """
    stop_status = StopStatus.MISSING
    position_qty = 100

    recovery_needed, action = recover_missing_stop(
        stop_status=stop_status,
        position_qty=position_qty,
    )

    # 복구 필요
    assert recovery_needed is True
    assert action == "PLACE"


def test_entry_working_blocks_stop_update():
    """
    entry_working=True → stop 갱신 금지 (SSOT: FLOW Section 2.5)

    FLOW Section 2.5:
        - entry_working=True (잔량 주문 활성)
        - Stop 갱신은 entry order 완전 체결 후에만

    Example:
        position_qty=120
        stop_qty=100 (delta 20%)
        entry_working=True

    Expected:
        should_update=False (entry_working 차단)
    """
    position_qty = 120
    stop_qty = 100
    last_stop_update_at = time() - 10.0  # debounce 통과
    current_time = time()
    entry_working = True

    should_update = should_update_stop(
        position_qty=position_qty,
        stop_qty=stop_qty,
        last_stop_update_at=last_stop_update_at,
        current_time=current_time,
        threshold_pct=0.20,
        debounce_seconds=2.0,
        entry_working=entry_working,  # 차단 조건
    )

    # entry_working=True → 갱신 차단
    assert should_update is False

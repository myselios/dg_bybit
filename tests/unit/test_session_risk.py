"""
tests/unit/test_session_risk.py
Session Risk Policy 테스트 (15 cases)

SSOT: task_plan.md Phase 9a

요구사항:
1. Daily Loss Cap (3 cases):
   - daily_pnl <= -5% equity → HALT + COOLDOWN (UTC 0시까지)
   - UTC 경계 넘으면 daily_pnl 리셋

2. Weekly Loss Cap (3 cases):
   - weekly_pnl <= -12.5% equity → COOLDOWN (7일)
   - 주 경계 넘으면 weekly_pnl 리셋

3. Loss Streak Kill (3 cases):
   - 3연패 → HALT (당일)
   - 5연패 → COOLDOWN (72h)

4. Fee/Slippage Anomaly (6 cases):
   - Fee spike: fee_ratio > 1.5, 2회 연속 → HALT 30분
   - Slippage spike: |slippage_usd| > threshold, 3회/10분 → HALT 60분
   - 10분 경계 넘으면 카운트 리셋
"""

import pytest
from application.session_risk import (
    SessionRiskStatus,
    check_daily_loss_cap,
    check_weekly_loss_cap,
    check_loss_streak_kill,
    check_fee_anomaly,
    check_slippage_anomaly,
)


# ============================================================================
# Daily Loss Cap (3 cases)
# ============================================================================


def test_daily_loss_cap_not_exceeded():
    """
    시나리오: daily_pnl = -4%, cap = 5% → ALLOW

    검증:
    - is_halted = False
    - cooldown_until = None
    """
    # Given: equity $100, daily_pnl = -$4 (-4%), cap = 5%
    equity_usd = 100.0
    daily_realized_pnl_usd = -4.0
    daily_loss_cap_pct = 5.0

    # When: check_daily_loss_cap()
    status = check_daily_loss_cap(
        equity_usd=equity_usd,
        daily_realized_pnl_usd=daily_realized_pnl_usd,
        daily_loss_cap_pct=daily_loss_cap_pct,
    )

    # Then: ALLOW (no halt)
    assert not status.is_halted, "Should not halt when daily loss < cap"
    assert status.cooldown_until is None, "No cooldown when not halted"


def test_daily_loss_cap_exceeded():
    """
    시나리오: daily_pnl = -6%, cap = 5% → HALT + COOLDOWN (UTC 0시)

    검증:
    - is_halted = True
    - cooldown_until = next UTC 0:00
    - halt_reason = "daily_loss_cap_exceeded"
    """
    # Given: equity $100, daily_pnl = -$6 (-6%), cap = 5%
    equity_usd = 100.0
    daily_realized_pnl_usd = -6.0
    daily_loss_cap_pct = 5.0
    current_timestamp = 1737600000.0  # 2026-01-23 00:00:00 UTC (example)

    # When: check_daily_loss_cap()
    status = check_daily_loss_cap(
        equity_usd=equity_usd,
        daily_realized_pnl_usd=daily_realized_pnl_usd,
        daily_loss_cap_pct=daily_loss_cap_pct,
        current_timestamp=current_timestamp,
    )

    # Then: HALT + COOLDOWN
    assert status.is_halted, "Should halt when daily loss > cap"
    assert status.halt_reason == "daily_loss_cap_exceeded"
    assert status.cooldown_until is not None, "Cooldown until next UTC 0:00"
    # cooldown_until should be next day UTC 0:00 (86400 seconds later)
    expected_cooldown = current_timestamp + 86400.0
    assert status.cooldown_until == expected_cooldown


def test_daily_loss_cap_reset_at_boundary():
    """
    시나리오: UTC 경계 넘으면 daily_pnl 리셋

    검증:
    - 이전 일자: daily_pnl = -$6 → HALT
    - 다음 일자: 같은 equity, daily_pnl = $0 → ALLOW
    """
    # Given: 이전 일자 (day 1), HALT 상태
    equity_usd = 100.0
    daily_pnl_day1 = -6.0
    daily_loss_cap_pct = 5.0
    timestamp_day1 = 1737600000.0  # 2026-01-23 00:00:00 UTC

    status_day1 = check_daily_loss_cap(
        equity_usd=equity_usd,
        daily_realized_pnl_usd=daily_pnl_day1,
        daily_loss_cap_pct=daily_loss_cap_pct,
        current_timestamp=timestamp_day1,
    )
    assert status_day1.is_halted, "Day 1: should halt"

    # When: 다음 일자 (day 2), daily_pnl 리셋 (0)
    daily_pnl_day2 = 0.0
    timestamp_day2 = timestamp_day1 + 86400.0  # 다음날 UTC 0:00

    status_day2 = check_daily_loss_cap(
        equity_usd=equity_usd,
        daily_realized_pnl_usd=daily_pnl_day2,
        daily_loss_cap_pct=daily_loss_cap_pct,
        current_timestamp=timestamp_day2,
    )

    # Then: ALLOW (리셋됨)
    assert not status_day2.is_halted, "Day 2: daily_pnl reset, should allow"


# ============================================================================
# Weekly Loss Cap (3 cases)
# ============================================================================


def test_weekly_loss_cap_not_exceeded():
    """
    시나리오: weekly_pnl = -10%, cap = 12.5% → ALLOW

    검증:
    - is_halted = False
    - cooldown_until = None
    """
    # Given: equity $100, weekly_pnl = -$10 (-10%), cap = 12.5%
    equity_usd = 100.0
    weekly_realized_pnl_usd = -10.0
    weekly_loss_cap_pct = 12.5

    # When: check_weekly_loss_cap()
    status = check_weekly_loss_cap(
        equity_usd=equity_usd,
        weekly_realized_pnl_usd=weekly_realized_pnl_usd,
        weekly_loss_cap_pct=weekly_loss_cap_pct,
    )

    # Then: ALLOW
    assert not status.is_halted, "Should not halt when weekly loss < cap"
    assert status.cooldown_until is None


def test_weekly_loss_cap_exceeded():
    """
    시나리오: weekly_pnl = -15%, cap = 12.5% → COOLDOWN (7일)

    검증:
    - is_halted = True
    - cooldown_until = current_timestamp + 7 days
    - halt_reason = "weekly_loss_cap_exceeded"
    """
    # Given: equity $100, weekly_pnl = -$15 (-15%), cap = 12.5%
    equity_usd = 100.0
    weekly_realized_pnl_usd = -15.0
    weekly_loss_cap_pct = 12.5
    current_timestamp = 1737600000.0

    # When: check_weekly_loss_cap()
    status = check_weekly_loss_cap(
        equity_usd=equity_usd,
        weekly_realized_pnl_usd=weekly_realized_pnl_usd,
        weekly_loss_cap_pct=weekly_loss_cap_pct,
        current_timestamp=current_timestamp,
    )

    # Then: HALT + COOLDOWN (7 days = 604800 seconds)
    assert status.is_halted
    assert status.halt_reason == "weekly_loss_cap_exceeded"
    expected_cooldown = current_timestamp + 604800.0  # 7 days
    assert status.cooldown_until == expected_cooldown


def test_weekly_loss_cap_reset_at_boundary():
    """
    시나리오: 주 경계 넘으면 weekly_pnl 리셋

    검증:
    - week 1: weekly_pnl = -$15 → HALT
    - week 2: weekly_pnl = $0 → ALLOW
    """
    # Given: week 1, HALT 상태
    equity_usd = 100.0
    weekly_pnl_week1 = -15.0
    weekly_loss_cap_pct = 12.5
    timestamp_week1 = 1737600000.0

    status_week1 = check_weekly_loss_cap(
        equity_usd=equity_usd,
        weekly_realized_pnl_usd=weekly_pnl_week1,
        weekly_loss_cap_pct=weekly_loss_cap_pct,
        current_timestamp=timestamp_week1,
    )
    assert status_week1.is_halted, "Week 1: should halt"

    # When: week 2 (7 days later), weekly_pnl 리셋 (0)
    weekly_pnl_week2 = 0.0
    timestamp_week2 = timestamp_week1 + 604800.0  # 7 days later

    status_week2 = check_weekly_loss_cap(
        equity_usd=equity_usd,
        weekly_realized_pnl_usd=weekly_pnl_week2,
        weekly_loss_cap_pct=weekly_loss_cap_pct,
        current_timestamp=timestamp_week2,
    )

    # Then: ALLOW (리셋됨)
    assert not status_week2.is_halted, "Week 2: weekly_pnl reset, should allow"


# ============================================================================
# Loss Streak Kill (3 cases)
# ============================================================================


def test_loss_streak_2():
    """
    시나리오: loss_streak = 2 → ALLOW

    검증:
    - is_halted = False
    - cooldown_until = None
    """
    # Given: loss_streak = 2
    loss_streak_count = 2

    # When: check_loss_streak_kill()
    status = check_loss_streak_kill(loss_streak_count=loss_streak_count)

    # Then: ALLOW
    assert not status.is_halted, "Should not halt at 2 streak"
    assert status.cooldown_until is None


def test_loss_streak_3_halt():
    """
    시나리오: loss_streak = 3 → HALT (당일)

    검증:
    - is_halted = True
    - halt_reason = "loss_streak_3_halt"
    - cooldown_until = next UTC 0:00 (당일 종료)
    """
    # Given: loss_streak = 3
    loss_streak_count = 3
    current_timestamp = 1737600000.0

    # When: check_loss_streak_kill()
    status = check_loss_streak_kill(
        loss_streak_count=loss_streak_count,
        current_timestamp=current_timestamp,
    )

    # Then: HALT (당일)
    assert status.is_halted
    assert status.halt_reason == "loss_streak_3_halt"
    # cooldown_until = next day UTC 0:00
    expected_cooldown = current_timestamp + 86400.0
    assert status.cooldown_until == expected_cooldown


def test_loss_streak_5_cooldown():
    """
    시나리오: loss_streak = 5 → COOLDOWN (72h)

    검증:
    - is_halted = True
    - halt_reason = "loss_streak_5_cooldown"
    - cooldown_until = current_timestamp + 72h
    """
    # Given: loss_streak = 5
    loss_streak_count = 5
    current_timestamp = 1737600000.0

    # When: check_loss_streak_kill()
    status = check_loss_streak_kill(
        loss_streak_count=loss_streak_count,
        current_timestamp=current_timestamp,
    )

    # Then: COOLDOWN (72h = 259200 seconds)
    assert status.is_halted
    assert status.halt_reason == "loss_streak_5_cooldown"
    expected_cooldown = current_timestamp + 259200.0  # 72 hours
    assert status.cooldown_until == expected_cooldown


# ============================================================================
# Fee/Slippage Anomaly (6 cases)
# ============================================================================


def test_fee_spike_single():
    """
    시나리오: fee_ratio 1.6 1회 → ALLOW

    검증:
    - is_halted = False
    """
    # Given: fee_ratio = 1.6 (50% spike), threshold = 1.5, 1회
    fee_ratio_history = [1.6]
    fee_spike_threshold = 1.5

    # When: check_fee_anomaly()
    status = check_fee_anomaly(
        fee_ratio_history=fee_ratio_history,
        fee_spike_threshold=fee_spike_threshold,
    )

    # Then: ALLOW (1회만)
    assert not status.is_halted, "Should not halt on single fee spike"


def test_fee_spike_consecutive_halt():
    """
    시나리오: fee_ratio 1.6, 1.7 연속 2회 → HALT 30분

    검증:
    - is_halted = True
    - halt_reason = "fee_spike_consecutive"
    - cooldown_until = current_timestamp + 30분
    """
    # Given: fee_ratio = [1.6, 1.7] (2회 연속), threshold = 1.5
    fee_ratio_history = [1.6, 1.7]
    fee_spike_threshold = 1.5
    current_timestamp = 1737600000.0

    # When: check_fee_anomaly()
    status = check_fee_anomaly(
        fee_ratio_history=fee_ratio_history,
        fee_spike_threshold=fee_spike_threshold,
        current_timestamp=current_timestamp,
    )

    # Then: HALT 30분 (1800 seconds)
    assert status.is_halted
    assert status.halt_reason == "fee_spike_consecutive"
    expected_cooldown = current_timestamp + 1800.0  # 30 minutes
    assert status.cooldown_until == expected_cooldown


def test_fee_spike_non_consecutive():
    """
    시나리오: fee_ratio [1.6, 1.0, 1.7] (비연속) → ALLOW

    검증:
    - is_halted = False (2회 연속이 아님)
    """
    # Given: fee_ratio = [1.6, 1.0, 1.7] (중간에 정상)
    fee_ratio_history = [1.6, 1.0, 1.7]
    fee_spike_threshold = 1.5

    # When: check_fee_anomaly()
    status = check_fee_anomaly(
        fee_ratio_history=fee_ratio_history,
        fee_spike_threshold=fee_spike_threshold,
    )

    # Then: ALLOW (연속 아님)
    assert not status.is_halted, "Should not halt if spikes are not consecutive"


def test_slippage_spike_2_times():
    """
    시나리오: 10분 내 slippage spike 2회 → ALLOW

    검증:
    - is_halted = False (threshold = 3회)
    """
    # Given: slippage_usd = [-$2, -$2.5], threshold = $2, 2회, 10분 내
    slippage_history = [
        {"slippage_usd": -2.0, "timestamp": 1737600000.0},
        {"slippage_usd": -2.5, "timestamp": 1737600300.0},  # 5분 후
    ]
    slippage_threshold_usd = 2.0
    window_seconds = 600.0  # 10분
    current_timestamp = 1737600500.0  # 최근 slippage 이후 3분

    # When: check_slippage_anomaly()
    status = check_slippage_anomaly(
        slippage_history=slippage_history,
        slippage_threshold_usd=slippage_threshold_usd,
        window_seconds=window_seconds,
        current_timestamp=current_timestamp,
    )

    # Then: ALLOW (2회 < 3회)
    assert not status.is_halted, "Should not halt with only 2 slippage spikes"


def test_slippage_spike_3_times_halt():
    """
    시나리오: 10분 내 slippage spike 3회 → HALT 60분

    검증:
    - is_halted = True
    - halt_reason = "slippage_spike_3_times"
    - cooldown_until = current_timestamp + 60분
    """
    # Given: slippage_usd = [-$2.1, -$2.5, -$3], threshold = $2, 3회, 10분 내
    slippage_history = [
        {"slippage_usd": -2.1, "timestamp": 1737600000.0},  # threshold 초과
        {"slippage_usd": -2.5, "timestamp": 1737600200.0},  # 3분 20초 후
        {"slippage_usd": -3.0, "timestamp": 1737600400.0},  # 6분 40초 후
    ]
    slippage_threshold_usd = 2.0
    window_seconds = 600.0  # 10분
    current_timestamp = 1737600500.0  # 최근 slippage 이후 1분 40초

    # When: check_slippage_anomaly()
    status = check_slippage_anomaly(
        slippage_history=slippage_history,
        slippage_threshold_usd=slippage_threshold_usd,
        window_seconds=window_seconds,
        current_timestamp=current_timestamp,
    )

    # Then: HALT 60분 (3600 seconds)
    assert status.is_halted
    assert status.halt_reason == "slippage_spike_3_times"
    expected_cooldown = current_timestamp + 3600.0  # 60 minutes
    assert status.cooldown_until == expected_cooldown


def test_slippage_spike_window_expired():
    """
    시나리오: 11분 전 spike → 카운트 제외

    검증:
    - is_halted = False (window 밖의 spike는 제외)
    """
    # Given: slippage_usd = [-$2, -$2.5, -$3], 첫 번째는 11분 전
    slippage_history = [
        {"slippage_usd": -2.0, "timestamp": 1737600000.0},  # 11분 전
        {"slippage_usd": -2.5, "timestamp": 1737600660.0},  # window 내
        {"slippage_usd": -3.0, "timestamp": 1737600720.0},  # window 내
    ]
    slippage_threshold_usd = 2.0
    window_seconds = 600.0  # 10분
    current_timestamp = 1737600660.0 + 600.0  # 두 번째 spike 기준 10분 후

    # When: check_slippage_anomaly()
    status = check_slippage_anomaly(
        slippage_history=slippage_history,
        slippage_threshold_usd=slippage_threshold_usd,
        window_seconds=window_seconds,
        current_timestamp=current_timestamp,
    )

    # Then: ALLOW (window 내 2회만, < 3회)
    assert not status.is_halted, "Should not count spikes outside window"

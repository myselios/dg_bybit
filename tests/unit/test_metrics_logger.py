"""
tests/unit/test_metrics_logger.py
Unit tests for metrics logger (Phase 5: Observability)

Purpose:
- Metrics logging schema (winrate/streak/multiplier 변화)
- 시간에 따른 성과 추적 (closed trades 기준)
- Schema validation (필수 필드 누락 시 실패)

SSOT:
- FLOW.md Section 9: Metrics Update는 Closed Trades만
- account_builder_policy.md Section 11: Performance Gates (Winrate + Streak)
- task_plan.md Phase 5: Observability (metrics 변화 로그)

Test Coverage:
1. log_metrics_update_includes_required_fields (필수 필드: winrate, streak, multiplier)
2. log_metrics_update_tracks_performance_over_time (시간에 따른 변화 추적)
3. validate_metrics_schema_rejects_missing_required_field (필수 필드 누락 → ValidationError)
4. log_metrics_update_includes_num_closed_trades (closed trades 수 포함)
"""

from src.infrastructure.logging.metrics_logger import (
    log_metrics_update,
    validate_metrics_schema,
    MetricsLogValidationError,
)


def test_log_metrics_update_includes_required_fields():
    """
    Metrics 로그 필수 필드 검증

    task_plan.md Phase 5:
        - metrics_logger: winrate/streak/multiplier 변화

    Required fields:
        - timestamp (float)
        - winrate (float, 0.0 ~ 1.0)
        - win_streak (int)
        - loss_streak (int)
        - size_multiplier (float)
        - num_closed_trades (int)

    Example:
        winrate=0.6 (60%)
        win_streak=2
        loss_streak=0
        size_multiplier=1.0
        num_closed_trades=10

    Expected:
        log entry 생성 성공
        모든 필수 필드 존재
    """
    log_entry = log_metrics_update(
        timestamp=1705593600.0,
        winrate=0.6,
        win_streak=2,
        loss_streak=0,
        size_multiplier=1.0,
        num_closed_trades=10,
    )

    # 필수 필드 검증
    assert log_entry["timestamp"] == 1705593600.0
    assert log_entry["winrate"] == 0.6
    assert log_entry["win_streak"] == 2
    assert log_entry["loss_streak"] == 0
    assert log_entry["size_multiplier"] == 1.0
    assert log_entry["num_closed_trades"] == 10


def test_log_metrics_update_tracks_performance_over_time():
    """
    시간에 따른 성과 추적

    FLOW Section 9:
        - Winrate/Streak는 CLOSED 거래만 집계
        - pnl > 0 → win_streak++, pnl <= 0 → loss_streak++

    account_builder_policy Section 11.2:
        - 3 consecutive losses → size_mult = max(size_mult * 0.5, 0.25)
        - 3 consecutive wins → size_mult = min(size_mult * 1.5, 1.0)

    Example timeline:
        t0: 5 trades, winrate=0.6, win_streak=2, loss_streak=0, size_mult=1.0
        t1: 8 trades, winrate=0.625, win_streak=3, loss_streak=0, size_mult=1.0 (3연승 직전)
        t2: 10 trades, winrate=0.7, win_streak=4, loss_streak=0, size_mult=1.0 → 0.75 (3연승 달성)

    Expected:
        각 시점의 metrics 변화 추적 가능
    """
    # t0
    log_t0 = log_metrics_update(
        timestamp=1705593000.0,
        winrate=0.6,
        win_streak=2,
        loss_streak=0,
        size_multiplier=1.0,
        num_closed_trades=5,
    )

    # t1 (3연승 직전)
    log_t1 = log_metrics_update(
        timestamp=1705593300.0,
        winrate=0.625,
        win_streak=3,
        loss_streak=0,
        size_multiplier=1.0,
        num_closed_trades=8,
    )

    # t2 (3연승 달성 → size_mult 증가)
    log_t2 = log_metrics_update(
        timestamp=1705593600.0,
        winrate=0.7,
        win_streak=4,
        loss_streak=0,
        size_multiplier=0.75,  # 0.5 * 1.5 = 0.75
        num_closed_trades=10,
    )

    # 시간 순서 확인
    assert log_t0["timestamp"] < log_t1["timestamp"] < log_t2["timestamp"]

    # Winrate 개선 확인
    assert log_t0["winrate"] < log_t1["winrate"] < log_t2["winrate"]

    # Size multiplier 변화 확인 (3연승 달성 후 증가)
    assert log_t0["size_multiplier"] == 1.0
    assert log_t1["size_multiplier"] == 1.0
    assert log_t2["size_multiplier"] == 0.75  # 증가


def test_validate_metrics_schema_rejects_missing_required_field():
    """
    필수 필드 누락 → MetricsLogValidationError

    task_plan.md Phase 5:
        - schema 테스트(필수 필드 누락 시 실패)

    Example:
        log_entry = {"winrate": 0.6}  # timestamp 누락

    Expected:
        MetricsLogValidationError 발생
    """
    # Case 1: timestamp 누락
    log_entry = {
        # "timestamp" 누락
        "winrate": 0.6,
        "win_streak": 2,
        "loss_streak": 0,
        "size_multiplier": 1.0,
        "num_closed_trades": 10,
    }

    try:
        validate_metrics_schema(log_entry)
        assert False, "Expected MetricsLogValidationError for missing timestamp"
    except MetricsLogValidationError as e:
        assert "timestamp" in str(e).lower()

    # Case 2: winrate 누락
    log_entry = {
        "timestamp": 1705593600.0,
        # "winrate" 누락
        "win_streak": 2,
        "loss_streak": 0,
        "size_multiplier": 1.0,
        "num_closed_trades": 10,
    }

    try:
        validate_metrics_schema(log_entry)
        assert False, "Expected MetricsLogValidationError for missing winrate"
    except MetricsLogValidationError as e:
        assert "winrate" in str(e).lower()


def test_log_metrics_update_includes_num_closed_trades():
    """
    Closed trades 수 포함 (재현 가능성)

    FLOW Section 9:
        - Winrate/Streak는 CLOSED 거래만 집계

    account_builder_policy Section 11.1:
        - N = number of CLOSED trades
        - N < 10: backtest_winrate >= 55% only
        - 10 <= N < 30: live_winrate < 40% → WARNING
        - N >= 30: live_winrate < 45% → HALT

    Required field:
        - num_closed_trades (int)

    Example:
        num_closed_trades=5 (N < 10 구간)

    Expected:
        log entry에 num_closed_trades 포함
        Winrate gate 구간 판단 가능
    """
    log_entry = log_metrics_update(
        timestamp=1705593600.0,
        winrate=0.6,
        win_streak=2,
        loss_streak=0,
        size_multiplier=1.0,
        num_closed_trades=5,  # N < 10
    )

    # num_closed_trades 검증
    assert log_entry["num_closed_trades"] == 5

    # Winrate gate 구간 판단 가능
    # N < 10 → backtest만 사용
    assert log_entry["num_closed_trades"] < 10

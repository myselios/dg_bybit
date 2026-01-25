"""
tests/unit/test_metrics_tracker.py
Unit tests for metrics tracker (FLOW Section 9 + account_builder_policy Section 11)

Purpose:
- Winrate 계산 (최근 50 closed trades)
- Streak multiplier (3연승/3연패)
- Size multiplier 조정 (min 0.25, max 1.0)
- Winrate gate 강제 (N < 10 / 10-30 / 30+)

SSOT:
- FLOW.md Section 9: Metrics Update는 Closed Trades만
- account_builder_policy.md Section 11: Performance Gates (Winrate + Streak)

Test Coverage:
1. calculate_winrate_rolling_window (최근 50 closed trades 기준)
2. update_metrics_on_closed_trade_win (pnl > 0 → win_streak++, loss_streak=0)
3. update_metrics_on_closed_trade_loss (pnl <= 0 → loss_streak++, win_streak=0)
4. loss_streak_reduces_size_multiplier (3 연패 → size_mult * 0.5, min 0.25)
5. win_streak_recovers_size_multiplier (3 연승 → size_mult * 1.5, max 1.0)
6. winrate_gate_enforcement (N < 10: backtest만, 10-30: soft gate, 30+: hard gate)
"""

from src.application.metrics_tracker import (
    calculate_winrate,
    update_streak_on_closed_trade,
    apply_streak_multiplier,
    check_winrate_gate,
)


def test_calculate_winrate_rolling_window():
    """
    Winrate 계산 (최근 50 closed trades 기준)

    FLOW Section 9:
        - Winrate는 CLOSED 거래만 집계
        - Rolling window: 최근 50 trades (또는 그 이하)

    account_builder_policy Section 11.1:
        - live_winrate = wins / total (최근 50)

    Example:
        closed_trades = [
            {"pnl_btc": 0.001},  # win
            {"pnl_btc": -0.0005},  # loss
            {"pnl_btc": 0.002},  # win
            {"pnl_btc": 0.0001},  # win
            {"pnl_btc": -0.001},  # loss
        ]
        wins = 3, total = 5
        winrate = 3 / 5 = 0.6 (60%)

    Expected:
        winrate = 0.6
    """
    closed_trades = [
        {"pnl_btc": 0.001},  # win
        {"pnl_btc": -0.0005},  # loss
        {"pnl_btc": 0.002},  # win
        {"pnl_btc": 0.0001},  # win
        {"pnl_btc": -0.001},  # loss
    ]

    winrate = calculate_winrate(closed_trades, window_size=50)

    # 3 wins / 5 total = 0.6
    assert abs(winrate - 0.6) < 1e-6, f"Expected 0.6, got {winrate}"


def test_update_metrics_on_closed_trade_win():
    """
    pnl > 0 → win_streak++, loss_streak=0 (FLOW Section 9)

    FLOW Section 9:
        if pnl_btc > 0:
            win_streak += 1
            loss_streak = 0

    Example:
        pnl_btc = 0.001 (win)
        win_streak = 1, loss_streak = 2

    Expected:
        new_win_streak = 2
        new_loss_streak = 0
    """
    pnl_btc = 0.001  # win
    win_streak = 1
    loss_streak = 2

    new_win_streak, new_loss_streak = update_streak_on_closed_trade(
        pnl_btc=pnl_btc,
        win_streak=win_streak,
        loss_streak=loss_streak,
    )

    # pnl > 0 → win_streak++, loss_streak=0
    assert new_win_streak == 2
    assert new_loss_streak == 0


def test_update_metrics_on_closed_trade_loss():
    """
    pnl <= 0 → loss_streak++, win_streak=0 (FLOW Section 9)

    FLOW Section 9:
        else:
            loss_streak += 1
            win_streak = 0

    Example:
        pnl_btc = -0.0005 (loss)
        win_streak = 2, loss_streak = 0

    Expected:
        new_win_streak = 0
        new_loss_streak = 1
    """
    pnl_btc = -0.0005  # loss
    win_streak = 2
    loss_streak = 0

    new_win_streak, new_loss_streak = update_streak_on_closed_trade(
        pnl_btc=pnl_btc,
        win_streak=win_streak,
        loss_streak=loss_streak,
    )

    # pnl <= 0 → loss_streak++, win_streak=0
    assert new_win_streak == 0
    assert new_loss_streak == 1


def test_loss_streak_reduces_size_multiplier():
    """
    3 연패 → size_multiplier × 0.5 (min 0.25)

    account_builder_policy Section 11.2:
        - 3 consecutive losses → size_mult = max(size_mult * 0.5, 0.25)

    Example:
        loss_streak = 3
        current_size_mult = 1.0

    Expected:
        new_size_mult = max(1.0 * 0.5, 0.25) = 0.5

    Example 2:
        loss_streak = 3
        current_size_mult = 0.5

    Expected:
        new_size_mult = max(0.5 * 0.5, 0.25) = 0.25 (min cap)
    """
    # Case 1: 1.0 → 0.5
    loss_streak = 3
    current_size_mult = 1.0

    new_size_mult = apply_streak_multiplier(
        loss_streak=loss_streak,
        win_streak=0,
        current_size_mult=current_size_mult,
        loss_reduce_ratio=0.5,
        win_recover_ratio=1.5,
        min_multiplier=0.25,
        max_multiplier=1.0,
    )

    assert abs(new_size_mult - 0.5) < 1e-6, f"Expected 0.5, got {new_size_mult}"

    # Case 2: 0.5 → 0.25 (min cap)
    loss_streak = 3
    current_size_mult = 0.5

    new_size_mult = apply_streak_multiplier(
        loss_streak=loss_streak,
        win_streak=0,
        current_size_mult=current_size_mult,
        loss_reduce_ratio=0.5,
        win_recover_ratio=1.5,
        min_multiplier=0.25,
        max_multiplier=1.0,
    )

    assert abs(new_size_mult - 0.25) < 1e-6, f"Expected 0.25, got {new_size_mult}"


def test_win_streak_recovers_size_multiplier():
    """
    3 연승 → size_multiplier × 1.5 (max 1.0)

    account_builder_policy Section 11.2:
        - 3 consecutive wins → size_mult = min(size_mult * 1.5, 1.0)

    Example:
        win_streak = 3
        current_size_mult = 0.5

    Expected:
        new_size_mult = min(0.5 * 1.5, 1.0) = 0.75

    Example 2:
        win_streak = 3
        current_size_mult = 0.8

    Expected:
        new_size_mult = min(0.8 * 1.5, 1.0) = 1.0 (max cap)
    """
    # Case 1: 0.5 → 0.75
    win_streak = 3
    current_size_mult = 0.5

    new_size_mult = apply_streak_multiplier(
        loss_streak=0,
        win_streak=win_streak,
        current_size_mult=current_size_mult,
        loss_reduce_ratio=0.5,
        win_recover_ratio=1.5,
        min_multiplier=0.25,
        max_multiplier=1.0,
    )

    assert abs(new_size_mult - 0.75) < 1e-6, f"Expected 0.75, got {new_size_mult}"

    # Case 2: 0.8 → 1.0 (max cap)
    win_streak = 3
    current_size_mult = 0.8

    new_size_mult = apply_streak_multiplier(
        loss_streak=0,
        win_streak=win_streak,
        current_size_mult=current_size_mult,
        loss_reduce_ratio=0.5,
        win_recover_ratio=1.5,
        min_multiplier=0.25,
        max_multiplier=1.0,
    )

    assert abs(new_size_mult - 1.0) < 1e-6, f"Expected 1.0, got {new_size_mult}"


def test_winrate_gate_enforcement():
    """
    Winrate gate 강제 (N < 10 / 10-30 / 30+)

    account_builder_policy Section 11.1:
        - N < 10: backtest_winrate >= 55% only (live 무시)
        - 10 <= N < 30: live_winrate < 40% → WARNING + size_mult *= 0.5
        - N >= 30: live_winrate < 45% → HALT

    Example 1:
        N = 5 (< 10)
        backtest_winrate = 0.58 (58% >= 55%)

    Expected:
        gate_status = "PASS"
        action = "ALLOW"

    Example 2:
        N = 20 (10-30)
        live_winrate = 0.35 (35% < 40%)

    Expected:
        gate_status = "WARNING"
        action = "REDUCE_SIZE"
        size_mult *= 0.5

    Example 3:
        N = 40 (>= 30)
        live_winrate = 0.42 (42% < 45%)

    Expected:
        gate_status = "FAIL"
        action = "HALT"
    """
    # Case 1: N < 10, backtest 55% 이상
    result = check_winrate_gate(
        num_closed_trades=5,
        live_winrate=0.30,  # 무시됨
        backtest_winrate=0.58,
        backtest_min_pct=0.55,
        soft_min_pct=0.40,
        hard_min_pct=0.45,
    )

    assert result["gate_status"] == "PASS"
    assert result["action"] == "ALLOW"

    # Case 2: 10 <= N < 30, live < 40%
    result = check_winrate_gate(
        num_closed_trades=20,
        live_winrate=0.35,
        backtest_winrate=0.58,  # 무시됨
        backtest_min_pct=0.55,
        soft_min_pct=0.40,
        hard_min_pct=0.45,
    )

    assert result["gate_status"] == "WARNING"
    assert result["action"] == "REDUCE_SIZE"

    # Case 3: N >= 30, live < 45%
    result = check_winrate_gate(
        num_closed_trades=40,
        live_winrate=0.42,
        backtest_winrate=0.58,  # 무시됨
        backtest_min_pct=0.55,
        soft_min_pct=0.40,
        hard_min_pct=0.45,
    )

    assert result["gate_status"] == "FAIL"
    assert result["action"] == "HALT"

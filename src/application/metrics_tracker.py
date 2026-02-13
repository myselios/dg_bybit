"""
src/application/metrics_tracker.py
Metrics Tracker — Winrate/Streak 계산 및 Gate 강제 (FLOW Section 9 + Policy Section 11)

SSOT:
- FLOW.md Section 9: Metrics Update는 Closed Trades만
- account_builder_policy.md Section 11: Performance Gates (Winrate + Streak)

원칙:
1. Winrate는 CLOSED 거래만 집계 (최근 50 trades)
2. Streak: pnl > 0 → win_streak++, pnl <= 0 → loss_streak++
3. Loss streak 3연속 → size_mult × 0.5 (min 0.25)
4. Win streak 3연속 → size_mult × 1.5 (max 1.0)
5. Winrate gate: N < 10 (backtest만) / 10-30 (soft) / 30+ (hard)

Exports:
- calculate_winrate(): Winrate 계산 (최근 50 closed trades)
- update_streak_on_closed_trade(): Streak 갱신 (win/loss)
- apply_streak_multiplier(): Size multiplier 조정 (3연승/3연패)
- check_winrate_gate(): Winrate gate 강제 (N < 10 / 10-30 / 30+)
"""

from typing import List, Dict, Tuple


def calculate_winrate(closed_trades: List[Dict], window_size: int = 50) -> float:
    """
    Winrate 계산 (최근 50 closed trades 기준)

    Args:
        closed_trades: CLOSED 거래 목록 (각 거래는 {"pnl": float})
        window_size: Rolling window 크기 (기본 50)

    Returns:
        winrate: wins / total (0.0 ~ 1.0)

    FLOW Section 9:
        - Winrate는 CLOSED 거래만 집계

    account_builder_policy Section 11.1:
        - live_winrate: 최근 50 closed trades (또는 그 이하)
    """
    if not closed_trades:
        return 0.0

    # 최근 window_size 거래만 사용
    recent_trades = closed_trades[-window_size:]

    # pnl > 0 → win
    wins = sum(1 for trade in recent_trades if trade.get("pnl", 0) > 0)
    total = len(recent_trades)

    if total == 0:
        return 0.0

    return wins / total


def update_streak_on_closed_trade(
    pnl: float,
    win_streak: int,
    loss_streak: int,
) -> Tuple[int, int]:
    """
    Streak 갱신 (win/loss)

    Args:
        pnl: 청산 PnL (USDT)
        win_streak: 현재 연승 수
        loss_streak: 현재 연패 수

    Returns:
        (new_win_streak, new_loss_streak)

    FLOW Section 9:
        if pnl > 0:
            win_streak += 1
            loss_streak = 0
        else:
            loss_streak += 1
            win_streak = 0
    """
    if pnl > 0:
        # Win → win_streak++, loss_streak=0
        return win_streak + 1, 0
    else:
        # Loss → loss_streak++, win_streak=0
        return 0, loss_streak + 1


def apply_streak_multiplier(
    loss_streak: int,
    win_streak: int,
    current_size_mult: float,
    loss_reduce_ratio: float,
    win_recover_ratio: float,
    min_multiplier: float,
    max_multiplier: float,
) -> float:
    """
    Size multiplier 조정 (3연승/3연패)

    Args:
        loss_streak: 현재 연패 수
        win_streak: 현재 연승 수
        current_size_mult: 현재 size_multiplier
        loss_reduce_ratio: 연패 시 감소 비율 (기본 0.5)
        win_recover_ratio: 연승 시 증가 비율 (기본 1.5)
        min_multiplier: 최소 multiplier (기본 0.25)
        max_multiplier: 최대 multiplier (기본 1.0)

    Returns:
        new_size_mult: 조정된 size_multiplier

    account_builder_policy Section 11.2:
        - 3 consecutive losses → size_mult = max(size_mult * 0.5, 0.25)
        - 3 consecutive wins → size_mult = min(size_mult * 1.5, 1.0)
    """
    # (1) 3 연패 → 감소
    if loss_streak >= 3:
        new_size_mult = current_size_mult * loss_reduce_ratio
        return max(new_size_mult, min_multiplier)

    # (2) 3 연승 → 증가
    if win_streak >= 3:
        new_size_mult = current_size_mult * win_recover_ratio
        return min(new_size_mult, max_multiplier)

    # (3) 조건 미달 → 유지
    return current_size_mult


def check_winrate_gate(
    num_closed_trades: int,
    live_winrate: float,
    backtest_winrate: float,
    backtest_min_pct: float,
    soft_min_pct: float,
    hard_min_pct: float,
) -> Dict[str, str]:
    """
    Winrate gate 강제 (N < 10 / 10-30 / 30+)

    Args:
        num_closed_trades: CLOSED 거래 수 (N)
        live_winrate: Live winrate (0.0 ~ 1.0)
        backtest_winrate: Backtest winrate (0.0 ~ 1.0)
        backtest_min_pct: Backtest 최소 winrate (기본 0.55)
        soft_min_pct: Soft gate 최소 winrate (기본 0.40)
        hard_min_pct: Hard gate 최소 winrate (기본 0.45)

    Returns:
        {
            "gate_status": "PASS" | "WARNING" | "FAIL",
            "action": "ALLOW" | "REDUCE_SIZE" | "HALT"
        }

    account_builder_policy Section 11.1:
        - N < 10: backtest_winrate >= 55% only (live 무시)
        - 10 <= N < 30: live_winrate < 40% → WARNING + size_mult *= 0.5
        - N >= 30: live_winrate < 45% → HALT
    """
    # (1) N < 10: backtest만 확인
    if num_closed_trades < 10:
        if backtest_winrate >= backtest_min_pct:
            return {"gate_status": "PASS", "action": "ALLOW"}
        else:
            return {"gate_status": "FAIL", "action": "HALT"}

    # (2) 10 <= N < 30: soft gate (live < 40%)
    if 10 <= num_closed_trades < 30:
        if live_winrate < soft_min_pct:
            return {"gate_status": "WARNING", "action": "REDUCE_SIZE"}
        else:
            return {"gate_status": "PASS", "action": "ALLOW"}

    # (3) N >= 30: hard gate (live < 45%)
    if live_winrate < hard_min_pct:
        return {"gate_status": "FAIL", "action": "HALT"}
    else:
        return {"gate_status": "PASS", "action": "ALLOW"}

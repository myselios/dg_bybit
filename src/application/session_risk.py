"""
application/session_risk.py
Session Risk Policy (Phase 9a)

SSOT: task_plan.md Phase 9a

책임:
- Daily Loss Cap (일일 손실 상한 5%)
- Weekly Loss Cap (주간 손실 상한 12.5%)
- Loss Streak Kill (3연패 HALT, 5연패 COOLDOWN)
- Fee/Slippage Anomaly (연속 spike → HALT)

Exports:
- SessionRiskStatus: Session Risk 검증 결과
- check_daily_loss_cap: Daily loss cap 검증
- check_weekly_loss_cap: Weekly loss cap 검증
- check_loss_streak_kill: Loss streak kill 검증
- check_fee_anomaly: Fee spike anomaly 검증
- check_slippage_anomaly: Slippage spike anomaly 검증
"""

import math
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass(frozen=True)
class SessionRiskStatus:
    """
    Session Risk 검증 결과

    Fields:
    - is_halted: bool (HALT 여부)
    - halt_reason: Optional[str] (HALT 이유)
    - cooldown_until: Optional[float] (COOLDOWN 종료 시각, None = 무제한 허용)
    """

    is_halted: bool
    halt_reason: Optional[str] = None
    cooldown_until: Optional[float] = None


def check_daily_loss_cap(
    equity_usd: float,
    daily_realized_pnl_usd: float,
    daily_loss_cap_pct: float,
    current_timestamp: Optional[float] = None,
) -> SessionRiskStatus:
    """
    Daily Loss Cap 검증

    Args:
        equity_usd: 현재 equity (USD)
        daily_realized_pnl_usd: 당일 realized PnL (USD)
        daily_loss_cap_pct: Daily loss cap (%)
        current_timestamp: 현재 timestamp (초), None이면 cooldown 계산 안 함

    Returns:
        SessionRiskStatus

    SSOT: task_plan.md Phase 9a
    - Trigger: daily_pnl <= -daily_loss_cap_pct% equity
    - Action: HALT + COOLDOWN (다음날 UTC 0시까지)
    """
    # daily loss pct 계산
    daily_loss_pct = (daily_realized_pnl_usd / equity_usd) * 100.0

    # cap 초과 여부 확인
    if daily_loss_pct <= -daily_loss_cap_pct:
        # HALT + COOLDOWN (next day UTC 0:00)
        cooldown_until = None
        if current_timestamp is not None:
            # 다음날 UTC 0:00 = (floor(current / 86400) + 1) * 86400
            days = int(current_timestamp / 86400.0)
            next_utc_midnight = (days + 1) * 86400.0
            cooldown_until = next_utc_midnight

        return SessionRiskStatus(
            is_halted=True,
            halt_reason="daily_loss_cap_exceeded",
            cooldown_until=cooldown_until,
        )

    # ALLOW
    return SessionRiskStatus(is_halted=False)


def check_weekly_loss_cap(
    equity_usd: float,
    weekly_realized_pnl_usd: float,
    weekly_loss_cap_pct: float,
    current_timestamp: Optional[float] = None,
) -> SessionRiskStatus:
    """
    Weekly Loss Cap 검증

    Args:
        equity_usd: 현재 equity (USD)
        weekly_realized_pnl_usd: 주간 realized PnL (USD)
        weekly_loss_cap_pct: Weekly loss cap (%)
        current_timestamp: 현재 timestamp (초), None이면 cooldown 계산 안 함

    Returns:
        SessionRiskStatus

    SSOT: task_plan.md Phase 9a
    - Trigger: weekly_pnl <= -weekly_loss_cap_pct% equity
    - Action: COOLDOWN (7일)
    """
    # weekly loss pct 계산
    weekly_loss_pct = (weekly_realized_pnl_usd / equity_usd) * 100.0

    # cap 초과 여부 확인
    if weekly_loss_pct <= -weekly_loss_cap_pct:
        # HALT + COOLDOWN (7 days)
        cooldown_until = None
        if current_timestamp is not None:
            cooldown_until = current_timestamp + 604800.0  # 7 days

        return SessionRiskStatus(
            is_halted=True,
            halt_reason="weekly_loss_cap_exceeded",
            cooldown_until=cooldown_until,
        )

    # ALLOW
    return SessionRiskStatus(is_halted=False)


def check_loss_streak_kill(
    loss_streak_count: int,
    current_timestamp: Optional[float] = None,
) -> SessionRiskStatus:
    """
    Loss Streak Kill 검증

    Args:
        loss_streak_count: 연속 손실 카운트
        current_timestamp: 현재 timestamp (초), None이면 cooldown 계산 안 함

    Returns:
        SessionRiskStatus

    SSOT: task_plan.md Phase 9a
    - 3연패: HALT (당일 종료, 다음날 UTC 0시까지)
    - 5연패: COOLDOWN (72h)
    """
    # 5연패: COOLDOWN (72h)
    if loss_streak_count >= 5:
        cooldown_until = None
        if current_timestamp is not None:
            cooldown_until = current_timestamp + 259200.0  # 72 hours

        return SessionRiskStatus(
            is_halted=True,
            halt_reason="loss_streak_5_cooldown",
            cooldown_until=cooldown_until,
        )

    # 3연패: HALT (당일, next day UTC 0:00)
    if loss_streak_count >= 3:
        cooldown_until = None
        if current_timestamp is not None:
            # 다음날 UTC 0:00 = (floor(current / 86400) + 1) * 86400
            days = int(current_timestamp / 86400.0)
            next_utc_midnight = (days + 1) * 86400.0
            cooldown_until = next_utc_midnight

        return SessionRiskStatus(
            is_halted=True,
            halt_reason="loss_streak_3_halt",
            cooldown_until=cooldown_until,
        )

    # ALLOW
    return SessionRiskStatus(is_halted=False)


def check_fee_anomaly(
    fee_ratio_history: List[float],
    fee_spike_threshold: float,
    current_timestamp: Optional[float] = None,
) -> SessionRiskStatus:
    """
    Fee Spike Anomaly 검증

    Args:
        fee_ratio_history: Fee ratio 히스토리 (최근 순서)
        fee_spike_threshold: Fee spike threshold (예: 1.5 = 50% 초과)
        current_timestamp: 현재 timestamp (초), None이면 cooldown 계산 안 함

    Returns:
        SessionRiskStatus

    SSOT: task_plan.md Phase 9a
    - Fee spike: fee_ratio > threshold, 2회 연속 → HALT 30분
    """
    # 최소 2개 필요
    if len(fee_ratio_history) < 2:
        return SessionRiskStatus(is_halted=False)

    # 최근 2개 모두 threshold 초과 확인
    last_two = fee_ratio_history[-2:]
    if all(ratio > fee_spike_threshold for ratio in last_two):
        # HALT 30분
        cooldown_until = None
        if current_timestamp is not None:
            cooldown_until = current_timestamp + 1800.0  # 30 minutes

        return SessionRiskStatus(
            is_halted=True,
            halt_reason="fee_spike_consecutive",
            cooldown_until=cooldown_until,
        )

    # ALLOW
    return SessionRiskStatus(is_halted=False)


def check_slippage_anomaly(
    slippage_history: List[Dict[str, Any]],
    slippage_threshold_usd: float,
    window_seconds: float,
    current_timestamp: float,
) -> SessionRiskStatus:
    """
    Slippage Spike Anomaly 검증

    Args:
        slippage_history: Slippage 히스토리 (Dict with 'slippage_usd', 'timestamp')
        slippage_threshold_usd: Slippage threshold (USD)
        window_seconds: 시간 윈도우 (초, 예: 600 = 10분)
        current_timestamp: 현재 timestamp (초)

    Returns:
        SessionRiskStatus

    SSOT: task_plan.md Phase 9a
    - Slippage spike: |slippage_usd| > threshold, 3회/window → HALT 60분
    """
    # window 내의 spike 카운트
    window_start = current_timestamp - window_seconds
    spike_count = 0

    for entry in slippage_history:
        timestamp = entry["timestamp"]
        slippage_usd = entry["slippage_usd"]

        # window 내인지 확인
        if timestamp >= window_start:
            # threshold 초과 확인
            if abs(slippage_usd) > slippage_threshold_usd:
                spike_count += 1

    # 3회 이상 → HALT 60분
    if spike_count >= 3:
        cooldown_until = current_timestamp + 3600.0  # 60 minutes

        return SessionRiskStatus(
            is_halted=True,
            halt_reason="slippage_spike_3_times",
            cooldown_until=cooldown_until,
        )

    # ALLOW
    return SessionRiskStatus(is_halted=False)

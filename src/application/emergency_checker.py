"""
src/application/emergency_checker.py
Emergency Status Checker (Session Risk Integration)

Purpose:
- Integrate all emergency checks (balance, degraded, Session Risk Policy)
- Thin function called by Orchestrator
- Reduce orchestrator.py LOC (God Object refactoring)

SSOT:
- FLOW.md Section 7.1: Emergency Checks
- account_builder_policy.md Section 9: Session Risk Policy
- task_plan.md Phase 9c: Session Risk Integration

Design:
- check_emergency_status(): Pure function (no I/O, no state mutation)
- Returns {"status": "PASS" or "HALT", "reason": str}
- All emergency conditions in one place
"""

from typing import Optional
from infrastructure.exchange.market_data_interface import MarketDataInterface
from application.session_risk import (
    check_daily_loss_cap,
    check_weekly_loss_cap,
    check_loss_streak_kill,
    check_fee_anomaly,
    check_slippage_anomaly,
)


def check_emergency_status(
    market_data: MarketDataInterface,
    daily_loss_cap_pct: float,
    weekly_loss_cap_pct: float,
    fee_spike_threshold: float,
    slippage_threshold_usd: float,
    slippage_window_seconds: float,
    current_timestamp: Optional[float],
) -> dict:
    """
    Emergency 체크 (최우선)

    Args:
        market_data: Market data interface
        daily_loss_cap_pct: Daily loss cap (%, 예: 5.0 = 5%)
        weekly_loss_cap_pct: Weekly loss cap (%, 예: 12.5 = 12.5%)
        fee_spike_threshold: Fee spike threshold (예: 1.5)
        slippage_threshold_usd: Slippage threshold (USD, 예: 2.0)
        slippage_window_seconds: Slippage window (seconds, 예: 600.0)
        current_timestamp: Current timestamp (for Session Risk checks)

    Returns:
        {"status": "PASS" or "HALT", "reason": str}

    Emergency Conditions:
        1. balance_too_low (equity <= 0)
        2. degraded_timeout (WS degraded > 60s)
        3. Session Risk Policy 4개:
           - Daily Loss Cap (-5%)
           - Weekly Loss Cap (-12.5%)
           - Loss Streak Kill (3연패, 5연패)
           - Fee/Slippage Anomaly (2회 연속, 3회/10분)

    FLOW Section 7.1 + Phase 9c Session Risk Policy
    """
    # (1) balance_too_low 체크
    equity_btc = market_data.get_equity_btc()
    if equity_btc <= 0:
        return {"status": "HALT", "reason": "balance_too_low"}

    # (2) degraded timeout 체크 (60초)
    degraded_timeout = market_data.is_degraded_timeout()
    if degraded_timeout:
        return {"status": "HALT", "reason": "degraded_mode_timeout"}

    # Session Risk Policy 체크 (Phase 9c)
    btc_mark_price_usd = market_data.get_btc_mark_price_usd()
    equity_usd = equity_btc * btc_mark_price_usd

    # (3) Daily Loss Cap
    daily_pnl = market_data.get_daily_realized_pnl_usd()
    if daily_pnl is not None:
        daily_status = check_daily_loss_cap(
            equity_usd=equity_usd,
            daily_realized_pnl_usd=daily_pnl,
            daily_loss_cap_pct=daily_loss_cap_pct,
            current_timestamp=current_timestamp,
        )
        if daily_status.is_halted:
            return {"status": "HALT", "reason": daily_status.halt_reason}

    # (4) Weekly Loss Cap
    weekly_pnl = market_data.get_weekly_realized_pnl_usd()
    if weekly_pnl is not None:
        weekly_status = check_weekly_loss_cap(
            equity_usd=equity_usd,
            weekly_realized_pnl_usd=weekly_pnl,
            weekly_loss_cap_pct=weekly_loss_cap_pct,
            current_timestamp=current_timestamp,
        )
        if weekly_status.is_halted:
            return {"status": "HALT", "reason": weekly_status.halt_reason}

    # (5) Loss Streak Kill
    loss_streak = market_data.get_loss_streak_count()
    if loss_streak is not None:
        streak_status = check_loss_streak_kill(
            loss_streak_count=loss_streak,
            current_timestamp=current_timestamp,
        )
        if streak_status.is_halted:
            return {"status": "HALT", "reason": streak_status.halt_reason}

    # (6) Fee Anomaly
    fee_history = market_data.get_fee_ratio_history()
    if fee_history is not None:
        fee_status = check_fee_anomaly(
            fee_ratio_history=fee_history,
            fee_spike_threshold=fee_spike_threshold,
            current_timestamp=current_timestamp,
        )
        if fee_status.is_halted:
            return {"status": "HALT", "reason": fee_status.halt_reason}

    # (7) Slippage Anomaly
    slippage_history = market_data.get_slippage_history()
    if slippage_history is not None and current_timestamp is not None:
        slippage_status = check_slippage_anomaly(
            slippage_history=slippage_history,
            slippage_threshold_usd=slippage_threshold_usd,
            window_seconds=slippage_window_seconds,
            current_timestamp=current_timestamp,
        )
        if slippage_status.is_halted:
            return {"status": "HALT", "reason": slippage_status.halt_reason}

    # All checks passed
    return {"status": "PASS", "reason": None}

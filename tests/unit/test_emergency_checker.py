"""
tests/unit/test_emergency_checker.py

Gate: check_emergency_status() 단위 테스트

Purpose:
- emergency_checker.check_emergency_status()의 7가지 체크 경로 검증
- 각 HALT 조건 + 전체 PASS 경로 커버

Execution:
  pytest tests/unit/test_emergency_checker.py -v
"""

from unittest.mock import MagicMock
from application.emergency_checker import check_emergency_status
from application.session_risk import SessionRiskStatus


def _make_market_data(
    equity_usdt=105.0,
    degraded_timeout=False,
    daily_pnl=None,
    weekly_pnl=None,
    loss_streak=None,
    fee_history=None,
    slippage_history=None,
):
    """Helper: MarketDataInterface mock 생성."""
    md = MagicMock()
    md.get_equity_usdt.return_value = equity_usdt
    md.is_degraded_timeout.return_value = degraded_timeout
    md.get_daily_realized_pnl_usd.return_value = daily_pnl
    md.get_weekly_realized_pnl_usd.return_value = weekly_pnl
    md.get_loss_streak_count.return_value = loss_streak
    md.get_fee_ratio_history.return_value = fee_history
    md.get_slippage_history.return_value = slippage_history
    return md


# ============================================================
# (1) balance_too_low 체크
# ============================================================


def test_equity_zero_triggers_halt():
    """equity_usdt == 0 → HALT balance_too_low."""
    md = _make_market_data(equity_usdt=0.0)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "HALT"
    assert result["reason"] == "balance_too_low"


def test_equity_negative_triggers_halt():
    """equity_usdt < 0 → HALT balance_too_low."""
    md = _make_market_data(equity_usdt=-5.0)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "HALT"
    assert result["reason"] == "balance_too_low"


# ============================================================
# (2) degraded_mode_timeout 체크
# ============================================================


def test_degraded_timeout_triggers_halt():
    """WS degraded 60초 초과 → HALT degraded_mode_timeout."""
    md = _make_market_data(degraded_timeout=True)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "HALT"
    assert result["reason"] == "degraded_mode_timeout"


def test_not_degraded_passes():
    """WS degraded=False → 이 체크는 통과."""
    md = _make_market_data(degraded_timeout=False)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "PASS"
    assert result["reason"] is None


# ============================================================
# (3) daily_loss_cap 체크
# ============================================================


def test_daily_loss_cap_exceeded_triggers_halt():
    """일일 손실 -5% 초과 → HALT daily_loss_cap_exceeded."""
    # equity=100, daily_pnl=-6 → -6% > -5% cap
    md = _make_market_data(equity_usdt=100.0, daily_pnl=-6.0)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "HALT"
    assert "daily_loss_cap" in result["reason"]


def test_daily_loss_within_cap_passes():
    """일일 손실 -3% (cap 5% 이내) → PASS."""
    md = _make_market_data(equity_usdt=100.0, daily_pnl=-3.0)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "PASS"
    assert result["reason"] is None


def test_daily_pnl_none_skips_check():
    """daily_pnl=None → daily loss cap 체크 건너뛰기."""
    md = _make_market_data(equity_usdt=100.0, daily_pnl=None)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "PASS"


# ============================================================
# (4) weekly_loss_cap 체크
# ============================================================


def test_weekly_loss_cap_exceeded_triggers_halt():
    """주간 손실 -12.5% 초과 → HALT."""
    # equity=100, weekly_pnl=-15 → -15% > -12.5%
    md = _make_market_data(equity_usdt=100.0, weekly_pnl=-15.0)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "HALT"
    assert "weekly_loss_cap" in result["reason"]


def test_weekly_pnl_none_skips_check():
    """weekly_pnl=None → weekly loss cap 체크 건너뛰기."""
    md = _make_market_data(equity_usdt=100.0, weekly_pnl=None)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "PASS"


# ============================================================
# (5) loss_streak_kill 체크
# ============================================================


def test_loss_streak_5_triggers_halt():
    """5연패 → HALT."""
    md = _make_market_data(loss_streak=5)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "HALT"
    assert "loss_streak" in result["reason"]


def test_loss_streak_none_skips_check():
    """loss_streak=None → 체크 건너뛰기."""
    md = _make_market_data(loss_streak=None)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "PASS"


def test_loss_streak_2_passes():
    """2연패 → PASS (3연패부터 HALT)."""
    md = _make_market_data(loss_streak=2)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "PASS"


# ============================================================
# (6) fee_anomaly 체크
# ============================================================


def test_fee_anomaly_consecutive_spikes_triggers_halt():
    """Fee ratio 연속 spike → HALT."""
    # fee_spike_threshold=1.5, 연속 2회 초과 → HALT
    md = _make_market_data(fee_history=[2.0, 1.8])

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "HALT"
    assert "fee" in result["reason"]


def test_fee_history_none_skips_check():
    """fee_history=None → 체크 건너뛰기."""
    md = _make_market_data(fee_history=None)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "PASS"


def test_fee_history_below_threshold_passes():
    """Fee ratio가 threshold 미만 → PASS."""
    md = _make_market_data(fee_history=[1.0, 0.8, 1.2])

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "PASS"


# ============================================================
# (7) slippage_anomaly 체크
# ============================================================


def test_slippage_anomaly_triggers_halt():
    """Slippage 윈도우 내 3회 이상 → HALT."""
    ts = 1700000000.0
    slippage_data = [
        {"slippage_usd": 3.0, "timestamp": ts - 100},
        {"slippage_usd": 2.5, "timestamp": ts - 200},
        {"slippage_usd": 4.0, "timestamp": ts - 300},
    ]
    md = _make_market_data(slippage_history=slippage_data)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=ts,
    )

    assert result["status"] == "HALT"
    assert "slippage" in result["reason"]


def test_slippage_history_none_skips_check():
    """slippage_history=None → 체크 건너뛰기."""
    md = _make_market_data(slippage_history=None)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "PASS"


def test_slippage_with_none_timestamp_skips_check():
    """current_timestamp=None → slippage 체크 건너뛰기."""
    slippage_data = [
        {"slippage_usd": 3.0, "timestamp": 1700000000.0},
    ]
    md = _make_market_data(slippage_history=slippage_data)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=None,
    )

    assert result["status"] == "PASS"


# ============================================================
# 전체 PASS 경로
# ============================================================


def test_all_checks_pass_returns_pass():
    """모든 체크 통과 시 PASS 반환."""
    md = _make_market_data(
        equity_usdt=100.0,
        degraded_timeout=False,
        daily_pnl=-2.0,
        weekly_pnl=-5.0,
        loss_streak=1,
        fee_history=[0.5, 0.8],
        slippage_history=[],
    )

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "PASS"
    assert result["reason"] is None


# ============================================================
# Priority order: balance → degraded → daily → weekly → streak
# ============================================================


def test_balance_halt_takes_priority_over_degraded():
    """equity<=0과 degraded 동시 발생 시 balance_too_low가 먼저."""
    md = _make_market_data(equity_usdt=0.0, degraded_timeout=True)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "HALT"
    assert result["reason"] == "balance_too_low"


def test_degraded_halt_takes_priority_over_daily_loss():
    """degraded와 daily loss 동시 → degraded_mode_timeout이 먼저."""
    md = _make_market_data(
        equity_usdt=100.0,
        degraded_timeout=True,
        daily_pnl=-10.0,
    )

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "HALT"
    assert result["reason"] == "degraded_mode_timeout"


# ============================================================
# Boundary values
# ============================================================


def test_equity_exactly_zero_triggers_halt():
    """equity_usdt == 0 (경계값) → HALT."""
    md = _make_market_data(equity_usdt=0.0)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "HALT"
    assert result["reason"] == "balance_too_low"


def test_equity_small_positive_passes():
    """equity_usdt == 0.01 (작지만 양수) → balance check PASS."""
    md = _make_market_data(equity_usdt=0.01)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "PASS"


def test_daily_loss_at_exact_boundary():
    """daily_pnl이 정확히 -5% → HALT (boundary: <= -cap)."""
    md = _make_market_data(equity_usdt=100.0, daily_pnl=-5.0)

    result = check_emergency_status(
        market_data=md,
        daily_loss_cap_pct=5.0,
        weekly_loss_cap_pct=12.5,
        fee_spike_threshold=1.5,
        slippage_threshold_usd=2.0,
        slippage_window_seconds=600.0,
        current_timestamp=1700000000.0,
    )

    assert result["status"] == "HALT"
    assert "daily_loss_cap" in result["reason"]

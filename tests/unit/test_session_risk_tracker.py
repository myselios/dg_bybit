"""
tests/unit/test_session_risk_tracker.py
Session Risk Tracker Unit Tests

Purpose:
- Trade history → Daily/Weekly PnL 계산 검증
- Loss streak 계산 검증
- Fee ratio / Slippage tracking 검증
- UTC boundary 인식 검증

SSOT:
- docs/plans/task_plan.md Phase 12a-2
- Phase 9 Session Risk Policy
"""

import pytest
from datetime import datetime, timezone
from typing import List, Dict, Any

from application.session_risk_tracker import SessionRiskTracker, Trade, FillEvent


class TestSessionRiskTrackerDailyPnL:
    """Daily PnL tracking"""

    def test_track_daily_pnl_simple(self):
        """Daily PnL 계산 (단순)"""
        # Arrange
        tracker = SessionRiskTracker()

        # 2026-01-26 당일 거래 (UTC)
        day_start = datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc).timestamp()
        trades = [
            Trade(closed_pnl=5.0, timestamp=day_start + 100),  # +$5
            Trade(closed_pnl=-3.0, timestamp=day_start + 200),  # -$3
            Trade(closed_pnl=2.0, timestamp=day_start + 300),  # +$2
        ]

        # Act (2026-01-26 기준)
        current_date = datetime(2026, 1, 26, 12, 0, 0, tzinfo=timezone.utc)
        daily_pnl = tracker.track_daily_pnl(trades, current_date=current_date)

        # Assert
        assert daily_pnl == 4.0  # 5 - 3 + 2

    def test_track_daily_pnl_utc_boundary(self):
        """Daily PnL 계산 (UTC boundary 인식)"""
        # Arrange
        tracker = SessionRiskTracker()

        # 2026-01-25 23:59:00 UTC
        yesterday = datetime(2026, 1, 25, 23, 59, 0, tzinfo=timezone.utc).timestamp()
        # 2026-01-26 00:01:00 UTC
        today = datetime(2026, 1, 26, 0, 1, 0, tzinfo=timezone.utc).timestamp()

        trades = [
            Trade(closed_pnl=10.0, timestamp=yesterday),  # 어제
            Trade(closed_pnl=5.0, timestamp=today),  # 오늘
        ]

        # Act (오늘 날짜 기준)
        current_date = datetime(2026, 1, 26, 12, 0, 0, tzinfo=timezone.utc)
        daily_pnl = tracker.track_daily_pnl(trades, current_date=current_date)

        # Assert
        assert daily_pnl == 5.0  # 오늘 거래만 (어제 거래 제외)

    def test_track_daily_pnl_empty(self):
        """Daily PnL 계산 (거래 없음)"""
        # Arrange
        tracker = SessionRiskTracker()
        trades = []

        # Act
        daily_pnl = tracker.track_daily_pnl(trades)

        # Assert
        assert daily_pnl == 0.0


class TestSessionRiskTrackerWeeklyPnL:
    """Weekly PnL tracking"""

    def test_track_weekly_pnl_simple(self):
        """Weekly PnL 계산 (단순)"""
        # Arrange
        tracker = SessionRiskTracker()

        # 2026-01-26 (Monday, 이번 주)
        this_week_start = datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc).timestamp()
        trades = [
            Trade(closed_pnl=10.0, timestamp=this_week_start + 3600),  # Mon +1h
            Trade(closed_pnl=-5.0, timestamp=this_week_start + 86400),  # Tue
            Trade(closed_pnl=3.0, timestamp=this_week_start + 172800),  # Wed
        ]

        # Act (2026-01-26 기준)
        current_date = datetime(2026, 1, 26, 12, 0, 0, tzinfo=timezone.utc)
        weekly_pnl = tracker.track_weekly_pnl(trades, current_date=current_date)

        # Assert
        assert weekly_pnl == 8.0  # 10 - 5 + 3

    def test_track_weekly_pnl_week_rollover(self):
        """Weekly PnL 계산 (Week rollover)"""
        # Arrange
        tracker = SessionRiskTracker()

        # 2026-01-27 (Tuesday, 이번 주)
        this_week = datetime(2026, 1, 27, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        # 2026-01-25 (Sunday, 지난 주 마지막 날)
        last_week = datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp()

        trades = [
            Trade(closed_pnl=15.0, timestamp=last_week),  # 지난 주
            Trade(closed_pnl=7.0, timestamp=this_week),  # 이번 주
        ]

        # Act (이번 주 기준: 2026-01-26 Monday 시작)
        current_date = datetime(2026, 1, 27, 12, 0, 0, tzinfo=timezone.utc)
        weekly_pnl = tracker.track_weekly_pnl(trades, current_date=current_date)

        # Assert
        assert weekly_pnl == 7.0  # 이번 주 거래만 (2026-01-27)


class TestSessionRiskTrackerLossStreak:
    """Loss streak calculation"""

    def test_calculate_loss_streak_simple(self):
        """Loss streak 계산 (3연패)"""
        # Arrange
        tracker = SessionRiskTracker()
        trades = [
            Trade(closed_pnl=-2.0, timestamp=1737849600.0),
            Trade(closed_pnl=-1.5, timestamp=1737849700.0),
            Trade(closed_pnl=-3.0, timestamp=1737849800.0),
        ]

        # Act
        loss_streak = tracker.calculate_loss_streak(trades)

        # Assert
        assert loss_streak == 3

    def test_calculate_loss_streak_with_win(self):
        """Loss streak 계산 (승리로 중단)"""
        # Arrange
        tracker = SessionRiskTracker()
        trades = [
            Trade(closed_pnl=-2.0, timestamp=1737849600.0),
            Trade(closed_pnl=1.0, timestamp=1737849700.0),  # Win → 중단
            Trade(closed_pnl=-1.5, timestamp=1737849800.0),
        ]

        # Act
        loss_streak = tracker.calculate_loss_streak(trades)

        # Assert
        assert loss_streak == 1  # 마지막 loss만

    def test_calculate_loss_streak_zero_pnl(self):
        """Loss streak 계산 (0 PnL)"""
        # Arrange
        tracker = SessionRiskTracker()
        trades = [
            Trade(closed_pnl=-2.0, timestamp=1737849600.0),
            Trade(closed_pnl=0.0, timestamp=1737849700.0),  # 0 → 중단
        ]

        # Act
        loss_streak = tracker.calculate_loss_streak(trades)

        # Assert
        assert loss_streak == 0  # 0 PnL은 loss 아님

    def test_calculate_loss_streak_empty(self):
        """Loss streak 계산 (거래 없음)"""
        # Arrange
        tracker = SessionRiskTracker()
        trades = []

        # Act
        loss_streak = tracker.calculate_loss_streak(trades)

        # Assert
        assert loss_streak == 0


class TestSessionRiskTrackerFeeRatio:
    """Fee ratio tracking"""

    def test_track_fee_ratio_simple(self):
        """Fee ratio 계산 (단순)"""
        # Arrange
        tracker = SessionRiskTracker()
        fill_events = [
            FillEvent(fee=0.00001, notional=100.0),  # fee_ratio = 0.00001 / 100 = 0.0000001
            FillEvent(fee=0.002, notional=200.0),  # fee_ratio = 0.002 / 200 = 0.00001
            FillEvent(fee=0.003, notional=150.0),  # fee_ratio = 0.003 / 150 = 0.00002
        ]

        # Act
        fee_ratios = tracker.track_fee_ratio(fill_events)

        # Assert
        assert len(fee_ratios) == 3
        assert fee_ratios[0] == pytest.approx(0.0000001, abs=1e-8)
        assert fee_ratios[1] == pytest.approx(0.00001, abs=1e-7)
        assert fee_ratios[2] == pytest.approx(0.00002, abs=1e-7)

    def test_track_fee_ratio_empty(self):
        """Fee ratio 계산 (fill event 없음)"""
        # Arrange
        tracker = SessionRiskTracker()
        fill_events = []

        # Act
        fee_ratios = tracker.track_fee_ratio(fill_events)

        # Assert
        assert fee_ratios == []


class TestSessionRiskTrackerSlippage:
    """Slippage tracking"""

    def test_track_slippage_simple(self):
        """Slippage 계산 (단순)"""
        # Arrange
        tracker = SessionRiskTracker()

        # 현재 시간 기준 최근 이벤트
        current_time = datetime(2026, 1, 26, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        fill_events = [
            FillEvent(expected_price=50000.0, filled_price=49990.0, timestamp=current_time - 100),  # slippage = -10
            FillEvent(expected_price=50100.0, filled_price=50110.0, timestamp=current_time - 50),  # slippage = +10
        ]

        # Act (current_time 명시)
        slippage_history = tracker.track_slippage(fill_events, current_time=current_time)

        # Assert
        assert len(slippage_history) == 2
        assert slippage_history[0]["slippage_usd"] == -10.0
        assert slippage_history[0]["timestamp"] == current_time - 100
        assert slippage_history[1]["slippage_usd"] == 10.0

    def test_track_slippage_within_window(self):
        """Slippage 계산 (시간 윈도우 내)"""
        # Arrange
        tracker = SessionRiskTracker()
        window_seconds = 600  # 10분

        # 현재 시간: 2026-01-26 12:00:00 UTC
        current_time = datetime(2026, 1, 26, 12, 0, 0, tzinfo=timezone.utc).timestamp()

        # 11분 전 (윈도우 밖)
        old_event = FillEvent(expected_price=50000.0, filled_price=49980.0, timestamp=current_time - 660)
        # 5분 전 (윈도우 내)
        recent_event = FillEvent(expected_price=50100.0, filled_price=50105.0, timestamp=current_time - 300)

        fill_events = [old_event, recent_event]

        # Act
        slippage_history = tracker.track_slippage(
            fill_events, window_seconds=window_seconds, current_time=current_time
        )

        # Assert
        assert len(slippage_history) == 1  # 최근 이벤트만
        assert slippage_history[0]["slippage_usd"] == 5.0

    def test_track_slippage_empty(self):
        """Slippage 계산 (fill event 없음)"""
        # Arrange
        tracker = SessionRiskTracker()
        fill_events = []

        # Act
        slippage_history = tracker.track_slippage(fill_events)

        # Assert
        assert slippage_history == []

"""
src/application/session_risk_tracker.py
Session Risk Tracker — Trade History → Risk Metrics

Purpose:
- Trade history를 받아 Session Risk Policy 메트릭 계산
- Daily/Weekly PnL, Loss streak, Fee ratio, Slippage 추적

Design:
- UTC boundary 인식 (Daily/Weekly PnL)
- Rolling window 기반 metrics (Fee, Slippage)
- Stateless calculator (입력 데이터 → 메트릭 출력)

SSOT:
- docs/plans/task_plan.md Phase 12a-2
- docs/specs/account_builder_policy.md Section 9 (Session Risk Policy)
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional


@dataclass
class Trade:
    """
    거래 정보 (Trade history)

    Attributes:
        closed_pnl: 종료된 PnL (USD)
        timestamp: 거래 타임스탬프 (Unix timestamp, seconds)
    """
    closed_pnl: float
    timestamp: float


@dataclass
class FillEvent:
    """
    체결 이벤트 (Fill event)

    Attributes:
        fee: 수수료 (BTC)
        notional: 거래 금액 (USD)
        expected_price: 예상 체결 가격 (USD)
        filled_price: 실제 체결 가격 (USD)
        timestamp: 체결 타임스탬프 (Unix timestamp, seconds)
    """
    fee: float = 0.0
    notional: float = 0.0
    expected_price: float = 0.0
    filled_price: float = 0.0
    timestamp: float = 0.0


class SessionRiskTracker:
    """
    Session Risk Tracker — Trade history → Risk metrics

    역할:
    - Daily/Weekly PnL 계산 (UTC boundary 인식)
    - Loss streak 계산 (연속 손실 카운트)
    - Fee ratio 추적 (fee / notional)
    - Slippage 추적 (expected_price - filled_price)
    """

    def track_daily_pnl(
        self,
        trades: List[Trade],
        current_date: Optional[datetime] = None
    ) -> float:
        """
        당일 realized PnL 계산 (UTC boundary 인식)

        Args:
            trades: Trade 리스트 (최신순 또는 역순 무관)
            current_date: 현재 날짜 (None이면 utcnow() 사용)

        Returns:
            float: 당일 PnL 합계 (USD)
        """
        if not trades:
            return 0.0

        # 현재 날짜 (UTC)
        if current_date is None:
            current_date = datetime.now(timezone.utc)

        # 당일 시작 시각 (00:00:00 UTC)
        today_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_ts = today_start.timestamp()

        # 당일 거래만 필터링
        daily_pnl = 0.0
        for trade in trades:
            if trade.timestamp >= today_start_ts:
                daily_pnl += trade.closed_pnl

        return daily_pnl

    def track_weekly_pnl(
        self,
        trades: List[Trade],
        current_date: Optional[datetime] = None
    ) -> float:
        """
        주간 realized PnL 계산 (Week rollover 인식)

        Week 정의: ISO 8601 (Monday 00:00:00 UTC ~ Sunday 23:59:59 UTC)

        Args:
            trades: Trade 리스트
            current_date: 현재 날짜 (None이면 utcnow() 사용)

        Returns:
            float: 주간 PnL 합계 (USD)
        """
        if not trades:
            return 0.0

        # 현재 날짜 (UTC)
        if current_date is None:
            current_date = datetime.now(timezone.utc)

        # 이번 주 시작 (Monday 00:00:00 UTC)
        # ISO weekday: Monday=1, Sunday=7
        weekday = current_date.isoweekday()  # 1~7
        days_since_monday = weekday - 1
        this_week_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
        this_week_start_ts = this_week_start.timestamp()

        # 이번 주 거래만 필터링
        weekly_pnl = 0.0
        for trade in trades:
            if trade.timestamp >= this_week_start_ts:
                weekly_pnl += trade.closed_pnl

        return weekly_pnl

    def calculate_loss_streak(self, trades: List[Trade]) -> int:
        """
        연속 손실 카운트 (Loss streak)

        규칙:
        - 최근 거래부터 역순으로 스캔
        - closed_pnl < 0이면 loss로 카운트
        - closed_pnl >= 0이면 중단 (streak 끝)

        Args:
            trades: Trade 리스트 (timestamp 순서 무관, 역순 스캔)

        Returns:
            int: 연속 손실 카운트
        """
        if not trades:
            return 0

        # 최신 거래부터 역순 스캔 (timestamp 기준 정렬)
        sorted_trades = sorted(trades, key=lambda t: t.timestamp, reverse=True)

        loss_streak = 0
        for trade in sorted_trades:
            if trade.closed_pnl < 0:
                loss_streak += 1
            else:
                # 첫 번째 non-loss에서 중단
                break

        return loss_streak

    def track_fee_ratio(self, fill_events: List[FillEvent]) -> List[float]:
        """
        Fee ratio 히스토리 계산 (fee / notional)

        Args:
            fill_events: FillEvent 리스트

        Returns:
            List[float]: Fee ratio 리스트 (각 event의 fee / notional)
        """
        if not fill_events:
            return []

        fee_ratios = []
        for event in fill_events:
            if event.notional > 0:
                fee_ratio = event.fee / event.notional
                fee_ratios.append(fee_ratio)
            else:
                # notional이 0이면 fee ratio 계산 불가 (skip)
                pass

        return fee_ratios

    def track_slippage(
        self,
        fill_events: List[FillEvent],
        window_seconds: int = 600,
        current_time: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Slippage 히스토리 추적 (시간 윈도우 내)

        Slippage = filled_price - expected_price
        - Negative: 유리한 체결 (예상보다 낮은 가격에 매수)
        - Positive: 불리한 체결 (예상보다 높은 가격에 매수)

        Args:
            fill_events: FillEvent 리스트
            window_seconds: 시간 윈도우 (seconds, default: 600 = 10분)
            current_time: 현재 시각 (None이면 time.time() 사용)

        Returns:
            List[Dict[str, Any]]: Slippage 히스토리 (윈도우 내 이벤트만)
                - slippage_usd: Slippage (USD)
                - timestamp: 체결 타임스탬프
        """
        if not fill_events:
            return []

        # 현재 시각
        if current_time is None:
            import time
            current_time = time.time()

        # 윈도우 시작 시각
        window_start = current_time - window_seconds

        slippage_history = []
        for event in fill_events:
            # 윈도우 내 이벤트만 포함
            if event.timestamp >= window_start:
                slippage_usd = event.filled_price - event.expected_price
                slippage_history.append({
                    "slippage_usd": slippage_usd,
                    "timestamp": event.timestamp
                })

        return slippage_history

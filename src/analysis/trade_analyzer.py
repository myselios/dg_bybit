"""
trade_analyzer.py

Phase 13a: Trade log 분석 도구

Trade log 로드, 성과 지표 계산, 통계 분석.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta, date
import json
import statistics


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class MetricsBreakdown:
    """Market Regime별 분해 지표"""
    total_trades: int
    win_count: int
    loss_count: int
    winrate: float
    total_pnl: float
    avg_pnl: float
    sharpe_ratio: Optional[float]  # None if std=0


@dataclass
class PerformanceMetrics:
    """전체 성과 지표"""
    # 기본 지표
    total_trades: int
    win_count: int
    loss_count: int
    winrate: float  # win_count / total_trades

    # PnL 지표
    total_pnl: float  # USDT
    avg_pnl_per_trade: float
    max_drawdown_pct: float  # %
    max_single_loss: float  # USDT
    max_single_win: float  # USDT

    # 리스크 지표
    profit_factor: float  # gross_profit / gross_loss (None if gross_loss=0)
    sharpe_ratio: Optional[float]  # (avg_return - risk_free) / std_return
    sortino_ratio: Optional[float]  # (avg_return) / downside_deviation

    # 운영 지표
    avg_holding_time_seconds: float
    avg_slippage_usd: float
    total_fees_usd: float

    # 연속 손익
    max_consecutive_wins: int
    max_consecutive_losses: int

    # Regime별 분해
    regime_breakdown: Dict[str, MetricsBreakdown]

    # 신뢰 구간 (95%)
    pnl_confidence_interval: tuple  # (lower, upper)


# ============================================================================
# TradeAnalyzer Class
# ============================================================================

class TradeAnalyzer:
    """Trade log 분석 도구"""

    def __init__(self, log_dir: str = "logs/mainnet_dry_run"):
        """
        Args:
            log_dir: Trade log 디렉토리 경로

        Raises:
            FileNotFoundError: 로그 디렉토리가 존재하지 않음
        """
        self.log_dir = Path(log_dir)
        if not self.log_dir.exists():
            raise FileNotFoundError(f"Log directory not found: {log_dir}")

    def load_trades(
        self,
        start_date: str,
        end_date: str
    ) -> List[dict]:
        """
        기간 내 거래 로드

        Args:
            start_date: 시작일 (YYYY-MM-DD)
            end_date: 종료일 (YYYY-MM-DD)

        Returns:
            List[dict]: 거래 목록

        Raises:
            ValueError: 날짜 형식 오류
        """
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()

        trades = []
        current = start
        while current <= end:
            file_path = self.log_dir / f"trades_{current.isoformat()}.jsonl"
            if file_path.exists():
                trades.extend(self._load_jsonl(file_path))
            current = current + timedelta(days=1)

        return trades

    def _load_jsonl(self, file_path: Path) -> List[dict]:
        """
        JSONL 파일 로드

        Args:
            file_path: JSONL 파일 경로

        Returns:
            List[dict]: 거래 목록
        """
        trades = []
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    trades.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON at {file_path}:{line_num} - {e}")
        return trades

    def calculate_metrics(
        self,
        trades: List[dict]
    ) -> PerformanceMetrics:
        """
        성과 지표 계산

        Args:
            trades: 거래 목록

        Returns:
            PerformanceMetrics: 성과 지표
        """
        # 빈 리스트 처리 (테스트 요구사항에 맞춤)
        if not trades:
            return PerformanceMetrics(
                total_trades=0,
                win_count=0,
                loss_count=0,
                winrate=0.0,
                total_pnl=0.0,
                avg_pnl_per_trade=0.0,
                max_drawdown_pct=0.0,
                max_single_loss=0.0,
                max_single_win=0.0,
                profit_factor=0.0,
                sharpe_ratio=None,
                sortino_ratio=None,
                avg_holding_time_seconds=0.0,
                avg_slippage_usd=0.0,
                total_fees_usd=0.0,
                max_consecutive_wins=0,
                max_consecutive_losses=0,
                regime_breakdown={},
                pnl_confidence_interval=(0.0, 0.0)
            )

        # PnL 목록 추출
        pnls = [self._calculate_pnl(t) for t in trades]

        # 기본 지표
        total_trades = len(trades)
        win_count = sum(1 for pnl in pnls if pnl > 0)
        loss_count = total_trades - win_count
        winrate = win_count / total_trades if total_trades > 0 else 0.0

        # PnL 지표
        total_pnl = sum(pnls)
        avg_pnl = statistics.mean(pnls)
        max_drawdown_pct = self._calculate_max_drawdown(pnls)
        max_single_loss = min(pnls) if pnls else 0.0
        max_single_win = max(pnls) if pnls else 0.0

        # 리스크 지표
        profit_factor = self._calculate_profit_factor(pnls)
        sharpe_ratio = self._calculate_sharpe_ratio(pnls)
        sortino_ratio = self._calculate_sortino_ratio(pnls)

        # 운영 지표
        avg_holding_time = self._calculate_avg_holding_time(trades)
        avg_slippage = statistics.mean([t.get('slippage_usd', 0.0) for t in trades])
        total_fees = sum(
            t.get('fee_usd', 0.0) or sum(fill.get('fee', 0.0) for fill in t.get('fills', []))
            for t in trades
        )

        # 연속 손익
        max_consecutive_wins, max_consecutive_losses = self._calculate_consecutive_streaks(pnls)

        # Regime별 분해
        regime_breakdown = self._calculate_regime_breakdown(trades)

        # 신뢰 구간
        pnl_ci = self._calculate_confidence_interval(pnls, confidence=0.95)

        return PerformanceMetrics(
            total_trades=total_trades,
            win_count=win_count,
            loss_count=loss_count,
            winrate=winrate,
            total_pnl=total_pnl,
            avg_pnl_per_trade=avg_pnl,
            max_drawdown_pct=max_drawdown_pct,
            max_single_loss=max_single_loss,
            max_single_win=max_single_win,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            avg_holding_time_seconds=avg_holding_time,
            avg_slippage_usd=avg_slippage,
            total_fees_usd=total_fees,
            max_consecutive_wins=max_consecutive_wins,
            max_consecutive_losses=max_consecutive_losses,
            regime_breakdown=regime_breakdown,
            pnl_confidence_interval=pnl_ci
        )

    # ========== Private Helper Methods ==========

    def _calculate_pnl(self, trade: dict) -> float:
        """
        거래에서 PnL 추출

        Args:
            trade: 거래 데이터

        Returns:
            float: PnL (USDT)
        """
        # TradeLogV1: realized_pnl_usd 필드
        if 'realized_pnl_usd' in trade:
            return float(trade['realized_pnl_usd'])

        # 레거시: pnl 필드
        if 'pnl' in trade:
            return float(trade['pnl'])

        # 구형 포맷 (2/12): entry/exit price에서 역산
        if 'entry_price' in trade and 'exit_price' in trade:
            entry = float(trade['entry_price'])
            exit_p = float(trade['exit_price'])
            qty = float(trade.get('qty_btc', 0.001))
            direction = trade.get('direction', 'LONG')
            if direction == 'SHORT':
                return (entry - exit_p) * qty
            return (exit_p - entry) * qty

        return 0.0

    def _calculate_max_drawdown(self, pnls: List[float]) -> float:
        """
        최대 낙폭 계산 (%)

        Args:
            pnls: PnL 목록

        Returns:
            float: 최대 낙폭 (%)
        """
        if not pnls:
            return 0.0

        cumulative = []
        total = 0.0
        for pnl in pnls:
            total += pnl
            cumulative.append(total)

        # Running maximum
        peak = cumulative[0]
        max_dd = 0.0

        for value in cumulative:
            if value > peak:
                peak = value
            dd = (peak - value) / abs(peak) * 100 if peak != 0 else 0.0
            max_dd = max(max_dd, dd)

        return max_dd

    def _calculate_profit_factor(self, pnls: List[float]) -> float:
        """
        Profit Factor 계산

        Args:
            pnls: PnL 목록

        Returns:
            float: Profit Factor (gross_profit / gross_loss)
        """
        gross_profit = sum(pnl for pnl in pnls if pnl > 0)
        gross_loss = abs(sum(pnl for pnl in pnls if pnl < 0))

        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0

        return gross_profit / gross_loss

    def _calculate_sharpe_ratio(
        self,
        pnls: List[float],
        risk_free_rate: float = 0.0
    ) -> Optional[float]:
        """
        Sharpe Ratio 계산

        Args:
            pnls: PnL 목록
            risk_free_rate: 무위험 수익률

        Returns:
            Optional[float]: Sharpe Ratio (None if std=0 or len < 2)
        """
        if len(pnls) < 2:
            return None

        mean_return = statistics.mean(pnls)
        std_return = statistics.stdev(pnls)

        if std_return == 0:
            return None

        return (mean_return - risk_free_rate) / std_return

    def _calculate_sortino_ratio(
        self,
        pnls: List[float],
        target_return: float = 0.0
    ) -> Optional[float]:
        """
        Sortino Ratio 계산 (하방 편차만 고려)

        Args:
            pnls: PnL 목록
            target_return: 목표 수익률

        Returns:
            Optional[float]: Sortino Ratio (None if downside_std=0 or len < 2)
        """
        if len(pnls) < 2:
            return None

        mean_return = statistics.mean(pnls)
        downside_returns = [pnl for pnl in pnls if pnl < target_return]

        if not downside_returns or len(downside_returns) < 2:
            return None

        downside_std = statistics.stdev(downside_returns)
        if downside_std == 0:
            return None

        return (mean_return - target_return) / downside_std

    def _calculate_avg_holding_time(self, trades: List[dict]) -> float:
        """
        평균 보유 시간 계산

        Args:
            trades: 거래 목록

        Returns:
            float: 평균 보유 시간 (초)
        """
        holding_times = [t.get('holding_time_seconds', 0.0) for t in trades]
        return statistics.mean(holding_times) if holding_times else 0.0

    def _calculate_consecutive_streaks(self, pnls: List[float]) -> tuple:
        """
        연속 승/패 계산

        Args:
            pnls: PnL 목록

        Returns:
            tuple: (max_consecutive_wins, max_consecutive_losses)
        """
        if not pnls:
            return 0, 0

        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for pnl in pnls:
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)

        return max_wins, max_losses

    def _calculate_regime_breakdown(self, trades: List[dict]) -> Dict[str, MetricsBreakdown]:
        """
        Market Regime별 성과 분해

        Args:
            trades: 거래 목록

        Returns:
            Dict[str, MetricsBreakdown]: Regime별 지표
        """
        regime_trades = {}
        for trade in trades:
            regime = trade.get('market_regime', 'UNKNOWN')
            if regime not in regime_trades:
                regime_trades[regime] = []
            regime_trades[regime].append(trade)

        breakdown = {}
        for regime, regime_list in regime_trades.items():
            pnls = [self._calculate_pnl(t) for t in regime_list]
            total_trades = len(regime_list)
            win_count = sum(1 for pnl in pnls if pnl > 0)
            loss_count = total_trades - win_count
            winrate = win_count / total_trades if total_trades > 0 else 0.0
            total_pnl = sum(pnls)
            avg_pnl = statistics.mean(pnls)
            sharpe = self._calculate_sharpe_ratio(pnls)

            breakdown[regime] = MetricsBreakdown(
                total_trades=total_trades,
                win_count=win_count,
                loss_count=loss_count,
                winrate=winrate,
                total_pnl=total_pnl,
                avg_pnl=avg_pnl,
                sharpe_ratio=sharpe
            )

        return breakdown

    def _calculate_confidence_interval(
        self,
        pnls: List[float],
        confidence: float = 0.95
    ) -> tuple:
        """
        신뢰 구간 계산 (t-distribution)

        Args:
            pnls: PnL 목록
            confidence: 신뢰 수준 (기본 0.95)

        Returns:
            tuple: (lower, upper) 신뢰 구간
        """
        if len(pnls) < 2:
            return (0.0, 0.0)

        mean = statistics.mean(pnls)
        std = statistics.stdev(pnls)
        n = len(pnls)

        # t-distribution critical value (간단히 z=1.96 사용, 정확한 구현은 scipy 필요)
        z_score = 1.96  # 95% confidence
        margin = z_score * (std / (n ** 0.5))

        return (mean - margin, mean + margin)

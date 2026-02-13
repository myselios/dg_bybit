"""
ab_comparator.py

Phase 13a: A/B 비교 도구

Before/After 기간 성과 비교, 통계 검정, 자동 추천 로직.
"""

from dataclasses import dataclass
from typing import List, Tuple, Dict

from .trade_analyzer import TradeAnalyzer, PerformanceMetrics
from .stat_test import StatTest, TTestResult, ChiSquareResult


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ComparisonResult:
    """A/B 비교 결과"""
    before_metrics: PerformanceMetrics
    after_metrics: PerformanceMetrics

    # 변화량 (절대값)
    winrate_delta_pct: float  # % (after - before)
    pnl_delta_usd: float  # USDT (after - before)
    sharpe_delta: float  # (after - before)

    # 변화량 (상대값, %)
    winrate_change_pct: float  # (after - before) / before * 100
    pnl_change_pct: float  # (after - before) / before * 100
    sharpe_change_pct: float  # (after - before) / before * 100

    # 통계 검정 결과
    winrate_test: ChiSquareResult
    pnl_test: TTestResult

    # 결론
    is_significant: bool  # p < 0.05 (both tests)
    recommendation: str  # "Keep", "Revert", "Need more data", "Inconclusive"
    reasoning: str  # 추천 이유


# ============================================================================
# ABComparator Class
# ============================================================================

class ABComparator:
    """A/B 비교 도구"""

    def compare(
        self,
        before_trades: List[dict],
        after_trades: List[dict]
    ) -> ComparisonResult:
        """
        A/B 비교 수행

        Args:
            before_trades: 변경 전 거래 목록
            after_trades: 변경 후 거래 목록

        Returns:
            ComparisonResult: 비교 결과

        Raises:
            ValueError: 샘플 크기 부족
        """
        # Step 1: TradeAnalyzer로 Before/After metrics 계산
        # (log_dir는 calculate_metrics에서 사용되지 않으므로 임시 디렉토리 사용)
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            analyzer = TradeAnalyzer(log_dir=tmpdir)
            before_metrics = analyzer.calculate_metrics(before_trades)
            after_metrics = analyzer.calculate_metrics(after_trades)

        # Step 2: Delta 계산 (절대값)
        winrate_delta_pct = after_metrics.winrate - before_metrics.winrate
        pnl_delta_usd = after_metrics.total_pnl - before_metrics.total_pnl
        sharpe_delta = self._calculate_sharpe_delta(before_metrics, after_metrics)

        # Step 3: Delta 계산 (상대값, %)
        winrate_change_pct = (
            (after_metrics.winrate - before_metrics.winrate) / before_metrics.winrate * 100
            if before_metrics.winrate != 0 else 0.0
        )
        pnl_change_pct = (
            (after_metrics.total_pnl - before_metrics.total_pnl) / before_metrics.total_pnl * 100
            if before_metrics.total_pnl != 0 else 0.0
        )
        sharpe_change_pct = (
            (sharpe_delta / before_metrics.sharpe_ratio * 100)
            if before_metrics.sharpe_ratio and before_metrics.sharpe_ratio != 0 else 0.0
        )

        # Step 4: 통계 검정
        winrate_test, pnl_test = self._run_statistical_tests(
            before_trades, after_trades, before_metrics, after_metrics
        )

        # Step 5: 통계적 유의성 판단
        is_significant = self._is_statistically_significant(winrate_test, pnl_test)

        # Step 6: 추천 로직
        recommendation, reasoning = self._generate_recommendation(
            before_metrics, after_metrics,
            winrate_delta_pct, pnl_delta_usd, sharpe_delta,
            is_significant,
            winrate_test, pnl_test
        )

        return ComparisonResult(
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            winrate_delta_pct=winrate_delta_pct,
            pnl_delta_usd=pnl_delta_usd,
            sharpe_delta=sharpe_delta,
            winrate_change_pct=winrate_change_pct,
            pnl_change_pct=pnl_change_pct,
            sharpe_change_pct=sharpe_change_pct,
            winrate_test=winrate_test,
            pnl_test=pnl_test,
            is_significant=is_significant,
            recommendation=recommendation,
            reasoning=reasoning
        )

    def _calculate_sharpe_delta(
        self,
        before_metrics: PerformanceMetrics,
        after_metrics: PerformanceMetrics
    ) -> float:
        """Sharpe Ratio delta 계산"""
        before_sharpe = before_metrics.sharpe_ratio or 0.0
        after_sharpe = after_metrics.sharpe_ratio or 0.0
        return after_sharpe - before_sharpe

    def _run_statistical_tests(
        self,
        before_trades: List[dict],
        after_trades: List[dict],
        before_metrics: PerformanceMetrics,
        after_metrics: PerformanceMetrics
    ) -> Tuple[ChiSquareResult, TTestResult]:
        """통계 검정 실행"""
        # PnL 목록 추출
        before_pnls = [t.get('pnl', 0.0) for t in before_trades]
        after_pnls = [t.get('pnl', 0.0) for t in after_trades]

        # t-test (PnL 평균 차이)
        try:
            pnl_test = StatTest.t_test(before_pnls, after_pnls)
        except ValueError:
            # 샘플 크기 부족 시 더미 결과 반환
            pnl_test = TTestResult(
                statistic=0.0,
                pvalue=1.0,
                mean_before=before_metrics.avg_pnl_per_trade,
                mean_after=after_metrics.avg_pnl_per_trade,
                std_before=0.0,
                std_after=0.0
            )

        # chi-square test (승률 차이)
        try:
            winrate_test = StatTest.chi_square_test(
                winrate_before=before_metrics.winrate,
                sample_size_before=before_metrics.total_trades,
                winrate_after=after_metrics.winrate,
                sample_size_after=after_metrics.total_trades
            )
        except ValueError:
            # 샘플 크기 부족 시 더미 결과 반환
            winrate_test = ChiSquareResult(
                statistic=0.0,
                pvalue=1.0,
                winrate_before=before_metrics.winrate,
                winrate_after=after_metrics.winrate,
                sample_size_before=before_metrics.total_trades,
                sample_size_after=after_metrics.total_trades
            )

        return winrate_test, pnl_test

    def _is_statistically_significant(
        self,
        winrate_test: ChiSquareResult,
        pnl_test: TTestResult
    ) -> bool:
        """통계적 유의성 판단 (p < 0.05, both tests)"""
        return winrate_test.pvalue < 0.05 and pnl_test.pvalue < 0.05

    def _generate_recommendation(
        self,
        before_metrics: PerformanceMetrics,
        after_metrics: PerformanceMetrics,
        winrate_delta: float,
        pnl_delta: float,
        sharpe_delta: float,
        is_significant: bool,
        winrate_test: ChiSquareResult,
        pnl_test: TTestResult
    ) -> Tuple[str, str]:
        """
        자동 추천 로직

        Returns:
            Tuple[str, str]: (recommendation, reasoning)
        """
        # 샘플 크기 확인
        if before_metrics.total_trades < 5 or after_metrics.total_trades < 5:
            return (
                "Need more data",
                f"Insufficient sample size: Before={before_metrics.total_trades}, "
                f"After={after_metrics.total_trades}. Need at least 5 trades in each period."
            )

        # 통계적으로 유의하지 않은 경우
        if not is_significant:
            return (
                "Need more data",
                f"Change is not statistically significant (p >= 0.05). "
                f"Winrate p={winrate_test.pvalue:.4f}, PnL p={pnl_test.pvalue:.4f}. "
                "Need more trades to confirm the trend."
            )

        # 통계적으로 유의한 경우: 4가지 추천 로직
        # (1) 모든 지표 개선
        if pnl_delta > 0 and winrate_delta > 0 and sharpe_delta > 0:
            return (
                "Keep",
                f"All metrics improved: PnL +${pnl_delta:.2f}, "
                f"Winrate +{winrate_delta*100:.1f}%, Sharpe +{sharpe_delta:.2f}. "
                "Change is statistically significant (p < 0.05)."
            )

        # (2) 모든 지표 악화
        if pnl_delta < 0 and winrate_delta < 0 and sharpe_delta < 0:
            return (
                "Revert",
                f"All metrics worsened: PnL ${pnl_delta:.2f}, "
                f"Winrate {winrate_delta*100:.1f}%, Sharpe {sharpe_delta:.2f}. "
                "Change is statistically significant (p < 0.05)."
            )

        # (3) PnL 개선 (다른 지표 무관)
        if pnl_delta > 0:
            return (
                "Keep",
                f"PnL improved (+${pnl_delta:.2f}) despite mixed results in other metrics. "
                "Profit is primary objective."
            )

        # (4) PnL 악화
        return (
            "Revert",
            f"PnL declined (${pnl_delta:.2f}). Revert to previous parameters."
        )

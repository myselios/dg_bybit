"""
stat_test.py

Phase 13a: 통계 검정 도구

t-test, chi-square test, confidence interval 계산.
"""

from dataclasses import dataclass
from typing import List, Tuple
import statistics

try:
    from scipy import stats
except ImportError:
    raise ImportError(
        "scipy is required for statistical testing. "
        "Install it with: pip install scipy"
    )


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TTestResult:
    """t-test 결과"""
    statistic: float
    pvalue: float
    mean_before: float
    mean_after: float
    std_before: float
    std_after: float


@dataclass
class ChiSquareResult:
    """Chi-square test 결과"""
    statistic: float
    pvalue: float
    winrate_before: float
    winrate_after: float
    sample_size_before: int
    sample_size_after: int


# ============================================================================
# StatTest Class
# ============================================================================

class StatTest:
    """통계 검정 도구"""

    @staticmethod
    def t_test(
        before_pnls: List[float],
        after_pnls: List[float]
    ) -> TTestResult:
        """
        평균 PnL 차이 검정 (Independent two-sample t-test)

        Args:
            before_pnls: 변경 전 PnL 목록
            after_pnls: 변경 후 PnL 목록

        Returns:
            TTestResult: t-test 결과

        Raises:
            ValueError: 샘플 크기 부족 (각 그룹 최소 2개 필요)
        """
        if len(before_pnls) < 2 or len(after_pnls) < 2:
            raise ValueError("t-test requires at least 2 samples in each group")

        # t-test 수행 (Independent two-sample t-test)
        statistic, pvalue = stats.ttest_ind(before_pnls, after_pnls)

        return TTestResult(
            statistic=float(statistic),
            pvalue=float(pvalue),
            mean_before=statistics.mean(before_pnls),
            mean_after=statistics.mean(after_pnls),
            std_before=statistics.stdev(before_pnls),
            std_after=statistics.stdev(after_pnls)
        )

    @staticmethod
    def chi_square_test(
        winrate_before: float,
        sample_size_before: int,
        winrate_after: float,
        sample_size_after: int
    ) -> ChiSquareResult:
        """
        Winrate 차이 검정 (Chi-square test for independence)

        Args:
            winrate_before: 변경 전 승률 (0.0 ~ 1.0)
            sample_size_before: 변경 전 총 거래 수
            winrate_after: 변경 후 승률 (0.0 ~ 1.0)
            sample_size_after: 변경 후 총 거래 수

        Returns:
            ChiSquareResult: Chi-square test 결과

        Raises:
            ValueError: 샘플 크기 부족 (각 그룹 최소 5개 필요)
        """
        if sample_size_before < 5 or sample_size_after < 5:
            raise ValueError("Chi-square test requires at least 5 samples in each group")

        # Wins 계산
        wins_before = int(winrate_before * sample_size_before)
        losses_before = sample_size_before - wins_before

        wins_after = int(winrate_after * sample_size_after)
        losses_after = sample_size_after - wins_after

        # Contingency table
        # [[wins_before, losses_before],
        #  [wins_after, losses_after]]
        observed = [
            [wins_before, losses_before],
            [wins_after, losses_after]
        ]

        # Chi-square test
        chi2, pvalue, dof, expected = stats.chi2_contingency(observed)

        return ChiSquareResult(
            statistic=float(chi2),
            pvalue=float(pvalue),
            winrate_before=winrate_before,
            winrate_after=winrate_after,
            sample_size_before=sample_size_before,
            sample_size_after=sample_size_after
        )

    @staticmethod
    def confidence_interval(
        values: List[float],
        confidence: float = 0.95
    ) -> Tuple[float, float]:
        """
        신뢰 구간 계산 (t-distribution)

        Args:
            values: 값 목록
            confidence: 신뢰 수준 (기본 0.95)

        Returns:
            Tuple[float, float]: (lower_bound, upper_bound)

        Raises:
            ValueError: 빈 리스트
        """
        if not values:
            raise ValueError("Empty values list for confidence interval")

        # 단일 값인 경우 → (value, value) 반환
        if len(values) == 1:
            return (values[0], values[0])

        # 2개 이상인 경우 → t-distribution 사용
        mean = statistics.mean(values)
        std_err = statistics.stdev(values) / (len(values) ** 0.5)
        margin = std_err * stats.t.ppf((1 + confidence) / 2, len(values) - 1)

        return (mean - margin, mean + margin)

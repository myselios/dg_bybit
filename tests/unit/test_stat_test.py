"""
test_stat_test.py

Phase 13a: StatTest 단위 테스트
- t-test (평균 PnL 차이 검정)
- chi-square test (승률 차이 검정)
- confidence interval (신뢰 구간)
"""

import pytest
from src.analysis.stat_test import (
    StatTest,
    TTestResult,
    ChiSquareResult,
)


# ============================================================================
# Test Cases: t-test
# ============================================================================

def test_t_test_basic():
    """정상: 기본 t-test (평균 PnL 차이 검정)"""
    before_pnls = [100, 50, -30, 120, 80]  # mean=64, std≈54
    after_pnls = [150, 120, -10, 180, 100]  # mean=108, std≈74

    result = StatTest.t_test(before_pnls, after_pnls)

    assert result.mean_before == pytest.approx(64.0, abs=0.1)
    assert result.mean_after == pytest.approx(108.0, abs=0.1)
    assert result.pvalue >= 0.0
    assert result.pvalue <= 1.0
    # statistic 부호: after > before → positive
    # (단, two-tailed test이므로 절댓값만 의미 있음)


def test_t_test_identical_groups():
    """정상: 동일한 그룹 → p-value ≈ 1.0"""
    before_pnls = [100, 50, -30, 120, 80]
    after_pnls = [100, 50, -30, 120, 80]  # 동일

    result = StatTest.t_test(before_pnls, after_pnls)

    assert result.mean_before == pytest.approx(result.mean_after, abs=0.01)
    assert result.pvalue > 0.9  # 거의 1.0


def test_t_test_insufficient_samples_raises_error():
    """오류: 샘플 크기 부족 (각 그룹 최소 2개 필요)"""
    before_pnls = [100]  # 1개만
    after_pnls = [150, 120]

    with pytest.raises(ValueError, match="at least 2 samples"):
        StatTest.t_test(before_pnls, after_pnls)


# ============================================================================
# Test Cases: chi-square test
# ============================================================================

def test_chi_square_test_basic():
    """정상: 기본 chi-square test (승률 차이 검정)"""
    # Before: 60% winrate, 100 trades
    # After: 70% winrate, 100 trades
    result = StatTest.chi_square_test(
        winrate_before=0.60,
        sample_size_before=100,
        winrate_after=0.70,
        sample_size_after=100
    )

    assert result.winrate_before == 0.60
    assert result.winrate_after == 0.70
    assert result.sample_size_before == 100
    assert result.sample_size_after == 100
    assert result.pvalue >= 0.0
    assert result.pvalue <= 1.0


def test_chi_square_test_identical_winrates():
    """정상: 동일한 승률 → p-value ≈ 1.0"""
    result = StatTest.chi_square_test(
        winrate_before=0.55,
        sample_size_before=100,
        winrate_after=0.55,
        sample_size_after=100
    )

    assert result.pvalue > 0.9  # 거의 1.0


def test_chi_square_test_insufficient_samples_raises_error():
    """오류: 샘플 크기 부족 (각 그룹 최소 5개 필요)"""
    with pytest.raises(ValueError, match="at least 5 samples"):
        StatTest.chi_square_test(
            winrate_before=0.60,
            sample_size_before=3,  # 5개 미만
            winrate_after=0.70,
            sample_size_after=100
        )


# ============================================================================
# Test Cases: confidence interval
# ============================================================================

def test_confidence_interval_basic():
    """정상: 기본 신뢰 구간 계산 (95%)"""
    values = [100, 50, -30, 120, 80, 60, 90, 110, 40, 70]
    mean = sum(values) / len(values)  # 69.0

    lower, upper = StatTest.confidence_interval(values, confidence=0.95)

    assert lower < mean
    assert upper > mean
    # 95% CI should contain mean
    assert lower < 69.0 < upper


def test_confidence_interval_single_value():
    """경계: 값이 1개만 있을 때 → (value, value) 반환"""
    values = [100.0]
    lower, upper = StatTest.confidence_interval(values, confidence=0.95)

    assert lower == 100.0
    assert upper == 100.0


def test_confidence_interval_empty_list_raises_error():
    """오류: 빈 리스트 → ValueError"""
    with pytest.raises(ValueError, match="Empty values"):
        StatTest.confidence_interval([], confidence=0.95)

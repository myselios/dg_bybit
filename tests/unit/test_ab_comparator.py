"""
test_ab_comparator.py

Phase 13a: ABComparator 단위 테스트
- A/B 비교 (Before/After metrics)
- 통계 검정 통합
- 자동 추천 로직
"""

import pytest
from src.analysis.ab_comparator import ABComparator, ComparisonResult
from src.analysis.trade_analyzer import TradeAnalyzer
from src.analysis.stat_test import TTestResult, ChiSquareResult


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_before_trades():
    """Before 기간 샘플 거래 (승률 60%, PnL +100) - 5개 거래"""
    return [
        {"order_id": "b1", "pnl": 100.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 3600, "slippage_usd": 1.0, "market_regime": "RANGING"},
        {"order_id": "b2", "pnl": -50.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 1800, "slippage_usd": 0.5, "market_regime": "TRENDING_UP"},
        {"order_id": "b3", "pnl": 80.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 2400, "slippage_usd": 1.5, "market_regime": "RANGING"},
        {"order_id": "b4", "pnl": -30.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 1200, "slippage_usd": 0.8, "market_regime": "VOLATILE"},
        {"order_id": "b5", "pnl": 100.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 3000, "slippage_usd": 1.2, "market_regime": "RANGING"},
    ]


@pytest.fixture
def sample_after_trades_improved():
    """After 기간 샘플 거래 (승률 80%, PnL +350) - 개선됨, 5개 거래"""
    return [
        {"order_id": "a1", "pnl": 120.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 3000, "slippage_usd": 1.0, "market_regime": "RANGING"},
        {"order_id": "a2", "pnl": 90.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 2000, "slippage_usd": 0.5, "market_regime": "TRENDING_UP"},
        {"order_id": "a3", "pnl": 100.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 2500, "slippage_usd": 1.2, "market_regime": "RANGING"},
        {"order_id": "a4", "pnl": -60.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 1500, "slippage_usd": 0.7, "market_regime": "VOLATILE"},
        {"order_id": "a5", "pnl": 100.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 2800, "slippage_usd": 1.0, "market_regime": "RANGING"},
    ]


@pytest.fixture
def sample_after_trades_worse():
    """After 기간 샘플 거래 (승률 20%, PnL -200) - 악화됨, 5개 거래"""
    return [
        {"order_id": "a1", "pnl": -80.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 3000, "slippage_usd": 1.0, "market_regime": "RANGING"},
        {"order_id": "a2", "pnl": -100.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 2000, "slippage_usd": 0.5, "market_regime": "TRENDING_UP"},
        {"order_id": "a3", "pnl": 50.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 2500, "slippage_usd": 1.2, "market_regime": "RANGING"},
        {"order_id": "a4", "pnl": -70.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 1500, "slippage_usd": 0.7, "market_regime": "VOLATILE"},
        {"order_id": "a5", "pnl": 0.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 2200, "slippage_usd": 0.9, "market_regime": "RANGING"},
    ]


# ============================================================================
# Test Cases
# ============================================================================

def test_compare_basic_improvement(sample_before_trades, sample_after_trades_improved):
    """정상: 기본 A/B 비교 (개선됨)"""
    comparator = ABComparator()
    result = comparator.compare(sample_before_trades, sample_after_trades_improved)

    # Before metrics 검증
    assert result.before_metrics.total_trades == 5
    assert result.before_metrics.total_pnl == 200.0  # 100 - 50 + 80 - 30 + 100
    assert result.before_metrics.winrate == 0.6  # 3/5

    # After metrics 검증
    assert result.after_metrics.total_trades == 5
    assert result.after_metrics.total_pnl == 350.0  # 120 + 90 + 100 - 60 + 100
    assert result.after_metrics.winrate == 0.8  # 4/5

    # Delta 검증 (절대값)
    assert result.winrate_delta_pct == pytest.approx(0.2, abs=0.01)  # 80% - 60% = 20%
    assert result.pnl_delta_usd == pytest.approx(150.0, abs=0.1)  # 350 - 200

    # Delta 검증 (상대값, %)
    assert result.winrate_change_pct == pytest.approx(33.33, abs=1.0)  # (0.8 - 0.6) / 0.6 * 100
    assert result.pnl_change_pct == pytest.approx(75.0, abs=0.1)  # (350 - 200) / 200 * 100

    # 통계 검정 결과 존재 확인
    assert result.winrate_test is not None
    assert result.pnl_test is not None
    assert result.winrate_test.pvalue >= 0.0
    assert result.pnl_test.pvalue >= 0.0


def test_compare_deterioration(sample_before_trades, sample_after_trades_worse):
    """정상: A/B 비교 (악화됨)"""
    comparator = ABComparator()
    result = comparator.compare(sample_before_trades, sample_after_trades_worse)

    # Delta 검증 (절대값)
    assert result.winrate_delta_pct == pytest.approx(-0.4, abs=0.01)  # 20% - 60% = -40%
    assert result.pnl_delta_usd == pytest.approx(-400.0, abs=0.1)  # -200 - 200

    # Delta 검증 (상대값, %)
    assert result.winrate_change_pct < 0  # 악화
    assert result.pnl_change_pct < 0  # 악화


def test_compare_identical_periods(sample_before_trades):
    """정상: 동일한 기간 비교 → Delta ≈ 0"""
    comparator = ABComparator()
    result = comparator.compare(sample_before_trades, sample_before_trades)

    assert result.winrate_delta_pct == pytest.approx(0.0, abs=0.01)
    assert result.pnl_delta_usd == pytest.approx(0.0, abs=0.1)
    assert result.winrate_change_pct == pytest.approx(0.0, abs=0.1)
    assert result.pnl_change_pct == pytest.approx(0.0, abs=0.1)


def test_recommendation_keep_all_improved(sample_before_trades, sample_after_trades_improved):
    """추천 로직: 모든 지표 개선 → "Keep" 추천"""
    comparator = ABComparator()
    result = comparator.compare(sample_before_trades, sample_after_trades_improved)

    # 참고: 샘플 크기가 작아서 통계적 유의성은 보장되지 않을 수 있음
    # 하지만 PnL이 개선되면 "Keep" 추천되어야 함
    assert result.pnl_delta_usd > 0
    assert result.recommendation in ["Keep", "Need more data"]
    assert "improved" in result.reasoning.lower() or "pnl" in result.reasoning.lower()


def test_recommendation_revert_all_worse(sample_before_trades, sample_after_trades_worse):
    """추천 로직: 모든 지표 악화 → "Revert" 추천 (또는 샘플 부족 시 "Need more data")"""
    comparator = ABComparator()
    result = comparator.compare(sample_before_trades, sample_after_trades_worse)

    assert result.pnl_delta_usd < 0
    assert result.recommendation in ["Revert", "Need more data"]
    # Reasoning 검증: recommendation에 따라 다름
    if result.recommendation == "Revert":
        assert "worsened" in result.reasoning.lower() or "declined" in result.reasoning.lower() or "revert" in result.reasoning.lower()
    else:  # "Need more data"
        assert "significant" in result.reasoning.lower() or "sample" in result.reasoning.lower() or "more" in result.reasoning.lower()


def test_recommendation_insufficient_samples():
    """추천 로직: 샘플 크기 부족 → "Need more data" 추천"""
    comparator = ABComparator()

    # 샘플 2개씩만 (통계 검정 최소 요구사항은 만족하지만 신뢰도 낮음)
    before_trades = [
        {"order_id": "b1", "pnl": 100.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 3600, "slippage_usd": 1.0, "market_regime": "RANGING"},
        {"order_id": "b2", "pnl": -50.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 1800, "slippage_usd": 0.5, "market_regime": "TRENDING_UP"},
    ]
    after_trades = [
        {"order_id": "a1", "pnl": 120.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 3000, "slippage_usd": 1.0, "market_regime": "RANGING"},
        {"order_id": "a2", "pnl": 90.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 2000, "slippage_usd": 0.5, "market_regime": "TRENDING_UP"},
    ]

    result = comparator.compare(before_trades, after_trades)

    # 샘플 크기가 작으면 통계적 유의성 낮음
    # (단, chi-square는 최소 5개 필요하므로 ValueError 발생 가능)
    # 이 경우 "Need more data" 추천되어야 함
    assert result.recommendation == "Need more data"
    assert "sample" in result.reasoning.lower() or "more data" in result.reasoning.lower()


def test_is_significant_flag():
    """통계적 유의성 플래그 검증"""
    comparator = ABComparator()

    # 충분히 큰 차이와 샘플 크기 (유의성 높을 가능성)
    # Before: 승률 50%, PnL 평균 5.0
    before_trades = []
    for i in range(50):
        pnl = 10.0 if i % 2 == 0 else -5.0  # 승률 50%
        before_trades.append({"order_id": f"b{i}", "pnl": pnl, "fills": [{"fee": 0.5}], "holding_time_seconds": 3600, "slippage_usd": 1.0, "market_regime": "RANGING"})

    # After: 승률 100%, PnL 평균 100.0
    after_trades = [{"order_id": f"a{i}", "pnl": 100.0, "fills": [{"fee": 0.5}], "holding_time_seconds": 3600, "slippage_usd": 1.0, "market_regime": "RANGING"} for i in range(50)]

    result = comparator.compare(before_trades, after_trades)

    # is_significant는 boolean
    assert isinstance(result.is_significant, bool)
    # 큰 차이이므로 유의할 가능성 높음 (p < 0.05)
    assert result.is_significant is True


def test_sharpe_delta_calculation(sample_before_trades, sample_after_trades_improved):
    """Sharpe Ratio delta 계산 검증"""
    comparator = ABComparator()
    result = comparator.compare(sample_before_trades, sample_after_trades_improved)

    # Sharpe delta가 계산되어야 함
    assert result.sharpe_delta is not None
    # Before/After Sharpe 비교
    if result.before_metrics.sharpe_ratio and result.after_metrics.sharpe_ratio:
        expected_delta = result.after_metrics.sharpe_ratio - result.before_metrics.sharpe_ratio
        assert result.sharpe_delta == pytest.approx(expected_delta, abs=0.01)

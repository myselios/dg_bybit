"""
test_report_generator.py

Phase 13a: ReportGenerator 단위 테스트
- Markdown 리포트 생성
- JSON 리포트 생성
- A/B 비교 리포트 생성
"""

import json
import tempfile
from pathlib import Path
import pytest

from src.analysis.report_generator import ReportGenerator
from src.analysis.trade_analyzer import PerformanceMetrics, MetricsBreakdown
from src.analysis.ab_comparator import ComparisonResult
from src.analysis.stat_test import TTestResult, ChiSquareResult


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_metrics():
    """샘플 성과 지표"""
    return PerformanceMetrics(
        total_trades=10,
        win_count=6,
        loss_count=4,
        winrate=0.6,
        total_pnl=500.0,
        avg_pnl_per_trade=50.0,
        max_drawdown_pct=15.0,
        max_single_loss=-100.0,
        max_single_win=200.0,
        profit_factor=2.0,
        sharpe_ratio=1.5,
        sortino_ratio=2.0,
        avg_holding_time_seconds=7200,
        avg_slippage_usd=2.5,
        total_fees_usd=10.0,
        max_consecutive_wins=3,
        max_consecutive_losses=2,
        regime_breakdown={
            "RANGING": MetricsBreakdown(
                total_trades=6,
                win_count=4,
                loss_count=2,
                winrate=0.667,
                total_pnl=300.0,
                avg_pnl=50.0,
                sharpe_ratio=1.8
            ),
            "TRENDING": MetricsBreakdown(
                total_trades=4,
                win_count=2,
                loss_count=2,
                winrate=0.5,
                total_pnl=200.0,
                avg_pnl=50.0,
                sharpe_ratio=1.2
            )
        },
        pnl_confidence_interval=(30.0, 70.0)
    )


@pytest.fixture
def sample_comparison_result():
    """샘플 A/B 비교 결과"""
    before_metrics = PerformanceMetrics(
        total_trades=5, win_count=3, loss_count=2, winrate=0.6,
        total_pnl=100.0, avg_pnl_per_trade=20.0,
        max_drawdown_pct=10.0, max_single_loss=-50.0, max_single_win=80.0,
        profit_factor=1.8, sharpe_ratio=1.0, sortino_ratio=1.5,
        avg_holding_time_seconds=3600, avg_slippage_usd=1.0, total_fees_usd=2.5,
        max_consecutive_wins=2, max_consecutive_losses=1,
        regime_breakdown={}, pnl_confidence_interval=(10.0, 30.0)
    )

    after_metrics = PerformanceMetrics(
        total_trades=5, win_count=4, loss_count=1, winrate=0.8,
        total_pnl=200.0, avg_pnl_per_trade=40.0,
        max_drawdown_pct=5.0, max_single_loss=-30.0, max_single_win=100.0,
        profit_factor=3.0, sharpe_ratio=1.8, sortino_ratio=2.5,
        avg_holding_time_seconds=3000, avg_slippage_usd=0.8, total_fees_usd=2.5,
        max_consecutive_wins=3, max_consecutive_losses=1,
        regime_breakdown={}, pnl_confidence_interval=(30.0, 50.0)
    )

    return ComparisonResult(
        before_metrics=before_metrics,
        after_metrics=after_metrics,
        winrate_delta_pct=0.2,
        pnl_delta_usd=100.0,
        sharpe_delta=0.8,
        winrate_change_pct=33.33,
        pnl_change_pct=100.0,
        sharpe_change_pct=80.0,
        winrate_test=ChiSquareResult(
            statistic=0.5,
            pvalue=0.48,
            winrate_before=0.6,
            winrate_after=0.8,
            sample_size_before=5,
            sample_size_after=5
        ),
        pnl_test=TTestResult(
            statistic=2.0,
            pvalue=0.08,
            mean_before=20.0,
            mean_after=40.0,
            std_before=30.0,
            std_after=35.0
        ),
        is_significant=False,
        recommendation="Need more data",
        reasoning="Change is not statistically significant (p >= 0.05)."
    )


# ============================================================================
# Test Cases
# ============================================================================

def test_generate_markdown(sample_metrics):
    """정상: Markdown 리포트 생성"""
    generator = ReportGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.md"

        generator.generate_markdown(
            metrics=sample_metrics,
            output_path=str(output_path),
            period="2026-01-01:2026-01-31"
        )

        # 파일 존재 확인
        assert output_path.exists()

        # 내용 확인
        content = output_path.read_text(encoding='utf-8')
        assert "Trade Analysis Report" in content
        assert "2026-01-01:2026-01-31" in content
        assert "Total Trades" in content
        assert "10" in content  # total_trades
        assert "60.0%" in content  # winrate
        assert "$500.00" in content  # total_pnl
        assert "RANGING" in content  # regime breakdown
        assert "TRENDING" in content


def test_generate_json(sample_metrics):
    """정상: JSON 리포트 생성"""
    generator = ReportGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.json"

        generator.generate_json(
            metrics=sample_metrics,
            output_path=str(output_path),
            period="2026-01-01:2026-01-31"
        )

        # 파일 존재 확인
        assert output_path.exists()

        # JSON 파싱 확인
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert data["period"] == "2026-01-01:2026-01-31"
        assert data["metrics"]["total_trades"] == 10
        assert data["metrics"]["winrate"] == 0.6
        assert data["metrics"]["total_pnl"] == 500.0
        assert "RANGING" in data["regime_breakdown"]
        assert "TRENDING" in data["regime_breakdown"]


def test_generate_comparison_report(sample_comparison_result):
    """정상: A/B 비교 리포트 생성"""
    generator = ReportGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "comparison.md"

        generator.generate_comparison_report(
            result=sample_comparison_result,
            output_path=str(output_path)
        )

        # 파일 존재 확인
        assert output_path.exists()

        # 내용 확인
        content = output_path.read_text(encoding='utf-8')
        assert "A/B Comparison Report" in content
        assert "Recommendation" in content
        assert "Need more data" in content
        assert "Performance Delta" in content
        assert "Statistical Test Results" in content
        assert "Before Metrics Summary" in content
        assert "After Metrics Summary" in content


def test_markdown_directory_creation(sample_metrics):
    """정상: 출력 디렉토리 자동 생성"""
    generator = ReportGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "reports" / "nested" / "report.md"

        generator.generate_markdown(
            metrics=sample_metrics,
            output_path=str(output_path),
            period="2026-01-01:2026-01-31"
        )

        # 파일 존재 확인 (부모 디렉토리 자동 생성됨)
        assert output_path.exists()
        assert output_path.parent.exists()

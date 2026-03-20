"""
tests/dashboard/test_metrics_calculator.py

Phase 14a (Dashboard) Phase 2: Metrics Calculator 테스트

TDD RED Phase: 테스트 먼저 작성 (구현은 아직 없음)
"""

import pytest
import pandas as pd
from datetime import datetime
from typing import Dict, Any


# Test 1: Summary Metrics 계산
def test_calculate_summary_metrics():
    """
    Summary Metrics 계산: Total PnL, Win Rate, Trade Count

    Given: 거래 DataFrame (PnL 포함)
    When: calculate_summary() 호출
    Then: Total PnL, Win Rate, Trade Count 반환
    """
    from src.dashboard.metrics_calculator import calculate_summary

    # Arrange: 테스트 데이터 (승/패 혼합)
    df = pd.DataFrame([
        {
            "order_id": "order_1",
            "fills": [{"price": 50000.0, "qty": 100, "fee": 0.1}],
            "slippage_usd": 0.5,
            "latency_total_ms": 15.0,
            "pnl": 10.0,  # 승
        },
        {
            "order_id": "order_2",
            "fills": [{"price": 50100.0, "qty": 100, "fee": 0.1}],
            "slippage_usd": 0.3,
            "latency_total_ms": 12.0,
            "pnl": -5.0,  # 패
        },
        {
            "order_id": "order_3",
            "fills": [{"price": 50200.0, "qty": 100, "fee": 0.1}],
            "slippage_usd": 0.2,
            "latency_total_ms": 10.0,
            "pnl": 15.0,  # 승
        },
    ])

    # Act
    metrics = calculate_summary(df)

    # Assert
    assert isinstance(metrics, dict)
    assert "total_pnl" in metrics
    assert "win_rate" in metrics
    assert "trade_count" in metrics

    assert metrics["total_pnl"] == 20.0  # 10 - 5 + 15
    assert metrics["win_rate"] == pytest.approx(2 / 3, rel=1e-2)  # 2승 / 3거래
    assert metrics["trade_count"] == 3
    assert metrics["win_count"] == 2
    assert metrics["loss_count"] == 1


# Test 2: Session Risk 계산
def test_calculate_session_risk():
    """
    Session Risk 계산: Daily/Weekly Loss, Loss Streak

    Given: 거래 DataFrame (날짜, PnL 포함)
    When: calculate_session_risk() 호출
    Then: Daily Max Loss, Weekly Max Loss, Max Loss Streak 반환
    """
    from src.dashboard.metrics_calculator import calculate_session_risk

    # Arrange: 테스트 데이터 (연속 손실 포함)
    df = pd.DataFrame([
        {"order_id": "o1", "pnl": -10.0, "fills": [{"timestamp": "2026-02-01T10:00:00"}]},
        {"order_id": "o2", "pnl": -5.0, "fills": [{"timestamp": "2026-02-01T11:00:00"}]},
        {"order_id": "o3", "pnl": 15.0, "fills": [{"timestamp": "2026-02-01T12:00:00"}]},
        {"order_id": "o4", "pnl": -8.0, "fills": [{"timestamp": "2026-02-02T10:00:00"}]},
        {"order_id": "o5", "pnl": -3.0, "fills": [{"timestamp": "2026-02-02T11:00:00"}]},
        {"order_id": "o6", "pnl": -2.0, "fills": [{"timestamp": "2026-02-02T12:00:00"}]},
    ])

    # Act
    risk_metrics = calculate_session_risk(df)

    # Assert
    assert isinstance(risk_metrics, dict)
    assert "daily_max_loss" in risk_metrics
    assert "weekly_max_loss" in risk_metrics
    assert "max_loss_streak" in risk_metrics

    # 2026-02-01: -10 - 5 + 15 = 0 (손실 없음)
    # 2026-02-02: -8 - 3 - 2 = -13 (최대 손실)
    assert risk_metrics["daily_max_loss"] == -13.0

    # 주간 손실: -10 - 5 + 15 - 8 - 3 - 2 = -13
    assert risk_metrics["weekly_max_loss"] == -13.0

    # 연속 손실: o1, o2 (2연속) / o4, o5, o6 (3연속) → max = 3
    assert risk_metrics["max_loss_streak"] == 3


# Test 3: Regime Breakdown 계산
def test_calculate_regime_breakdown():
    """
    Market Regime별 성과 분석

    Given: 거래 DataFrame (market_regime 포함)
    When: calculate_regime_breakdown() 호출
    Then: Regime별 Trade Count, Win Rate, Total PnL DataFrame 반환
    """
    from src.dashboard.metrics_calculator import calculate_regime_breakdown

    # Arrange: 테스트 데이터 (Regime별 분류)
    df = pd.DataFrame([
        {"order_id": "o1", "pnl": 10.0, "market_regime": "ranging"},
        {"order_id": "o2", "pnl": -5.0, "market_regime": "ranging"},
        {"order_id": "o3", "pnl": 15.0, "market_regime": "trending_up"},
        {"order_id": "o4", "pnl": 20.0, "market_regime": "trending_up"},
        {"order_id": "o5", "pnl": -3.0, "market_regime": "trending_down"},
    ])

    # Act
    breakdown = calculate_regime_breakdown(df)

    # Assert
    assert isinstance(breakdown, pd.DataFrame)
    assert "regime" in breakdown.columns
    assert "trade_count" in breakdown.columns
    assert "win_rate" in breakdown.columns
    assert "total_pnl" in breakdown.columns

    # ranging: 2거래, 1승 1패, PnL = 5.0
    ranging = breakdown[breakdown["regime"] == "ranging"].iloc[0]
    assert ranging["trade_count"] == 2
    assert ranging["win_rate"] == pytest.approx(0.5, rel=1e-2)
    assert ranging["total_pnl"] == 5.0

    # trending_up: 2거래, 2승, PnL = 35.0
    trending_up = breakdown[breakdown["regime"] == "trending_up"].iloc[0]
    assert trending_up["trade_count"] == 2
    assert trending_up["win_rate"] == pytest.approx(1.0, rel=1e-2)
    assert trending_up["total_pnl"] == 35.0


# Test 4: Slippage Stats 계산
def test_calculate_slippage_stats():
    """
    Slippage 통계: 평균, 최대, 분포

    Given: 거래 DataFrame (slippage_usd 포함)
    When: calculate_slippage_stats() 호출
    Then: 평균 Slippage, 최대 Slippage, p95 Slippage 반환
    """
    from src.dashboard.metrics_calculator import calculate_slippage_stats

    # Arrange: 테스트 데이터 (Slippage 분포)
    df = pd.DataFrame([
        {"order_id": "o1", "slippage_usd": 0.5},
        {"order_id": "o2", "slippage_usd": 0.3},
        {"order_id": "o3", "slippage_usd": 1.2},
        {"order_id": "o4", "slippage_usd": 0.8},
        {"order_id": "o5", "slippage_usd": 0.4},
    ])

    # Act
    stats = calculate_slippage_stats(df)

    # Assert
    assert isinstance(stats, dict)
    assert "avg_slippage" in stats
    assert "max_slippage" in stats
    assert "p95_slippage" in stats

    # 평균: (0.5 + 0.3 + 1.2 + 0.8 + 0.4) / 5 = 0.64
    assert stats["avg_slippage"] == pytest.approx(0.64, rel=1e-2)

    # 최대: 1.2
    assert stats["max_slippage"] == 1.2

    # p95: pandas quantile 보간 사용 → 1.12 (0.8 + 0.75 * (1.2 - 0.8))
    assert stats["p95_slippage"] >= 1.1
    assert stats["p95_slippage"] <= 1.2


# Test 5: Latency Stats 계산
def test_calculate_latency_stats():
    """
    Latency 통계: 평균, p95, p99

    Given: 거래 DataFrame (latency_total_ms 포함)
    When: calculate_latency_stats() 호출
    Then: 평균 Latency, p95 Latency, p99 Latency 반환
    """
    from src.dashboard.metrics_calculator import calculate_latency_stats

    # Arrange: 테스트 데이터 (Latency 분포, 100개)
    latencies = [10.0 + i * 0.5 for i in range(100)]  # 10.0 ~ 59.5 ms
    df = pd.DataFrame([
        {"order_id": f"o{i}", "latency_total_ms": latencies[i]}
        for i in range(100)
    ])

    # Act
    stats = calculate_latency_stats(df)

    # Assert
    assert isinstance(stats, dict)
    assert "avg_latency_ms" in stats
    assert "p95_latency_ms" in stats
    assert "p99_latency_ms" in stats

    # 평균: (10.0 + 59.5) / 2 = 34.75
    assert stats["avg_latency_ms"] == pytest.approx(34.75, rel=1e-2)

    # p95: 상위 5% (95번째 값) ≈ 57.25 ms
    assert stats["p95_latency_ms"] >= 57.0
    assert stats["p95_latency_ms"] <= 58.0

    # p99: 상위 1% (99번째 값) ≈ 59.25 ms
    assert stats["p99_latency_ms"] >= 59.0
    assert stats["p99_latency_ms"] <= 60.0


# ============================================================================
# Stream C: 신규 함수 테스트
# ============================================================================

def _make_trade_df() -> "pd.DataFrame":
    """테스트용 트레이드 DataFrame (exit_time, hold_seconds 포함)"""
    import pandas as pd
    return pd.DataFrame([
        {
            "realized_pnl_usd": 10.0,
            "exit_time": 1_700_000_100.0,  # 2023-11-15 00:01:40 UTC
            "hold_seconds": 60.0,
            "market_regime": "trending_up",
        },
        {
            "realized_pnl_usd": -5.0,
            "exit_time": 1_700_000_200.0,
            "hold_seconds": 120.0,
            "market_regime": "ranging",
        },
        {
            "realized_pnl_usd": 8.0,
            "exit_time": 1_700_086_500.0,  # 다음 날
            "hold_seconds": None,
            "market_regime": "trending_up",
        },
        {
            "realized_pnl_usd": -3.0,
            "exit_time": 1_700_086_600.0,
            "hold_seconds": 300.0,
            "market_regime": "ranging",
        },
    ])


def test_calculate_cumulative_pnl_basic():
    """
    exit_time 기준 누적 PnL 계산

    Given: exit_time float 컬럼이 있는 DataFrame
    When: calculate_cumulative_pnl() 호출
    Then: exit_time 순서대로 누적합 pd.Series 반환
    """
    from src.dashboard.metrics_calculator import calculate_cumulative_pnl

    df = _make_trade_df()
    result = calculate_cumulative_pnl(df)

    assert isinstance(result, pd.Series)
    assert len(result) == 4
    # 마지막 값 = 총합 10 - 5 + 8 - 3 = 10.0
    assert float(result.iloc[-1]) == pytest.approx(10.0, rel=1e-6)


def test_calculate_cumulative_pnl_empty():
    """빈 DataFrame → 빈 Series 반환, crash 없음"""
    from src.dashboard.metrics_calculator import calculate_cumulative_pnl

    result = calculate_cumulative_pnl(pd.DataFrame())

    assert isinstance(result, pd.Series)
    assert len(result) == 0


def test_calculate_cumulative_pnl_null_exit_time():
    """exit_time null 행은 뒤로 정렬되어 포함됨, crash 없음"""
    from src.dashboard.metrics_calculator import calculate_cumulative_pnl

    df = pd.DataFrame([
        {"realized_pnl_usd": 5.0, "exit_time": 1_700_000_000.0},
        {"realized_pnl_usd": 3.0, "exit_time": None},
    ])
    result = calculate_cumulative_pnl(df)

    assert isinstance(result, pd.Series)
    assert len(result) == 2
    # 마지막 누적합 = 8.0
    assert float(result.iloc[-1]) == pytest.approx(8.0, rel=1e-6)


def test_calculate_win_rate_by_regime():
    """
    regime별 승률 계산

    Given: market_regime, realized_pnl_usd 컬럼이 있는 DataFrame
    When: calculate_win_rate_by_regime() 호출
    Then: regime → 승률 dict 반환
    """
    from src.dashboard.metrics_calculator import calculate_win_rate_by_regime

    df = _make_trade_df()
    result = calculate_win_rate_by_regime(df)

    assert isinstance(result, dict)
    assert "trending_up" in result
    assert "ranging" in result
    # trending_up: 10.0, 8.0 → 2승 / 2 = 1.0
    assert result["trending_up"] == pytest.approx(1.0, rel=1e-6)
    # ranging: -5.0, -3.0 → 0승 / 2 = 0.0
    assert result["ranging"] == pytest.approx(0.0, rel=1e-6)


def test_calculate_win_rate_by_regime_empty():
    """빈 DataFrame → 빈 dict 반환"""
    from src.dashboard.metrics_calculator import calculate_win_rate_by_regime

    result = calculate_win_rate_by_regime(pd.DataFrame())

    assert result == {}


def test_calculate_max_drawdown_basic():
    """
    최대 드로다운 계산

    Given: 순서대로 +10, -5, +8, -3 의 PnL (누적: 10, 5, 13, 10)
    Then: 최대 드로다운 = 고점 10 → 5 = -5.0
    """
    from src.dashboard.metrics_calculator import calculate_max_drawdown

    df = _make_trade_df()
    result = calculate_max_drawdown(df)

    assert isinstance(result, dict)
    assert "max_drawdown_usd" in result
    assert "max_drawdown_pct" in result
    assert "drawdown_series" in result
    # max drawdown: 누적 10→5 (두번째 트레이드 후), 또는 13→10 (네번째 후)
    # 고점 10에서 5로 = -5, 고점 13에서 10으로 = -3 → 최대는 -5
    assert result["max_drawdown_usd"] == pytest.approx(-5.0, rel=1e-6)
    assert result["max_drawdown_pct"] > 0


def test_calculate_max_drawdown_empty():
    """빈 DataFrame → max_drawdown_usd=0.0, crash 없음"""
    from src.dashboard.metrics_calculator import calculate_max_drawdown

    result = calculate_max_drawdown(pd.DataFrame())

    assert result["max_drawdown_usd"] == 0.0
    assert result["max_drawdown_pct"] == 0.0
    assert isinstance(result["drawdown_series"], pd.Series)


def test_calculate_hold_time_stats_basic():
    """
    hold_seconds 통계

    Given: 일부 null 포함한 hold_seconds 컬럼
    When: calculate_hold_time_stats() 호출
    Then: null을 제외한 유효 레코드만으로 평균/중앙값 계산
    """
    from src.dashboard.metrics_calculator import calculate_hold_time_stats

    df = _make_trade_df()
    result = calculate_hold_time_stats(df)

    assert isinstance(result, dict)
    assert "mean_seconds" in result
    assert "median_seconds" in result
    assert "hist_data" in result
    assert "valid_count" in result

    # 유효 레코드: 60, 120, 300 (None 제외) → 3건
    assert result["valid_count"] == 3
    assert result["mean_seconds"] == pytest.approx((60 + 120 + 300) / 3, rel=1e-6)
    assert len(result["hist_data"]) == 3


def test_calculate_hold_time_stats_empty():
    """빈 DataFrame → valid_count=0, hist_data=[] 반환"""
    from src.dashboard.metrics_calculator import calculate_hold_time_stats

    result = calculate_hold_time_stats(pd.DataFrame())

    assert result["valid_count"] == 0
    assert result["hist_data"] == []
    assert result["mean_seconds"] == 0.0


def test_calculate_daily_pnl_basic():
    """
    날짜별 PnL 합산

    Given: exit_time float 컬럼이 있는 DataFrame (2개 날짜)
    When: calculate_daily_pnl() 호출
    Then: 날짜별 PnL 합산 pd.Series 반환
    """
    from src.dashboard.metrics_calculator import calculate_daily_pnl

    df = _make_trade_df()
    result = calculate_daily_pnl(df)

    assert isinstance(result, pd.Series)
    # 2개 날짜가 있어야 함
    assert len(result) == 2
    # 첫 날: 10 - 5 = 5.0
    # 둘째 날: 8 - 3 = 5.0
    assert float(result.iloc[0]) == pytest.approx(5.0, rel=1e-6)
    assert float(result.iloc[1]) == pytest.approx(5.0, rel=1e-6)


def test_calculate_daily_pnl_empty():
    """빈 DataFrame → 빈 Series, crash 없음"""
    from src.dashboard.metrics_calculator import calculate_daily_pnl

    result = calculate_daily_pnl(pd.DataFrame())

    assert isinstance(result, pd.Series)
    assert len(result) == 0

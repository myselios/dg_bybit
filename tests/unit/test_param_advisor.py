"""
tests/unit/test_param_advisor.py

파라미터 어드바이저 단위 테스트
"""

import pytest
from src.application.param_advisor import (
    TradingParams,
    compute_stats,
    format_report,
    generate_recommendations,
)


def make_trade(pnl: float, regime: str = "ranging", direction: str = "LONG") -> dict:
    """테스트용 완료 트레이드 픽스처"""
    return {
        "entry_price": 70000.0,
        "exit_price": 70000.0 + pnl / 0.001,
        "realized_pnl_usd": pnl,
        "fee_usd": 0.05,
        "market_regime": regime,
        "direction": direction,
        "hold_seconds": 600.0,
        "qty_btc": 0.001,
        "funding_rate": 0.0001,
    }


class TestComputeStats:
    def test_win_rate_calculated_correctly(self):
        trades = [make_trade(1.0), make_trade(-1.0), make_trade(2.0)]
        stats = compute_stats(trades)
        assert stats.win_rate == pytest.approx(2 / 3, rel=0.01)
        assert stats.total_trades == 3

    def test_regime_grouping(self):
        trades = [
            make_trade(1.0, regime="ranging"),
            make_trade(-2.0, regime="ranging"),
            make_trade(3.0, regime="trending_up"),
        ]
        stats = compute_stats(trades)
        assert "ranging" in stats.by_regime
        assert "trending_up" in stats.by_regime
        assert stats.by_regime["ranging"].count == 2
        assert stats.by_regime["trending_up"].count == 1

    def test_max_loss_tracked(self):
        trades = [make_trade(-10.0), make_trade(-2.0), make_trade(5.0)]
        stats = compute_stats(trades)
        assert stats.max_loss == pytest.approx(-10.0, rel=0.01)

    def test_direction_grouping(self):
        trades = [
            make_trade(-3.0, direction="SHORT"),
            make_trade(1.0, direction="LONG"),
            make_trade(2.0, direction="LONG"),
        ]
        stats = compute_stats(trades)
        assert stats.by_direction["SHORT"].win_rate == 0.0
        assert stats.by_direction["LONG"].win_rate == 1.0


class TestGenerateRecommendations:
    def test_range_regime_poor_winrate_raises_t_range_entry(self):
        # Range 0% 승률 → T_RANGE_ENTRY 상향 추천
        trades = [make_trade(-5.0, regime="ranging") for _ in range(5)]
        stats = compute_stats(trades)
        params = TradingParams(t_range_entry=0.02)
        recs = generate_recommendations(stats, params)

        param_names = [r.param for r in recs]
        assert "T_RANGE_ENTRY" in param_names

        rec = next(r for r in recs if r.param == "T_RANGE_ENTRY")
        assert rec.suggested > rec.current  # 상향

    def test_low_overall_winrate_suggests_tighter_sl(self):
        # 전체 승률 25% → ATR_SL_MULT 하향 추천
        trades = [make_trade(-3.0) for _ in range(6)] + [make_trade(1.0) for _ in range(2)]
        stats = compute_stats(trades)
        params = TradingParams(atr_sl_mult=0.7)
        recs = generate_recommendations(stats, params)

        param_names = [r.param for r in recs]
        assert "ATR_SL_MULT" in param_names

        rec = next(r for r in recs if r.param == "ATR_SL_MULT")
        assert rec.suggested < rec.current  # SL 좁히기

    def test_small_sample_warning_included(self):
        trades = [make_trade(-1.0), make_trade(1.0)]
        stats = compute_stats(trades)
        recs = generate_recommendations(stats)

        warnings = [r for r in recs if r.param == "_WARNING"]
        assert len(warnings) > 0

    def test_good_performance_no_major_recommendations(self):
        # 승률 80% → 큰 추천 없음
        trades = [make_trade(2.0, regime="trending_up") for _ in range(12)] + [
            make_trade(-1.0, regime="trending_up") for _ in range(3)
        ]
        stats = compute_stats(trades)
        params = TradingParams()
        recs = generate_recommendations(stats, params)

        # T_RANGE_ENTRY, ATR_SL_MULT 추천 없어야 함
        param_names = [r.param for r in recs if r.param != "_WARNING"]
        assert "T_RANGE_ENTRY" not in param_names
        assert "ATR_SL_MULT" not in param_names


class TestFormatReport:
    def test_report_contains_overall_stats(self):
        trades = [make_trade(1.0), make_trade(-2.0), make_trade(3.0)]
        stats = compute_stats(trades)
        recs = generate_recommendations(stats)
        report = format_report(stats, recs)

        assert "총 트레이드: 3" in report
        assert "승률" in report

    def test_report_contains_current_params(self):
        trades = [make_trade(1.0)]
        stats = compute_stats(trades)
        recs = generate_recommendations(stats)
        params = TradingParams(t_trend=0.5, t_range_entry=0.02)
        report = format_report(stats, recs, params)

        assert "T_TREND" in report
        assert "0.5" in report

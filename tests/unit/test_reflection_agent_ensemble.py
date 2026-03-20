"""
tests/unit/test_reflection_agent_ensemble.py

Wave 2: ReflectionAgent ensemble signal feedback loop + ShadowTrader threshold validation.

TDD: RED phase — tests written before implementation.
"""

from application.agents.reflection_agent import ReflectionAgent
from application.shadow_trader import ShadowTrader


# ---------------------------------------------------------------------------
# Task 1: classify_trade uses actual signal_score from trade log
# ---------------------------------------------------------------------------


def test_high_score_loss_uses_signal_score():
    """score=5, pnl<0 → pattern must be 'high_score_loss'."""
    agent = ReflectionAgent()
    trade = {
        "trade_id": "T-001",
        "direction": "Buy",
        "entry_price": 50000.0,
        "exit_price": 49000.0,
        "pnl_usd": -10.0,
        "hold_seconds": 300,
        "ma_slope_pct": 0.15,
        "funding_rate": 0.0001,
        "signal_score": 5,
    }
    result = agent.analyze(trade)
    assert result.pattern == "high_score_loss"


def test_low_score_win_uses_signal_score():
    """score=1, pnl>0 → pattern must be 'low_score_win'."""
    agent = ReflectionAgent()
    trade = {
        "trade_id": "T-002",
        "direction": "Buy",
        "entry_price": 50000.0,
        "exit_price": 51000.0,
        "pnl_usd": 10.0,
        "hold_seconds": 300,
        "ma_slope_pct": 0.03,
        "funding_rate": 0.0001,
        "signal_score": 1,
    }
    result = agent.analyze(trade)
    assert result.pattern == "low_score_win"


def test_high_score_none_falls_back_to_slope_pattern():
    """signal_score=None, pnl<0 → falls back to slope-based pattern (not high_score_loss)."""
    agent = ReflectionAgent()
    trade = {
        "trade_id": "T-003",
        "direction": "Buy",
        "entry_price": 50000.0,
        "exit_price": 49000.0,
        "pnl_usd": -10.0,
        "hold_seconds": 300,
        "ma_slope_pct": 0.03,
        "funding_rate": 0.0001,
        "signal_score": None,
    }
    result = agent.analyze(trade)
    assert result.pattern != "high_score_loss"
    assert result.outcome == "loss"


def test_score_exactly_4_is_high_score_loss():
    """score=4 (boundary) + pnl<0 → 'high_score_loss'."""
    agent = ReflectionAgent()
    trade = {
        "trade_id": "T-004",
        "direction": "Buy",
        "entry_price": 50000.0,
        "exit_price": 49500.0,
        "pnl_usd": -5.0,
        "hold_seconds": 200,
        "ma_slope_pct": 0.12,
        "funding_rate": 0.0001,
        "signal_score": 4,
    }
    result = agent.analyze(trade)
    assert result.pattern == "high_score_loss"


def test_score_exactly_2_is_low_score_win():
    """score=2 (boundary) + pnl>0 → 'low_score_win'."""
    agent = ReflectionAgent()
    trade = {
        "trade_id": "T-005",
        "direction": "Buy",
        "entry_price": 50000.0,
        "exit_price": 51000.0,
        "pnl_usd": 10.0,
        "hold_seconds": 600,
        "ma_slope_pct": 0.04,
        "funding_rate": 0.0001,
        "signal_score": 2,
    }
    result = agent.analyze(trade)
    assert result.pattern == "low_score_win"


def test_score_3_win_is_good_entry():
    """score=3 + pnl>0 → 'good_entry' (not low_score_win)."""
    agent = ReflectionAgent()
    trade = {
        "trade_id": "T-006",
        "direction": "Buy",
        "entry_price": 50000.0,
        "exit_price": 51000.0,
        "pnl_usd": 10.0,
        "hold_seconds": 600,
        "ma_slope_pct": 0.1,
        "funding_rate": 0.0001,
        "signal_score": 3,
    }
    result = agent.analyze(trade)
    assert result.pattern == "good_entry"


# ---------------------------------------------------------------------------
# Task 2: analyze_score_distribution
# ---------------------------------------------------------------------------


def test_analyze_score_distribution_groups_by_bucket():
    """Distribution groups trades into correct score buckets."""
    agent = ReflectionAgent()
    trades = [
        # Bucket 0-1
        {"signal_score": 0, "pnl_usd": -5.0},
        {"signal_score": 1, "pnl_usd": 3.0},
        # Bucket 2
        {"signal_score": 2, "pnl_usd": -2.0},
        {"signal_score": 2, "pnl_usd": 4.0},
        # Bucket 3
        {"signal_score": 3, "pnl_usd": 6.0},
        # Bucket 4
        {"signal_score": 4, "pnl_usd": -8.0},
        {"signal_score": 4, "pnl_usd": 5.0},
        # Bucket 5-6
        {"signal_score": 5, "pnl_usd": -3.0},
        {"signal_score": 6, "pnl_usd": 7.0},
    ]
    result = agent.analyze_score_distribution(trades)

    assert "0-1" in result
    assert "2" in result
    assert "3" in result
    assert "4" in result
    assert "5-6" in result

    # Bucket 0-1 has 2 trades
    assert result["0-1"]["count"] == 2
    # Bucket 2 has 2 trades, 1 win → win_rate=0.5
    assert result["2"]["count"] == 2
    assert result["2"]["win_rate"] == 0.5
    # Bucket 3 has 1 trade, 1 win → win_rate=1.0
    assert result["3"]["count"] == 1
    assert result["3"]["win_rate"] == 1.0


def test_analyze_score_distribution_avg_pnl():
    """avg_pnl is correctly calculated per bucket."""
    agent = ReflectionAgent()
    trades = [
        {"signal_score": 3, "pnl_usd": 4.0},
        {"signal_score": 3, "pnl_usd": -2.0},
    ]
    result = agent.analyze_score_distribution(trades)
    assert result["3"]["count"] == 2
    assert abs(result["3"]["avg_pnl"] - 1.0) < 0.001


def test_analyze_score_distribution_skips_none_score():
    """Trades with signal_score=None are excluded from distribution."""
    agent = ReflectionAgent()
    trades = [
        {"signal_score": None, "pnl_usd": 5.0},
        {"signal_score": 3, "pnl_usd": 2.0},
    ]
    result = agent.analyze_score_distribution(trades)
    total_count = sum(b["count"] for b in result.values())
    assert total_count == 1


def test_analyze_score_distribution_returns_all_buckets():
    """Even buckets with 0 trades are included in result."""
    agent = ReflectionAgent()
    trades = [{"signal_score": 3, "pnl_usd": 5.0}]
    result = agent.analyze_score_distribution(trades)
    assert set(result.keys()) == {"0-1", "2", "3", "4", "5-6"}


def test_analyze_score_distribution_empty_list():
    """Empty trades list returns all buckets with count=0."""
    agent = ReflectionAgent()
    result = agent.analyze_score_distribution([])
    assert all(b["count"] == 0 for b in result.values())
    assert all(b["win_rate"] == 0.0 for b in result.values())
    assert all(b["avg_pnl"] == 0.0 for b in result.values())


# ---------------------------------------------------------------------------
# Task 3: ShadowTrader.compare_score_thresholds
# ---------------------------------------------------------------------------


def _make_trade(score, pnl):
    return {"signal_score": score, "pnl_usd": pnl}


def test_shadow_trader_compare_thresholds_returns_all_variants():
    """compare_score_thresholds returns dict with keys 2, 3, 4."""
    trader = ShadowTrader()
    trades = [
        _make_trade(2, 5.0),
        _make_trade(3, -3.0),
        _make_trade(4, 8.0),
        _make_trade(5, -1.0),
        _make_trade(1, 2.0),
    ]
    result = trader.compare_score_thresholds(trades)
    assert 2 in result
    assert 3 in result
    assert 4 in result


def test_shadow_trader_compare_thresholds_filters_correctly():
    """Threshold=4 keeps only trades with score>=4."""
    trader = ShadowTrader()
    trades = [
        _make_trade(2, -5.0),
        _make_trade(3, -3.0),
        _make_trade(4, 8.0),
        _make_trade(5, 10.0),
    ]
    result = trader.compare_score_thresholds(trades)
    # threshold=4: only scores 4 and 5 → 2 trades
    assert result[4]["trades_kept"] == 2


def test_shadow_trader_compare_thresholds_win_rate():
    """win_rate is correctly computed per threshold."""
    trader = ShadowTrader()
    trades = [
        _make_trade(3, 5.0),   # win
        _make_trade(3, -3.0),  # loss
        _make_trade(4, 8.0),   # win
        _make_trade(5, -2.0),  # loss
    ]
    result = trader.compare_score_thresholds(trades)
    # threshold=3: 4 trades, 2 wins → 0.5
    assert result[3]["win_rate"] == 0.5
    # threshold=4: 2 trades (score 4 win, score 5 loss) → 0.5
    assert result[4]["win_rate"] == 0.5


def test_shadow_trader_compare_thresholds_net_pnl():
    """net_pnl sums correctly per threshold."""
    trader = ShadowTrader()
    trades = [
        _make_trade(2, 1.0),
        _make_trade(3, 2.0),
        _make_trade(4, -4.0),
    ]
    result = trader.compare_score_thresholds(trades)
    # threshold=2: all 3 trades → net_pnl = -1.0
    assert abs(result[2]["net_pnl"] - (-1.0)) < 0.001
    # threshold=3: scores 3 and 4 → 2.0 + (-4.0) = -2.0
    assert abs(result[3]["net_pnl"] - (-2.0)) < 0.001
    # threshold=4: score 4 only → -4.0
    assert abs(result[4]["net_pnl"] - (-4.0)) < 0.001


def test_shadow_trader_compare_thresholds_recommendation():
    """optimal_threshold is the one with best net_pnl and enough trades."""
    trader = ShadowTrader()
    trades = [
        _make_trade(2, -10.0),
        _make_trade(3, 5.0),
        _make_trade(4, 8.0),
        _make_trade(5, 6.0),
    ]
    result = trader.compare_score_thresholds(trades)
    # threshold=2: -10+5+8+6=9 (net = 9)
    # threshold=3: 5+8+6=19 (net = 19) ← best
    # threshold=4: 8+6=14
    assert result["optimal_threshold"] == 3


def test_shadow_trader_compare_thresholds_none_score_fallback():
    """Trades with signal_score=None are included at all thresholds (fallback keep all)."""
    trader = ShadowTrader()
    trades = [
        {"signal_score": None, "pnl_usd": 5.0},
        _make_trade(4, 3.0),
    ]
    result = trader.compare_score_thresholds(trades)
    # None-score trades are kept at every threshold level
    assert result[4]["trades_kept"] == 2


def test_shadow_trader_compare_thresholds_empty_trades():
    """Empty trades list returns all thresholds with 0 trades."""
    trader = ShadowTrader()
    result = trader.compare_score_thresholds([])
    assert result[2]["trades_kept"] == 0
    assert result[3]["trades_kept"] == 0
    assert result[4]["trades_kept"] == 0

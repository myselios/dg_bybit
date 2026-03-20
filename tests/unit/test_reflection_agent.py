"""TDD — ReflectionAgent unit tests.

Tests for S7 post-trade reflection analysis:
- Pattern classification (regime_mismatch, good_entry, threshold_too_high/low)
- Multi-indicator patterns (rsi_oversold_miss, high_score_loss, low_score_win)
- Streak tracking for score_threshold auto-adjustment
- Hypothesis generation
- Parameter delta suggestions
- Immutability of ReflectionResult
"""

import pytest
from application.agents.reflection_agent import ReflectionAgent, ReflectionResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent():
    return ReflectionAgent()


@pytest.fixture
def loss_trade():
    """Loss trade with moderate slope — basic loss scenario."""
    return {
        "trade_id": "T-001",
        "direction": "Buy",
        "entry_price": 85000.0,
        "exit_price": 84500.0,
        "pnl_usd": -5.0,
        "hold_seconds": 120,
        "ma_slope_pct": 0.15,
        "funding_rate": 0.0001,
    }


@pytest.fixture
def win_trade():
    """Winning trade with decent slope — good entry scenario."""
    return {
        "trade_id": "T-002",
        "direction": "Buy",
        "entry_price": 85000.0,
        "exit_price": 85800.0,
        "pnl_usd": 8.0,
        "hold_seconds": 600,
        "ma_slope_pct": 0.6,
        "funding_rate": 0.0001,
    }


@pytest.fixture
def ranging_loss_trade():
    """Loss trade with near-zero slope — regime mismatch scenario."""
    return {
        "trade_id": "T-003",
        "direction": "Buy",
        "entry_price": 85000.0,
        "exit_price": 84700.0,
        "pnl_usd": -3.0,
        "hold_seconds": 300,
        "ma_slope_pct": 0.02,   # near-zero slope = ranging market
        "funding_rate": 0.0001,
    }


@pytest.fixture
def low_slope_loss_trade():
    """Loss trade with low but non-zero slope — threshold too low scenario."""
    return {
        "trade_id": "T-004",
        "direction": "Sell",
        "entry_price": 85000.0,
        "exit_price": 85200.0,
        "pnl_usd": -2.0,
        "hold_seconds": 180,
        "ma_slope_pct": 0.08,   # low slope, suggests threshold should be higher
        "funding_rate": -0.0001,
    }


# ---------------------------------------------------------------------------
# Test 1: Loss trade returns ReflectionResult with correct outcome
# ---------------------------------------------------------------------------

def test_analyze_loss_returns_reflection_result(agent, loss_trade):
    # Act
    result = agent.analyze(loss_trade)

    # Assert
    assert isinstance(result, ReflectionResult)
    assert result.trade_id == "T-001"
    assert result.outcome == "loss"


# ---------------------------------------------------------------------------
# Test 2: Win trade reinforces "good_entry" pattern
# ---------------------------------------------------------------------------

def test_analyze_win_reinforces_pattern(agent, win_trade):
    # Act
    result = agent.analyze(win_trade)

    # Assert
    assert result.outcome == "win"
    assert result.pattern == "good_entry"


# ---------------------------------------------------------------------------
# Test 3: Loss + near-zero slope -> "regime_mismatch"
# ---------------------------------------------------------------------------

def test_analyze_loss_with_ranging_slope_detects_regime_mismatch(agent, ranging_loss_trade):
    # Act
    result = agent.analyze(ranging_loss_trade)

    # Assert
    assert result.outcome == "loss"
    assert result.pattern == "regime_mismatch"


# ---------------------------------------------------------------------------
# Test 4: hypothesis field is never empty
# ---------------------------------------------------------------------------

def test_analyze_generates_hypothesis_text(agent, loss_trade):
    # Act
    result = agent.analyze(loss_trade)

    # Assert — hypothesis must be a non-empty string
    assert isinstance(result.hypothesis, str)
    assert len(result.hypothesis) > 0


# ---------------------------------------------------------------------------
# Test 5: Loss + low slope -> param_delta suggests threshold increase
# ---------------------------------------------------------------------------

def test_analyze_loss_suggests_threshold_increase(agent, low_slope_loss_trade):
    # Act
    result = agent.analyze(low_slope_loss_trade)

    # Assert — should suggest raising T_TREND threshold
    assert result.outcome == "loss"
    assert isinstance(result.param_delta, dict)
    assert "T_TREND" in result.param_delta


# ---------------------------------------------------------------------------
# Test 6: ReflectionResult is immutable (frozen dataclass)
# ---------------------------------------------------------------------------

def test_analyze_result_immutable(agent, win_trade):
    # Act
    result = agent.analyze(win_trade)

    # Assert — frozen=True means attribute assignment raises
    with pytest.raises(AttributeError):
        result.outcome = "loss"


# ---------------------------------------------------------------------------
# Test 7: ReflectionResult schema — all required fields present
# ---------------------------------------------------------------------------

def test_reflection_result_schema(agent, loss_trade):
    # Act
    result = agent.analyze(loss_trade)

    # Assert — all fields exist and have correct types
    assert hasattr(result, "trade_id")
    assert hasattr(result, "outcome")
    assert hasattr(result, "pattern")
    assert hasattr(result, "hypothesis")
    assert hasattr(result, "param_delta")

    assert isinstance(result.trade_id, str)
    assert isinstance(result.outcome, str)
    assert isinstance(result.pattern, str)
    assert isinstance(result.hypothesis, str)
    assert isinstance(result.param_delta, dict)


# ---------------------------------------------------------------------------
# Test 8: rsi_oversold_miss — RSI<30 + SHORT + loss
# ---------------------------------------------------------------------------

def test_analyze_rsi_oversold_miss_pattern(agent):
    """RSI<30이었는데 SHORT(Sell)을 들어가 손실 → rsi_oversold_miss."""
    trade = {
        "trade_id": "T-010",
        "direction": "Sell",
        "entry_price": 85000.0,
        "exit_price": 85500.0,
        "pnl_usd": -4.0,
        "hold_seconds": 200,
        "ma_slope_pct": 0.03,
        "funding_rate": 0.0001,
        "rsi": 25.0,   # 매우 oversold → LONG이어야 했는데 SHORT 진입
        "score": 2,
    }
    result = agent.analyze(trade)

    assert result.pattern == "rsi_oversold_miss"
    assert result.outcome == "loss"
    assert "rsi_oversold_threshold" in result.param_delta


# ---------------------------------------------------------------------------
# Test 9: high_score_loss — score>=4 + loss
# ---------------------------------------------------------------------------

def test_analyze_high_score_loss_pattern(agent):
    """signal score >= 4인데 손실 → high_score_loss."""
    trade = {
        "trade_id": "T-011",
        "direction": "Buy",
        "entry_price": 85000.0,
        "exit_price": 84200.0,
        "pnl_usd": -8.0,
        "hold_seconds": 150,
        "ma_slope_pct": 0.3,
        "funding_rate": 0.0001,
        "rsi": 55.0,
        "score": 5,    # 고점수인데 손실
    }
    result = agent.analyze(trade)

    assert result.pattern == "high_score_loss"
    assert result.outcome == "loss"
    assert len(result.hypothesis) > 0


# ---------------------------------------------------------------------------
# Test 10: low_score_win — score<3 + win
# ---------------------------------------------------------------------------

def test_analyze_low_score_win_pattern(agent):
    """signal score <= 2인데 수익 → low_score_win."""
    trade = {
        "trade_id": "T-012",
        "direction": "Buy",
        "entry_price": 85000.0,
        "exit_price": 85600.0,
        "pnl_usd": 5.0,
        "hold_seconds": 400,
        "ma_slope_pct": 0.08,
        "funding_rate": 0.0001,
        "rsi": 45.0,
        "score": 2,    # 저점수인데 수익
    }
    result = agent.analyze(trade)

    assert result.pattern == "low_score_win"
    assert result.outcome == "win"
    assert "ma_slope_weight" in result.param_delta


# ---------------------------------------------------------------------------
# Test 11: high_score_loss 3회 연속 → score_threshold +1
# ---------------------------------------------------------------------------

def test_high_score_loss_streak_triggers_score_threshold_increase():
    """high_score_loss 3회 연속 발생 → score_threshold +1 제안."""
    fresh_agent = ReflectionAgent()

    high_score_loss_trade = {
        "trade_id": "T-020",
        "direction": "Buy",
        "entry_price": 85000.0,
        "exit_price": 84000.0,
        "pnl_usd": -7.0,
        "hold_seconds": 120,
        "ma_slope_pct": 0.2,
        "funding_rate": 0.0001,
        "rsi": 55.0,
        "score": 5,
    }

    # 3회 연속 분석
    for _ in range(3):
        result = fresh_agent.analyze(high_score_loss_trade)

    # 3회째에 score_threshold 조정 제안
    assert result.pattern == "high_score_loss"
    assert "score_threshold" in result.param_delta
    assert result.param_delta["score_threshold"] == "+1"


# ---------------------------------------------------------------------------
# Test 12: streak resets on different pattern
# ---------------------------------------------------------------------------

def test_high_score_loss_streak_resets_on_win():
    """high_score_loss 2회 후 win이 오면 streak 초기화."""
    fresh_agent = ReflectionAgent()

    high_score_loss_trade = {
        "trade_id": "T-030",
        "direction": "Buy",
        "entry_price": 85000.0,
        "exit_price": 84000.0,
        "pnl_usd": -7.0,
        "hold_seconds": 120,
        "ma_slope_pct": 0.2,
        "funding_rate": 0.0001,
        "rsi": 55.0,
        "score": 5,
    }
    win_trade = {
        "trade_id": "T-031",
        "direction": "Buy",
        "entry_price": 85000.0,
        "exit_price": 86000.0,
        "pnl_usd": 10.0,
        "hold_seconds": 600,
        "ma_slope_pct": 0.6,
        "funding_rate": 0.0001,
    }

    fresh_agent.analyze(high_score_loss_trade)
    fresh_agent.analyze(high_score_loss_trade)
    assert fresh_agent.high_score_loss_streak == 2

    fresh_agent.analyze(win_trade)
    assert fresh_agent.high_score_loss_streak == 0

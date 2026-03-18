"""TDD RED — ReflectionAgent unit tests.

Tests for S7 post-trade reflection analysis:
- Pattern classification (regime_mismatch, good_entry, threshold_too_high/low)
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

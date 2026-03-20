"""
tests/unit/test_kelly_sizer.py
TDD RED → GREEN: Kelly Criterion position sizing

Coverage:
1. Normal Kelly calculation (positive fraction)
2. Negative Kelly → minimum fraction (0.05)
3. Low win_rate fallback (< 0.1)
4. Normal win_rate with enough data → kelly mode
5. Max fraction cap (25%)
6. KellyResult immutability
7. Edge case: avg_loss_usd = 0
8. KellyResult schema validation
"""

import pytest
from application.kelly_sizer import KellyParams, KellyResult, calculate_kelly


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def normal_params():
    """Reasonable win_rate and payoff — should yield positive Kelly."""
    return KellyParams(
        win_rate=0.55,
        avg_win_usd=10.0,
        avg_loss_usd=8.0,
        equity_usdt=139.0,
    )


@pytest.fixture
def losing_params():
    """Win rate below breakeven — Kelly goes negative."""
    return KellyParams(
        win_rate=0.30,
        avg_win_usd=5.0,
        avg_loss_usd=10.0,
        equity_usdt=139.0,
    )


@pytest.fixture
def low_winrate_params():
    """Win rate < 0.1 → fallback mode."""
    return KellyParams(
        win_rate=0.05,
        avg_win_usd=20.0,
        avg_loss_usd=5.0,
        equity_usdt=200.0,
    )


@pytest.fixture
def high_kelly_params():
    """Very high Kelly fraction — should be capped at max_fraction."""
    return KellyParams(
        win_rate=0.90,
        avg_win_usd=50.0,
        avg_loss_usd=5.0,
        equity_usdt=500.0,
        max_fraction=0.25,
    )


# ---------------------------------------------------------------------------
# Test 1: Normal Kelly calculation returns positive fraction
# ---------------------------------------------------------------------------

def test_calculate_kelly_normal_returns_positive_fraction(normal_params):
    """Kelly formula: f = (p*b - q) / b, b = avg_win/avg_loss."""
    result = calculate_kelly(normal_params)

    assert isinstance(result, KellyResult)
    assert result.fraction > 0
    assert result.mode == "kelly"


# ---------------------------------------------------------------------------
# Test 2: Negative Kelly → minimum fraction 0.05
# ---------------------------------------------------------------------------

def test_calculate_kelly_negative_returns_minimum(losing_params):
    """Win rate below breakeven → Kelly is negative → use minimum 0.05."""
    result = calculate_kelly(losing_params)

    assert result.fraction == 0.05
    assert result.mode == "fallback"


# ---------------------------------------------------------------------------
# Test 3: Low win_rate (< 0.1) → fallback
# ---------------------------------------------------------------------------

def test_calculate_kelly_low_winrate_fallback(low_winrate_params):
    """Win rate < 0.1 → insufficient data → fallback mode, fraction=0.1."""
    result = calculate_kelly(low_winrate_params)

    assert result.fraction == 0.1
    assert result.mode == "fallback"


# ---------------------------------------------------------------------------
# Test 4: Normal win_rate → kelly mode
# ---------------------------------------------------------------------------

def test_calculate_kelly_normal_winrate_uses_kelly_mode(normal_params):
    """Win rate >= 0.1 → use Kelly formula → mode='kelly'."""
    result = calculate_kelly(normal_params)

    assert result.mode == "kelly"


# ---------------------------------------------------------------------------
# Test 5: Kelly fraction capped at max_fraction
# ---------------------------------------------------------------------------

def test_calculate_kelly_capped_at_max_fraction(high_kelly_params):
    """Very favorable odds → raw Kelly > max_fraction → cap at 0.25."""
    result = calculate_kelly(high_kelly_params)

    assert result.fraction <= high_kelly_params.max_fraction
    assert result.mode == "kelly"


# ---------------------------------------------------------------------------
# Test 6: position_usdt = equity * fraction
# ---------------------------------------------------------------------------

def test_calculate_kelly_position_usdt_equals_equity_times_fraction(normal_params):
    """position_usdt must equal equity_usdt * fraction."""
    result = calculate_kelly(normal_params)

    expected_position = normal_params.equity_usdt * result.fraction
    assert abs(result.position_usdt - expected_position) < 1e-9


# ---------------------------------------------------------------------------
# Test 7: KellyResult immutability (frozen dataclass)
# ---------------------------------------------------------------------------

def test_kelly_result_is_immutable(normal_params):
    """KellyResult frozen=True → attribute assignment raises FrozenInstanceError."""
    result = calculate_kelly(normal_params)

    with pytest.raises((AttributeError, TypeError)):
        result.fraction = 0.99  # type: ignore


# ---------------------------------------------------------------------------
# Test 8: KellyResult schema validation
# ---------------------------------------------------------------------------

def test_kelly_result_schema(normal_params):
    """KellyResult has all required fields with correct types."""
    result = calculate_kelly(normal_params)

    assert hasattr(result, "fraction")
    assert hasattr(result, "position_usdt")
    assert hasattr(result, "mode")

    assert isinstance(result.fraction, float)
    assert isinstance(result.position_usdt, float)
    assert isinstance(result.mode, str)
    assert result.mode in ("kelly", "fallback")


# ---------------------------------------------------------------------------
# Test 9: avg_loss_usd = 0 → fallback (division by zero protection)
# ---------------------------------------------------------------------------

def test_calculate_kelly_zero_avg_loss_fallback():
    """avg_loss_usd = 0 → can't compute Kelly ratio → fallback."""
    params = KellyParams(
        win_rate=0.6,
        avg_win_usd=10.0,
        avg_loss_usd=0.0,
        equity_usdt=150.0,
    )

    result = calculate_kelly(params)

    assert result.mode == "fallback"
    assert result.fraction >= 0.05


# ---------------------------------------------------------------------------
# Test 10: Correct Kelly formula value
# ---------------------------------------------------------------------------

def test_calculate_kelly_formula_value():
    """Verify Kelly formula: p=0.6, b=2.0 → f = (0.6*2 - 0.4)/2 = 0.4."""
    params = KellyParams(
        win_rate=0.6,
        avg_win_usd=20.0,
        avg_loss_usd=10.0,
        equity_usdt=100.0,
        max_fraction=0.5,  # high cap to verify raw formula
    )

    result = calculate_kelly(params)

    # b = 20/10 = 2.0
    # f = (0.6*2 - 0.4) / 2 = (1.2 - 0.4) / 2 = 0.8 / 2 = 0.4
    assert result.mode == "kelly"
    assert abs(result.fraction - 0.4) < 1e-9

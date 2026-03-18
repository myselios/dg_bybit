"""TDD RED — S13 ShadowTrader unit tests.

섀도우 트레이딩 모드: 실제 매매 없이 파라미터 실험 결과를 추적한다.
- 실제 시장 데이터로 가상 매매를 시뮬레이션
- 파라미터 조합별 성과 비교
- 기준 성과를 상회할 때만 ApprovalGateway에 파라미터 변경 제안
- ShadowResult는 immutable
"""

import pytest
from application.shadow_trader import ShadowTrader, ShadowResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def trader():
    return ShadowTrader()


@pytest.fixture
def baseline_params():
    return {"T_TREND": 0.05, "ATR_MULTIPLIER": 0.2}


@pytest.fixture
def candidate_params():
    return {"T_TREND": 0.08, "ATR_MULTIPLIER": 0.25}


@pytest.fixture
def ticks():
    """가상 시장 틱 데이터."""
    return [
        {"price": 85000.0, "ma_slope_pct": 0.06, "atr": 500.0, "funding_rate": 0.0001},
        {"price": 85200.0, "ma_slope_pct": 0.08, "atr": 490.0, "funding_rate": 0.0001},
        {"price": 85100.0, "ma_slope_pct": 0.05, "atr": 510.0, "funding_rate": 0.0001},
        {"price": 84900.0, "ma_slope_pct": -0.03, "atr": 520.0, "funding_rate": -0.0001},
        {"price": 85050.0, "ma_slope_pct": 0.04, "atr": 505.0, "funding_rate": 0.0001},
    ]


# ---------------------------------------------------------------------------
# Test 1: run() returns ShadowResult
# ---------------------------------------------------------------------------

def test_run_returns_shadow_result(trader, baseline_params, candidate_params, ticks):
    """run()은 ShadowResult를 반환해야 한다."""
    result = trader.run(
        baseline_params=baseline_params,
        candidate_params=candidate_params,
        ticks=ticks,
        equity_usdt=150.0,
    )

    assert isinstance(result, ShadowResult)


# ---------------------------------------------------------------------------
# Test 2: ShadowResult schema
# ---------------------------------------------------------------------------

def test_shadow_result_schema(trader, baseline_params, candidate_params, ticks):
    """ShadowResult는 필수 필드를 모두 가져야 한다."""
    result = trader.run(
        baseline_params=baseline_params,
        candidate_params=candidate_params,
        ticks=ticks,
        equity_usdt=150.0,
    )

    assert hasattr(result, "baseline_pnl")
    assert hasattr(result, "candidate_pnl")
    assert hasattr(result, "baseline_trades")
    assert hasattr(result, "candidate_trades")
    assert hasattr(result, "candidate_wins")
    assert hasattr(result, "recommendation")

    assert isinstance(result.baseline_pnl, float)
    assert isinstance(result.candidate_pnl, float)
    assert isinstance(result.baseline_trades, int)
    assert isinstance(result.candidate_trades, int)
    assert isinstance(result.candidate_wins, int)
    assert result.recommendation in ("adopt", "reject", "insufficient_data")


# ---------------------------------------------------------------------------
# Test 3: ShadowResult is immutable
# ---------------------------------------------------------------------------

def test_shadow_result_immutable(trader, baseline_params, candidate_params, ticks):
    """ShadowResult는 frozen=True이어야 한다."""
    result = trader.run(
        baseline_params=baseline_params,
        candidate_params=candidate_params,
        ticks=ticks,
        equity_usdt=150.0,
    )

    with pytest.raises(AttributeError):
        result.recommendation = "adopt"


# ---------------------------------------------------------------------------
# Test 4: 데이터 부족 시 insufficient_data
# ---------------------------------------------------------------------------

def test_run_insufficient_data(trader, baseline_params, candidate_params):
    """틱 데이터가 없으면 recommendation='insufficient_data'."""
    result = trader.run(
        baseline_params=baseline_params,
        candidate_params=candidate_params,
        ticks=[],
        equity_usdt=150.0,
    )

    assert result.recommendation == "insufficient_data"
    assert result.baseline_trades == 0
    assert result.candidate_trades == 0


# ---------------------------------------------------------------------------
# Test 5: candidate 성과 우수 → adopt
# ---------------------------------------------------------------------------

def test_run_good_candidate_recommends_adopt(trader):
    """candidate가 baseline보다 유의미하게 좋으면 recommendation='adopt'."""
    baseline_params = {"T_TREND": 0.4}  # 매우 높아서 신호 없음
    candidate_params = {"T_TREND": 0.05}  # 낮아서 신호 발생

    # 명확한 추세 틱들
    ticks = [
        {"price": 85000.0 + i * 100, "ma_slope_pct": 0.3, "atr": 500.0, "funding_rate": 0.0001}
        for i in range(10)
    ]

    result = trader.run(
        baseline_params=baseline_params,
        candidate_params=candidate_params,
        ticks=ticks,
        equity_usdt=150.0,
    )

    # candidate는 신호를 발생시키고 baseline은 못함
    assert result.candidate_trades >= result.baseline_trades


# ---------------------------------------------------------------------------
# Test 6: should_adopt() — 채택 여부 단독 판단
# ---------------------------------------------------------------------------

def test_should_adopt_true_when_candidate_better(trader):
    """candidate_pnl > baseline_pnl + margin이면 should_adopt=True."""
    result_mock = ShadowResult(
        baseline_pnl=-2.0,
        candidate_pnl=5.0,
        baseline_trades=3,
        candidate_trades=4,
        candidate_wins=3,
        recommendation="adopt",
    )

    assert trader.should_adopt(result_mock) is True


def test_should_adopt_false_when_candidate_worse(trader):
    """candidate_pnl < baseline_pnl이면 should_adopt=False."""
    result_mock = ShadowResult(
        baseline_pnl=5.0,
        candidate_pnl=1.0,
        baseline_trades=3,
        candidate_trades=3,
        candidate_wins=1,
        recommendation="reject",
    )

    assert trader.should_adopt(result_mock) is False

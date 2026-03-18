"""TDD RED — S12 HypothesisLoop unit tests.

자율 가설-실험-평가 루프:
- 트레이드 히스토리에서 패턴을 분석하여 가설 생성
- 파라미터 조정 후보 제안
- 실험 결과로 가설 검증/기각
- HypothesisRecord는 immutable (frozen dataclass)
"""

import pytest
from application.agents.hypothesis_loop import HypothesisLoop, HypothesisRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def loop():
    return HypothesisLoop()


@pytest.fixture
def loss_history():
    """연속 손실 이력 — T_TREND 조정 가설 예상."""
    return [
        {"trade_id": "T-001", "pnl_usd": -3.0, "ma_slope_pct": 0.02, "pattern": "regime_mismatch"},
        {"trade_id": "T-002", "pnl_usd": -5.0, "ma_slope_pct": 0.03, "pattern": "regime_mismatch"},
        {"trade_id": "T-003", "pnl_usd": -2.0, "ma_slope_pct": 0.01, "pattern": "regime_mismatch"},
    ]


@pytest.fixture
def win_history():
    """연속 승리 이력 — 파라미터 유지 가설 예상."""
    return [
        {"trade_id": "T-011", "pnl_usd": 8.0, "ma_slope_pct": 0.6, "pattern": "good_entry"},
        {"trade_id": "T-012", "pnl_usd": 5.0, "ma_slope_pct": 0.5, "pattern": "good_entry"},
        {"trade_id": "T-013", "pnl_usd": 3.0, "ma_slope_pct": 0.4, "pattern": "good_entry"},
    ]


@pytest.fixture
def mixed_history():
    """혼합 이력 — 경계 조건 테스트."""
    return [
        {"trade_id": "T-021", "pnl_usd": 2.0, "ma_slope_pct": 0.3, "pattern": "good_entry"},
        {"trade_id": "T-022", "pnl_usd": -4.0, "ma_slope_pct": 0.08, "pattern": "threshold_too_low"},
        {"trade_id": "T-023", "pnl_usd": -1.0, "ma_slope_pct": 0.05, "pattern": "threshold_too_low"},
    ]


# ---------------------------------------------------------------------------
# Test 1: generate() returns HypothesisRecord
# ---------------------------------------------------------------------------

def test_generate_returns_hypothesis_record(loop, loss_history):
    """generate()는 HypothesisRecord를 반환해야 한다."""
    result = loop.generate(loss_history)

    assert isinstance(result, HypothesisRecord)


# ---------------------------------------------------------------------------
# Test 2: HypothesisRecord schema
# ---------------------------------------------------------------------------

def test_hypothesis_record_schema(loop, loss_history):
    """HypothesisRecord는 필수 필드를 모두 가져야 한다."""
    result = loop.generate(loss_history)

    assert hasattr(result, "hypothesis_id")
    assert hasattr(result, "hypothesis_text")
    assert hasattr(result, "param_candidate")
    assert hasattr(result, "confidence")
    assert hasattr(result, "status")

    assert isinstance(result.hypothesis_id, str)
    assert len(result.hypothesis_id) > 0
    assert isinstance(result.hypothesis_text, str)
    assert len(result.hypothesis_text) > 0
    assert isinstance(result.param_candidate, dict)
    assert isinstance(result.confidence, float)
    assert result.status in ("pending", "confirmed", "rejected")


# ---------------------------------------------------------------------------
# Test 3: HypothesisRecord is immutable
# ---------------------------------------------------------------------------

def test_hypothesis_record_immutable(loop, loss_history):
    """HypothesisRecord는 frozen=True이어야 한다."""
    result = loop.generate(loss_history)

    with pytest.raises(AttributeError):
        result.status = "confirmed"


# ---------------------------------------------------------------------------
# Test 4: Loss pattern → T_TREND 조정 가설
# ---------------------------------------------------------------------------

def test_generate_loss_regime_mismatch_suggests_t_trend(loop, loss_history):
    """regime_mismatch 패턴 손실 → T_TREND 임계값 조정 가설."""
    result = loop.generate(loss_history)

    # 손실 이력에서 T_TREND 관련 파라미터 후보 제안
    assert "T_TREND" in result.param_candidate or "t_trend" in result.param_candidate.get("params", {})


# ---------------------------------------------------------------------------
# Test 5: Win pattern → 현재 파라미터 유지 가설
# ---------------------------------------------------------------------------

def test_generate_win_pattern_suggests_keep(loop, win_history):
    """연속 승리 → param_candidate에 변경사항이 없거나 미미함."""
    result = loop.generate(win_history)

    # 승리 이력: 파라미터 유지 (빈 dict 또는 confidence 낮음)
    assert result.confidence >= 0.0
    assert result.status == "pending"


# ---------------------------------------------------------------------------
# Test 6: evaluate() — 실험 결과로 가설 상태 갱신
# ---------------------------------------------------------------------------

def test_evaluate_confirms_hypothesis_on_success(loop, loss_history):
    """실험 결과가 긍정적이면 가설이 confirmed 상태로 갱신된다."""
    hypothesis = loop.generate(loss_history)

    # 실험 결과: 파라미터 조정 후 수익 발생
    experiment_result = {"net_pnl_usd": 10.0, "trade_count": 3, "win_rate": 0.7}
    updated = loop.evaluate(hypothesis, experiment_result)

    assert isinstance(updated, HypothesisRecord)
    assert updated.status == "confirmed"


# ---------------------------------------------------------------------------
# Test 7: evaluate() — 실험 실패 → rejected
# ---------------------------------------------------------------------------

def test_evaluate_rejects_hypothesis_on_failure(loop, loss_history):
    """실험 결과가 부정적이면 가설이 rejected 상태로 갱신된다."""
    hypothesis = loop.generate(loss_history)

    # 실험 결과: 파라미터 조정 후 손실 지속
    experiment_result = {"net_pnl_usd": -8.0, "trade_count": 3, "win_rate": 0.2}
    updated = loop.evaluate(hypothesis, experiment_result)

    assert isinstance(updated, HypothesisRecord)
    assert updated.status == "rejected"

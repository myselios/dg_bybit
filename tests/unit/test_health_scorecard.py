"""
tests/unit/test_health_scorecard.py

S8: HealthScorecard TDD RED — 실패하는 테스트 7개

등급 기준:
- A: signal_rate>5/h AND win_rate>0.5 AND consecutive_losses<3
- B: signal_rate>2/h AND win_rate>0.4
- C: signal_rate>0/h (진입은 하고 있음)
- D: signal_rate==0/h AND uptime>0 (살아있지만 진입 없음)
- F: 완전 비정상 (uptime==0 등)
"""

import pytest
from dataclasses import FrozenInstanceError

from src.application.health_scorecard import HealthScorecard, HealthScore


# ---------- 1. D등급: 신호 0건이지만 봇 살아있음 ----------
def test_zero_signal_rate_is_D_grade():
    """signal_count_1h=0, uptime>0 -> D등급"""
    # Arrange
    scorecard = HealthScorecard()

    # Act
    result = scorecard.score(
        signal_count_1h=0,
        win_rate=0.0,
        consecutive_losses=0,
        uptime_pct=0.95,
    )

    # Assert
    assert result.grade == "D"
    assert result.signal_rate == 0.0


# ---------- 2. F등급: 봇 다운 ----------
def test_zero_uptime_is_F_grade():
    """uptime_pct=0.0 -> F등급"""
    # Arrange
    scorecard = HealthScorecard()

    # Act
    result = scorecard.score(
        signal_count_1h=0,
        win_rate=0.0,
        consecutive_losses=0,
        uptime_pct=0.0,
    )

    # Assert
    assert result.grade == "F"
    assert result.score == 0.0


# ---------- 3. A등급: 좋은 성과 ----------
def test_good_performance_is_A_grade():
    """signal_count_1h=10, win_rate=0.6, consecutive_losses=1 -> A등급"""
    # Arrange
    scorecard = HealthScorecard()

    # Act
    result = scorecard.score(
        signal_count_1h=10,
        win_rate=0.6,
        consecutive_losses=1,
    )

    # Assert
    assert result.grade == "A"
    assert result.signal_rate == 10.0
    assert result.win_rate == 0.6
    assert result.score >= 80.0


# ---------- 4. B등급: 보통 성과 ----------
def test_moderate_performance_is_B_grade():
    """signal_count_1h=3, win_rate=0.45 -> B등급"""
    # Arrange
    scorecard = HealthScorecard()

    # Act
    result = scorecard.score(
        signal_count_1h=3,
        win_rate=0.45,
        consecutive_losses=2,
    )

    # Assert
    assert result.grade == "B"
    assert result.signal_rate == 3.0
    assert result.win_rate == 0.45


# ---------- 5. 연속손실 다운그레이드 ----------
def test_consecutive_losses_downgrades():
    """
    signal_rate>5, win_rate>0.5이지만 consecutive_losses=5
    -> A 조건 불충족(consecutive_losses>=3), B 이하로 다운그레이드
    """
    # Arrange
    scorecard = HealthScorecard()

    # Act
    result = scorecard.score(
        signal_count_1h=10,
        win_rate=0.55,
        consecutive_losses=5,
    )

    # Assert
    assert result.grade != "A"
    assert result.consecutive_losses == 5
    assert result.grade in ("B", "C")


# ---------- 6. D등급 CRITICAL 알림 ----------
def test_zero_signal_alert_message():
    """D등급일 때 CRITICAL 알림이 alerts에 포함"""
    # Arrange
    scorecard = HealthScorecard()

    # Act
    result = scorecard.score(
        signal_count_1h=0,
        win_rate=0.0,
        consecutive_losses=0,
        uptime_pct=0.9,
    )

    # Assert
    assert result.grade == "D"
    assert len(result.alerts) >= 1
    assert any("CRITICAL" in alert or "signal" in alert.lower() for alert in result.alerts)


# ---------- 7. HealthScore 불변성 ----------
def test_health_score_immutable():
    """HealthScore는 frozen dataclass - 속성 변경 시 에러"""
    # Arrange
    health = HealthScore(
        grade="A",
        score=90.0,
        signal_rate=10.0,
        win_rate=0.6,
        consecutive_losses=0,
        alerts=[],
    )

    # Act & Assert
    with pytest.raises(FrozenInstanceError):
        health.grade = "F"

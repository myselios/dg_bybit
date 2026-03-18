"""
tests/unit/test_approval_gateway.py

S10: ApprovalGateway TDD RED 테스트
모든 테스트는 아직 구현체가 없으므로 ImportError로 실패해야 한다.
"""

import pytest
from application.agents.approval_gateway import (
    ApprovalGateway,
    ChangeType,
    ParamChange,
)


# ── 헬퍼 ──────────────────────────────────────────────

def _make_t_trend_change(old: float, new: float) -> ParamChange:
    """T_TREND 파라미터 변경 픽스처"""
    return ParamChange(param_name="T_TREND", old_value=old, new_value=new)


# ── 1) Minor 변경 → 자동승인 ─────────────────────────

def test_auto_approve_minor_t_trend_change():
    # Arrange — 30% 변경 (0.5 → 0.65)
    gw = ApprovalGateway()
    change = _make_t_trend_change(old=0.5, new=0.65)

    # Act
    result = gw.auto_approve(change)

    # Assert — Minor이므로 자동승인
    assert result is True


# ── 2) Major 변경 → 승인 거부 ────────────────────────

def test_auto_approve_major_t_trend_change():
    # Arrange — 60% 변경 (0.5 → 0.8)
    gw = ApprovalGateway()
    change = _make_t_trend_change(old=0.5, new=0.8)

    # Act
    result = gw.auto_approve(change)

    # Assert — Major이므로 자동승인 거부
    assert result is False


# ── 3) classify Minor ────────────────────────────────

def test_classify_minor_change():
    # Arrange — 30% 변경
    gw = ApprovalGateway()
    change = _make_t_trend_change(old=0.5, new=0.65)

    # Act
    result = gw.classify_change(change)

    # Assert
    assert result == ChangeType.MINOR


# ── 4) classify Major ────────────────────────────────

def test_classify_major_change():
    # Arrange — 60% 변경
    gw = ApprovalGateway()
    change = _make_t_trend_change(old=0.5, new=0.8)

    # Act
    result = gw.classify_change(change)

    # Assert
    assert result == ChangeType.MAJOR


# ── 5) TELEGRAM_BOT_TOKEN 없어도 auto_approve 동작 ──

def test_auto_approve_no_telegram_env_falls_back(monkeypatch):
    # Arrange — 환경변수 제거
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    gw = ApprovalGateway()
    change = _make_t_trend_change(old=0.5, new=0.65)

    # Act
    result = gw.auto_approve(change)

    # Assert — Minor이므로 Telegram 없이도 자동승인
    assert result is True


# ── 6) ParamChange frozen (불변) ─────────────────────

def test_param_change_immutable():
    # Arrange
    change = ParamChange(param_name="T_TREND", old_value=0.5, new_value=0.65)

    # Act & Assert — frozen dataclass 변경 시도 시 에러
    with pytest.raises(AttributeError):
        change.new_value = 9.99

    assert change.new_value == 0.65

"""
tests/unit/test_drawdown_recovery.py

DrawdownRecovery 단위 테스트 (TDD RED-GREEN-REFACTOR)

목적:
  - 일일 손실 50% 초과 시 포지션 크기 30% 축소 검증
  - 일일 손실 80% 초과 시 당일 트레이딩 HALT 검증
  - 정상 상태(손실 없음, 50% 미만) 시 NORMAL 반환 검증
  - 다음날 0시 자동 복구 검증

실행:
  pytest tests/unit/test_drawdown_recovery.py -v
"""

from application.drawdown_recovery import (
    DrawdownState,
    check_drawdown_recovery,
)


# ============================================================
# helpers
# ============================================================

def _check(
    daily_loss_usd: float,
    max_loss_usd: float,
    last_reset_date: str = "2026-03-23",
    today: str = "2026-03-23",
) -> DrawdownState:
    return check_drawdown_recovery(
        daily_loss_usd=daily_loss_usd,
        max_loss_usd=max_loss_usd,
        last_reset_date=last_reset_date,
        today=today,
    )


# ============================================================
# (1) NORMAL — 손실 없음
# ============================================================

def test_no_loss_returns_normal():
    """손실 0 → NORMAL, size_multiplier=1.0."""
    state = _check(daily_loss_usd=0.0, max_loss_usd=15.0)

    assert state.status == "NORMAL"
    assert state.size_multiplier == 1.0


def test_small_loss_below_50pct_returns_normal():
    """daily_loss < 50% of max_loss → NORMAL."""
    # max_loss=15, 50% = 7.5 → loss=7.0 (46.7%) → NORMAL
    state = _check(daily_loss_usd=7.0, max_loss_usd=15.0)

    assert state.status == "NORMAL"
    assert state.size_multiplier == 1.0


# ============================================================
# (2) REDUCE — 손실 50%~80%
# ============================================================

def test_loss_exactly_50pct_triggers_reduce():
    """daily_loss == 50% of max_loss → REDUCE, size_multiplier=0.7."""
    state = _check(daily_loss_usd=7.5, max_loss_usd=15.0)

    assert state.status == "REDUCE"
    assert state.size_multiplier == 0.7


def test_loss_75pct_triggers_reduce():
    """daily_loss 75% → REDUCE, size_multiplier=0.7."""
    state = _check(daily_loss_usd=11.25, max_loss_usd=15.0)

    assert state.status == "REDUCE"
    assert state.size_multiplier == 0.7


def test_loss_just_below_80pct_triggers_reduce():
    """daily_loss 79.9% → 여전히 REDUCE (80% 미만)."""
    state = _check(daily_loss_usd=11.985, max_loss_usd=15.0)

    assert state.status == "REDUCE"
    assert state.size_multiplier == 0.7


# ============================================================
# (3) HALT — 손실 80% 이상
# ============================================================

def test_loss_exactly_80pct_triggers_halt():
    """daily_loss == 80% of max_loss → HALT."""
    state = _check(daily_loss_usd=12.0, max_loss_usd=15.0)

    assert state.status == "HALT"
    assert state.size_multiplier == 0.0


def test_loss_100pct_triggers_halt():
    """daily_loss == max_loss (100%) → HALT."""
    state = _check(daily_loss_usd=15.0, max_loss_usd=15.0)

    assert state.status == "HALT"
    assert state.size_multiplier == 0.0


def test_loss_exceeds_max_triggers_halt():
    """daily_loss > max_loss → HALT (초과 손실)."""
    state = _check(daily_loss_usd=20.0, max_loss_usd=15.0)

    assert state.status == "HALT"
    assert state.size_multiplier == 0.0


# ============================================================
# (4) 날짜 초기화 — 다음날 0시 복구
# ============================================================

def test_next_day_resets_halt_to_normal():
    """이전 날 HALT였어도 다음 날 → NORMAL (일일 손실 0 가정)."""
    # 어제 HALT 기준 손실이 있었지만, today가 달라서 daily_loss=0으로 전달됨
    state = _check(
        daily_loss_usd=0.0,
        max_loss_usd=15.0,
        last_reset_date="2026-03-22",
        today="2026-03-23",
    )

    assert state.status == "NORMAL"
    assert state.size_multiplier == 1.0
    assert state.reset_occurred is True


def test_same_day_no_reset():
    """같은 날이면 reset_occurred=False."""
    state = _check(
        daily_loss_usd=0.0,
        max_loss_usd=15.0,
        last_reset_date="2026-03-23",
        today="2026-03-23",
    )

    assert state.reset_occurred is False


# ============================================================
# (5) halt_reason 메시지 검증
# ============================================================

def test_halt_has_reason():
    """HALT 상태에는 halt_reason이 있어야 한다."""
    state = _check(daily_loss_usd=12.0, max_loss_usd=15.0)

    assert state.status == "HALT"
    assert state.halt_reason is not None
    assert len(state.halt_reason) > 0


def test_reduce_has_reason():
    """REDUCE 상태에도 이유가 있어야 한다."""
    state = _check(daily_loss_usd=7.5, max_loss_usd=15.0)

    assert state.status == "REDUCE"
    assert state.halt_reason is not None


def test_normal_no_halt_reason():
    """NORMAL 상태에는 halt_reason이 None이어야 한다."""
    state = _check(daily_loss_usd=0.0, max_loss_usd=15.0)

    assert state.status == "NORMAL"
    assert state.halt_reason is None


# ============================================================
# (6) max_loss_usd=0 방어 (ZeroDivision)
# ============================================================

def test_zero_max_loss_returns_halt():
    """max_loss_usd=0 → 방어적으로 HALT 반환 (ZeroDivision 방지)."""
    state = _check(daily_loss_usd=0.0, max_loss_usd=0.0)

    assert state.status == "HALT"
    assert state.size_multiplier == 0.0

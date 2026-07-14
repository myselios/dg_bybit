"""
src/application/drawdown_recovery.py

Drawdown Recovery 모듈 — Wave 5 Stream C

목적:
  일일 손실이 max_loss 대비 특정 비율 초과 시 포지션 크기 축소 또는 당일 거래 중단.

로직:
  - 일일 손실 < 50%  → NORMAL  (size_multiplier=1.0)
  - 일일 손실 ≥ 50%  → REDUCE  (size_multiplier=0.7, 30% 축소)
  - 일일 손실 ≥ 80%  → HALT    (size_multiplier=0.0, 당일 거래 중단)
  - 다음 날 0시 자동 복구 (reset_occurred=True)

설계 원칙:
  - Pure function — I/O 없음, 상태 변이 없음
  - 불변 dataclass 반환 (frozen=True)
  - ZeroDivision 방어 (max_loss_usd=0 → HALT)

연계:
  - orchestrator.py: check_drawdown_recovery() 호출 후 size_multiplier를
    build_sizing_params() 의 max_loss_usdt에 곱해 포지션 크기 조정
  - emergency_checker.py: HALT 시 check_emergency_status()와 독립적으로 동작
    (기존 daily_loss_cap과 별개 — recovery는 진입 크기 제어, emergency는 전면 중단)
"""

from dataclasses import dataclass
from typing import Optional

# ── 임계값 상수 ─────────────────────────────────────────────────────────────
_REDUCE_THRESHOLD = 0.50   # 50%: 포지션 크기 30% 축소
_HALT_THRESHOLD = 0.80     # 80%: 당일 거래 중단
_REDUCE_MULTIPLIER = 0.70  # 축소 배율 (70% = 30% 감소)


@dataclass(frozen=True)
class DrawdownState:
    """Drawdown Recovery 상태.

    Attributes:
        status: "NORMAL" | "REDUCE" | "HALT"
        size_multiplier: 포지션 크기 배율 (0.0~1.0)
            - NORMAL=1.0, REDUCE=0.7, HALT=0.0
        halt_reason: 상태 설명 문자열 (NORMAL은 None)
        reset_occurred: 다음 날 날짜 변경으로 인해 초기화 발생 여부
    """

    status: str
    size_multiplier: float
    halt_reason: Optional[str]
    reset_occurred: bool


def check_drawdown_recovery(
    daily_loss_usd: float,
    max_loss_usd: float,
    last_reset_date: str,
    today: str,
) -> DrawdownState:
    """Drawdown Recovery 상태 계산 (pure function).

    Args:
        daily_loss_usd: 당일 실현 손실 (양수 = 손실, USD)
        max_loss_usd: 최대 허용 손실 (USD, Stage별 설정값)
        last_reset_date: 마지막 초기화 날짜 ("YYYY-MM-DD")
        today: 오늘 날짜 ("YYYY-MM-DD")

    Returns:
        DrawdownState: 상태, 포지션 크기 배율, 이유, 초기화 여부

    Examples:
        >>> check_drawdown_recovery(0.0, 15.0, "2026-03-23", "2026-03-23")
        DrawdownState(status='NORMAL', size_multiplier=1.0, ...)

        >>> check_drawdown_recovery(7.5, 15.0, "2026-03-23", "2026-03-23")
        DrawdownState(status='REDUCE', size_multiplier=0.7, ...)

        >>> check_drawdown_recovery(12.0, 15.0, "2026-03-23", "2026-03-23")
        DrawdownState(status='HALT', size_multiplier=0.0, ...)
    """
    # (1) 날짜 초기화 감지
    reset_occurred = last_reset_date != today

    # (2) max_loss_usd=0 방어 (ZeroDivision)
    if max_loss_usd <= 0.0:
        return DrawdownState(
            status="HALT",
            size_multiplier=0.0,
            halt_reason="max_loss_usd=0: invalid configuration",
            reset_occurred=reset_occurred,
        )

    # (3) 손실 비율 계산 (양수 손실 기준)
    loss_ratio = daily_loss_usd / max_loss_usd

    # (4) HALT: 80% 이상
    if loss_ratio >= _HALT_THRESHOLD:
        pct = loss_ratio * 100
        return DrawdownState(
            status="HALT",
            size_multiplier=0.0,
            halt_reason=(
                f"daily_loss={daily_loss_usd:.2f} USD ({pct:.1f}% of max_loss={max_loss_usd:.2f}) "
                f"≥ {int(_HALT_THRESHOLD * 100)}% — 당일 거래 중단"
            ),
            reset_occurred=reset_occurred,
        )

    # (5) REDUCE: 50% 이상 80% 미만
    if loss_ratio >= _REDUCE_THRESHOLD:
        pct = loss_ratio * 100
        return DrawdownState(
            status="REDUCE",
            size_multiplier=_REDUCE_MULTIPLIER,
            halt_reason=(
                f"daily_loss={daily_loss_usd:.2f} USD ({pct:.1f}% of max_loss={max_loss_usd:.2f}) "
                f"≥ {int(_REDUCE_THRESHOLD * 100)}% — 포지션 크기 30% 축소"
            ),
            reset_occurred=reset_occurred,
        )

    # (6) NORMAL: 50% 미만
    return DrawdownState(
        status="NORMAL",
        size_multiplier=1.0,
        halt_reason=None,
        reset_occurred=reset_occurred,
    )

"""
Domain Intents — Action Commands from State Transition

FLOW.md 기반 행동 명령 정의 (도메인 계약)

Intent는 순수 전이 함수(transition)의 출력이며,
executor가 I/O로 실행하는 명령어다.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class StopIntent:
    """
    Stop Loss 갱신 의도 (도메인 계약)

    Action:
    - NONE: 갱신 안 함
    - PLACE: Stop 설치 (첫 부분체결)
    - AMEND: Stop 수정 (qty 변경)
    - CANCEL_AND_PLACE: Stop 재설치 (최후 수단)
    """
    action: str  # "NONE" | "PLACE" | "AMEND" | "CANCEL_AND_PLACE"
    desired_qty: Optional[int]
    reason: str


@dataclass
class HaltIntent:
    """
    HALT 의도 (모든 진입 차단)
    """
    reason: str


@dataclass
class CancelOrderIntent:
    """
    주문 취소 의도
    """
    order_id: Optional[str] = None
    order_link_id: Optional[str] = None


@dataclass
class LogIntent:
    """
    로그 기록 의도
    """
    level: str  # "INFO" | "WARNING" | "ERROR"
    code: str
    message: str
    context: Optional[dict] = None


@dataclass
class TransitionIntents:
    """
    State Transition 결과로 발생하는 행동 의도들

    Oracle 테스트는 이 intents를 검증함
    """
    stop_intent: Optional[StopIntent] = None
    halt_intent: Optional[HaltIntent] = None
    cancel_intent: Optional[CancelOrderIntent] = None
    log_intent: Optional[LogIntent] = None
    entry_blocked: bool = False  # HALT/COOLDOWN → 진입 차단

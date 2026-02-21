"""
Domain State Models

FLOW.md Section 1 기반 State Machine 정의
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional

# Re-export events for backward compatibility
from domain.events import EventType, ExecutionEvent

__all__ = [
    'State',
    'StopStatus',
    'Direction',
    'Position',
    'PendingOrder',
    'EventType',
    'ExecutionEvent'
]


class State(Enum):
    """
    Execution State Machine (FLOW Section 1)

    6가지 상태만 존재:
    - FLAT: 포지션 없음, 진입 가능
    - ENTRY_PENDING: Entry 주문 대기 중
    - IN_POSITION: 포지션 오픈 (Stop Loss 유지)
    - EXIT_PENDING: Exit 주문 대기 중
    - HALT: 모든 진입 차단 (Manual reset)
    - COOLDOWN: 일시적 차단 (자동 해제)
    """
    FLAT = "FLAT"
    ENTRY_PENDING = "ENTRY_PENDING"
    IN_POSITION = "IN_POSITION"
    EXIT_PENDING = "EXIT_PENDING"
    HALT = "HALT"
    COOLDOWN = "COOLDOWN"


class StopStatus(Enum):
    """
    Stop Loss 서브상태 (FLOW Section 1)

    IN_POSITION 서브상태로 사용:
    - ACTIVE: Stop 주문 활성 (정상)
    - PENDING: Stop 설치/갱신 중 (일시적)
    - MISSING: Stop 없음 (비정상, 즉시 복구 필요)
    - ERROR: Stop 복구 실패 (HALT 고려)
    """
    ACTIVE = "ACTIVE"
    PENDING = "PENDING"
    MISSING = "MISSING"
    ERROR = "ERROR"


class Direction(Enum):
    """포지션 방향"""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Position:
    """
    포지션 상태

    FLOW Section 1 기준:
    - qty: 포지션 수량 (contracts)
    - entry_price: 진입가
    - direction: LONG or SHORT
    - stop_status: Stop Loss 서브상태
    - entry_working: 잔량 주문 활성 여부 (PARTIAL_FILL)
    """
    qty: int
    entry_price: float
    direction: Direction
    signal_id: str  # 추적용

    # Stop Loss 관련
    stop_status: StopStatus = StopStatus.PENDING
    stop_order_id: Optional[str] = None
    stop_price: Optional[float] = None

    # PARTIAL_FILL 서브상태
    entry_working: bool = False  # 잔량 주문 활성 여부
    entry_order_id: Optional[str] = None

    # 복구 카운터
    stop_recovery_fail_count: int = 0

    # DCA / TP 상태
    base_qty: int = 0
    dca_count: int = 0
    dca_pending: bool = False
    tp1_done: bool = False


@dataclass
class PendingOrder:
    """
    대기 중인 주문 (ENTRY_PENDING/EXIT_PENDING)

    상태 전환 추적용:
    - order_id: 주문 ID
    - order_link_id: client order ID
    - placed_at: 주문 시각
    - signal_id: 추적용
    """
    order_id: str
    order_link_id: str
    placed_at: float
    signal_id: str
    qty: int
    price: float
    side: str  # "Buy" or "Sell"

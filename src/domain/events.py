"""
Domain Events — Execution Events

FLOW.md Section 2.5 기반 상태 전환 트리거 이벤트
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class EventType(Enum):
    """
    Execution Event 타입 (FLOW Section 2.5)

    상태 전환 트리거:
    - FILL: 완전 체결 → ENTRY_PENDING → IN_POSITION
    - PARTIAL_FILL: 부분 체결 → ENTRY_PENDING → IN_POSITION (entry_working=True)
    - CANCEL: 취소 → filled_qty 확인
    - REJECT: 거절 → ENTRY_PENDING → FLAT
    - LIQUIDATION: 강제청산 → IN_POSITION → HALT
    - ADL: 자동감소 → IN_POSITION → (수량 감소 or FLAT)
    """
    FILL = "FILL"
    PARTIAL_FILL = "PARTIAL_FILL"
    CANCEL = "CANCEL"
    REJECT = "REJECT"
    LIQUIDATION = "LIQUIDATION"
    ADL = "ADL"


@dataclass
class ExecutionEvent:
    """
    Execution Event (FLOW Section 2.5)

    상태 확정 규칙:
    - 정상 모드: 이벤트가 상태 전이 트리거
    - DEGRADED 모드: Reconcile로 보조 (확정 아님)
    """
    type: EventType
    order_id: str
    order_link_id: str
    filled_qty: int
    order_qty: int
    timestamp: float

    # 추가 정보 (optional)
    exec_price: Optional[float] = None
    fee_paid: Optional[float] = None
    position_qty_after: Optional[int] = None  # ADL 이벤트 처리용 (변경 후 포지션 수량)

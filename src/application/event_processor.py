"""
src/application/event_processor.py
Event Processing Helpers (Phase 11b)

Purpose:
- Helper functions for Event Processing (FILL event → Position update)
- Reduce orchestrator.py LOC (God Object refactoring)
- Self-healing check (Position vs State consistency)

SSOT:
- FLOW.md Section 2.5: Event Processing Flow
- task_plan.md Phase 11b: Event Processing (Atomic State Transition)

Design:
- Pure functions (no state mutation, return values only)
- Accept necessary parameters explicitly
- Dual ID tracking for FILL event matching
- Self-healing check for Position vs State consistency
"""

from typing import Optional, Dict, Any
from domain.state import State, Position, Direction


def verify_state_consistency(
    position: Optional[Position],
    state: State,
) -> Optional[str]:
    """
    Position vs State 일관성 검증 (Self-healing check)

    Args:
        position: 현재 Position 객체 (None이면 포지션 없음)
        state: 현재 State

    Returns:
        Optional[str]: 일관성 위반 시 이유 문자열, 정상 시 None

    Phase 11b: Risk mitigation (Section 9 리스크 분석)

    일관성 규칙:
    - Position != None → State는 IN_POSITION 또는 EXIT_PENDING이어야 함
    - Position = None → State는 FLAT, ENTRY_PENDING, COOLDOWN, HALT 중 하나여야 함

    위반 조합 (HALT 트리거):
    1. Position != None and State in [FLAT, ENTRY_PENDING] → "position_state_inconsistent"
    2. Position = None and State = IN_POSITION → "position_state_inconsistent"
    """
    # Case 1: Position이 있는데 State가 FLAT 또는 ENTRY_PENDING
    if position is not None:
        if state in [State.FLAT, State.ENTRY_PENDING]:
            return "position_state_inconsistent"

    # Case 2: Position이 없는데 State가 IN_POSITION
    if position is None:
        if state == State.IN_POSITION:
            return "position_state_inconsistent"

    # 일관성 정상
    return None


def match_pending_order(
    event,  # ExecutionEvent or dict
    pending_order: Optional[dict],
) -> bool:
    """
    FILL event를 Pending order와 매칭

    Args:
        event: FILL event (ExecutionEvent dataclass or dict)
            - order_id / orderId: Bybit 서버 생성 ID
            - order_link_id / orderLinkId: 클라이언트 ID (optional)
        pending_order: Pending order 정보 (None이면 매칭 실패)
            - order_id: 주문 ID
            - order_link_id: 클라이언트 ID

    Returns:
        bool: 매칭 성공 시 True

    매칭 조건 (Dual ID tracking):
    1. event.order_id == pending_order["order_id"] (우선)
    2. event.order_link_id == pending_order["order_link_id"] (fallback)

    리스크 완화: Dual ID tracking으로 매칭 실패 방지
    """
    if pending_order is None:
        return False

    # ExecutionEvent (dataclass) 또는 dict 모두 지원
    if hasattr(event, 'order_id'):
        # ExecutionEvent dataclass
        event_order_id = event.order_id
        event_order_link_id = event.order_link_id
    else:
        # dict (backward compatibility)
        event_order_id = event.get("orderId")
        event_order_link_id = event.get("orderLinkId")

    # orderId 매칭 (우선)
    if event_order_id == pending_order["order_id"]:
        return True

    # orderLinkId 매칭 (fallback)
    if event_order_link_id == pending_order["order_link_id"]:
        return True

    return False


def create_position_from_fill(
    event,  # ExecutionEvent or dict
    pending_order: Optional[dict],
) -> Position:
    """
    FILL event → Position 생성

    Args:
        event: FILL event (ExecutionEvent dataclass or dict)
            - filled_qty / execQty: 체결 수량
            - exec_price / execPrice: 체결 가격
            - side (from pending_order): "Buy" or "Sell"
        pending_order: Pending order 정보 (signal_id, side 필요)
            - signal_id: Signal ID
            - side: "Buy" or "Sell"

    Returns:
        Position: entry_price, qty, direction, stop_price, signal_id

    Stop price 계산:
    - LONG: entry_price * (1 - stop_distance_pct)
    - SHORT: entry_price * (1 + stop_distance_pct)
    - stop_distance_pct = 3% (Policy Section 9)
    """
    # Event에서 데이터 추출 (ExecutionEvent 또는 dict 지원)
    if hasattr(event, 'filled_qty'):
        # ExecutionEvent dataclass
        qty = event.filled_qty
        entry_price = event.exec_price
    else:
        # dict (backward compatibility)
        qty = int(event["execQty"])
        entry_price = float(event["execPrice"])

    # Side는 pending_order에서 가져옴 (ExecutionEvent에는 없음)
    side = pending_order["side"] if pending_order else "Buy"

    # Signal ID (pending_order에서 가져옴)
    signal_id = pending_order["signal_id"] if pending_order else "unknown"

    # Direction 계산
    direction = Direction.LONG if side == "Buy" else Direction.SHORT

    # Stop price 계산 (3% stop distance)
    stop_distance_pct = 0.03
    if direction == Direction.LONG:
        stop_price = entry_price * (1 - stop_distance_pct)
    else:  # SHORT
        stop_price = entry_price * (1 + stop_distance_pct)

    return Position(
        qty=qty,
        entry_price=entry_price,
        direction=direction,
        signal_id=signal_id,
        stop_price=stop_price,
    )

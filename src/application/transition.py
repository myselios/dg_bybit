"""
State Transition — Pure Function

FLOW.md Section 2.5 기반 상태 전환 로직 (순수 함수)
FLOW_REF: docs/constitution/FLOW.md#2.5 (Last verified: 2026-01-19)

원칙:
1. 순수 함수 (side-effect 없음, I/O 금지)
2. 입력: (state, position, event, pending_order)
3. 출력: (new_state, new_position, intents)
4. Oracle 테스트로 전부 검증 가능

이 파일은 FLOW.md 전이 규칙의 구현체다 (테스트로 준수 강제).
"""

from typing import Optional, Tuple
from dataclasses import replace

from domain.state import (
    State,
    StopStatus,
    Direction,
    Position,
    PendingOrder
)
from domain.events import (
    EventType,
    ExecutionEvent,
)
from domain.intent import (
    TransitionIntents,
    StopIntent,
    HaltIntent
)


def transition(
    current_state: State,
    current_position: Optional[Position],
    event: ExecutionEvent,
    pending_order: Optional[PendingOrder] = None
) -> Tuple[State, Optional[Position], TransitionIntents]:
    """
    순수 함수 State Transition (Oracle Testable)

    Args:
        current_state: 현재 상태
        current_position: 현재 포지션 (IN_POSITION/EXIT_PENDING만)
        event: Execution event
        pending_order: 대기 중인 주문 (ENTRY_PENDING/EXIT_PENDING)

    Returns:
        (new_state, new_position, intents)

    FLOW 규칙:
    - ENTRY_PENDING + FILL → IN_POSITION
    - ENTRY_PENDING + PARTIAL_FILL → IN_POSITION (entry_working=True)
    - ENTRY_PENDING + REJECT → FLAT
    - ENTRY_PENDING + CANCEL (filled_qty=0) → FLAT
    - ENTRY_PENDING + CANCEL (filled_qty>0) → IN_POSITION
    - EXIT_PENDING + FILL → FLAT
    - EXIT_PENDING + REJECT/CANCEL → stay (재시도)
    - FLAT + FILL (unexpected) → HALT
    - LIQUIDATION → HALT (any state)
    - ADL → IN_POSITION (수량 감소 or FLAT) [FLOW Section 2.5]
    - IN_POSITION + PARTIAL_FILL/FILL → qty 증가
    """
    intents = TransitionIntents()

    # Emergency events: LIQUIDATION만 최우선 처리 (FLOW 준수)
    if event.type == EventType.LIQUIDATION:
        return _handle_emergency(current_state, event, intents)

    # ENTRY_PENDING 상태 처리
    if current_state == State.ENTRY_PENDING:
        return _handle_entry_pending(event, pending_order, intents)

    # EXIT_PENDING 상태 처리
    elif current_state == State.EXIT_PENDING:
        return _handle_exit_pending(current_position, event, intents)

    # IN_POSITION 상태 처리
    elif current_state == State.IN_POSITION:
        return _handle_in_position(current_position, event, intents)

    # FLAT 상태에서 예상치 못한 이벤트
    elif current_state == State.FLAT:
        return _handle_flat(event, intents)

    # 기타 상태: 유지
    return current_state, current_position, intents


def _handle_entry_pending(
    event: ExecutionEvent,
    pending_order: Optional[PendingOrder],
    intents: TransitionIntents
) -> Tuple[State, Optional[Position], TransitionIntents]:
    """
    ENTRY_PENDING 상태 처리 (FLOW Section 2.5)

    Critical Safety Rule:
      - ENTRY_PENDING인데 pending_order=None → HALT
      - 더미 값으로 진행 금지 (실거래 폭탄)
      - 상태 불일치는 조용히 넘기면 안 됨
    """
    # Safety Gate: pending_order 필수 확인
    if pending_order is None:
        intents.halt_intent = HaltIntent(
            reason="entry_pending_state_without_pending_order"
        )
        intents.entry_blocked = True
        return State.HALT, None, intents

    if event.type == EventType.FILL:
        # 완전 체결 → IN_POSITION
        position = Position(
            qty=event.filled_qty,
            entry_price=pending_order.price,
            direction=_determine_direction(pending_order.side),
            signal_id=pending_order.signal_id,
            stop_status=StopStatus.PENDING,
            entry_working=False
        )

        # Stop PLACE intent
        intents.stop_intent = StopIntent(
            action="PLACE",
            desired_qty=event.filled_qty,
            reason="entry_fill_requires_immediate_stop"
        )

        return State.IN_POSITION, position, intents

    elif event.type == EventType.PARTIAL_FILL:
        # 부분 체결 → IN_POSITION (치명적 규칙)
        position = Position(
            qty=event.filled_qty,
            entry_price=pending_order.price,
            direction=_determine_direction(pending_order.side),
            signal_id=pending_order.signal_id,
            stop_status=StopStatus.PENDING,
            entry_working=True,  # 잔량 주문 활성
            entry_order_id=event.order_id
        )

        # Stop PLACE intent (즉시)
        intents.stop_intent = StopIntent(
            action="PLACE",
            desired_qty=event.filled_qty,
            reason="first_partial_fill_requires_immediate_stop_install"
        )

        return State.IN_POSITION, position, intents

    elif event.type == EventType.CANCEL:
        # CANCEL: filled_qty 확인 필수
        if event.filled_qty > 0:
            # 부분체결 후 취소 → IN_POSITION
            position = Position(
                qty=event.filled_qty,
                entry_price=pending_order.price,
                direction=_determine_direction(pending_order.side),
                signal_id=pending_order.signal_id,
                stop_status=StopStatus.PENDING,
                entry_working=False  # 잔량 취소됨
            )

            # Stop PLACE intent
            intents.stop_intent = StopIntent(
                action="PLACE",
                desired_qty=event.filled_qty,
                reason="partial_fill_before_cancel_requires_stop"
            )

            return State.IN_POSITION, position, intents
        else:
            # 체결 없이 취소 → FLAT
            return State.FLAT, None, intents

    elif event.type == EventType.REJECT:
        # 주문 거절 → FLAT
        return State.FLAT, None, intents

    # 기타 이벤트: 상태 유지
    return State.ENTRY_PENDING, None, intents


def _handle_exit_pending(
    current_position: Optional[Position],
    event: ExecutionEvent,
    intents: TransitionIntents
) -> Tuple[State, Optional[Position], TransitionIntents]:
    """
    EXIT_PENDING 상태 처리

    규칙:
    - PARTIAL_FILL: position.qty 감소 + EXIT_PENDING 유지
    - FILL (정상): → FLAT
    - FILL (과체결): → HALT
    - REJECT/CANCEL: 상태 유지 (재시도)
    """
    if current_position is None:
        # Position 없으면 비정상 → 상태 유지
        return State.EXIT_PENDING, current_position, intents

    if event.type == EventType.PARTIAL_FILL:
        # 부분 청산 → qty 감소, EXIT_PENDING 유지
        remaining_qty = current_position.qty - event.filled_qty

        if remaining_qty < 0:
            # 과체결 감지 → HALT
            intents.halt_intent = HaltIntent(
                reason="exit_partial_fill_exceeded_position_qty"
            )
            intents.entry_blocked = True
            return State.HALT, None, intents

        # 정상 부분 청산
        new_position = replace(current_position, qty=remaining_qty)
        return State.EXIT_PENDING, new_position, intents

    elif event.type == EventType.FILL:
        # 완전 청산
        remaining_qty = current_position.qty - event.filled_qty

        if remaining_qty < 0:
            # 과체결 감지 → HALT
            intents.halt_intent = HaltIntent(
                reason="exit_fill_exceeded_position_qty"
            )
            intents.entry_blocked = True
            return State.HALT, None, intents

        # 정상 청산 완료 → FLAT
        return State.FLAT, None, intents

    elif event.type in [EventType.REJECT, EventType.CANCEL]:
        # 청산 실패 → 상태 유지 (재시도)
        return State.EXIT_PENDING, current_position, intents

    return State.EXIT_PENDING, current_position, intents


def _handle_flat(
    event: ExecutionEvent,
    intents: TransitionIntents
) -> Tuple[State, Optional[Position], TransitionIntents]:
    """
    FLAT 상태에서 예상치 못한 이벤트 처리
    """
    if event.type == EventType.FILL:
        # 유령 체결 → HALT
        intents.halt_intent = HaltIntent(reason="unexpected_fill_while_flat")
        intents.entry_blocked = True
        return State.HALT, None, intents

    # 기타 이벤트: 무시
    return State.FLAT, None, intents


def _handle_emergency(
    current_state: State,
    event: ExecutionEvent,
    intents: TransitionIntents
) -> Tuple[State, Optional[Position], TransitionIntents]:
    """
    Emergency Events 처리 (LIQUIDATION only)

    FLOW 준수: LIQUIDATION만 즉시 HALT
    (ADL은 IN_POSITION에서 수량 변경으로 처리)

    모든 상태에서 최우선 처리
    → HALT 전환 + halt_intent 생성
    """
    # HALT로 전환
    intents.halt_intent = HaltIntent(
        reason=f"{event.type.name.lower()}_event_requires_immediate_halt"
    )
    intents.entry_blocked = True

    # Position은 청산됨
    return State.HALT, None, intents


def _handle_in_position(
    current_position: Optional[Position],
    event: ExecutionEvent,
    intents: TransitionIntents
) -> Tuple[State, Optional[Position], TransitionIntents]:
    """
    IN_POSITION 상태에서 추가 체결 처리 (Phase 0.5)

    규칙:
    - ADL: 수량 감소 or FLAT (FLOW Section 2.5 준수)
    - PARTIAL_FILL (entry_working=True): qty 증가 + AMEND intent
    - FILL (entry order 완전 체결): qty 증가 + entry_working=False
    - stop_status=MISSING → PLACE intent (복구)
    - Invalid qty (<=0 or negative) → HALT
    """
    if current_position is None:
        # Position 없으면 비정상 → 상태 유지
        return State.IN_POSITION, current_position, intents

    # [ADL 처리] FLOW Section 2.5 준수: 수량 감소 or FLAT
    if event.type == EventType.ADL:
        if event.position_qty_after is None:
            # ADL 이벤트에 position_qty_after 없음 → HALT (데이터 무결성)
            intents.halt_intent = HaltIntent(
                reason="adl_event_missing_position_qty_after"
            )
            intents.entry_blocked = True
            return State.HALT, None, intents

        if event.position_qty_after == 0:
            # 수량 0 → FLAT
            return State.FLAT, None, intents
        else:
            # 수량 감소 → IN_POSITION 유지 + Stop AMEND
            new_position = replace(
                current_position,
                qty=event.position_qty_after,
                entry_working=False  # ADL 후 entry order는 없음
            )

            intents.stop_intent = StopIntent(
                action="AMEND",
                desired_qty=event.position_qty_after,
                reason="adl_reduced_position_qty_requires_stop_update"
            )

            return State.IN_POSITION, new_position, intents

    # (D) Invalid qty 방어: filled_qty <= 0 → HALT
    if event.type in [EventType.PARTIAL_FILL, EventType.FILL]:
        if event.filled_qty <= 0:
            intents.halt_intent = HaltIntent(
                reason="invalid_filled_qty_non_positive"
            )
            intents.entry_blocked = True
            return State.HALT, None, intents

    if event.type == EventType.PARTIAL_FILL:
        # 추가 부분 체결 → qty 증가
        if current_position.entry_working and event.order_id == current_position.entry_order_id:
            # Entry order의 추가 체결
            new_qty = current_position.qty + event.filled_qty

            # (D) 계산 결과 qty < 0 방어
            if new_qty < 0:
                intents.halt_intent = HaltIntent(
                    reason="calculated_qty_negative_after_partial_fill"
                )
                intents.entry_blocked = True
                return State.HALT, None, intents

            new_position = replace(current_position, qty=new_qty)

            # Stop AMEND intent (qty 변경)
            intents.stop_intent = StopIntent(
                action="AMEND",
                desired_qty=new_qty,
                reason="additional_partial_fill_requires_stop_qty_update"
            )

            return State.IN_POSITION, new_position, intents

    elif event.type == EventType.FILL:
        # Entry order 완전 체결 → qty 증가 + entry_working=False
        if current_position.entry_working and event.order_id == current_position.entry_order_id:
            new_qty = current_position.qty + event.filled_qty

            # (D) 계산 결과 qty < 0 방어
            if new_qty < 0:
                intents.halt_intent = HaltIntent(
                    reason="calculated_qty_negative_after_fill"
                )
                intents.entry_blocked = True
                return State.HALT, None, intents

            new_position = replace(
                current_position,
                qty=new_qty,
                entry_working=False,
                entry_order_id=None
            )

            # Stop AMEND intent (최종 qty)
            intents.stop_intent = StopIntent(
                action="AMEND",
                desired_qty=new_qty,
                reason="entry_fill_complete_final_stop_qty_update"
            )

            return State.IN_POSITION, new_position, intents

    # stop_status=MISSING 복구: PLACE intent
    if current_position.stop_status == StopStatus.MISSING:
        intents.stop_intent = StopIntent(
            action="PLACE",
            desired_qty=current_position.qty,
            reason="stop_missing_requires_immediate_placement"
        )
        # 상태는 유지, intent만 발생
        return State.IN_POSITION, current_position, intents

    # 기타 이벤트: 상태 유지
    return State.IN_POSITION, current_position, intents


def is_entry_allowed(state: State) -> bool:
    """
    진입 허용 여부 (oracle 테스트 계약)

    Args:
        state: 현재 상태

    Returns:
        False: HALT or COOLDOWN
        True: otherwise
    """
    if state == State.HALT:
        return False
    if state == State.COOLDOWN:
        return False
    return True


def _determine_direction(side: str) -> Direction:
    """주문 side → Direction 변환"""
    return Direction.LONG if side == "Buy" else Direction.SHORT

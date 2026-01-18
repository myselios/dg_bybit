"""
Event Router — Execution Event → State Transition

FLOW.md Section 2.5 기반 상태 전환 로직

원칙:
1. 상태 확정은 이벤트로만 (정상 모드)
2. PARTIAL_FILL은 즉시 IN_POSITION 전환
3. CANCEL 시 filled_qty 확인 필수
"""

from typing import Optional, Tuple, Dict, Any
from dataclasses import replace
import sys
from pathlib import Path

# Import path 통일 (src. 제거)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from domain.state import (
    State,
    StopStatus,
    Direction,
    EventType,
    ExecutionEvent,
    Position,
    PendingOrder
)


class EventRouter:
    """
    Execution Event Router

    책임:
    - Execution event → state transition
    - Position 생성/업데이트
    - Stop status 관리 (외부 호출 필요)

    Oracle 테스트 계약:
    - state, position: 상태 검증
    - halt_reason: HALT 사유 추적
    - degraded_mode: WS 상태 추적
    - entry_allowed: 진입 차단 여부 (HALT/COOLDOWN)
    """

    def __init__(self):
        self.state: State = State.FLAT
        self.position: Optional[Position] = None
        self.pending_order: Optional[PendingOrder] = None

        # Oracle 테스트 계약 필드
        self.halt_reason: Optional[str] = None
        self.degraded_mode: bool = False
        self.cooldown_ends_at: Optional[float] = None  # COOLDOWN 만료 시각

    def handle_event(
        self,
        event: ExecutionEvent,
        pending_order: Optional[PendingOrder] = None
    ) -> Tuple[State, Optional[Position]]:
        """
        Execution Event 처리 → State Transition

        Args:
            event: Execution event
            pending_order: 대기 중인 주문 (ENTRY_PENDING/EXIT_PENDING)

        Returns:
            (new_state, new_position)

        FLOW 규칙:
        - ENTRY_PENDING + FILL → IN_POSITION
        - ENTRY_PENDING + REJECT → FLAT
        - ENTRY_PENDING + CANCEL (filled_qty=0) → FLAT
        - ENTRY_PENDING + CANCEL (filled_qty>0) → IN_POSITION
        - ENTRY_PENDING + PARTIAL_FILL → IN_POSITION (entry_working=True)
        - EXIT_PENDING + FILL → FLAT
        - EXIT_PENDING + REJECT/CANCEL → stay (재시도)
        """
        # ENTRY_PENDING 상태에서의 처리
        if self.state == State.ENTRY_PENDING:
            return self._handle_entry_pending(event, pending_order)

        # EXIT_PENDING 상태에서의 처리
        elif self.state == State.EXIT_PENDING:
            return self._handle_exit_pending(event)

        # 기타 상태: 이벤트 무시 (비정상)
        return self.state, self.position

    def _handle_entry_pending(
        self,
        event: ExecutionEvent,
        pending_order: Optional[PendingOrder]
    ) -> Tuple[State, Optional[Position]]:
        """
        ENTRY_PENDING 상태에서의 이벤트 처리

        FLOW Section 2.5 규칙:
        - FILL: 완전 체결 → IN_POSITION
        - PARTIAL_FILL: 부분 체결 → IN_POSITION (entry_working=True)
        - CANCEL (filled_qty=0): → FLAT
        - CANCEL (filled_qty>0): → IN_POSITION (부분체결됨)
        - REJECT: → FLAT
        """
        if event.type == EventType.FILL:
            # 완전 체결 → IN_POSITION
            self.state = State.IN_POSITION

            # Position 생성
            self.position = Position(
                qty=event.filled_qty,
                entry_price=pending_order.price if pending_order else 0.0,
                direction=self._determine_direction(pending_order.side if pending_order else "Buy"),
                signal_id=pending_order.signal_id if pending_order else "unknown",
                stop_status=StopStatus.PENDING,  # Stop 설치 필요
                entry_working=False  # 완전 체결, 잔량 없음
            )

            return self.state, self.position

        elif event.type == EventType.PARTIAL_FILL:
            # 부분 체결 → IN_POSITION (치명적 규칙)
            self.state = State.IN_POSITION

            # Position 생성 (filled_qty 기준)
            self.position = Position(
                qty=event.filled_qty,
                entry_price=pending_order.price if pending_order else 0.0,
                direction=self._determine_direction(pending_order.side if pending_order else "Buy"),
                signal_id=pending_order.signal_id if pending_order else "unknown",
                stop_status=StopStatus.PENDING,  # Stop 즉시 설치 필요
                entry_working=True,  # 잔량 주문 활성
                entry_order_id=event.order_id
            )

            return self.state, self.position

        elif event.type == EventType.CANCEL:
            # CANCEL: filled_qty 확인 필수
            if event.filled_qty > 0:
                # 부분체결 후 취소 → IN_POSITION
                self.state = State.IN_POSITION

                self.position = Position(
                    qty=event.filled_qty,
                    entry_price=pending_order.price if pending_order else 0.0,
                    direction=self._determine_direction(pending_order.side if pending_order else "Buy"),
                    signal_id=pending_order.signal_id if pending_order else "unknown",
                    stop_status=StopStatus.PENDING,  # Stop 즉시 설치
                    entry_working=False  # 잔량 취소됨
                )

                return self.state, self.position
            else:
                # 체결 없이 취소 → FLAT
                self.state = State.FLAT
                self.position = None
                return self.state, self.position

        elif event.type == EventType.REJECT:
            # 주문 거절 → FLAT
            self.state = State.FLAT
            self.position = None
            return self.state, self.position

        # 기타 이벤트: 상태 유지
        return self.state, self.position

    def _handle_exit_pending(
        self,
        event: ExecutionEvent
    ) -> Tuple[State, Optional[Position]]:
        """
        EXIT_PENDING 상태에서의 이벤트 처리

        FLOW 규칙:
        - FILL: 청산 완료 → FLAT
        - REJECT/CANCEL: 상태 유지 (재시도)
        """
        if event.type == EventType.FILL:
            # 청산 완료 → FLAT
            self.state = State.FLAT
            self.position = None
            return self.state, self.position

        elif event.type in [EventType.REJECT, EventType.CANCEL]:
            # 청산 실패 → 상태 유지 (재시도)
            return self.state, self.position

        return self.state, self.position

    def _determine_direction(self, side: str) -> Direction:
        """
        주문 side → Direction 변환

        Buy → LONG
        Sell → SHORT
        """
        return Direction.LONG if side == "Buy" else Direction.SHORT

    def transition_to(self, new_state: State):
        """수동 상태 전환 (Emergency/HALT 등)"""
        self.state = new_state

    def halt(self, reason: str):
        """
        HALT 상태로 전환

        Args:
            reason: HALT 사유 (oracle 테스트용)
        """
        self.state = State.HALT
        self.halt_reason = reason
        # Position은 유지 (Stop Loss 유지)

    @property
    def entry_allowed(self) -> bool:
        """
        진입 허용 여부 (oracle 테스트 계약)

        Returns:
            False: HALT or COOLDOWN
            True: otherwise
        """
        if self.state == State.HALT:
            return False
        if self.state == State.COOLDOWN:
            return False
        return True

    def get_stop_update_intent(self) -> Optional[Dict[str, Any]]:
        """
        Stop 갱신 의도 반환 (oracle 테스트 계약)

        Returns:
            {
                "action": "NONE" | "PLACE" | "AMEND" | "CANCEL_AND_PLACE",
                "desired_qty": Optional[int],
                "reason": str
            }

        Note: 실제 구현은 StopUpdatePolicy 컴포넌트로 분리 예정
              지금은 테스트 계약 정의만
        """
        # 스텁: 실제 구현은 나중에
        # 현재는 테스트가 FakeExchange.calls를 통해 검증 가능
        return None

    def reset(self):
        """상태 초기화 (테스트용)"""
        self.state = State.FLAT
        self.position = None
        self.pending_order = None
        self.halt_reason = None
        self.degraded_mode = False
        self.cooldown_ends_at = None

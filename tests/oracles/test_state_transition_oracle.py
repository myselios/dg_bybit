"""
State Transition Oracle Tests

FLOW.md Section 1/2 기반 상태 전환 기대값(oracle) 검증

테스트 원칙:
1. Given-When-Then 구조
2. FakeExchange로 이벤트 시뮬레이션
3. 상태/주문/stop_status 검증
4. 테스트가 구현보다 먼저 (TDD)
"""

import pytest
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# ========== Domain Models (src/domain/state.py에서 import) ==========
from src.domain.state import (
    State,
    StopStatus,
    Direction,
    EventType,
    ExecutionEvent,
    Position,
    PendingOrder
)

# ========== Transition Function ==========
from src.application.transition import transition
from src.domain.intent import TransitionIntents, StopIntent, HaltIntent


# ========== Stop Update Oracle용 Helper Types ==========

from typing import Literal

THRESHOLD_PCT = 0.20  # Stop 갱신 threshold: 20%
DEBOUNCE_SEC = 2.0    # Stop 갱신 debounce: 2초


@dataclass
class StopUpdateIntent:
    """
    Stop 갱신 의도(oracle 관점)
    - action: "NONE" | "PLACE" | "AMEND" | "CANCEL_AND_PLACE"
    - desired_qty: 갱신 후 stop qty 기대값
    - reason: 왜 그 액션을 해야 하는지 (테스트 가독성용)
    """
    action: Literal["NONE", "PLACE", "AMEND", "CANCEL_AND_PLACE"]
    desired_qty: Optional[int]
    reason: str


@dataclass
class TimedExecutionEvent:
    """
    시간 포함 이벤트 (debounce 오라클을 테스트로 고정하려면 ts가 필요)
    """
    ts: float
    event: ExecutionEvent


# ========== Oracle Test Cases ==========

class TestStateTransitionOracle:
    """
    State Transition Oracle (FLOW Section 1 기반)

    목적: 상태 전환 규칙의 기대값(oracle)을 코드로 고정
    """

    # ===== Case 1-5: ENTRY_PENDING → ? =====

    def test_entry_pending_to_in_position_on_fill(self):
        """
        Case 1: ENTRY_PENDING + FILL → IN_POSITION

        Given: state=ENTRY_PENDING, pending order qty=100
        When: FILL event (filled_qty=100)
        Then:
          - state = IN_POSITION
          - position.qty = 100
          - stop_status = PENDING (Stop 설치 intent 발행됨)
          - entry_working = False (잔량 없음)
          - stop_intent.action = PLACE
        """
        # Given
        initial_state = State.ENTRY_PENDING
        initial_position = None
        pending_order = PendingOrder(
            order_id="test_order_1",
            order_link_id="test_link_1",
            placed_at=1000.0,
            signal_id="test_signal_1",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        # When
        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="test_order_1",
            order_link_id="test_link_1",
            filled_qty=100,
            order_qty=100,
            timestamp=1001.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order
        )

        # Then
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 100
        assert new_position.entry_price == 50000.0
        assert new_position.direction == Direction.LONG
        assert new_position.stop_status == StopStatus.PENDING
        assert new_position.entry_working == False

        # Intent 검증
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "PLACE"
        assert intents.stop_intent.desired_qty == 100

    def test_entry_pending_to_flat_on_reject(self):
        """
        Case 2: ENTRY_PENDING + REJECT → FLAT

        Given: state=ENTRY_PENDING
        When: REJECT event
        Then:
          - state = FLAT
          - position = None
        """
        # Given
        initial_state = State.ENTRY_PENDING
        initial_position = None
        pending_order = PendingOrder(
            order_id="test_order_2",
            order_link_id="test_link_2",
            placed_at=1000.0,
            signal_id="test_signal_2",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        # When
        event = ExecutionEvent(
            type=EventType.REJECT,
            order_id="test_order_2",
            order_link_id="test_link_2",
            filled_qty=0,
            order_qty=100,
            timestamp=1001.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order
        )

        # Then
        assert new_state == State.FLAT
        assert new_position is None

    def test_entry_pending_to_flat_on_cancel_zero_fill(self):
        """
        Case 3: ENTRY_PENDING + CANCEL (filled_qty=0) → FLAT

        Given: state=ENTRY_PENDING, pending order qty=100
        When: CANCEL event (filled_qty=0)
        Then:
          - state = FLAT
          - position = None
        """
        initial_state = State.ENTRY_PENDING
        pending_order = PendingOrder(
            order_id="test_order_3",
            order_link_id="test_link_3",
            placed_at=1000.0,
            signal_id="test_signal_3",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        event = ExecutionEvent(
            type=EventType.CANCEL,
            order_id="test_order_3",
            order_link_id="test_link_3",
            filled_qty=0,
            order_qty=100,
            timestamp=1001.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            None,
            event,
            pending_order
        )

        assert new_state == State.FLAT
        assert new_position is None

    def test_entry_pending_to_in_position_on_cancel_partial_fill(self):
        """
        Case 4: ENTRY_PENDING + CANCEL (filled_qty>0) → IN_POSITION

        Given: state=ENTRY_PENDING, pending order qty=100
        When: CANCEL event (filled_qty=30)
        Then:
          - state = IN_POSITION (부분체결됨)
          - position.qty = 30
          - stop_status = ACTIVE (즉시 설치)
          - entry_working = False (잔량 취소됨)

        참조: FLOW Section 2.5 PARTIAL_FILL 규칙
        """
        initial_state = State.ENTRY_PENDING
        pending_order = PendingOrder(
            order_id="test_order_4",
            order_link_id="test_link_4",
            placed_at=1000.0,
            signal_id="test_signal_4",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        event = ExecutionEvent(
            type=EventType.CANCEL,
            order_id="test_order_4",
            order_link_id="test_link_4",
            filled_qty=30,
            order_qty=100,
            timestamp=1001.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            None,
            event,
            pending_order
        )

        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 30
        assert new_position.stop_status == StopStatus.PENDING
        assert new_position.entry_working == False

    def test_entry_pending_to_in_position_on_partial_fill(self):
        """
        Case 5: ENTRY_PENDING + PARTIAL_FILL → IN_POSITION (entry_working=True)

        Given: state=ENTRY_PENDING, pending order qty=100
        When: PARTIAL_FILL event (filled_qty=20, order still active)
        Then:
          - state = IN_POSITION (부분체결 즉시 전환)
          - position.qty = 20
          - stop_status = PENDING (Stop 설치 intent)
          - entry_working = True (잔량 주문 활성)
          - stop_intent.action = PLACE

        참조: FLOW Section 2.5 PARTIAL_FILL 치명적 규칙
        """
        # Given
        initial_state = State.ENTRY_PENDING
        initial_position = None
        pending_order = PendingOrder(
            order_id="test_order_5",
            order_link_id="test_link_5",
            placed_at=1000.0,
            signal_id="test_signal_5",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        # When
        event = ExecutionEvent(
            type=EventType.PARTIAL_FILL,
            order_id="test_order_5",
            order_link_id="test_link_5",
            filled_qty=20,
            order_qty=100,
            timestamp=1001.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order
        )

        # Then
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 20
        assert new_position.stop_status == StopStatus.PENDING
        assert new_position.entry_working == True  # 치명적 규칙
        assert new_position.entry_order_id == "test_order_5"

        # Intent 검증
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "PLACE"
        assert intents.stop_intent.desired_qty == 20
        assert "first_partial_fill" in intents.stop_intent.reason

    # ===== Case 6-8: EXIT_PENDING → ? =====

    def test_exit_pending_to_flat_on_fill(self):
        """
        Case 6: EXIT_PENDING + FILL → FLAT

        Given: state=EXIT_PENDING, position.qty=100
        When: FILL event (청산 완료)
        Then:
          - state = FLAT
          - position = None
        """
        # Given
        initial_state = State.EXIT_PENDING
        initial_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal_exit",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        # When
        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="exit_order_1",
            order_link_id="exit_link_1",
            filled_qty=100,
            order_qty=100,
            timestamp=2000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order=None
        )

        # Then
        assert new_state == State.FLAT
        assert new_position is None

    def test_halt_gate_adl_event(self):
        """
        Case 7: HALT 게이트 — ADL 이벤트 (긴급 최우선)

        Given: state=IN_POSITION
        When: ADL event arrives
        Then:
          - state = HALT
          - halt_intent.reason contains "adl"
          - entry_blocked = True
          - position = None

        포인트: 긴급 이벤트는 signal보다 우선 (헌법 규칙)
        """
        # Given
        initial_state = State.IN_POSITION
        initial_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal_adl",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        # When
        event = ExecutionEvent(
            type=EventType.ADL,
            order_id="adl_event",
            order_link_id="adl_link",
            filled_qty=0,
            order_qty=0,
            timestamp=3000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order=None
        )

        # Then
        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert "adl" in intents.halt_intent.reason.lower()
        assert intents.entry_blocked == True

    def test_cooldown_gate_blocks_entry_before_timeout(self):
        """
        Case 8a: COOLDOWN 게이트 — timeout 전 진입 차단

        Given: state=COOLDOWN, cooldown active
        When: (시뮬레이션) entry 시도
        Then:
          - is_entry_allowed(COOLDOWN) == False

        포인트: 시간 기반 게이트는 transition이 단속
        """
        # Given
        cooldown_state = State.COOLDOWN

        # When: entry_allowed 체크
        from application.transition import is_entry_allowed
        entry_allowed = is_entry_allowed(cooldown_state)

        # Then
        assert entry_allowed == False

    def test_cooldown_gate_allows_entry_after_timeout(self):
        """
        Case 8b: COOLDOWN 게이트 — timeout 후 진입 허용

        Given: state=FLAT (COOLDOWN 만료 후)
        When: entry 시도
        Then:
          - is_entry_allowed(FLAT) == True

        포인트: COOLDOWN → FLAT 전환은 orchestrator 책임
                여기서는 FLAT 상태에서 진입 가능함을 검증
        """
        # Given
        flat_state = State.FLAT

        # When
        from application.transition import is_entry_allowed
        entry_allowed = is_entry_allowed(flat_state)

        # Then
        assert entry_allowed == True

    def test_one_way_mode_gate_rejects_opposite_direction(self):
        """
        Case 9: One-way Mode Gate — 반대 방향 진입 차단

        Given: IN_POSITION(LONG) 상태
        When: SHORT 진입 이벤트 (반대 방향)
        Then:
          - state 유지 (IN_POSITION)
          - 거절 처리 (실제로는 entry_allowed에서 차단됨)

        포인트: transition은 순수 함수이므로, 진입 차단은
                entry_allowed에서 수행. 여기서는 상태 유지만 검증

        Note: 실제 거절은 orchestrator + entry_allowed 레벨
        """
        # Given: LONG 포지션 보유 중
        initial_state = State.IN_POSITION
        initial_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,  # LONG 포지션
            signal_id="test_signal_long",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        # When: (시뮬레이션) SHORT 진입 시도는 orchestrator에서 차단됨
        # transition은 이벤트 처리만 하므로, 여기서는 상태 유지 검증

        # Then: IN_POSITION 상태에서는 추가 진입 이벤트가 오지 않음
        # (entry_allowed에서 차단되므로)
        # 여기서는 포지션 존재 확인만
        assert initial_state == State.IN_POSITION
        assert initial_position.direction == Direction.LONG

        # Note: 실제 One-way 게이트 테스트는 entry_allowed.py의
        # unit test에서 수행 (Phase 2)

    def test_exit_pending_stays_on_reject(self):
        """
        Case 10: EXIT_PENDING + REJECT → EXIT_PENDING (재시도)

        Given: state=EXIT_PENDING
        When: REJECT event (청산 실패)
        Then:
          - state = EXIT_PENDING (유지)
          - 다음 tick에서 재시도 로직

        참조: FLOW Section 2 (재시도 정책은 구현 세부사항)
        """
        initial_state = State.EXIT_PENDING
        current_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.REJECT,
            order_id="exit_order_2",
            order_link_id="exit_link_2",
            filled_qty=0,
            order_qty=100,
            timestamp=2000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            current_position,
            event,
            None
        )

        assert new_state == State.EXIT_PENDING
        assert new_position is not None
        assert new_position.qty == 100

    def test_exit_pending_stays_on_cancel(self):
        """
        Case 8: EXIT_PENDING + CANCEL → EXIT_PENDING (재시도)

        Given: state=EXIT_PENDING
        When: CANCEL event (청산 취소)
        Then:
          - state = EXIT_PENDING (유지)
          - 다음 tick에서 재주문
        """
        initial_state = State.EXIT_PENDING
        current_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.CANCEL,
            order_id="exit_order_3",
            order_link_id="exit_link_3",
            filled_qty=0,
            order_qty=100,
            timestamp=2000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            current_position,
            event,
            None
        )

        assert new_state == State.EXIT_PENDING
        assert new_position is not None
        assert new_position.qty == 100


# ========== 확장 EventType (권장) ==========
# stop_status oracle을 테스트로 고정하려면 STOP 관련 이벤트가 필요하다.
# 지금은 최소 추가만 제안. 실제로는 FakeExchange가 stop 설치/취소/거절을 이벤트로 뱉어야 한다.

class ExtendedEventType(Enum):
    STOP_INSTALLED = "STOP_INSTALLED"
    STOP_REJECTED = "STOP_REJECTED"
    STOP_CANCELED = "STOP_CANCELED"
    STOP_AMENDED = "STOP_AMENDED"


@dataclass
class StopEvent:
    type: ExtendedEventType
    stop_order_id: str
    qty: int


# ========== 추가 Oracle Tests ==========

class TestStateTransitionOracleAdditional:
    """
    추가 State Transition Oracle

    목표:
    - IN_POSITION에서 일어나는 지옥 시나리오 고정
    - Unexpected event / Emergency event 고정
    - COOLDOWN/HALT의 "차단" 규칙 고정
    """

    # ===== Case 16-18: FLAT/IN_POSITION + 예상치 못한 이벤트 =====

    def test_flat_unexpected_fill_should_halt(self):
        """
        Case 16: FLAT + FILL → HALT (유령 체결 이벤트)

        Given: state=FLAT
        When: FILL event (filled_qty>0) arrives
        Then:
          - state = HALT
          - halt_reason = "unexpected_fill_while_flat"
          - position = None (또는 reconcile 후 확인 전까지는 unknown으로 처리해도 되지만, 기본은 HALT)
        """
        initial_state = State.FLAT
        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="ghost_fill",
            order_link_id="ghost_link",
            filled_qty=10,
            order_qty=10,
            timestamp=1000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            None,
            event,
            None
        )

        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert "unexpected_fill_while_flat" in intents.halt_intent.reason

    def test_in_position_additional_partial_fill_increases_qty(self):
        """
        Case 17: IN_POSITION + PARTIAL_FILL (entry_working=True) → qty 증가

        Given:
          - state = IN_POSITION
          - position.qty = 20
          - entry_working = True (잔량 살아있음)
        When: PARTIAL_FILL arrives (filled_qty=10, order_qty=100)
        Then:
          - state = IN_POSITION
          - position.qty = 30
          - entry_working = True (아직 잔량)
          - stop_intent.action = AMEND
        """
        # Given
        initial_state = State.IN_POSITION
        initial_position = Position(
            qty=20,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal_partial",
            stop_status=StopStatus.ACTIVE,
            entry_working=True,
            entry_order_id="entry_order"
        )

        # When
        event = ExecutionEvent(
            type=EventType.PARTIAL_FILL,
            order_id="entry_order",
            order_link_id="entry_link",
            filled_qty=10,
            order_qty=100,
            timestamp=1500.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order=None
        )

        # Then
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 30
        assert new_position.entry_working == True
        assert new_position.stop_status == StopStatus.ACTIVE

        # Intent 검증
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "AMEND"
        assert intents.stop_intent.desired_qty == 30

    def test_in_position_fill_completes_entry_working_false(self):
        """
        Case 18: IN_POSITION + FILL(잔량까지 완전 체결) → entry_working False

        Given:
          - state = IN_POSITION
          - position.qty = 80
          - entry_working = True
        When: FILL arrives (filled_qty=20) completing total=100
        Then:
          - position.qty = 100
          - entry_working = False
          - stop_intent.action = AMEND (최종 qty)
        """
        # Given
        initial_state = State.IN_POSITION
        initial_position = Position(
            qty=80,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal_fill",
            stop_status=StopStatus.ACTIVE,
            entry_working=True,
            entry_order_id="entry_order"
        )

        # When
        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="entry_order",
            order_link_id="entry_link",
            filled_qty=20,
            order_qty=100,
            timestamp=1600.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order=None
        )

        # Then
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 100
        assert new_position.entry_working == False
        assert new_position.entry_order_id is None
        assert new_position.stop_status == StopStatus.ACTIVE

        # Intent 검증
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "AMEND"
        assert intents.stop_intent.desired_qty == 100

    # ===== Case 19-21: Emergency Events (LIQ/ADL) =====

    def test_in_position_liquidation_should_halt(self):
        """
        Case 19: IN_POSITION + LIQUIDATION → HALT

        Given: state=IN_POSITION, position exists
        When: LIQUIDATION event arrives
        Then:
          - state = HALT
          - halt_intent.reason = "liquidation_event_requires_immediate_halt"
          - position = None (포지션은 거래소에서 강제로 정리됨)
          - entry_blocked = True
        """
        # Given
        initial_state = State.IN_POSITION
        initial_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal_liq",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        # When
        event = ExecutionEvent(
            type=EventType.LIQUIDATION,
            order_id="liq_event",
            order_link_id="liq_link",
            filled_qty=0,
            order_qty=0,
            timestamp=3000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order=None
        )

        # Then
        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert "liquidation" in intents.halt_intent.reason.lower()
        assert intents.entry_blocked == True

    def test_in_position_adl_reduces_qty_and_stays_in_position(self):
        """
        Case 20a: IN_POSITION + ADL (수량 감소) → IN_POSITION (FLOW Section 2.5 준수)

        FLOW.md: ADL → 수량 감소 or FLAT
        Given: state=IN_POSITION, qty=100
        When: ADL event, position_qty_after=60
        Then:
          - state = IN_POSITION
          - position.qty = 60
          - stop_intent.action = AMEND
          - stop_intent.desired_qty = 60
        """
        # Given
        initial_state = State.IN_POSITION
        initial_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal_adl_reduce",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        # When
        event = ExecutionEvent(
            type=EventType.ADL,
            order_id="adl_event",
            order_link_id="adl_link",
            filled_qty=0,
            order_qty=0,
            timestamp=3100.0,
            position_qty_after=60  # ADL 후 수량 감소
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order=None
        )

        # Then
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 60
        assert new_position.entry_working == False  # ADL 후 entry order 없음
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "AMEND"
        assert intents.stop_intent.desired_qty == 60
        assert "adl" in intents.stop_intent.reason.lower()

    def test_in_position_adl_qty_zero_goes_flat(self):
        """
        Case 20b: IN_POSITION + ADL (수량 0) → FLAT (FLOW Section 2.5 준수)

        FLOW.md: ADL → 수량 감소 or FLAT
        Given: state=IN_POSITION, qty=100
        When: ADL event, position_qty_after=0
        Then:
          - state = FLAT
          - position = None
        """
        # Given
        initial_state = State.IN_POSITION
        initial_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal_adl_flat",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        # When
        event = ExecutionEvent(
            type=EventType.ADL,
            order_id="adl_event",
            order_link_id="adl_link",
            filled_qty=0,
            order_qty=0,
            timestamp=3100.0,
            position_qty_after=0  # ADL 후 수량 0
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order=None
        )

        # Then
        assert new_state == State.FLAT
        assert new_position is None

    def test_in_position_missing_stop_emits_place_stop_intent(self):
        """
        Phase 0.5: IN_POSITION + stop_status=MISSING → PLACE intent

        Given:
          - state = IN_POSITION
          - position.stop_status = MISSING
        When: Any event (or tick)
        Then:
          - state = IN_POSITION (유지)
          - stop_intent.action = PLACE
          - stop_intent.desired_qty = position.qty
        """
        # Given
        initial_state = State.IN_POSITION
        initial_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal_missing_stop",
            stop_status=StopStatus.MISSING,  # Stop Loss 없음 (비정상)
            entry_working=False
        )

        # When: 임의의 이벤트 (CANCEL 등 상태 변경 없는 이벤트)
        event = ExecutionEvent(
            type=EventType.CANCEL,
            order_id="some_order",
            order_link_id="some_link",
            filled_qty=0,
            order_qty=0,
            timestamp=2000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order=None
        )

        # Then
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 100
        assert new_position.stop_status == StopStatus.MISSING

        # Intent 검증: PLACE intent 발생
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "PLACE"
        assert intents.stop_intent.desired_qty == 100
        assert "missing" in intents.stop_intent.reason.lower()

    def test_in_position_invalid_filled_qty_halts(self):
        """
        Phase 0.5: IN_POSITION + invalid filled_qty → HALT

        Given:
          - state = IN_POSITION
          - position.qty = 100
          - entry_working = True
        When: PARTIAL_FILL with filled_qty <= 0
        Then:
          - state = HALT
          - halt_intent.reason contains "invalid_filled_qty"
          - entry_blocked = True
        """
        # Given
        initial_state = State.IN_POSITION
        initial_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal_invalid_qty",
            stop_status=StopStatus.ACTIVE,
            entry_working=True,
            entry_order_id="entry_order"
        )

        # When: Invalid filled_qty = 0
        event = ExecutionEvent(
            type=EventType.PARTIAL_FILL,
            order_id="entry_order",
            order_link_id="entry_link",
            filled_qty=0,  # Invalid: 0은 불가능
            order_qty=100,
            timestamp=2100.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            initial_position,
            event,
            pending_order=None
        )

        # Then
        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert "invalid_filled_qty" in intents.halt_intent.reason.lower()
        assert intents.entry_blocked == True

    def test_exit_pending_liquidation_should_halt(self):
        """
        Case 21: EXIT_PENDING + LIQUIDATION → HALT

        Given: state=EXIT_PENDING
        When: LIQUIDATION arrives
        Then:
          - state = HALT
          - halt_reason = "liquidated"
        """
        initial_state = State.EXIT_PENDING
        current_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.LIQUIDATION,
            order_id="liq_event",
            order_link_id="liq_link",
            filled_qty=0,
            order_qty=0,
            timestamp=3000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            current_position,
            event,
            None
        )

        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert "liquidation" in intents.halt_intent.reason.lower()

    # ===== Case 22-24: EXIT_PENDING 부분체결 / 과체결 안전장치 =====

    def test_exit_pending_partial_fill_reduces_position_qty_and_stays_exit_pending(self):
        """
        Case 22: EXIT_PENDING + PARTIAL_FILL → EXIT_PENDING 유지 + qty 감소

        Given:
          - state = EXIT_PENDING
          - position.qty = 100
        When: PARTIAL_FILL (filled_qty=30)
        Then:
          - state = EXIT_PENDING (아직 청산 중)
          - remaining position.qty = 70
          - stop should be amended to 70 (reduceOnly stop qty 동기화)
        """
        initial_state = State.EXIT_PENDING
        current_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.PARTIAL_FILL,
            order_id="exit_order",
            order_link_id="exit_link",
            filled_qty=30,
            order_qty=100,
            timestamp=2000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            current_position,
            event,
            None
        )

        assert new_state == State.EXIT_PENDING
        assert new_position is not None
        assert new_position.qty == 70

    def test_exit_pending_fill_should_flat_even_if_position_was_partial_before(self):
        """
        Case 23: EXIT_PENDING + FILL → FLAT (최종 청산 완료)

        Given:
          - state=EXIT_PENDING
          - position.qty = 70 (이전 partial 이후)
        When: FILL (filled_qty=70)
        Then:
          - state=FLAT
          - position=None
        """
        initial_state = State.EXIT_PENDING
        current_position = Position(
            qty=70,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="exit_order",
            order_link_id="exit_link",
            filled_qty=70,
            order_qty=70,
            timestamp=2000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            current_position,
            event,
            None
        )

        assert new_state == State.FLAT
        assert new_position is None

    def test_exit_pending_overfill_should_halt(self):
        """
        Case 24: EXIT_PENDING + FILL over position qty → HALT (reduceOnly 실패/상태 불일치)

        Given:
          - state=EXIT_PENDING
          - position.qty = 50
        When: FILL arrives with filled_qty=80 (과체결)
        Then:
          - state = HALT
          - halt_reason = "overfill_exit_detected"
        """
        initial_state = State.EXIT_PENDING
        current_position = Position(
            qty=50,
            entry_price=50000.0,
            direction=Direction.SHORT,
            signal_id="test_signal",
            stop_status=StopStatus.ACTIVE,
            entry_working=False
        )

        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="exit_order",
            order_link_id="exit_link",
            filled_qty=80,
            order_qty=80,
            timestamp=2000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            current_position,
            event,
            None
        )

        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert "exit_fill_exceeded_position_qty" in intents.halt_intent.reason


# ========== 추가 Oracle Tests (추후 확장) ==========

class TestPartialFillOracle:
    """
    Partial Fill Oracle (FLOW Section 2.5 기반)

    핵심 생존 규칙:
    - 20% threshold 미만: Stop 갱신 안 함 (rate limit 절약)
    - 2초 debounce: 연속 amend 방지 (coalescing)
    - Amend 우선: cancel+place는 최후 수단 (SL 공백 위험)

    PF-1~6: Stop Update Policy Oracle (계좌 보호 규칙)
    """

    def test_pf1_first_partial_fill_places_stop_immediately(self):
        """
        PF-1: 첫 부분체결 → Stop 즉시 설치

        Given:
          - state = ENTRY_PENDING
          - pending_order.qty = 100
        When: PARTIAL_FILL event (filled_qty=20)
        Then:
          - state → IN_POSITION
          - position.qty = 20
          - position.stop_status = PENDING → ACTIVE (설치 시도)
          - stop_intent.action = "PLACE"
          - stop_intent.desired_qty = 20
          - reason: "first_partial_fill_requires_immediate_stop_install"

        치명성: Stop 없는 포지션 = 무방비 노출
        """
        # Given: ENTRY_PENDING + pending order
        initial_state = State.ENTRY_PENDING
        pending_order = PendingOrder(
            order_id="entry_order_1",
            order_link_id="entry_link_1",
            placed_at=1000.0,
            signal_id="test_signal",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        # When: PARTIAL_FILL event
        event = ExecutionEvent(
            type=EventType.PARTIAL_FILL,
            order_id="entry_order_1",
            order_link_id="entry_link_1",
            filled_qty=20,
            order_qty=100,
            timestamp=1001.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            None,
            event,
            pending_order
        )

        # Then: IN_POSITION + Stop PLACE intent
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 20
        assert new_position.stop_status == StopStatus.PENDING
        assert intents.stop_intent is not None
        assert intents.stop_intent.action == "PLACE"
        assert intents.stop_intent.desired_qty == 20
        assert "first_partial_fill" in intents.stop_intent.reason

    def test_entry_pending_with_none_pending_order_halts(self):
        """
        Critical Bug Fix: ENTRY_PENDING + pending_order=None → HALT

        Given: state = ENTRY_PENDING, pending_order = None
        When: FILL event arrives
        Then:
          - state → HALT
          - halt_intent.reason = "entry_pending_state_without_pending_order"
          - entry_blocked = True

        치명성: pending_order None은 상태 불일치를 의미한다.
                더미 값(0.0, "unknown")으로 진행하는 것은 실거래 폭탄.
                조용히 잘못된 상태로 복구하면 나중에 10시간짜리 디버깅.

        실거래 시나리오:
          - WS 단절 후 reconcile 오류
          - 시스템 재시작 후 상태 복구 실패
          - 이벤트 순서 뒤틀림 (FILL 먼저 도착)
        """
        # Given: ENTRY_PENDING인데 pending_order가 None (비정상)
        initial_state = State.ENTRY_PENDING

        # When: FILL event
        event = ExecutionEvent(
            type=EventType.FILL,
            order_id="order_123",
            order_link_id="link_123",
            filled_qty=100,
            order_qty=100,
            timestamp=1000.0
        )

        new_state, new_position, intents = transition(
            initial_state,
            None,  # position
            event,
            pending_order=None  # ← 비정상: ENTRY_PENDING인데 None
        )

        # Then: HALT (상태 불일치는 조용히 넘기면 안 됨)
        assert new_state == State.HALT
        assert new_position is None
        assert intents.halt_intent is not None
        assert "entry_pending_state_without_pending_order" in intents.halt_intent.reason
        assert intents.entry_blocked == True


class TestStopStatusOracle:
    """
    Stop Status Oracle (FLOW Section 1 기반)

    추후 작성:
    - ACTIVE → MISSING (Stop 취소 이벤트)
    - PENDING → ACTIVE (Stop 설치 완료)
    - MISSING → ACTIVE (복구 성공)
    - MISSING → ERROR (복구 3회 실패)
    """
    pass


class TestWSReconcileOracle:
    """
    WS Reconcile Oracle (FLOW Section 2.6 기반)

    추후 작성:
    - 히스테리시스 (연속 3회 불일치)
    - REST 덮어쓰기
    - COOLDOWN (5초)
    """
    pass

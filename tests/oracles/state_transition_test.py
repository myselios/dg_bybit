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
import sys
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# src를 import path에 추가
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

# ========== Domain Models (src/domain/state.py에서 import) ==========
from domain.state import (
    State,
    StopStatus,
    Direction,
    EventType,
    ExecutionEvent,
    Position,
    PendingOrder
)

# ========== Transition Function ==========
from application.services.state_transition import (
    transition,
    TransitionIntents,
    StopIntent,
    HaltIntent
)


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

        event = ExecutionEvent(
            type=EventType.CANCEL,
            order_id="test_order_3",
            filled_qty=0,
            order_qty=100
        )

        expected_state = State.FLAT
        expected_position = None

        assert True  # Placeholder

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

        event = ExecutionEvent(
            type=EventType.CANCEL,
            order_id="test_order_4",
            filled_qty=30,
            order_qty=100
        )

        expected_state = State.IN_POSITION
        expected_position_qty = 30
        expected_stop_status = StopStatus.ACTIVE
        expected_entry_working = False

        assert True  # Placeholder

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

        event = ExecutionEvent(
            type=EventType.REJECT,
            order_id="exit_order_2",
            filled_qty=0,
            order_qty=100
        )

        expected_state = State.EXIT_PENDING  # 유지

        assert True  # Placeholder

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

        event = ExecutionEvent(
            type=EventType.CANCEL,
            order_id="exit_order_3",
            filled_qty=0,
            order_qty=100
        )

        expected_state = State.EXIT_PENDING  # 유지

        assert True  # Placeholder

    # ===== Case 9-10: stop_status 복구 로직 =====

    def test_stop_missing_recovery_success(self):
        """
        Case 9: IN_POSITION + stop_status=MISSING → 복구 성공 → ACTIVE

        Given:
          - state = IN_POSITION
          - position.qty = 100
          - stop_status = MISSING
        When: tick (복구 시도)
        Then:
          - stop_status = ACTIVE (복구 성공)
          - stop_recovery_fail_count = 0

        참조: FLOW Section 1 stop_status 관리 규칙
        """
        initial_state = State.IN_POSITION
        initial_stop_status = StopStatus.MISSING

        # 복구 성공 시뮬레이션 (FakeExchange)
        expected_stop_status = StopStatus.ACTIVE
        expected_fail_count = 0

        assert True  # Placeholder

    def test_stop_missing_recovery_fail_3_times_halt(self):
        """
        Case 10: IN_POSITION + stop_status=MISSING → 3회 실패 → ERROR → HALT

        Given:
          - state = IN_POSITION
          - stop_status = MISSING
          - stop_recovery_fail_count = 2
        When: tick (복구 시도 실패)
        Then:
          - stop_status = ERROR
          - state = HALT
          - reason = "stop_loss_unrecoverable"

        참조: FLOW Section 1 stop_status ERROR 조건
        """
        initial_state = State.IN_POSITION
        initial_stop_status = StopStatus.MISSING
        initial_fail_count = 2

        # 복구 실패 시뮬레이션
        expected_stop_status = StopStatus.ERROR
        expected_state = State.HALT
        expected_halt_reason = "stop_loss_unrecoverable"

        assert True  # Placeholder

    # ===== Case 11-13: WS DEGRADED 모드 =====

    def test_ws_degraded_flat_entry_blocked(self):
        """
        Case 11: WS DEGRADED + FLAT → entry 차단

        Given:
          - state = FLAT
          - ws_heartbeat_timeout = True (10초 초과)
        When: tick
        Then:
          - degraded_mode = True
          - entry_allowed = False

        참조: FLOW Section 2.6 WS DEGRADED Mode
        """
        initial_state = State.FLAT
        ws_heartbeat_timeout = True

        expected_degraded_mode = True
        expected_entry_allowed = False

        assert True  # Placeholder

    def test_ws_degraded_in_position_aggressive_reconcile(self):
        """
        Case 12: WS DEGRADED + IN_POSITION → reconcile interval=1초

        Given:
          - state = IN_POSITION
          - ws_event_drop_count = 3 (연속 드랍)
        When: tick
        Then:
          - degraded_mode = True
          - reconcile_interval = 1.0 (1초, 포지션 보호)
          - entry_allowed = True (IN_POSITION이므로 진입 차단 없음)

        참조: FLOW Section 2.6 WS DEGRADED Mode
        """
        initial_state = State.IN_POSITION
        ws_event_drop_count = 3

        expected_degraded_mode = True
        expected_reconcile_interval = 1.0
        expected_entry_allowed = True  # IN_POSITION은 진입 차단 대상 아님

        assert True  # Placeholder

    def test_ws_degraded_60s_timeout_halt(self):
        """
        Case 13: WS DEGRADED 60초 지속 → HALT

        Given:
          - state = FLAT (or any)
          - degraded_mode = True
          - degraded_mode_entered_at = now() - 61s
        When: tick
        Then:
          - state = HALT
          - halt_reason = "degraded_mode_timeout"

        참조: FLOW Section 2.5 DEGRADED 장기 미복구 시 HALT
        """
        initial_state = State.FLAT
        degraded_mode = True
        degraded_duration = 61  # 61초

        expected_state = State.HALT
        expected_halt_reason = "degraded_mode_timeout"

        assert True  # Placeholder

    # ===== Case 14-15: orderLinkId 검증 =====

    def test_order_link_id_length_exceeds_36_reject(self):
        """
        Case 14: orderLinkId 길이 36자 초과 → 사전 검증 실패

        Given: signal_id 생성 시 길이 36자 초과
        When: place_order 호출 전 검증
        Then:
          - assertion error or validation error
          - 주문 시도 자체 안 함

        참조: FLOW Section 8 Idempotency Key 검증
        """
        signal_id = "very_long_signal_id_that_exceeds_thirty_six_characters_limit"
        client_order_id = f"{signal_id}_Buy"  # 길이 > 36

        # 사전 검증 (길이 체크)
        assert len(client_order_id) > 36

        # TODO: 실제 구현에서 validation error 발생 검증
        # with pytest.raises(ValidationError):
        #     place_order(..., orderLinkId=client_order_id)

        assert True  # Placeholder

    def test_same_signal_retry_same_order_link_id(self):
        """
        Case 15: 동일 signal 재시도 → 동일 orderLinkId

        Given:
          - signal_id = "grid_a3f8d2e1c4_l"
          - direction = "Buy"
        When: place_order 재시도 (동일 signal)
        Then:
          - orderLinkId = "grid_a3f8d2e1c4_l_Buy" (동일)
          - Bybit가 중복 감지

        참조: FLOW Section 8 Idempotency 규칙
        """
        signal_id = "grid_a3f8d2e1c4_l"
        direction = "Buy"

        # 첫 시도
        client_order_id_1 = f"{signal_id}_{direction}"

        # 재시도
        client_order_id_2 = f"{signal_id}_{direction}"

        # 검증: 동일 ID
        assert client_order_id_1 == client_order_id_2

        # TODO: FakeExchange로 중복 감지 시뮬레이션
        assert True  # Placeholder


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
        event = ExecutionEvent(type=EventType.FILL, order_id="ghost_fill", filled_qty=10, order_qty=10)

        expected_state = State.HALT
        expected_halt_reason = "unexpected_fill_while_flat"
        expected_position = None

        assert True  # Placeholder

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

    def test_in_position_adl_should_halt(self):
        """
        Case 20: IN_POSITION + ADL → HALT

        ADL은 체결/청산이 의도와 다르게 발생한 것이라 시스템 신뢰가 깨진 상태.
        Given: state=IN_POSITION
        When: ADL event arrives
        Then:
          - state = HALT
          - halt_reason contains "adl"
          - entry_blocked = True
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
            timestamp=3100.0
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
        event = ExecutionEvent(type=EventType.LIQUIDATION, order_id="liq_event", filled_qty=0, order_qty=0)

        expected_state = State.HALT
        expected_halt_reason = "liquidated"

        assert True  # Placeholder

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
        initial_position_qty = 100
        event = ExecutionEvent(type=EventType.PARTIAL_FILL, order_id="exit_order", filled_qty=30, order_qty=100)

        expected_state = State.EXIT_PENDING
        expected_remaining_qty = 70
        expected_stop_status = StopStatus.ACTIVE  # 보통 ACTIVE 유지 + qty amend 요청

        assert True  # Placeholder

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
        event = ExecutionEvent(type=EventType.FILL, order_id="exit_order", filled_qty=70, order_qty=70)

        expected_state = State.FLAT
        expected_position = None

        assert True  # Placeholder

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
        position_qty = 50
        event = ExecutionEvent(type=EventType.FILL, order_id="exit_order", filled_qty=80, order_qty=80)

        expected_state = State.HALT
        expected_halt_reason = "overfill_exit_detected"

        assert True  # Placeholder

    # ===== Case 25-27: HALT/COOLDOWN의 "차단 규칙" =====

    def test_halt_blocks_new_entry_attempts(self):
        """
        Case 25: HALT 상태에서는 신규 진입 시도 자체가 없어야 한다.

        Given: state=HALT
        When: tick runs
        Then:
          - no place_order called
          - state remains HALT
        """
        initial_state = State.HALT
        expected_state = State.HALT
        expected_place_order_calls = 0

        assert True  # Placeholder

    def test_cooldown_blocks_entry_until_timeout(self):
        """
        Case 26: COOLDOWN 동안 FLAT로 복귀해도 entry 차단

        Given:
          - state=COOLDOWN
          - cooldown_ends_at = now() + 3s
        When: tick before timeout
        Then:
          - state remains COOLDOWN (or FLAT but entry_allowed=False; 둘 중 하나로 FLOW에 고정해야 함)
        """
        initial_state = State.COOLDOWN
        cooldown_remaining = 3

        expected_state = State.COOLDOWN  # 오라클로 고정 추천
        expected_entry_allowed = False

        assert True  # Placeholder

    def test_cooldown_timeout_returns_to_flat(self):
        """
        Case 27: COOLDOWN 만료 → FLAT

        Given:
          - state=COOLDOWN
          - cooldown_ends_at = now() - 1s
        When: tick
        Then:
          - state = FLAT
        """
        initial_state = State.COOLDOWN
        expected_state = State.FLAT

        assert True  # Placeholder

    # ===== Case 28-30: Idempotency/Validation/One-way 강제 =====

    def test_order_link_id_invalid_characters_rejected(self):
        """
        Case 28: orderLinkId 허용 문자/regex 위반 → 사전 검증 실패

        Given: client_order_id contains invalid chars (e.g. space, unicode, special)
        When: validate before sending
        Then:
          - ValidationError
          - 주문 호출 0회
        """
        client_order_id = "bad id 💥"  # 명백히 invalid
        assert True  # Placeholder

    def test_one_way_position_idx_must_be_zero_else_halt(self):
        """
        Case 29: One-way 강제 위반 (positionIdx != 0) → HALT

        Given: exchange snapshot reports positionIdx=1 or 2
        When: reconcile reads snapshot
        Then:
          - state=HALT
          - halt_reason="hedge_mode_detected"
        """
        reported_position_idx = 1

        expected_state = State.HALT
        expected_halt_reason = "hedge_mode_detected"

        assert True  # Placeholder

    def test_rest_budget_exceeded_blocks_rest_calls(self):
        """
        Case 30: REST budget 초과 → REST 호출 차단 + (선택) DEGRADED/HALT

        Given:
          - rest_budget_remaining = 0
          - ws_healthy = True (가능하면 WS로만 운영)
        When: tick wants to call REST snapshot
        Then:
          - REST call blocked
          - state unchanged (or degraded_mode true if 지속되면)
        """
        rest_budget_remaining = 0
        ws_healthy = True

        expected_rest_calls = 0
        expected_state_unchanged = True

        assert True  # Placeholder


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
        pending_order_qty = 100
        partial_filled_qty = 20

        # When: PARTIAL_FILL event
        event = ExecutionEvent(
            type=EventType.PARTIAL_FILL,
            order_id="entry_order_1",
            filled_qty=partial_filled_qty,
            order_qty=pending_order_qty
        )

        # Then: IN_POSITION + Stop PLACE intent
        expected_new_state = State.IN_POSITION
        expected_position_qty = 20
        expected_stop_intent = StopUpdateIntent(
            action="PLACE",
            desired_qty=20,
            reason="first_partial_fill_requires_immediate_stop_install"
        )

        assert True  # Placeholder

    def test_pf2_additional_fill_below_20pct_threshold_no_stop_update(self):
        """
        PF-2: 추가 체결 < 20% threshold → Stop 갱신 안 함

        Given:
          - state = IN_POSITION
          - position.qty = 20
          - stop.qty = 20 (ACTIVE)
          - last_stop_update_at = ts=1.0
        When: PARTIAL_FILL event (+3, total 23)
          - ts = 5.0 (debounce 통과)
          - delta_qty = 3
          - delta_ratio = 3/20 = 15% < 20%
        Then:
          - position.qty = 23 (업데이트)
          - stop.qty = 20 (유지)
          - stop_intent.action = "NONE"
          - reason: "delta_under_20pct_threshold_blocks_stop_update"

        근거: Rate limit 절약 (20% 미만 변화는 위험 증가 미미)
        """
        # Given: IN_POSITION with stop
        current_position_qty = 20
        current_stop_qty = 20
        last_stop_update_ts = 1.0

        # When: PARTIAL_FILL (+3, delta 15%)
        additional_fill_qty = 3
        new_position_qty = current_position_qty + additional_fill_qty
        event_ts = 5.0

        delta_qty = additional_fill_qty
        delta_ratio = delta_qty / current_stop_qty
        assert delta_ratio == 0.15  # 15% < THRESHOLD_PCT(20%)

        # Debounce check
        time_since_last_update = event_ts - last_stop_update_ts
        assert time_since_last_update >= DEBOUNCE_SEC  # debounce 통과

        # Then: NONE (threshold 미달)
        expected_stop_intent = StopUpdateIntent(
            action="NONE",
            desired_qty=None,
            reason="delta_under_20pct_threshold_blocks_stop_update"
        )

        assert True  # Placeholder

    def test_pf3_additional_fill_at_or_above_20pct_threshold_amend_stop(self):
        """
        PF-3: 추가 체결 >= 20% threshold → AMEND 우선

        Given:
          - state = IN_POSITION
          - position.qty = 20
          - stop.qty = 20 (ACTIVE)
          - last_stop_update_at = ts=1.0
        When: PARTIAL_FILL event (+4, total 24)
          - ts = 5.0 (debounce 통과)
          - delta_qty = 4
          - delta_ratio = 4/20 = 20% == threshold
        Then:
          - position.qty = 24
          - stop_intent.action = "AMEND"
          - stop_intent.desired_qty = 24
          - reason: "delta_at_or_above_20pct_triggers_amend_priority"

        근거: AMEND는 원자적(Stop 공백 없음) + rate limit 1회만 소모
        """
        # Given
        current_position_qty = 20
        current_stop_qty = 20
        last_stop_update_ts = 1.0

        # When: PARTIAL_FILL (+4, delta 20%)
        additional_fill_qty = 4
        new_position_qty = current_position_qty + additional_fill_qty
        event_ts = 5.0

        delta_qty = additional_fill_qty
        delta_ratio = delta_qty / current_stop_qty
        assert delta_ratio == 0.20  # 20% == THRESHOLD_PCT

        time_since_last_update = event_ts - last_stop_update_ts
        assert time_since_last_update >= DEBOUNCE_SEC

        # Then: AMEND
        expected_stop_intent = StopUpdateIntent(
            action="AMEND",
            desired_qty=24,
            reason="delta_at_or_above_20pct_triggers_amend_priority"
        )

        assert True  # Placeholder

    def test_pf4_debounce_blocks_rapid_amends_and_coalesces_to_last_qty(self):
        """
        PF-4: Debounce(2s) → 연속 AMEND 차단 + 최종 qty로 coalescing

        Given:
          - state = IN_POSITION
          - position.qty = 20
          - stop.qty = 20 (ACTIVE)
          - last_stop_update_at = ts=1.0
        When: 연속 PARTIAL_FILL events (threshold 모두 통과)
          - Event A: ts=3.0, +4 (total 24, delta 20%)
          - Event B: ts=4.0, +6 (total 30, delta 25%)
        Then:
          - Event A (ts=3.0):
              - time_since_last = 2.0s → debounce 통과 → AMEND to 24 scheduled
          - Event B (ts=4.0):
              - time_since_last = 1.0s < 2.0s → debounce 차단
              - 기존 pending AMEND를 24→30으로 update (coalescing)
          - 최종 AMEND call count = 1 (30으로)

        근거: Rate limit 보호 + 최신 qty 반영
        """
        # Given
        initial_position_qty = 20
        initial_stop_qty = 20
        last_stop_update_ts = 1.0

        # Event sequence
        events = [
            TimedExecutionEvent(
                ts=3.0,
                event=ExecutionEvent(
                    type=EventType.PARTIAL_FILL,
                    order_id="entry_1",
                    filled_qty=4,  # +4 (total 24)
                    order_qty=100
                )
            ),
            TimedExecutionEvent(
                ts=4.0,
                event=ExecutionEvent(
                    type=EventType.PARTIAL_FILL,
                    order_id="entry_1",
                    filled_qty=6,  # +6 (total 30)
                    order_qty=100
                )
            )
        ]

        # Then: Single AMEND to final qty
        expected_stop_amend_call_count = 1
        expected_final_amend_qty = 30
        expected_reason = "debounce_coalesced_multiple_fills_to_final_qty"

        assert True  # Placeholder

    def test_pf5_amend_reject_should_retry_amend_not_immediate_cancel_place(self):
        """
        PF-5: AMEND 거절 → AMEND 재시도 (즉시 cancel+place 금지)

        Given:
          - state = IN_POSITION
          - position.qty = 20 → 24 (PARTIAL_FILL)
          - stop.qty = 20 (ACTIVE)
          - AMEND intent issued (qty 24)
        When: AMEND 거절 (rate limit / temporary error)
          - amend_fail_count = 1 (< 2)
          - next tick
        Then:
          - next_intent.action = "AMEND" (재시도)
          - next_intent.desired_qty = 24
          - reason: "amend_rejected_retry_amend_before_cancel_place"
          - cancel+place 사용 안 함 (fail_count < 2)

        근거: AMEND 실패 대부분 일시적 (rate limit, network glitch)
              cancel+place는 Stop 공백 위험 → 최후 수단
        """
        # Given: AMEND attempt failed once
        current_position_qty = 24
        current_stop_qty = 20
        amend_fail_count = 1

        # When: Decide next action
        # (amend_fail_count < 2 → retry AMEND)

        # Then: AMEND retry
        expected_next_intent = StopUpdateIntent(
            action="AMEND",
            desired_qty=24,
            reason="amend_rejected_retry_amend_before_cancel_place"
        )

        assert amend_fail_count < 2
        assert True  # Placeholder

    def test_pf6_cancel_place_only_when_amend_impossible_or_stop_missing(self):
        """
        PF-6: Cancel+Place는 최후 수단 (Stop 공백 위험)

        허용 조건 (OR):
        A) stop_status = MISSING (Stop이 아예 없음)
        B) AMEND 응답 = ORDER_NOT_FOUND (Stop이 사라짐)
        C) amend_fail_count >= 2 + debounce 통과 (연속 실패 → 구조적 문제)

        Given:
          - Scenario A: stop_status = MISSING
        When: position.qty changed (threshold 통과)
        Then:
          - stop_intent.action = "CANCEL_AND_PLACE" (사실상 PLACE)
          - reason: "stop_missing_requires_cancel_place_or_place"

        Given:
          - Scenario C: amend_fail_count = 2
        When: position.qty changed + debounce 통과
        Then:
          - stop_intent.action = "CANCEL_AND_PLACE"
          - reason: "amend_repeated_failures_force_cancel_place_as_last_resort"

        위험: Cancel→Place 사이 Stop 공백 (수백ms ~ 초)
              → 이 구간에 급변동 시 무방비
        """
        # Scenario A: MISSING stop
        scenario_a_stop_status = StopStatus.MISSING
        scenario_a_position_qty = 30

        expected_scenario_a_intent = StopUpdateIntent(
            action="CANCEL_AND_PLACE",
            desired_qty=30,
            reason="stop_missing_requires_cancel_place_or_place"
        )

        # Scenario C: amend_fail_count >= 2
        scenario_c_amend_fail_count = 2
        scenario_c_position_qty = 30
        scenario_c_stop_qty = 20

        expected_scenario_c_intent = StopUpdateIntent(
            action="CANCEL_AND_PLACE",
            desired_qty=30,
            reason="amend_repeated_failures_force_cancel_place_as_last_resort"
        )

        assert scenario_a_stop_status == StopStatus.MISSING
        assert scenario_c_amend_fail_count >= 2
        assert True  # Placeholder


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

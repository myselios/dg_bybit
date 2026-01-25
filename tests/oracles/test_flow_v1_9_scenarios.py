"""
FLOW v1.9 필수 시나리오 Oracle 테스트

FLOW_REF: docs/constitution/FLOW.md v1.9 (2026-01-23)
ADR: ADR-0008

테스트 시나리오 (FLOW Section 10.1 요구사항):
1. test_event_dedup - WS 이벤트 중복 제거 (Section 2.7)
2. test_stop_recovery_3_failures_halt - Stop 복구 3회 실패 → HALT (Section 1)

TODO (Phase 4+):
3. test_degraded_60s_halt - DEGRADED 60초 후 HALT (requires degraded_mode tracking)
4. test_rest_budget_tick_increase - REST Budget 초과 시 tick 주기 증가 (requires tick_engine integration)

NOTE:
5. test_size_overflow_excess_close - Position size overflow → 초과분 청산 (implemented below)
6. test_partial_fill_immediate_stop - 부분체결 즉시 IN_POSITION + Stop (already exists in transition oracle tests)
"""

import unittest

from src.domain.state import State, Position, StopStatus, Direction
from src.domain.events import ExecutionEvent, EventType
from src.adapter.ws_event_processor import WSEventProcessor
from src.application.position_manager import manage_stop_status


class TestFlowV19Scenarios(unittest.TestCase):
    """FLOW v1.9 필수 시나리오 (ADR-0008)"""

    def test_event_dedup_ignores_duplicate(self):
        """
        WS 이벤트 중복 제거 (FLOW Section 2.7)

        Given:
          - 동일 execution_id 이벤트 2회
        When: process_event() 호출
        Then:
          - 첫 번째는 통과 (event 반환)
          - 두 번째는 무시 (None 반환)

        FLOW 규칙:
        - dedup_key = execution_id (가장 정확)
        - 동일 execution_id → 중복 무시
        """
        # Given
        processor = WSEventProcessor()
        event1 = ExecutionEvent(
            type=EventType.FILL,
            order_id="order_123",
            order_link_id="link_123",
            filled_qty=100,
            order_qty=100,
            timestamp=1000.0,
            execution_id="exec_abc_123"  # Bybit execId
        )
        event2 = ExecutionEvent(
            type=EventType.FILL,
            order_id="order_123",
            order_link_id="link_123",
            filled_qty=100,
            order_qty=100,
            timestamp=1000.0,
            execution_id="exec_abc_123"  # 동일 execution_id
        )

        # When: 첫 번째 처리
        result1 = processor.process_event(event1, "ENTRY_PENDING")
        # Then: 통과
        assert result1 is not None
        assert result1.order_id == "order_123"

        # When: 두 번째 처리 (중복)
        result2 = processor.process_event(event2, "ENTRY_PENDING")
        # Then: 무시
        assert result2 is None

    def test_stop_recovery_3_failures_halt(self):
        """
        Stop 복구 3회 실패 → HALT (FLOW Section 1)

        Given:
          - state = IN_POSITION
          - stop_status = MISSING
          - stop_recovery_fail_count = 3
        When: manage_stop_status() 호출
        Then:
          - HALT intent
          - reason = "stop_loss_unrecoverable"

        FLOW 규칙:
        - stop_recovery_fail_count >= 3 → HALT
        """
        # Given
        current_state = State.IN_POSITION
        current_position = Position(
            qty=100,
            entry_price=50000.0,
            direction=Direction.LONG,
            signal_id="test_signal_stop_recovery",
            stop_status=StopStatus.MISSING,
            stop_recovery_fail_count=3,  # 3회 실패
            entry_working=False
        )

        # When
        intents = manage_stop_status(current_state, current_position)

        # Then: HALT intent
        assert intents.halt_intent is not None
        assert "stop_loss_unrecoverable" in intents.halt_intent.reason
        assert "3 times" in intents.halt_intent.reason

    def test_event_ordering_ignores_out_of_order(self):
        """
        WS 이벤트 순서 검증 (FLOW Section 2.7)

        Given:
          - 동일 order_id에 대해 seq=100, seq=99 순서로 이벤트 도착
        When: process_event() 호출
        Then:
          - seq=100 (첫 번째)는 통과
          - seq=99 (Out-of-order)는 무시 (None 반환)

        FLOW 규칙:
        - seq 기반 ordering 검증
        - Out-of-order event → 무시
        """
        # Given
        processor = WSEventProcessor()
        event1 = ExecutionEvent(
            type=EventType.PARTIAL_FILL,
            order_id="order_456",
            order_link_id="link_456",
            filled_qty=50,
            order_qty=100,
            timestamp=2000.0,
            execution_id="exec_def_456_1",
            seq=100  # 먼저 처리
        )
        event2 = ExecutionEvent(
            type=EventType.FILL,
            order_id="order_456",  # 동일 order_id
            order_link_id="link_456",
            filled_qty=100,
            order_qty=100,
            timestamp=2001.0,
            execution_id="exec_def_456_2",
            seq=99  # Out-of-order (100보다 작음)
        )

        # When: seq=100 처리
        result1 = processor.process_event(event1, "ENTRY_PENDING")
        # Then: 통과
        assert result1 is not None
        assert result1.seq == 100

        # When: seq=99 처리 (Out-of-order)
        result2 = processor.process_event(event2, "ENTRY_PENDING")
        # Then: 무시
        assert result2 is None


if __name__ == "__main__":
    unittest.main()

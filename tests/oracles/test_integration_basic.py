"""
기본 통합 테스트 — FakeExchange + EventRouter 동작 검증

목적:
1. FakeExchange가 이벤트를 올바르게 생성하는지 검증
2. EventRouter가 상태 전환을 올바르게 수행하는지 검증
3. oracle 테스트의 기반 확인
"""

import pytest

from infrastructure.exchange.fake_exchange import FakeExchange, DuplicateOrderError
from domain.state import State, StopStatus, Direction, EventType, PendingOrder
from application.event_router import EventRouter


class TestBasicIntegration:
    """기본 통합 테스트 — FakeExchange + EventRouter"""

    def test_fake_exchange_place_order(self):
        """FakeExchange: 주문 생성 및 조회"""
        fake = FakeExchange()

        # 주문
        order = fake.place_order(
            symbol="BTCUSDT",
            side="Buy",
            qty=100,
            price=50000,
            order_link_id="test_order_1"
        )

        # 검증
        assert order.order_id is not None
        assert order.qty == 100
        assert order.order_link_id == "test_order_1"
        assert order.status.value == "New"

        # 조회
        retrieved = fake.get_order_by_link_id("test_order_1")
        assert retrieved is not None
        assert retrieved.order_id == order.order_id

    def test_fake_exchange_duplicate_order_link_id(self):
        """FakeExchange: orderLinkId 중복 거절"""
        fake = FakeExchange()

        # 첫 주문
        fake.place_order(
            symbol="BTCUSDT",
            side="Buy",
            qty=100,
            price=50000,
            order_link_id="test_order_1"
        )

        # 중복 주문 시도
        with pytest.raises(DuplicateOrderError):
            fake.place_order(
                symbol="BTCUSDT",
                side="Buy",
                qty=50,
                price=50100,
                order_link_id="test_order_1"  # 중복
            )

    def test_fake_exchange_scenario_fill(self):
        """FakeExchange: FILL 시나리오"""
        fake = FakeExchange()

        # 시나리오 설정
        fake.set_scenario("fill")

        # 주문
        order = fake.place_order(
            symbol="BTCUSDT",
            side="Buy",
            qty=100,
            price=50000,
            order_link_id="test_order_fill"
        )

        # 이벤트 확인
        events = fake.tick()
        assert len(events) == 1
        assert events[0].type == EventType.FILL
        assert events[0].filled_qty == 100

        # 주문 상태 확인
        assert order.status.value == "Filled"
        assert order.filled_qty == 100

    def test_fake_exchange_scenario_partial_fill(self):
        """FakeExchange: PARTIAL_FILL 시나리오"""
        fake = FakeExchange()

        # 시나리오 설정 (20 체결)
        fake.set_scenario("partial_fill", filled_qty=20)

        # 주문
        order = fake.place_order(
            symbol="BTCUSDT",
            side="Buy",
            qty=100,
            price=50000,
            order_link_id="test_order_partial"
        )

        # 이벤트 확인
        events = fake.tick()
        assert len(events) == 1
        assert events[0].type == EventType.PARTIAL_FILL
        assert events[0].filled_qty == 20
        assert events[0].order_qty == 100

        # 주문 상태 확인
        assert order.status.value == "PartiallyFilled"
        assert order.filled_qty == 20

    def test_event_router_entry_pending_to_in_position_on_fill(self):
        """EventRouter: ENTRY_PENDING + FILL → IN_POSITION"""
        router = EventRouter()

        # Given: ENTRY_PENDING
        current_state = State.ENTRY_PENDING
        current_position = None
        pending_order = PendingOrder(
            order_id="test_order_1",
            order_link_id="test_order_link_1",
            placed_at=1000.0,
            signal_id="signal_1",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        # When: FILL event
        from domain.state import ExecutionEvent as DomainExecutionEvent
        event = DomainExecutionEvent(
            type=EventType.FILL,
            order_id="test_order_1",
            order_link_id="test_order_link_1",
            filled_qty=100,
            order_qty=100,
            timestamp=1001.0
        )

        new_state, new_position, intents = router.handle_event(
            current_state, current_position, event, pending_order
        )

        # Then: IN_POSITION
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 100
        assert new_position.entry_price == 50000.0
        assert new_position.direction == Direction.LONG
        assert new_position.stop_status == StopStatus.PENDING
        assert new_position.entry_working is False

    def test_event_router_entry_pending_to_in_position_on_partial_fill(self):
        """EventRouter: ENTRY_PENDING + PARTIAL_FILL → IN_POSITION (entry_working=True)"""
        router = EventRouter()

        # Given: ENTRY_PENDING
        current_state = State.ENTRY_PENDING
        current_position = None
        pending_order = PendingOrder(
            order_id="test_order_2",
            order_link_id="test_order_link_2",
            placed_at=1000.0,
            signal_id="signal_2",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        # When: PARTIAL_FILL event
        from domain.state import ExecutionEvent as DomainExecutionEvent
        event = DomainExecutionEvent(
            type=EventType.PARTIAL_FILL,
            order_id="test_order_2",
            order_link_id="test_order_link_2",
            filled_qty=20,
            order_qty=100,
            timestamp=1001.0
        )

        new_state, new_position, intents = router.handle_event(
            current_state, current_position, event, pending_order
        )

        # Then: IN_POSITION + entry_working=True
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 20  # filled_qty
        assert new_position.entry_working is True  # 잔량 활성
        assert new_position.stop_status == StopStatus.PENDING

    def test_event_router_entry_pending_to_flat_on_reject(self):
        """EventRouter: ENTRY_PENDING + REJECT → FLAT"""
        router = EventRouter()

        # Given: ENTRY_PENDING
        current_state = State.ENTRY_PENDING
        current_position = None
        pending_order = PendingOrder(
            order_id="test_order_3",
            order_link_id="test_order_link_3",
            placed_at=1000.0,
            signal_id="signal_3",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        # When: REJECT event
        from domain.state import ExecutionEvent as DomainExecutionEvent
        event = DomainExecutionEvent(
            type=EventType.REJECT,
            order_id="test_order_3",
            order_link_id="test_order_link_3",
            filled_qty=0,
            order_qty=100,
            timestamp=1001.0
        )

        new_state, new_position, intents = router.handle_event(
            current_state, current_position, event, pending_order
        )

        # Then: FLAT
        assert new_state == State.FLAT
        assert new_position is None

    def test_event_router_entry_pending_to_flat_on_cancel_zero_fill(self):
        """EventRouter: ENTRY_PENDING + CANCEL (filled_qty=0) → FLAT"""
        router = EventRouter()

        # Given: ENTRY_PENDING
        current_state = State.ENTRY_PENDING
        current_position = None
        pending_order = PendingOrder(
            order_id="test_order_4",
            order_link_id="test_order_link_4",
            placed_at=1000.0,
            signal_id="signal_4",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        # When: CANCEL event (filled_qty=0)
        from domain.state import ExecutionEvent as DomainExecutionEvent
        event = DomainExecutionEvent(
            type=EventType.CANCEL,
            order_id="test_order_4",
            order_link_id="test_order_link_4",
            filled_qty=0,
            order_qty=100,
            timestamp=1001.0
        )

        new_state, new_position, intents = router.handle_event(
            current_state, current_position, event, pending_order
        )

        # Then: FLAT
        assert new_state == State.FLAT
        assert new_position is None

    def test_event_router_entry_pending_to_in_position_on_cancel_partial_fill(self):
        """EventRouter: ENTRY_PENDING + CANCEL (filled_qty>0) → IN_POSITION"""
        router = EventRouter()

        # Given: ENTRY_PENDING
        current_state = State.ENTRY_PENDING
        current_position = None
        pending_order = PendingOrder(
            order_id="test_order_5",
            order_link_id="test_order_link_5",
            placed_at=1000.0,
            signal_id="signal_5",
            qty=100,
            price=50000.0,
            side="Buy"
        )

        # When: CANCEL event (filled_qty=30, 부분체결 후 취소)
        from domain.state import ExecutionEvent as DomainExecutionEvent
        event = DomainExecutionEvent(
            type=EventType.CANCEL,
            order_id="test_order_5",
            order_link_id="test_order_link_5",
            filled_qty=30,
            order_qty=100,
            timestamp=1001.0
        )

        new_state, new_position, intents = router.handle_event(
            current_state, current_position, event, pending_order
        )

        # Then: IN_POSITION (부분체결됨)
        assert new_state == State.IN_POSITION
        assert new_position is not None
        assert new_position.qty == 30
        assert new_position.entry_working is False  # 잔량 취소됨
        assert new_position.stop_status == StopStatus.PENDING

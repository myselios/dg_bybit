"""
FakeExchange — 테스트용 거래소 시뮬레이터

목적:
1. 실거래 시나리오 재현 (PARTIAL_FILL, REJECT, CANCEL, latency)
2. orderLinkId 중복 체크
3. 이벤트 시뮬레이션 (테스트 제어 가능)
4. WebSocket 이벤트 스트림 흉내
5. Stop 명령 호출 기록 (oracle 테스트용)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Tuple, Any
from collections import deque
import time

from domain.state import EventType, ExecutionEvent


class OrderStatus(Enum):
    """주문 상태 (Bybit 기준)"""
    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"


class StopOrderResult(Enum):
    """Stop 주문 결과 (oracle 테스트용)"""
    OK = "OK"
    REJECTED = "REJECTED"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMIT = "RATE_LIMIT"


@dataclass
class Order:
    """주문 상태"""
    order_id: str
    order_link_id: str
    symbol: str
    side: str  # "Buy" or "Sell"
    order_type: str  # "Limit", "Market"
    qty: int
    price: Optional[float]
    status: OrderStatus
    filled_qty: int = 0
    created_at: float = field(default_factory=time.time)

    # Conditional Order 파라미터
    trigger_price: Optional[str] = None
    trigger_direction: Optional[int] = None
    trigger_by: Optional[str] = None

    # 속성
    reduce_only: bool = False
    position_idx: int = 0


class FakeExchange:
    """
    테스트용 거래소 시뮬레이터

    특징:
    - 주문 저장 (in-memory)
    - orderLinkId 중복 체크
    - 이벤트 시뮬레이션 (시나리오 기반)
    - 시간 제어 (tick)
    - Stop 명령 호출 기록 (oracle 테스트용)
    """

    def __init__(self):
        self.orders: Dict[str, Order] = {}  # order_id → Order
        self.orders_by_link_id: Dict[str, str] = {}  # order_link_id → order_id
        self.event_queue: deque[ExecutionEvent] = deque()

        # 시나리오 훅 (테스트에서 주입)
        self.scenario: Optional[Dict] = None
        self.scenario_trigger: Optional[Callable] = None

        # 시뮬레이션 상태
        self.current_time = time.time()
        self.order_counter = 1000

        # 호출 기록 (oracle 테스트용)
        self.calls: List[Tuple[str, float, Dict[str, Any]]] = []  # (method, ts, params)

        # 실패 주입 플래그 (oracle 테스트용)
        self.inject_stop_place_reject: bool = False
        self.inject_stop_amend_reject: bool = False
        self.inject_stop_amend_not_found: bool = False
        self.inject_stop_amend_rate_limit: bool = False

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: Optional[float] = None,
        order_type: str = "Limit",
        order_link_id: Optional[str] = None,
        trigger_price: Optional[str] = None,
        trigger_direction: Optional[int] = None,
        trigger_by: str = "LastPrice",
        reduce_only: bool = False,
        position_idx: int = 0,
        **kwargs
    ) -> Order:
        """
        주문 생성 (FakeExchange 시뮬레이션)

        중복 체크:
        - orderLinkId가 이미 존재하면 DuplicateOrderError

        시나리오 적용:
        - REJECT 시나리오: 즉시 거절
        - FILL/PARTIAL_FILL: 이벤트 큐에 추가 (tick에서 발생)
        """
        # orderLinkId 검증 (FLOW Section 8)
        if order_link_id:
            if len(order_link_id) > 36:
                raise ValueError(f"orderLinkId too long: {len(order_link_id)} > 36")

            # 중복 체크
            if order_link_id in self.orders_by_link_id:
                existing_order_id = self.orders_by_link_id[order_link_id]
                raise DuplicateOrderError(
                    f"Order with orderLinkId={order_link_id} already exists: {existing_order_id}"
                )

        # 주문 ID 생성
        order_id = f"fake_order_{self.order_counter}"
        self.order_counter += 1

        # 주문 객체 생성
        order = Order(
            order_id=order_id,
            order_link_id=order_link_id or "",
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            price=price,
            status=OrderStatus.NEW,
            trigger_price=trigger_price,
            trigger_direction=trigger_direction,
            trigger_by=trigger_by,
            reduce_only=reduce_only,
            position_idx=position_idx
        )

        # 저장
        self.orders[order_id] = order
        if order_link_id:
            self.orders_by_link_id[order_link_id] = order_id

        # 시나리오 적용 (테스트 훅)
        if self.scenario:
            self._apply_scenario(order)

        return order

    def _apply_scenario(self, order: Order):
        """
        시나리오 적용 (테스트에서 주입한 동작)

        시나리오 타입:
        - "reject": 즉시 거절
        - "fill": tick에서 완전 체결 이벤트
        - "partial_fill": tick에서 부분 체결 이벤트
        - "cancel": tick에서 취소 이벤트
        - "latency": 지연 후 체결
        """
        scenario_type = self.scenario.get("type")

        if scenario_type == "reject":
            # 즉시 거절
            order.status = OrderStatus.REJECTED

            # 이벤트 큐에 REJECT 추가
            event = ExecutionEvent(
                type=EventType.REJECT,
                order_id=order.order_id,
                order_link_id=order.order_link_id,
                filled_qty=0,
                order_qty=order.qty,
                timestamp=self.current_time
            )
            self.event_queue.append(event)

        elif scenario_type == "fill":
            # tick에서 완전 체결 예약
            delay = self.scenario.get("delay", 0)

            def fill_callback():
                order.status = OrderStatus.FILLED
                order.filled_qty = order.qty

                event = ExecutionEvent(
                    type=EventType.FILL,
                    order_id=order.order_id,
                    order_link_id=order.order_link_id,
                    filled_qty=order.qty,
                    order_qty=order.qty,
                    timestamp=self.current_time
                )
                self.event_queue.append(event)

            # 지연 없으면 즉시, 있으면 tick에서
            if delay == 0:
                fill_callback()

        elif scenario_type == "partial_fill":
            # tick에서 부분 체결 예약
            filled_qty = self.scenario.get("filled_qty", order.qty // 2)

            def partial_fill_callback():
                order.status = OrderStatus.PARTIALLY_FILLED
                order.filled_qty = filled_qty

                event = ExecutionEvent(
                    type=EventType.PARTIAL_FILL,
                    order_id=order.order_id,
                    order_link_id=order.order_link_id,
                    filled_qty=filled_qty,
                    order_qty=order.qty,
                    timestamp=self.current_time
                )
                self.event_queue.append(event)

            partial_fill_callback()

        elif scenario_type == "cancel":
            # tick에서 취소 예약
            filled_qty = self.scenario.get("filled_qty", 0)  # 취소 전 부분체결 여부

            def cancel_callback():
                order.status = OrderStatus.CANCELLED
                order.filled_qty = filled_qty

                event = ExecutionEvent(
                    type=EventType.CANCEL,
                    order_id=order.order_id,
                    order_link_id=order.order_link_id,
                    filled_qty=filled_qty,
                    order_qty=order.qty,
                    timestamp=self.current_time
                )
                self.event_queue.append(event)

            cancel_callback()

    def get_order(self, order_id: str) -> Optional[Order]:
        """주문 조회 (order_id)"""
        return self.orders.get(order_id)

    def get_order_by_link_id(self, order_link_id: str) -> Optional[Order]:
        """주문 조회 (orderLinkId)"""
        order_id = self.orders_by_link_id.get(order_link_id)
        if order_id:
            return self.orders[order_id]
        return None

    def tick(self) -> List[ExecutionEvent]:
        """
        시간 진행 (이벤트 발생)

        Returns:
            발생한 이벤트 리스트
        """
        self.current_time += 1.0

        # 이벤트 큐에서 모든 이벤트 반환
        events = list(self.event_queue)
        self.event_queue.clear()

        return events

    def set_scenario(self, scenario_type: str, **kwargs):
        """
        시나리오 설정 (테스트 훅)

        Examples:
            fake.set_scenario("reject")
            fake.set_scenario("fill", delay=0)
            fake.set_scenario("partial_fill", filled_qty=20)
            fake.set_scenario("cancel", filled_qty=0)
        """
        self.scenario = {"type": scenario_type, **kwargs}

    def clear_scenario(self):
        """시나리오 초기화"""
        self.scenario = None

    # ========== Stop Order Methods (Oracle 테스트용) ==========

    def place_stop_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        trigger_price: str,
        trigger_direction: int,
        trigger_by: str = "LastPrice",
        order_link_id: Optional[str] = None,
        **kwargs
    ) -> Tuple[StopOrderResult, Optional[Order]]:
        """
        Stop Loss 주문 생성 (Conditional Market Order)

        Args:
            symbol: 심볼
            side: "Buy" or "Sell"
            qty: 수량
            trigger_price: 트리거 가격
            trigger_direction: 1 (rising) or 2 (falling)
            trigger_by: "LastPrice" (기본값)
            order_link_id: orderLinkId

        Returns:
            (StopOrderResult, Order or None)
        """
        # 호출 기록
        self.calls.append((
            "place_stop_order",
            self.current_time,
            {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "trigger_price": trigger_price,
                "trigger_direction": trigger_direction,
                "order_link_id": order_link_id
            }
        ))

        # 실패 주입
        if self.inject_stop_place_reject:
            return (StopOrderResult.REJECTED, None)

        # 성공: place_order 재사용
        try:
            order = self.place_order(
                symbol=symbol,
                side=side,
                qty=qty,
                price=None,
                order_type="Market",
                order_link_id=order_link_id,
                trigger_price=trigger_price,
                trigger_direction=trigger_direction,
                trigger_by=trigger_by,
                reduce_only=True,
                position_idx=0,
                **kwargs
            )
            return (StopOrderResult.OK, order)
        except Exception:
            return (StopOrderResult.REJECTED, None)

    def amend_stop_order(
        self,
        order_id: Optional[str] = None,
        order_link_id: Optional[str] = None,
        qty: Optional[int] = None,
        trigger_price: Optional[str] = None,
        **kwargs
    ) -> StopOrderResult:
        """
        Stop Loss 주문 수정 (AMEND)

        Args:
            order_id: 주문 ID
            order_link_id: orderLinkId
            qty: 수정할 수량
            trigger_price: 수정할 트리거 가격

        Returns:
            StopOrderResult
        """
        # 호출 기록
        self.calls.append((
            "amend_stop_order",
            self.current_time,
            {
                "order_id": order_id,
                "order_link_id": order_link_id,
                "qty": qty,
                "trigger_price": trigger_price
            }
        ))

        # 실패 주입 (우선순위: NOT_FOUND > RATE_LIMIT > REJECT)
        if self.inject_stop_amend_not_found:
            return StopOrderResult.NOT_FOUND

        if self.inject_stop_amend_rate_limit:
            return StopOrderResult.RATE_LIMIT

        if self.inject_stop_amend_reject:
            return StopOrderResult.REJECTED

        # 주문 조회
        order = None
        if order_id:
            order = self.get_order(order_id)
        elif order_link_id:
            order = self.get_order_by_link_id(order_link_id)

        if not order:
            return StopOrderResult.NOT_FOUND

        # 수정
        if qty is not None:
            order.qty = qty
        if trigger_price is not None:
            order.trigger_price = trigger_price

        return StopOrderResult.OK

    def cancel_stop_order(
        self,
        order_id: Optional[str] = None,
        order_link_id: Optional[str] = None,
        **kwargs
    ) -> StopOrderResult:
        """
        Stop Loss 주문 취소

        Args:
            order_id: 주문 ID
            order_link_id: orderLinkId

        Returns:
            StopOrderResult
        """
        # 호출 기록
        self.calls.append((
            "cancel_stop_order",
            self.current_time,
            {
                "order_id": order_id,
                "order_link_id": order_link_id
            }
        ))

        # 주문 조회
        order = None
        if order_id:
            order = self.get_order(order_id)
        elif order_link_id:
            order = self.get_order_by_link_id(order_link_id)

        if not order:
            return StopOrderResult.NOT_FOUND

        # 취소
        order.status = OrderStatus.CANCELLED

        # 이벤트 큐에 CANCEL 추가
        event = ExecutionEvent(
            type=EventType.CANCEL,
            order_id=order.order_id,
            order_link_id=order.order_link_id,
            filled_qty=order.filled_qty,
            order_qty=order.qty,
            timestamp=self.current_time
        )
        self.event_queue.append(event)

        return StopOrderResult.OK

    def reset(self):
        """상태 초기화 (테스트 간 격리)"""
        self.orders.clear()
        self.orders_by_link_id.clear()
        self.event_queue.clear()
        self.scenario = None
        self.order_counter = 1000
        self.calls.clear()
        self.inject_stop_place_reject = False
        self.inject_stop_amend_reject = False
        self.inject_stop_amend_not_found = False
        self.inject_stop_amend_rate_limit = False


class DuplicateOrderError(Exception):
    """중복 주문 예외 (orderLinkId 중복)"""
    pass

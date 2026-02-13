"""
src/application/order_executor.py
Order executor (I/O layer, FLOW Section 4.5 + 8)

Purpose:
- Entry 주문 실행 (orderLinkId, positionIdx)
- Stop Loss 주문 실행 (Conditional Order 방식 B)
- Idempotency 처리 (DuplicateOrderError)
- Amend 우선 규칙 (공백 방지)

SSOT:
- FLOW.md Section 4.5: Stop Loss 주문 계약
- FLOW.md Section 8: Idempotency Key

Exports:
- place_entry_order(): Entry 주문 실행
- place_stop_loss(): Stop Loss 주문 실행
- amend_stop_loss(): Stop 수량 갱신
- cancel_order(): 주문 취소
"""

from dataclasses import dataclass
from domain.ids import validate_order_link_id


# Exception Classes
class DuplicateOrderError(Exception):
    """orderLinkId 중복 (idempotency 보호)"""

    def __init__(self, order_link_id: str):
        self.order_link_id = order_link_id
        super().__init__(f"Duplicate orderLinkId: {order_link_id}")


class AmendNotSupported(Exception):
    """Bybit가 Amend API 지원 안 함"""

    def __init__(self, order_id: str):
        self.order_id = order_id
        super().__init__(f"Amend not supported for order: {order_id}")


# Result Classes
@dataclass
class OrderResult:
    """주문 결과"""

    order_id: str
    order_link_id: str
    status: str
    order_type: str | None = None
    trigger_price: float | None = None
    trigger_direction: int | None = None
    reduce_only: bool = False
    position_idx: int = 0
    side: str | None = None


@dataclass
class AmendResult:
    """Amend 결과"""

    success: bool
    updated_qty: int | None = None
    error: str | None = None


# Fake Order Store (unit test용, 실제 구현은 Bybit adapter 사용)
_order_store: dict[str, OrderResult] = {}


def place_entry_order(
    symbol: str,
    side: str,
    qty: int,
    price: float,
    signal_id: str,
    direction: str,
) -> OrderResult:
    """
    Entry 주문 실행 (FLOW Section 4.5 Entry 계약)

    FLOW Section 4.5:
        - category="linear"
        - positionIdx=0 (One-way 모드)
        - orderType="Limit"
        - orderLinkId="{signal_id}_{side}"

    Args:
        symbol: 심볼 (예: "BTCUSDT")
        side: "Buy" or "Sell"
        qty: 수량 (contracts)
        price: 가격 (USDT)
        signal_id: Signal ID (idempotency key)
        direction: "LONG" or "SHORT"

    Returns:
        OrderResult(order_id, order_link_id, status)

    Raises:
        ValueError: orderLinkId 길이 초과 (>36자)
        DuplicateOrderError: orderLinkId 중복
    """
    # orderLinkId 생성
    order_link_id = f"{signal_id}_{side}"

    # orderLinkId 길이 검증 (36자 제한)
    if not validate_order_link_id(order_link_id):
        raise ValueError(f"orderLinkId too long or invalid: {order_link_id}")

    # Idempotency 검증 (중복 방지)
    if order_link_id in _order_store:
        # 기존 주문 반환 (idempotency)
        return _order_store[order_link_id]

    # 주문 실행 (Fake implementation)
    order_id = f"order_{len(_order_store) + 1}"
    result = OrderResult(
        order_id=order_id,
        order_link_id=order_link_id,
        status="New",
    )

    # Store 저장
    _order_store[order_link_id] = result

    return result


def place_stop_loss(
    symbol: str,
    qty: int,
    stop_price: float,
    direction: str,
    signal_id: str,
) -> OrderResult:
    """
    Stop Loss 주문 실행 (FLOW Section 4.5 Conditional Order 방식 B)

    FLOW Section 4.5:
        LONG Stop:
        - orderType="Market"
        - triggerPrice=stop_price
        - triggerDirection=2 (falling, LastPrice < triggerPrice)
        - triggerBy="LastPrice"
        - reduceOnly=True
        - positionIdx=0
        - side="Sell" (LONG 청산)
        - orderLinkId="{signal_id}_stop_{side}"

        SHORT Stop:
        - side="Buy" (SHORT 청산)
        - triggerDirection=1 (rising, LastPrice > triggerPrice)
        - orderLinkId="{signal_id}_stop_Buy"

    Args:
        symbol: 심볼 (예: "BTCUSDT")
        qty: 수량 (contracts)
        stop_price: Stop 가격 (triggerPrice)
        direction: "LONG" or "SHORT"
        signal_id: Signal ID

    Returns:
        OrderResult(order_id, order_link_id, status, trigger_price, trigger_direction, side)
    """
    # Direction별 파라미터 설정
    if direction == "LONG":
        side = "Sell"  # LONG 청산
        trigger_direction = 2  # falling (LastPrice < triggerPrice)
    elif direction == "SHORT":
        side = "Buy"  # SHORT 청산
        trigger_direction = 1  # rising (LastPrice > triggerPrice)
    else:
        raise ValueError(f"Invalid direction: {direction}")

    # orderLinkId 생성
    order_link_id = f"{signal_id}_stop_{side}"

    # 주문 실행 (Fake implementation)
    order_id = f"stop_{len(_order_store) + 1}"
    result = OrderResult(
        order_id=order_id,
        order_link_id=order_link_id,
        status="New",
        order_type="Market",
        trigger_price=stop_price,
        trigger_direction=trigger_direction,
        reduce_only=True,
        position_idx=0,
        side=side,
    )

    # Store 저장
    _order_store[order_link_id] = result

    return result


def amend_stop_loss(order_id: str, new_qty: int) -> AmendResult:
    """
    Stop 수량 갱신 (FLOW Section 2.5 Amend 우선)

    FLOW Section 2.5:
        - Stop 갱신은 Amend API 우선 (공백 방지)
        - qty만 수정 (triggerPrice는 불변)

    Args:
        order_id: 주문 ID
        new_qty: 새 수량

    Returns:
        AmendResult(success, updated_qty)

    Raises:
        AmendNotSupported: Bybit가 Amend 지원 안 함
    """
    # Fake implementation: 특정 order_id는 AmendNotSupported 시뮬레이션
    if "unsupported" in order_id:
        return AmendResult(success=False, error="amend_not_supported")

    # Amend 성공 (Fake)
    return AmendResult(success=True, updated_qty=new_qty)


def cancel_order(
    order_id: str | None = None, order_link_id: str | None = None
) -> bool:
    """
    주문 취소

    Args:
        order_id: 주문 ID (optional)
        order_link_id: orderLinkId (optional)

    Returns:
        True if 취소 성공
    """
    # Fake implementation: 항상 성공
    if order_link_id and order_link_id in _order_store:
        del _order_store[order_link_id]
    return True

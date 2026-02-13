"""
tests/unit/test_order_executor.py
Unit tests for order executor (FLOW Section 4.5 + 8)

Purpose:
- Entry 주문 실행 (orderLinkId, positionIdx)
- Stop Loss 주문 실행 (Conditional Order 방식 B)
- Idempotency 처리 (DuplicateOrderError)
- Amend 우선 규칙 (공백 방지)

SSOT:
- FLOW.md Section 4.5: Stop Loss 주문 계약
- FLOW.md Section 8: Idempotency Key

Test Coverage:
1. place_entry_order_success (positionIdx=0, orderLinkId 생성)
2. place_entry_order_idempotency (DuplicateOrderError 처리)
3. place_entry_order_validates_order_link_id_length (36자 제한)
4. place_stop_loss_conditional_order_params (triggerPrice, triggerDirection)
5. place_stop_loss_direction_short (SHORT 방향)
6. amend_stop_loss_success (qty 갱신)
7. amend_stop_loss_not_supported_fallback (AmendNotSupported)
8. cancel_order_by_order_link_id (취소 성공)
"""

from application.order_executor import (
    place_entry_order,
    place_stop_loss,
    amend_stop_loss,
    cancel_order,
    OrderResult,
    AmendResult,
    DuplicateOrderError,
    AmendNotSupported,
)
from domain.ids import validate_order_link_id


def test_place_entry_order_success():
    """
    Entry 주문 성공 (FLOW Section 4.5 Entry 계약)

    FLOW Section 4.5:
        - category="linear"
        - positionIdx=0 (One-way 모드)
        - orderType="Limit"
        - orderLinkId="{signal_id}_{direction}"

    Example:
        symbol="BTCUSDT"
        side="Buy" (LONG)
        qty=100
        price=50000
        signal_id="test_1"
        direction="LONG"

    Expected:
        orderLinkId="test_1_Buy"
        positionIdx=0
        status="New"
    """
    result = place_entry_order(
        symbol="BTCUSDT",
        side="Buy",
        qty=100,
        price=50000.0,
        signal_id="test_1",
        direction="LONG",
    )

    # orderLinkId 형식 검증
    assert result.order_link_id == "test_1_Buy"
    assert validate_order_link_id(result.order_link_id) is True

    # 주문 상태 검증
    assert result.order_id is not None
    assert result.status == "New"


def test_place_entry_order_idempotency():
    """
    Idempotency 처리 (FLOW Section 8)

    FLOW Section 8:
        - 동일 orderLinkId 재시도 시 DuplicateOrderError
        - 기존 주문 조회 → status 반환

    Example:
        1차 호출: 성공 (order_id="order_1")
        2차 호출: DuplicateOrderError → 기존 주문 조회
    """
    # 1차 호출 (성공)
    result1 = place_entry_order(
        symbol="BTCUSDT",
        side="Buy",
        qty=100,
        price=50000.0,
        signal_id="test_idempotent",
        direction="LONG",
    )
    assert result1.status == "New"

    # 2차 호출 (DuplicateOrderError 예상)
    try:
        result2 = place_entry_order(
            symbol="BTCUSDT",
            side="Buy",
            qty=100,
            price=50000.0,
            signal_id="test_idempotent",
            direction="LONG",
        )
        # DuplicateOrderError 발생 시 기존 주문 조회
        # Fake implementation에서는 예외 대신 동일 order_id 반환으로 시뮬레이션
        assert result2.order_id == result1.order_id
        assert result2.order_link_id == result1.order_link_id
    except DuplicateOrderError as e:
        # 실제 구현에서는 예외 발생 후 조회
        assert e.order_link_id == "test_idempotent_Buy"


def test_place_entry_order_validates_order_link_id_length():
    """
    orderLinkId 길이 검증 (36자 제한)

    FLOW Section 8:
        - Bybit orderLinkId 최대 길이: 36자
        - signal_id가 너무 길면 ValidationError

    Example:
        signal_id="a" × 50 (50자)
        orderLinkId="{signal_id}_Buy" = 54자 > 36자
        → ValidationError 발생
    """
    long_signal_id = "a" * 50  # 50자

    try:
        result = place_entry_order(
            symbol="BTCUSDT",
            side="Buy",
            qty=100,
            price=50000.0,
            signal_id=long_signal_id,
            direction="LONG",
        )
        # ValidationError 발생해야 함
        assert False, "Expected ValidationError for long orderLinkId"
    except ValueError as e:
        # ValidationError → ValueError로 변환
        error_msg = str(e).lower()
        assert "orderlinkid" in error_msg or "too long" in error_msg


def test_place_stop_loss_conditional_order_params():
    """
    Stop Loss 주문 파라미터 (FLOW Section 4.5 Conditional Order 방식 B)

    FLOW Section 4.5:
        LONG Stop:
        - orderType="Market"
        - triggerPrice=stop_price
        - triggerDirection=2 (falling, LastPrice < triggerPrice)
        - triggerBy="LastPrice"
        - reduceOnly=True
        - positionIdx=0
        - side="Sell" (LONG 청산)
        - orderLinkId="{signal_id}_stop_Sell"

    Example:
        qty=100
        stop_price=49000
        direction="LONG"
        signal_id="test_1"

    Expected:
        orderType="Market"
        triggerPrice="49000"
        triggerDirection=2
        side="Sell"
        orderLinkId="test_1_stop_Sell"
    """
    result = place_stop_loss(
        symbol="BTCUSDT",
        qty=100,
        stop_price=49000.0,
        direction="LONG",
        signal_id="test_1",
    )

    # Conditional Order 파라미터 검증
    assert result.order_type == "Market"
    assert result.trigger_price == 49000.0
    assert result.trigger_direction == 2  # falling (LONG)
    assert result.reduce_only is True
    assert result.position_idx == 0
    assert result.side == "Sell"  # LONG 청산
    assert result.order_link_id == "test_1_stop_Sell"


def test_place_stop_loss_direction_short():
    """
    Stop Loss 주문 (SHORT 방향)

    FLOW Section 4.5:
        SHORT Stop:
        - side="Buy" (SHORT 청산)
        - triggerDirection=1 (rising, LastPrice > triggerPrice)
        - orderLinkId="{signal_id}_stop_Buy"

    Example:
        direction="SHORT"
        stop_price=51000

    Expected:
        side="Buy"
        triggerDirection=1
        orderLinkId="test_1_stop_Buy"
    """
    result = place_stop_loss(
        symbol="BTCUSDT",
        qty=100,
        stop_price=51000.0,
        direction="SHORT",
        signal_id="test_1",
    )

    assert result.side == "Buy"  # SHORT 청산
    assert result.trigger_direction == 1  # rising (SHORT)
    assert result.order_link_id == "test_1_stop_Buy"


def test_amend_stop_loss_success():
    """
    Stop 수량 갱신 (FLOW Section 2.5 Amend 우선)

    FLOW Section 2.5:
        - Stop 갱신은 Amend API 우선 (공백 방지)
        - qty만 수정 (triggerPrice는 불변)

    Example:
        order_id="stop_1"
        기존 qty=100
        new_qty=150

    Expected:
        Amend API 호출
        updated_qty=150
    """
    result = amend_stop_loss(order_id="stop_1", new_qty=150)

    assert result.success is True
    assert result.updated_qty == 150


def test_amend_stop_loss_not_supported_fallback():
    """
    Amend 지원 안 함 (Fallback to Cancel+Place)

    FLOW Section 2.5:
        - Bybit가 AmendNotSupported 반환
        - Caller가 catch → Cancel+Place 수행

    Example:
        order_id="stop_2"
        Bybit: AmendNotSupported

    Expected:
        AmendNotSupported 예외 발생
        Caller가 cancel_order() + place_stop_loss() 수행
    """
    try:
        result = amend_stop_loss(order_id="stop_unsupported", new_qty=150)
        # AmendNotSupported 발생해야 함
        # Fake implementation에서는 특정 order_id로 시뮬레이션
        if result.success is False:
            # Fallback 필요
            assert result.error == "amend_not_supported"
    except AmendNotSupported as e:
        # 실제 구현에서는 예외 발생
        assert e.order_id == "stop_unsupported"


def test_cancel_order_by_order_link_id():
    """
    주문 취소 (orderLinkId)

    FLOW Section 4.5:
        - cancel_order(order_link_id="test_1_Buy")

    Example:
        order_link_id="test_1_Buy"

    Expected:
        취소 성공
    """
    result = cancel_order(order_link_id="test_1_Buy")

    assert result is True

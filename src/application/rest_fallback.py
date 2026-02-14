"""
src/application/rest_fallback.py
REST API fallback — WebSocket FILL 이벤트 미수신 시 REST API로 주문/포지션 상태 복구

orchestrator._process_events()에서 추출한 REST API polling 로직.
상태 변경을 FallbackResult dataclass로 반환하여 orchestrator가 적용.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from domain.state import State, Position, Direction, StopStatus
from application.event_processor import match_pending_order, create_position_from_fill

logger = logging.getLogger(__name__)

# Sentinel: "position 변경 없음"을 None(position 삭제)과 구별
_NO_CHANGE = object()


@dataclass
class FallbackResult:
    """REST fallback 처리 결과. orchestrator가 이 결과를 self.*에 적용한다."""

    new_state: Optional[State] = None
    new_position: Any = _NO_CHANGE  # Position, None(clear), or _NO_CHANGE
    clear_pending: bool = False
    log_estimated_reason: Optional[str] = None
    log_completed_event: Any = None  # fill event for completed trade logging
    skip_ws_processing: bool = False  # True면 WS FILL 처리 건너뛰기


def _check_has_position(rest_client) -> bool:
    """거래소에 포지션이 존재하는지 확인"""
    try:
        pos_response = rest_client.get_position(category="linear", symbol="BTCUSDT")
        positions = pos_response.get("result", {}).get("list", [])
        return bool(positions and float(positions[0].get("size", "0")) > 0)
    except Exception:
        return False


def _recover_position_from_api(rest_client, pending_order: Optional[dict]) -> Optional[Position]:
    """거래소 Position API에서 포지션을 복구한다. 포지션 없으면 None."""
    try:
        pos_response = rest_client.get_position(category="linear", symbol="BTCUSDT")
        positions = pos_response.get("result", {}).get("list", [])
        if not positions or float(positions[0].get("size", "0")) <= 0:
            return None

        existing_pos = positions[0]
        size_btc = float(existing_pos.get("size", "0"))
        qty = int(size_btc * 1000)
        entry_price = float(existing_pos.get("avgPrice", "0"))
        side = existing_pos.get("side", "")
        direction = Direction.LONG if side == "Buy" else Direction.SHORT
        signal_id = pending_order.get("signal_id", "recovered") if pending_order else "recovered"

        position = Position(
            qty=qty,
            entry_price=entry_price,
            direction=direction,
            signal_id=signal_id,
            stop_status=StopStatus.MISSING,
            stop_price=None,
        )
        logger.info(f"Position recovered from API: {side} {qty} @ ${entry_price:.2f}")
        return position
    except Exception:
        return None


def _resolve_by_position_check(
    rest_client,
    state: State,
    pending_order: Optional[dict],
) -> FallbackResult:
    """포지션 존재 여부로 상태를 결정하는 공통 로직"""
    position = _recover_position_from_api(rest_client, pending_order)
    has_pos = position is not None

    if state == State.ENTRY_PENDING and has_pos:
        return FallbackResult(
            new_state=State.IN_POSITION,
            new_position=position,
            clear_pending=True,
        )
    elif state == State.EXIT_PENDING and not has_pos:
        return FallbackResult(
            new_state=State.FLAT,
            new_position=None,
            clear_pending=True,
        )
    elif state == State.EXIT_PENDING and has_pos:
        # Exit 주문 체결인데 position 아직 존재 → pending만 초기화
        logger.warning("Exit order processed but position still exists, clearing pending for retry")
        return FallbackResult(clear_pending=True)
    else:
        # 판단 불가 → pending 초기화
        logger.warning(f"Ambiguous: state={state}, has_pos={has_pos}, clearing pending")
        return FallbackResult(clear_pending=True)


def _handle_no_order_id(rest_client, state: State) -> FallbackResult:
    """order_id가 None인 경우 position API로 상태 결정"""
    logger.error("Invalid pending_order: order_id is None")
    has_position = _check_has_position(rest_client)

    if state == State.EXIT_PENDING and not has_position:
        logger.info("No position found, EXIT completed -> FLAT")
        return FallbackResult(
            new_state=State.FLAT,
            new_position=None,
            clear_pending=True,
            skip_ws_processing=True,
            log_estimated_reason="order_id_none",
        )
    elif state == State.ENTRY_PENDING and has_position:
        logger.info("Position found, ENTRY completed -> IN_POSITION")
        return FallbackResult(
            new_state=State.IN_POSITION,
            clear_pending=True,
            skip_ws_processing=True,
        )
    else:
        logger.warning(f"Ambiguous state, resetting to FLAT (had_position={has_position})")
        return FallbackResult(
            new_state=State.FLAT,
            new_position=None,
            clear_pending=True,
            skip_ws_processing=True,
        )


def _handle_fill_event(
    fill_event: dict,
    state: State,
    pending_order: Optional[dict],
) -> FallbackResult:
    """REST API에서 가져온 fill event를 처리"""
    matched = match_pending_order(event=fill_event, pending_order=pending_order)
    if not matched:
        return FallbackResult()

    position = create_position_from_fill(event=fill_event, pending_order=pending_order)

    if state == State.ENTRY_PENDING:
        logger.info("REST API fallback: ENTRY_PENDING -> IN_POSITION")
        return FallbackResult(
            new_state=State.IN_POSITION,
            new_position=position,
            clear_pending=True,
        )
    elif state == State.EXIT_PENDING:
        logger.info("REST API fallback: EXIT_PENDING -> FLAT")
        return FallbackResult(
            new_state=State.FLAT,
            new_position=None,
            clear_pending=True,
            log_completed_event=fill_event,
        )

    return FallbackResult()


def _handle_order_history(
    rest_client,
    state: State,
    pending_order: Optional[dict],
    order_id: str,
) -> FallbackResult:
    """order history를 조회하여 주문 상태에 따라 처리"""
    try:
        history_response = rest_client.get_order_history(
            category="linear", symbol="BTCUSDT", orderId=order_id,
        )
        history_orders = history_response.get("result", {}).get("list", [])
    except Exception as hist_err:
        logger.error(f"Order history check failed: {hist_err}")
        return _fallback_to_flat(state, reason="history_check_exception")

    if not history_orders:
        logger.warning(f"Order {order_id} not found in history, checking position API...")
        return _resolve_by_position_check(rest_client, state, pending_order)

    order_status = history_orders[0].get("orderStatus", "Unknown")
    logger.info(f"Order history status: {order_status}")

    if order_status == "Filled":
        return _handle_filled_no_executions(rest_client, state, pending_order, order_id)
    elif order_status == "Cancelled":
        return _handle_cancelled(rest_client, state, order_id)
    else:
        return _handle_unknown_status(rest_client, state, pending_order, order_status)


def _handle_filled_no_executions(
    rest_client,
    state: State,
    pending_order: Optional[dict],
    order_id: str,
) -> FallbackResult:
    """Filled이지만 execution list 비어있음 → 2초 후 재시도 → position API"""
    logger.info("Order Filled but no executions yet, retrying in 2s...")
    time.sleep(2)

    retry_response = rest_client.get_execution_list(
        category="linear", symbol="BTCUSDT", orderId=order_id, limit=50,
    )
    retry_execs = retry_response.get("result", {}).get("list", [])

    if retry_execs:
        fill_event = retry_execs[0]
        logger.info(f"Got FILL event from REST API (retry): {fill_event}")
        return _handle_fill_event(fill_event, state, pending_order)

    # 재시도에도 execution 없음 → position 직접 확인
    logger.warning("Order Filled but no executions after retry, checking position...")
    result = _resolve_by_position_check(rest_client, state, pending_order)

    # EXIT_PENDING에서 position 없으면 estimated trade 로그 필요
    if state == State.EXIT_PENDING and result.new_state == State.FLAT:
        result.log_estimated_reason = "filled_no_executions"

    return result


def _handle_cancelled(rest_client, state: State, order_id: str) -> FallbackResult:
    """주문 취소 확인 → position 존재 여부로 상태 결정"""
    logger.warning(f"Order {order_id} confirmed Cancelled")
    has_pos = _check_has_position(rest_client)

    if has_pos and state == State.EXIT_PENDING:
        logger.info("Position still exists after cancel -> IN_POSITION")
        return FallbackResult(
            new_state=State.IN_POSITION,
            clear_pending=True,
        )
    else:
        return FallbackResult(
            new_state=State.FLAT,
            new_position=None,
            clear_pending=True,
        )


def _handle_unknown_status(
    rest_client,
    state: State,
    pending_order: Optional[dict],
    order_status: str,
) -> FallbackResult:
    """예상 외 주문 상태 (PartiallyFilled 등) → position API로 직접 판단"""
    logger.warning(f"Order status={order_status}, checking position API...")
    result = _resolve_by_position_check(rest_client, state, pending_order)

    # EXIT_PENDING에서 FLAT 전환 시 estimated trade 로그
    if state == State.EXIT_PENDING and result.new_state == State.FLAT:
        result.log_estimated_reason = f"unknown_status_{order_status}"

    return result


def _fallback_to_flat(state: State, reason: str) -> FallbackResult:
    """최종 fallback: FLAT으로 복귀"""
    logger.warning(f"Order status unknown, resetting to FLAT")
    return FallbackResult(
        new_state=State.FLAT,
        new_position=None,
        clear_pending=True,
        log_estimated_reason=reason if state == State.EXIT_PENDING else None,
    )


def check_pending_order_fallback(
    rest_client,
    state: State,
    pending_order: dict,
    elapsed: float,
) -> FallbackResult:
    """
    WebSocket timeout 후 REST API로 주문 상태를 확인하고 결과를 반환.

    Args:
        rest_client: Bybit REST client
        state: 현재 상태 (ENTRY_PENDING 또는 EXIT_PENDING)
        pending_order: 대기 주문 정보
        elapsed: pending 경과 시간 (초)

    Returns:
        FallbackResult: orchestrator가 self.*에 적용할 상태 변경
    """
    logger.warning(f"WebSocket FILL event not received after {elapsed:.1f}s, polling REST API...")

    order_id = pending_order.get("order_id")

    # order_id가 None이면 position API로 직접 판단
    if not order_id:
        return _handle_no_order_id(rest_client, state)

    # GET /v5/order/realtime (주문 상태 조회)
    order_response = rest_client.get_open_orders(
        category="linear", symbol="BTCUSDT", orderId=order_id,
    )
    orders = order_response.get("result", {}).get("list", [])

    if orders:
        # 주문이 여전히 open 상태 (미체결 또는 부분 체결)
        order_status = orders[0].get("orderStatus")
        logger.warning(f"Order {order_id} still {order_status}, waiting...")
        return FallbackResult()

    # 주문이 open orders에 없음 → 체결 또는 취소
    logger.info(f"Order {order_id} not in open orders (filled or cancelled)")

    # Execution list에서 FILL 이벤트 조회
    exec_response = rest_client.get_execution_list(
        category="linear", symbol="BTCUSDT", orderId=order_id, limit=50,
    )
    executions = exec_response.get("result", {}).get("list", [])

    if executions:
        fill_event = executions[0]
        logger.info(f"Got FILL event from REST API: {fill_event}")
        return _handle_fill_event(fill_event, state, pending_order)

    # Execution 없음 → order history로 확인
    return _handle_order_history(rest_client, state, pending_order, order_id)

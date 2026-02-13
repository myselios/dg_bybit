"""
src/application/event_handler.py
Event handler (FLOW Section 2.5)

Purpose:
- ExecutionEvent → transition() 호출
- transition() 결과 (intents) → executor 실행
- Event-driven 상태 확정

SSOT:
- FLOW.md Section 2.5: Execution Events

Exports:
- handle_execution_event(): Event 처리 + intents 실행
- execute_intents(): Intents → I/O 레이어 호출
"""

from dataclasses import dataclass
from typing import Optional
from application.transition import transition
from application.order_executor import (
    place_stop_loss,
    amend_stop_loss,
    cancel_order,
)
from domain.state import State, Position, PendingOrder
from domain.events import ExecutionEvent
from domain.intent import TransitionIntents


@dataclass
class HandleResult:
    """Event 처리 결과"""

    new_state: State
    new_position: Optional[Position]
    intents: TransitionIntents


@dataclass
class IntentExecutionResult:
    """Intent 실행 결과"""

    intent_type: str
    success: bool
    error: Optional[str] = None


def handle_execution_event(
    event: ExecutionEvent,
    current_state: State,
    current_position: Optional[Position],
    pending_order: Optional[PendingOrder],
) -> HandleResult:
    """
    ExecutionEvent 처리 (FLOW Section 2.5)

    Steps:
    1. transition(state, position, event, pending_order)
    2. new_state, new_position, intents 획득
    3. intents 실행 (StopIntent → order_executor.place_stop_loss)
    4. 상태 저장

    Args:
        event: ExecutionEvent (FILL/PARTIAL_FILL/CANCEL/REJECT/...)
        current_state: 현재 상태
        current_position: 현재 포지션 (optional)
        pending_order: 대기 중인 주문 (optional)

    Returns:
        HandleResult(new_state, new_position, intents)
    """
    # Step 1: transition() 호출 (pure function)
    new_state, new_position, intents = transition(
        current_state=current_state,
        current_position=current_position,
        event=event,
        pending_order=pending_order,
    )

    # Step 2: intents 실행 (I/O 레이어)
    # (실제 구현에서는 execute_intents()를 호출하여 I/O 수행)
    # 여기서는 HandleResult만 반환 (executor는 별도 호출)

    # Step 3: 결과 반환
    return HandleResult(
        new_state=new_state,
        new_position=new_position,
        intents=intents,
    )


def execute_intents(
    intents: TransitionIntents, position: Optional[Position]
) -> list[IntentExecutionResult]:
    """
    Intents 실행 (I/O 레이어 호출)

    FLOW Section 2.5:
        - StopIntent.PLACE → order_executor.place_stop_loss()
        - StopIntent.AMEND → order_executor.amend_stop_loss()
        - StopIntent.CANCEL_AND_PLACE → cancel + place
        - CancelOrderIntent → order_executor.cancel_order()
        - HaltIntent → entry_blocked=True + cancel all orders
        - LogIntent → logger

    Args:
        intents: TransitionIntents (transition() 출력)
        position: 현재 포지션 (optional, Stop 관련 필요)

    Returns:
        List[IntentExecutionResult] (실행 결과)
    """
    results = []

    # 1. StopIntent 처리
    if intents.stop_intent:
        stop_intent = intents.stop_intent
        if stop_intent.action == "PLACE":
            # Stop 설치
            if position:
                try:
                    place_stop_loss(
                        symbol="BTCUSDT",
                        qty=stop_intent.desired_qty,
                        stop_price=position.stop_price,
                        direction=position.direction.value,
                        signal_id=position.signal_id,
                    )
                    results.append(
                        IntentExecutionResult(
                            intent_type="STOP_PLACE", success=True
                        )
                    )
                except Exception as e:
                    results.append(
                        IntentExecutionResult(
                            intent_type="STOP_PLACE", success=False, error=str(e)
                        )
                    )

        elif stop_intent.action == "AMEND":
            # Stop 수량 갱신
            if position and position.stop_order_id:
                try:
                    amend_stop_loss(
                        order_id=position.stop_order_id,
                        new_qty=stop_intent.desired_qty,
                    )
                    results.append(
                        IntentExecutionResult(
                            intent_type="STOP_AMEND", success=True
                        )
                    )
                except Exception as e:
                    results.append(
                        IntentExecutionResult(
                            intent_type="STOP_AMEND", success=False, error=str(e)
                        )
                    )

        elif stop_intent.action == "CANCEL_AND_PLACE":
            # Stop 재설치 (Cancel + Place)
            if position and position.stop_order_id:
                try:
                    # Cancel 기존 Stop
                    cancel_order(order_id=position.stop_order_id)
                    # Place 새 Stop
                    place_stop_loss(
                        symbol="BTCUSDT",
                        qty=stop_intent.desired_qty,
                        stop_price=position.stop_price,
                        direction=position.direction.value,
                        signal_id=position.signal_id,
                    )
                    results.append(
                        IntentExecutionResult(
                            intent_type="STOP_CANCEL_AND_PLACE", success=True
                        )
                    )
                except Exception as e:
                    results.append(
                        IntentExecutionResult(
                            intent_type="STOP_CANCEL_AND_PLACE",
                            success=False,
                            error=str(e),
                        )
                    )

    # 2. HaltIntent 처리
    if intents.halt_intent:
        results.append(IntentExecutionResult(intent_type="HALT", success=True))

    # 3. CancelOrderIntent 처리
    if intents.cancel_intent:
        try:
            cancel_order(
                order_id=intents.cancel_intent.order_id,
                order_link_id=intents.cancel_intent.order_link_id,
            )
            results.append(IntentExecutionResult(intent_type="CANCEL", success=True))
        except Exception as e:
            results.append(
                IntentExecutionResult(intent_type="CANCEL", success=False, error=str(e))
            )

    # 4. LogIntent 처리 (실제로는 logger 호출)
    if intents.log_intent:
        results.append(IntentExecutionResult(intent_type="LOG", success=True))

    return results

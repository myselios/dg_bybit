"""
application/exit_manager.py
Exit Manager — Stop Loss 도달 확인 및 Exit 주문 발주

SSOT: docs/plans/task_plan.md Phase 11

책임:
1. check_stop_hit(): Stop loss 도달 확인 (LONG/SHORT별)
2. create_exit_intent(): Exit 주문 Intent 생성 (Market order)

Exports:
- check_stop_hit: Stop loss 도달 확인
- create_exit_intent: Exit intent 생성
"""

from typing import Optional
from src.domain.state import Position, Direction
from src.domain.intent import TransitionIntents, ExitIntent


def check_stop_hit(current_price: float, position: Position) -> bool:
    """
    Stop loss 도달 확인

    Args:
        current_price: 현재 가격 (USD)
        position: 현재 포지션

    Returns:
        bool: Stop loss 도달 여부

    규칙:
    - LONG: current_price <= stop_price
    - SHORT: current_price >= stop_price
    - stop_price가 None이면 False (확인 불가)
    """
    # stop_price가 None이면 확인 불가
    if position.stop_price is None:
        return False

    # LONG: 가격 하락 → stop_price 이하
    if position.direction == Direction.LONG:
        return current_price <= position.stop_price

    # SHORT: 가격 상승 → stop_price 이상
    # position.direction == Direction.SHORT
    return current_price >= position.stop_price


def create_exit_intent(position: Position, reason: str) -> TransitionIntents:
    """
    Exit intent 생성 (강제 청산)

    Args:
        position: 현재 포지션
        reason: Exit 이유 (stop_loss_hit, manual_exit, etc.)

    Returns:
        TransitionIntents: Exit intent 포함

    Grid 전략:
    - Market order로 즉시 청산 (시장가)
    - 전량 청산 (position.qty)
    """
    intents = TransitionIntents()

    # Exit intent 생성
    intents.exit_intent = ExitIntent(
        qty=position.qty,
        reason=reason,
        order_type="Market",
        stop_price=position.stop_price,  # For logging
    )

    return intents

"""
Tick Orchestrator (FLOW.md Section 2 준수)

FLOW_REF: docs/constitution/FLOW.md#2 (Tick Execution Flow, 1 Cycle)
Last verified: 2026-01-19

Tick 실행 순서 강제:
[1] Update Snapshot (항상)
[1.5] Emergency Check (최우선, 항상) ← Signal보다 먼저
[2] Handle Execution Events
[3] Manage Position (IN_POSITION only)
[4] Evaluate Entry (FLAT only)
[5] Evaluate Exit (IN_POSITION only)

Implementation Status: Phase 0.5 골격 (Phase 1+에서 단계별 구현 예정)
"""

from typing import Dict, Any

from domain.intent import TransitionIntents
from application.emergency import evaluate as emergency_evaluate


def tick(snapshot: Dict[str, Any]) -> TransitionIntents:
    """
    1 Tick 실행 (순수 함수, 순서 강제)

    Args:
        snapshot: {
            # Market
            "price_drop_1m": float,
            "price_drop_5m": float,
            "mark_price_usd": float,
            "atr_pct_24h": float,

            # Account
            "equity_btc": float,
            "equity_usd": float,
            "margin_used_btc": float,

            # Orders
            "pending_orders": List[PendingOrder],
            "fills": List[ExecutionEvent],

            # State
            "current_state": State,
            "current_position": Optional[Position],

            # Health
            "latency_rest_p95": float,
            "ws_last_heartbeat_ts": float,
            "ws_event_drop_count": int,
            "timestamp": float,
            "last_balance_ts": float
        }

    Returns:
        TransitionIntents (Emergency/Transition/Stop/Log)

    Implementation:
        Phase 1에서 Emergency Check 구현.
        Phase 2+에서 Entry/Exit 구현.
        현재는 최소 골격 (순서만 강제).
    """
    # [1.5] Emergency Check (최우선, 항상)
    # Signal보다 먼저 실행 (FLOW 헌법)
    emergency_status = emergency_evaluate(snapshot)

    # TODO: emergency_status → State transition / emergency_block 처리

    # [2] Handle Execution Events
    # TODO: Phase 0 transition() 호출

    # [3] Manage Position (IN_POSITION only)
    # TODO: Phase 3 구현

    # [4] Evaluate Entry (FLAT only)
    # TODO: Phase 2 구현

    # [5] Evaluate Exit (IN_POSITION only)
    # TODO: Phase 3 구현

    # 현재는 빈 intents 반환
    return TransitionIntents(stop_intents=[], halt_intents=[])

"""
src/infrastructure/logging/halt_logger.py
Halt Logger — HALT 이유 + context snapshot (재현 가능성)

SSOT:
- FLOW.md Section 7.1: Emergency Conditions (HALT 조건)
- task_plan.md Phase 5: HALT 로그는 "context snapshot" 필수

원칙:
1. HALT 이유 + 상태 + context snapshot 포함
2. Context snapshot: 가격, equity, stage_candidate, latency, position, stop_status 등
3. Schema validation: 필수 필드 누락 시 HaltLogValidationError

Exports:
- log_halt(): HALT 로그 생성 (context snapshot 포함)
- validate_halt_schema(): Schema validation (필수 필드 검증)
- HaltLogValidationError: 필수 필드 누락 예외
"""

from typing import Dict, Any


class HaltLogValidationError(Exception):
    """Halt log schema validation 실패"""

    pass


def log_halt(
    timestamp: float,
    halt_reason: str,
    state: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    HALT 로그 생성 (context snapshot 포함)

    Args:
        timestamp: HALT 시각 (UNIX timestamp)
        halt_reason: HALT 이유 (e.g., "balance_too_low", "price_drop_1m")
        state: 현재 상태 (e.g., "FLAT", "IN_POSITION")
        context: Context snapshot (가격, equity, latency, position 등)

    Returns:
        log_entry: Halt log (dict)

    task_plan.md Phase 5:
        - HALT 로그는 "context snapshot" 필수(가격, equity, stage_candidate, latency 등)

    Context snapshot fields (example):
        - current_price (float)
        - equity_usdt (float)
        - equity_usd (float)
        - stage_candidate (int)
        - latency_ms (float)
        - position_qty (int, if IN_POSITION)
        - stop_status (str, if IN_POSITION)
        - stop_price (float, if IN_POSITION)
        - emergency_trigger (str, if emergency)
        - trigger_threshold (float, if emergency)
        - actual_value (float, if emergency)
    """
    log_entry = {
        "timestamp": timestamp,
        "halt_reason": halt_reason,
        "state": state,
        "context": context,
    }

    # Schema validation
    validate_halt_schema(log_entry)

    return log_entry


def validate_halt_schema(log_entry: Dict[str, Any]) -> None:
    """
    Halt log schema validation

    Args:
        log_entry: Halt log entry (dict)

    Raises:
        HaltLogValidationError: 필수 필드 누락

    task_plan.md Phase 5:
        - schema 테스트(필수 필드 누락 시 실패)

    Required fields:
        - timestamp (float)
        - halt_reason (str)
        - state (str)
        - context (dict)
    """
    required_fields = ["timestamp", "halt_reason", "state", "context"]

    for field in required_fields:
        if field not in log_entry:
            raise HaltLogValidationError(f"Missing required field: {field}")

    # context는 dict여야 함
    if not isinstance(log_entry.get("context"), dict):
        raise HaltLogValidationError("context must be a dict")

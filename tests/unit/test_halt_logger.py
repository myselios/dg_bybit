"""
tests/unit/test_halt_logger.py
Unit tests for halt logger (Phase 5: Observability)

Purpose:
- HALT event logging schema (이유 + context snapshot)
- 재현 가능성 (가격, equity, stage_candidate, latency, position, stop_status 등)
- Schema validation (필수 필드 누락 시 실패)

SSOT:
- FLOW.md Section 7.1: Emergency Conditions (HALT 조건)
- task_plan.md Phase 5: HALT 로그는 "context snapshot" 필수

Test Coverage:
1. log_halt_includes_required_fields (HALT 필수 필드)
2. log_halt_includes_context_snapshot (가격, equity, latency, position 등)
3. validate_halt_schema_rejects_missing_required_field (필수 필드 누락 → ValidationError)
4. log_halt_includes_emergency_trigger_type (emergency 트리거 타입)
"""

from infrastructure.logging.halt_logger import (
    log_halt,
    validate_halt_schema,
    HaltLogValidationError,
)


def test_log_halt_includes_required_fields():
    """
    HALT 로그 필수 필드 검증

    task_plan.md Phase 5:
        - HALT 로그는 "context snapshot" 필수

    Required fields (HALT):
        - timestamp (float)
        - halt_reason (str)
        - state (str)
        - context (dict)

    Example:
        halt_reason="balance_too_low"
        state="FLAT"

    Expected:
        log entry 생성 성공
        모든 필수 필드 존재
    """
    log_entry = log_halt(
        timestamp=1705593600.0,
        halt_reason="balance_too_low",
        state="FLAT",
        context={
            "current_price": 50000.0,
            "equity_usdt": 0.001,
            "equity_usd": 50.0,
        },
    )

    # 필수 필드 검증
    assert log_entry["timestamp"] == 1705593600.0
    assert log_entry["halt_reason"] == "balance_too_low"
    assert log_entry["state"] == "FLAT"
    assert log_entry["context"] is not None


def test_log_halt_includes_context_snapshot():
    """
    Context snapshot 포함 검증 (재현 가능성)

    task_plan.md Phase 5:
        - HALT 로그는 "context snapshot" 필수(가격, equity, stage_candidate, latency 등)

    Context snapshot fields:
        - current_price (float)
        - equity_usdt (float)
        - stage_candidate (int)
        - latency_ms (float)
        - position_qty (int, if IN_POSITION)
        - stop_status (str, if IN_POSITION)
        - stop_price (float, if IN_POSITION)

    Example:
        context = {
            "current_price": 50000.0,
            "equity_usdt": 0.002,
            "equity_usd": 100.0,
            "stage_candidate": 1,
            "latency_ms": 150.0,
            "position_qty": 100,
            "stop_status": "ACTIVE",
            "stop_price": 49000.0,
        }

    Expected:
        log entry["context"]에 모든 필드 존재
    """
    log_entry = log_halt(
        timestamp=1705593600.0,
        halt_reason="latency_too_high",
        state="IN_POSITION",
        context={
            "current_price": 50000.0,
            "equity_usdt": 0.002,
            "equity_usd": 100.0,
            "stage_candidate": 1,
            "latency_ms": 6000.0,  # 6초 (> 5초 threshold)
            "position_qty": 100,
            "stop_status": "ACTIVE",
            "stop_price": 49000.0,
        },
    )

    # Context snapshot 필드 검증
    context = log_entry["context"]
    assert context["current_price"] == 50000.0
    assert context["equity_usdt"] == 0.002
    assert context["equity_usd"] == 100.0
    assert context["stage_candidate"] == 1
    assert context["latency_ms"] == 6000.0
    assert context["position_qty"] == 100
    assert context["stop_status"] == "ACTIVE"
    assert context["stop_price"] == 49000.0


def test_validate_halt_schema_rejects_missing_required_field():
    """
    필수 필드 누락 → HaltLogValidationError

    task_plan.md Phase 5:
        - schema 테스트(필수 필드 누락 시 실패)

    Example:
        log_entry = {"halt_reason": "test"}  # timestamp 누락

    Expected:
        HaltLogValidationError 발생
    """
    # Case 1: timestamp 누락
    log_entry = {
        # "timestamp" 누락
        "halt_reason": "balance_too_low",
        "state": "FLAT",
        "context": {},
    }

    try:
        validate_halt_schema(log_entry)
        assert False, "Expected HaltLogValidationError for missing timestamp"
    except HaltLogValidationError as e:
        assert "timestamp" in str(e).lower()

    # Case 2: halt_reason 누락
    log_entry = {
        "timestamp": 1705593600.0,
        # "halt_reason" 누락
        "state": "FLAT",
        "context": {},
    }

    try:
        validate_halt_schema(log_entry)
        assert False, "Expected HaltLogValidationError for missing halt_reason"
    except HaltLogValidationError as e:
        assert "halt_reason" in str(e).lower()

    # Case 3: context 누락
    log_entry = {
        "timestamp": 1705593600.0,
        "halt_reason": "balance_too_low",
        "state": "FLAT",
        # "context" 누락
    }

    try:
        validate_halt_schema(log_entry)
        assert False, "Expected HaltLogValidationError for missing context"
    except HaltLogValidationError as e:
        assert "context" in str(e).lower()


def test_log_halt_includes_emergency_trigger_type():
    """
    Emergency 트리거 타입 포함 (재현 가능성)

    FLOW Section 7.1:
        - price_drop_1m (1분 -10%)
        - price_drop_10m (10분 -20%)
        - balance_too_low (equity < 0 또는 < 30초 loss)
        - latency_too_high (REST latency > 5초)

    Required fields (Emergency context):
        - emergency_trigger (str, e.g., "price_drop_1m")
        - trigger_threshold (float, e.g., -0.10)
        - actual_value (float, e.g., -0.12)

    Example:
        emergency_trigger="price_drop_1m"
        trigger_threshold=-0.10
        actual_value=-0.12

    Expected:
        log entry에 emergency_trigger 정보 포함
    """
    log_entry = log_halt(
        timestamp=1705593600.0,
        halt_reason="price_drop_1m",
        state="FLAT",
        context={
            "current_price": 45000.0,
            "equity_usdt": 0.002,
            "equity_usd": 90.0,
            "emergency_trigger": "price_drop_1m",
            "trigger_threshold": -0.10,
            "actual_value": -0.12,  # 12% 하락
        },
    )

    # Emergency trigger 정보 검증
    context = log_entry["context"]
    assert context["emergency_trigger"] == "price_drop_1m"
    assert context["trigger_threshold"] == -0.10
    assert context["actual_value"] == -0.12

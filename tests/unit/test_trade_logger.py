"""
tests/unit/test_trade_logger.py
Unit tests for trade logger (Phase 5: Observability)

Purpose:
- Trade event logging schema (entry/exit/fee/pnl)
- 재현 가능성 (정책 버전, 스테이지, 게이트 결과 포함)
- Schema validation (필수 필드 누락 시 실패)

SSOT:
- FLOW.md Section 6.2: Fee Post-Trade Verification (trade_log["fee"])
- task_plan.md Phase 5: Observability (재현 가능한 로그 스키마)

Test Coverage:
1. log_trade_entry_includes_required_fields (진입 로그 필수 필드)
2. log_trade_exit_includes_pnl_and_fee (청산 로그 pnl + fee)
3. validate_trade_schema_rejects_missing_required_field (필수 필드 누락 → ValidationError)
4. log_trade_includes_policy_version_for_reproducibility (정책 버전 포함)
5. log_trade_includes_stage_and_gate_results (스테이지 + 게이트 결과)
"""

from infrastructure.logging.trade_logger import (
    log_trade_entry,
    log_trade_exit,
    validate_trade_schema,
    TradeLogValidationError,
)


def test_log_trade_entry_includes_required_fields():
    """
    진입 로그 필수 필드 검증

    task_plan.md Phase 5:
        - 로그는 "재현 가능"해야 함
        - 필수 필드 누락 시 실패

    Required fields (Entry):
        - signal_id (str)
        - timestamp (float)
        - event_type ("ENTRY")
        - side ("Buy" or "Sell")
        - qty (int)
        - price (float)
        - order_id (str)
        - order_link_id (str)

    Example:
        signal_id="test_1"
        event_type="ENTRY"
        side="Buy"
        qty=100
        price=50000.0

    Expected:
        log entry 생성 성공
        모든 필수 필드 존재
    """
    log_entry = log_trade_entry(
        signal_id="test_1",
        timestamp=1705593600.0,
        side="Buy",
        qty=100,
        price=50000.0,
        order_id="order_1",
        order_link_id="test_1_Buy",
    )

    # 필수 필드 검증
    assert log_entry["signal_id"] == "test_1"
    assert log_entry["timestamp"] == 1705593600.0
    assert log_entry["event_type"] == "ENTRY"
    assert log_entry["side"] == "Buy"
    assert log_entry["qty"] == 100
    assert log_entry["price"] == 50000.0
    assert log_entry["order_id"] == "order_1"
    assert log_entry["order_link_id"] == "test_1_Buy"


def test_log_trade_exit_includes_pnl_and_fee():
    """
    청산 로그 pnl + fee 검증

    FLOW Section 6.2:
        trade_log["fee"] = {
            "estimated_usd": estimated_fee_usd,
            "actual_usd": actual_fee_usd,
            "fee_ratio": fee_ratio,
        }

    Required fields (Exit):
        - signal_id (str)
        - timestamp (float)
        - event_type ("EXIT")
        - side ("Sell" or "Buy")
        - qty (int)
        - price (float)
        - pnl_btc (float)
        - pnl_usd (float)
        - fee_btc (float)
        - fee_usd (float)
        - fee_ratio (float, actual/estimated)

    Example:
        pnl_btc=0.001
        pnl_usd=50.0
        fee_btc=0.00002
        fee_usd=1.0

    Expected:
        log entry 생성 성공
        pnl + fee 필드 존재
    """
    log_entry = log_trade_exit(
        signal_id="test_1",
        timestamp=1705593700.0,
        side="Sell",
        qty=100,
        price=51000.0,
        pnl_btc=0.001,
        pnl_usd=50.0,
        fee_btc=0.00002,
        fee_usd=1.0,
        estimated_fee_usd=0.8,
    )

    # 필수 필드 검증
    assert log_entry["event_type"] == "EXIT"
    assert log_entry["pnl_btc"] == 0.001
    assert log_entry["pnl_usd"] == 50.0
    assert log_entry["fee_btc"] == 0.00002
    assert log_entry["fee_usd"] == 1.0
    assert abs(log_entry["fee_ratio"] - 1.25) < 0.01  # 1.0 / 0.8 = 1.25


def test_validate_trade_schema_rejects_missing_required_field():
    """
    필수 필드 누락 → ValidationError

    task_plan.md Phase 5:
        - schema 테스트(필수 필드 누락 시 실패)

    Example:
        log_entry = {"signal_id": "test_1"}  # timestamp 누락

    Expected:
        TradeLogValidationError 발생
    """
    # Case 1: timestamp 누락
    log_entry = {
        "signal_id": "test_1",
        # "timestamp" 누락
        "event_type": "ENTRY",
        "side": "Buy",
        "qty": 100,
        "price": 50000.0,
    }

    try:
        validate_trade_schema(log_entry)
        assert False, "Expected TradeLogValidationError for missing timestamp"
    except TradeLogValidationError as e:
        assert "timestamp" in str(e).lower()

    # Case 2: event_type 누락
    log_entry = {
        "signal_id": "test_1",
        "timestamp": 1705593600.0,
        # "event_type" 누락
        "side": "Buy",
        "qty": 100,
        "price": 50000.0,
    }

    try:
        validate_trade_schema(log_entry)
        assert False, "Expected TradeLogValidationError for missing event_type"
    except TradeLogValidationError as e:
        assert "event_type" in str(e).lower()


def test_log_trade_includes_policy_version_for_reproducibility():
    """
    정책 버전 포함 (재현 가능성)

    task_plan.md Phase 5:
        - 로그는 "재현 가능"해야 한다(결정 근거/정책 버전/스테이지/게이트 결과 포함)

    Required fields (Reproducibility):
        - policy_version (str, e.g., "2.2")
        - flow_version (str, e.g., "1.8")

    Example:
        policy_version="2.2"
        flow_version="1.8"

    Expected:
        log entry에 policy_version, flow_version 포함
    """
    log_entry = log_trade_entry(
        signal_id="test_1",
        timestamp=1705593600.0,
        side="Buy",
        qty=100,
        price=50000.0,
        order_id="order_1",
        order_link_id="test_1_Buy",
        policy_version="2.2",
        flow_version="1.8",
    )

    # 재현 가능성 필드 검증
    assert log_entry["policy_version"] == "2.2"
    assert log_entry["flow_version"] == "1.8"


def test_log_trade_includes_stage_and_gate_results():
    """
    스테이지 + 게이트 결과 포함 (재현 가능성)

    task_plan.md Phase 5:
        - 결정 근거/정책 버전/스테이지/게이트 결과 포함

    Required fields (Decision Context):
        - stage_candidate (int, e.g., 1)
        - gate_results (dict, e.g., {"ev_gate": "PASS", "volatility_gate": "PASS"})

    Example:
        stage_candidate=1
        gate_results={"ev_gate": "PASS", "liq_gate": "PASS"}

    Expected:
        log entry에 stage_candidate, gate_results 포함
    """
    log_entry = log_trade_entry(
        signal_id="test_1",
        timestamp=1705593600.0,
        side="Buy",
        qty=100,
        price=50000.0,
        order_id="order_1",
        order_link_id="test_1_Buy",
        stage_candidate=1,
        gate_results={"ev_gate": "PASS", "liq_gate": "PASS"},
    )

    # 결정 근거 필드 검증
    assert log_entry["stage_candidate"] == 1
    assert log_entry["gate_results"]["ev_gate"] == "PASS"
    assert log_entry["gate_results"]["liq_gate"] == "PASS"

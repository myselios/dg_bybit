"""
src/infrastructure/logging/trade_logger.py
Trade Logger — 실거래 감사(audit) 가능한 Trade Event 로그 스키마

SSOT:
- FLOW.md Section 6.2: Fee Post-Trade Verification (trade_log["fee"])
- task_plan.md Phase 5: Observability (재현 가능한 로그 스키마)

원칙:
1. 재현 가능성: 정책 버전, 스테이지, 게이트 결과 포함
2. Schema validation: 필수 필드 누락 시 TradeLogValidationError
3. Entry/Exit 구분: event_type="ENTRY" vs "EXIT"

Exports:
- log_trade_entry(): 진입 로그 (필수 필드 + 재현 정보)
- log_trade_exit(): 청산 로그 (pnl + fee + 재현 정보)
- validate_trade_schema(): Schema validation (필수 필드 검증)
- TradeLogValidationError: 필수 필드 누락 예외
"""

from typing import Dict, Any, Optional


class TradeLogValidationError(Exception):
    """Trade log schema validation 실패"""

    pass


def log_trade_entry(
    signal_id: str,
    timestamp: float,
    side: str,
    qty: int,
    price: float,
    order_id: str,
    order_link_id: str,
    policy_version: str = "unknown",
    flow_version: str = "unknown",
    stage_candidate: Optional[int] = None,
    gate_results: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    진입 로그 생성

    Args:
        signal_id: Signal ID
        timestamp: 이벤트 시각 (UNIX timestamp)
        side: "Buy" or "Sell"
        qty: 수량 (contracts)
        price: 진입 가격 (USD)
        order_id: Order ID
        order_link_id: Order Link ID
        policy_version: 정책 버전 (재현 가능성)
        flow_version: FLOW 버전 (재현 가능성)
        stage_candidate: 스테이지 후보
        gate_results: 게이트 결과 (dict)

    Returns:
        log_entry: Trade entry log (dict)

    task_plan.md Phase 5:
        - 로그는 "재현 가능"해야 함
        - 필수 필드: signal_id, timestamp, event_type, side, qty, price, order_id, order_link_id
        - 재현 정보: policy_version, flow_version, stage_candidate, gate_results
    """
    log_entry = {
        "signal_id": signal_id,
        "timestamp": timestamp,
        "event_type": "ENTRY",
        "side": side,
        "qty": qty,
        "price": price,
        "order_id": order_id,
        "order_link_id": order_link_id,
        "policy_version": policy_version,
        "flow_version": flow_version,
    }

    # 선택 필드 (재현 정보)
    if stage_candidate is not None:
        log_entry["stage_candidate"] = stage_candidate

    if gate_results is not None:
        log_entry["gate_results"] = gate_results

    # Schema validation
    validate_trade_schema(log_entry)

    return log_entry


def log_trade_exit(
    signal_id: str,
    timestamp: float,
    side: str,
    qty: int,
    price: float,
    pnl_usdt: float,
    pnl_usd: float,
    fee_usdt: float,
    fee_usd: float,
    estimated_fee_usd: float,
    policy_version: str = "unknown",
    flow_version: str = "unknown",
    stage_candidate: Optional[int] = None,
    gate_results: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    청산 로그 생성

    Args:
        signal_id: Signal ID
        timestamp: 이벤트 시각 (UNIX timestamp)
        side: "Sell" or "Buy"
        qty: 수량 (contracts)
        price: 청산 가격 (USD)
        pnl_usdt: PnL (USDT)
        pnl_usd: PnL (USD)
        fee_usdt: Fee (USDT)
        fee_usd: Fee (USD, actual)
        estimated_fee_usd: Fee (USD, estimated)
        policy_version: 정책 버전
        flow_version: FLOW 버전
        stage_candidate: 스테이지 후보
        gate_results: 게이트 결과

    Returns:
        log_entry: Trade exit log (dict)

    FLOW Section 6.2:
        trade_log["fee"] = {
            "estimated_usd": estimated_fee_usd,
            "actual_usd": actual_fee_usd,
            "fee_ratio": fee_ratio,
        }
    """
    # Fee ratio 계산
    fee_ratio = fee_usd / estimated_fee_usd if estimated_fee_usd > 0 else 0.0

    log_entry = {
        "signal_id": signal_id,
        "timestamp": timestamp,
        "event_type": "EXIT",
        "side": side,
        "qty": qty,
        "price": price,
        "pnl_usdt": pnl_usdt,
        "pnl_usd": pnl_usd,
        "fee_usdt": fee_usdt,
        "fee_usd": fee_usd,
        "fee_ratio": fee_ratio,
        "policy_version": policy_version,
        "flow_version": flow_version,
    }

    # 선택 필드
    if stage_candidate is not None:
        log_entry["stage_candidate"] = stage_candidate

    if gate_results is not None:
        log_entry["gate_results"] = gate_results

    # Schema validation
    validate_trade_schema(log_entry)

    return log_entry


def validate_trade_schema(log_entry: Dict[str, Any]) -> None:
    """
    Trade log schema validation

    Args:
        log_entry: Trade log entry (dict)

    Raises:
        TradeLogValidationError: 필수 필드 누락

    task_plan.md Phase 5:
        - schema 테스트(필수 필드 누락 시 실패)

    Required fields (모든 log):
        - signal_id
        - timestamp
        - event_type

    Required fields (ENTRY):
        - side, qty, price

    Required fields (EXIT):
        - side, qty, price, pnl_usdt, pnl_usd, fee_usdt, fee_usd
    """
    # (1) 기본 필수 필드
    required_fields = ["signal_id", "timestamp", "event_type"]

    for field in required_fields:
        if field not in log_entry:
            raise TradeLogValidationError(f"Missing required field: {field}")

    # (2) event_type별 필수 필드
    event_type = log_entry.get("event_type")

    if event_type == "ENTRY":
        entry_required = ["side", "qty", "price"]
        for field in entry_required:
            if field not in log_entry:
                raise TradeLogValidationError(
                    f"Missing required field for ENTRY: {field}"
                )

    elif event_type == "EXIT":
        exit_required = ["side", "qty", "price", "pnl_usdt", "pnl_usd", "fee_usdt", "fee_usd"]
        for field in exit_required:
            if field not in log_entry:
                raise TradeLogValidationError(
                    f"Missing required field for EXIT: {field}"
                )

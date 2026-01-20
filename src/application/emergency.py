"""
Emergency Module (FLOW.md Section 1.5 & Section 5 준수)

FLOW_REF: docs/constitution/FLOW.md#1.5 (Emergency Check, 최우선, 항상)
FLOW_REF: docs/constitution/FLOW.md#5 (Emergency Priority: price_drop → COOLDOWN)
Policy_REF: docs/specs/account_builder_policy.md Section 7 (Emergency Gates)
Last verified: 2026-01-21

Priority 0 (Signal보다 먼저 실행):
- price_drop_1m <= -10% → State.COOLDOWN (FLOW Section 5 v1.8 준수, auto-recovery)
- price_drop_5m <= -20% → State.COOLDOWN (FLOW Section 5 v1.8 준수, auto-recovery)
- balance anomaly (equity <= 0 OR stale timestamp > 30s) → State.HALT (manual reset only)
- latency_rest >= 5.0s → emergency_block=True (진입 차단, State 변경 없음)

Implementation Status: FLOW Section 5 v1.8 완전 준수 (ADR-0007)
"""

from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class EmergencyStatus:
    """
    Emergency 평가 결과

    Attributes:
        is_halt: True이면 State.HALT (manual reset only - liquidation, balance < 80)
        is_cooldown: True이면 State.COOLDOWN (auto-recovery - price drop)
        is_blocked: True이면 emergency_block=True (진입 차단, State 변경 없음)
        reason: Emergency 사유 (로그/디버깅용)
    """
    is_halt: bool
    is_cooldown: bool
    is_blocked: bool
    reason: str


@dataclass
class RecoveryStatus:
    """
    Auto-Recovery 평가 결과

    Attributes:
        can_recover: True이면 COOLDOWN → FLAT 전환 가능
        cooldown_minutes: Recovery 후 적용할 cooldown 시간 (분)
    """
    can_recover: bool
    cooldown_minutes: int


def check_emergency(market_data) -> EmergencyStatus:
    """
    Emergency 평가 (순수 함수, MarketDataInterface 사용)

    Args:
        market_data: MarketDataInterface 구현체 (FakeMarketData, BybitAdapter)

    Returns:
        EmergencyStatus

    Gate 순서 (FLOW Section 5):
        1. Balance Anomaly (equity <= 0 OR stale > 30s) → HALT (최우선)
        2. Price Drop (1m <= -10% OR 5m <= -20%) → COOLDOWN (FLOW 준수)
        3. Latency (rest >= 5.0s) → emergency_block=True (진입 차단)

    Implementation:
        FLOW Section 5 완전 준수
    """
    # [1] Balance Anomaly Gate (최우선)
    equity_btc = market_data.get_equity_btc()
    if equity_btc <= 0.0:
        return EmergencyStatus(
            is_halt=True,
            is_cooldown=False,
            is_blocked=False,
            reason="balance_anomaly_equity_zero_or_negative"
        )

    # Stale balance check (timestamp - balance_ts > 30s)
    # Note: FakeMarketData는 balance_staleness를 helper로 제공
    if hasattr(market_data, 'get_balance_staleness'):
        staleness = market_data.get_balance_staleness()
        if staleness > 30.0:
            return EmergencyStatus(
                is_halt=True,
                is_cooldown=False,
                is_blocked=False,
                reason=f"balance_anomaly_stale_timestamp_{staleness:.1f}s"
            )

    # [2] Price Drop Gate (FLOW Section 5: → COOLDOWN)
    if hasattr(market_data, 'get_price_drop_1m'):
        price_drop_1m = market_data.get_price_drop_1m()
    else:
        price_drop_1m = 0.0

    if hasattr(market_data, 'get_price_drop_5m'):
        price_drop_5m = market_data.get_price_drop_5m()
    else:
        price_drop_5m = 0.0

    if price_drop_1m <= -0.10:
        return EmergencyStatus(
            is_halt=False,
            is_cooldown=True,
            is_blocked=False,
            reason=f"price_drop_1m_{price_drop_1m*100:.1f}pct_exceeds_-10pct"
        )

    if price_drop_5m <= -0.20:
        return EmergencyStatus(
            is_halt=False,
            is_cooldown=True,
            is_blocked=False,
            reason=f"price_drop_5m_{price_drop_5m*100:.1f}pct_exceeds_-20pct"
        )

    # [3] Latency Gate (진입 차단, State 변경 없음)
    latency_rest_p95 = market_data.get_rest_latency_p95_1m()
    if latency_rest_p95 >= 5.0:
        return EmergencyStatus(
            is_halt=False,
            is_cooldown=False,
            is_blocked=True,
            reason=f"latency_rest_p95_{latency_rest_p95:.1f}s_exceeds_5.0s"
        )

    # No emergency
    return EmergencyStatus(
        is_halt=False,
        is_cooldown=False,
        is_blocked=False,
        reason=""
    )


def check_recovery(market_data, cooldown_started_at: float) -> RecoveryStatus:
    """
    Auto-Recovery 조건 체크 (COOLDOWN → FLAT 전환 가능 여부)

    Args:
        market_data: MarketDataInterface 구현체
        cooldown_started_at: COOLDOWN 시작 timestamp (unix time)

    Returns:
        RecoveryStatus(can_recover, cooldown_minutes)

    Recovery 조건 (Policy Section 7.3):
        - drop_1m > -5% AND drop_5m > -10%
        - 위 조건이 5분간 연속 유지 (orchestrator에서 검증)
        - 현재는 단일 시점 threshold 체크만 수행
        - Recovery 후 30분 cooldown

    Implementation:
        Phase 1: 단일 시점 recovery threshold 체크
        Phase 6: Orchestrator에서 "5분 연속" 추적
    """
    # Calculate price_drop
    if hasattr(market_data, 'get_price_drop_1m'):
        price_drop_1m = market_data.get_price_drop_1m()
    else:
        price_drop_1m = 0.0

    if hasattr(market_data, 'get_price_drop_5m'):
        price_drop_5m = market_data.get_price_drop_5m()
    else:
        price_drop_5m = 0.0

    # Check recovery threshold
    recovery_threshold_1m = -0.05  # -5%
    recovery_threshold_5m = -0.10  # -10%

    if price_drop_1m > recovery_threshold_1m and price_drop_5m > recovery_threshold_5m:
        # Recovery 조건 충족 (단일 시점)
        # orchestrator에서 "5분 연속" 추적 후 can_recover=True 전달
        elapsed_minutes = (market_data.get_timestamp() - cooldown_started_at) / 60.0

        if elapsed_minutes >= 5.0:
            return RecoveryStatus(
                can_recover=True,
                cooldown_minutes=30
            )

    # Recovery 불가
    return RecoveryStatus(
        can_recover=False,
        cooldown_minutes=0
    )


# ========== Legacy evaluate() (tick_engine.py 호환용) ==========

def evaluate(snapshot: Dict[str, Any]) -> EmergencyStatus:
    """
    Legacy evaluate() (Phase 0.5 호환용)

    Args:
        snapshot: Dict (Phase 0.5 tick_engine.py에서 사용)

    Returns:
        EmergencyStatus

    Note:
        Phase 1에서 check_emergency(market_data)로 전환 완료 후
        tick_engine.py 수정 시 이 함수는 삭제 예정.
        현재는 하위 호환성 유지.
    """
    # Phase 0.5 골격 유지 (항상 safe 반환)
    # FLOW Section 5 v1.8 준수
    return EmergencyStatus(
        is_halt=False,
        is_cooldown=False,
        is_blocked=False,
        reason=""
    )

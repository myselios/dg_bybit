"""
WS Health Module (FLOW.md Section 2.4 준수)

FLOW_REF: docs/constitution/FLOW.md#2.4 (WS Health Tracking & DEGRADED Mode)
Policy_REF: docs/specs/account_builder_policy.md Section 7.2 (WS Health Gates)
Last verified: 2026-01-19

WS Health Rules:
- heartbeat timeout > 10s → degraded_mode=True
- event drop count >= 3 → degraded_mode=True
- degraded duration >= 60s → State.HALT (manual reset)

WS Recovery (Policy Section 7.3):
- heartbeat OK AND event drop == 0 → degraded_mode=False
- Recovery 후 5분 cooldown

Implementation Status: Phase 1 완전 구현
"""

from dataclasses import dataclass


@dataclass
class WSHealthStatus:
    """
    WS Health 평가 결과

    Attributes:
        is_degraded: True이면 degraded_mode 진입
        duration_s: degraded 지속 시간 (seconds, 미사용 시 0.0)
        reason: degraded 사유 (로그/디버깅용)
    """
    is_degraded: bool
    duration_s: float
    reason: str


@dataclass
class WSRecoveryStatus:
    """
    WS Recovery 평가 결과

    Attributes:
        can_recover: True이면 degraded_mode → normal 전환 가능
        cooldown_minutes: Recovery 후 적용할 cooldown 시간 (분)
    """
    can_recover: bool
    cooldown_minutes: int


def check_ws_health(market_data) -> WSHealthStatus:
    """
    WS Health 평가 (순수 함수, MarketDataInterface 사용)

    Args:
        market_data: MarketDataInterface 구현체 (FakeMarketData, BybitAdapter)

    Returns:
        WSHealthStatus

    Gate 순서 (FLOW Section 2.4):
        1. Heartbeat timeout > 10s → degraded_mode=True
        2. Event drop count >= 3 → degraded_mode=True

    Implementation:
        Phase 1 완전 구현 (FLOW Section 2.4 준수)
    """
    # [1] Heartbeat Timeout Gate
    ws_last_heartbeat_ts = market_data.get_ws_last_heartbeat_ts()
    current_ts = market_data.get_timestamp()
    heartbeat_timeout_s = current_ts - ws_last_heartbeat_ts

    if heartbeat_timeout_s > 10.0:
        return WSHealthStatus(
            is_degraded=True,
            duration_s=heartbeat_timeout_s,
            reason=f"heartbeat_timeout_{heartbeat_timeout_s:.1f}s_exceeds_10s"
        )

    # [2] Event Drop Gate
    event_drop_count = market_data.get_ws_event_drop_count()

    if event_drop_count >= 3:
        return WSHealthStatus(
            is_degraded=True,
            duration_s=0.0,
            reason=f"event_drop_count_{event_drop_count}_exceeds_3"
        )

    # WS Healthy
    return WSHealthStatus(
        is_degraded=False,
        duration_s=0.0,
        reason=""
    )


def check_degraded_timeout(market_data, degraded_started_at: float) -> bool:
    """
    DEGRADED 지속 시간이 60s 이상인지 체크 (HALT 권고)

    Args:
        market_data: MarketDataInterface 구현체
        degraded_started_at: DEGRADED 시작 timestamp (unix time)

    Returns:
        bool: True이면 HALT 권고 (degraded duration >= 60s)

    FLOW: docs/constitution/FLOW.md Section 2.4
    Policy: docs/specs/account_builder_policy.md Section 7.2
    """
    current_ts = market_data.get_timestamp()
    degraded_duration_s = current_ts - degraded_started_at

    return degraded_duration_s >= 60.0


def check_ws_recovery(market_data) -> WSRecoveryStatus:
    """
    WS Recovery 조건 체크 (DEGRADED → normal 전환 가능 여부)

    Args:
        market_data: MarketDataInterface 구현체

    Returns:
        WSRecoveryStatus(can_recover, cooldown_minutes)

    Recovery 조건 (FLOW Section 2.4 & Policy Section 7.3):
        - heartbeat OK (timeout <= 10s)
        - event drop count == 0
        - Recovery 후 5분 cooldown

    Implementation:
        Phase 1: 단일 시점 recovery threshold 체크
        Phase 6: Orchestrator에서 recovery 조건 추적
    """
    # Check heartbeat
    ws_last_heartbeat_ts = market_data.get_ws_last_heartbeat_ts()
    current_ts = market_data.get_timestamp()
    heartbeat_timeout_s = current_ts - ws_last_heartbeat_ts

    if heartbeat_timeout_s > 10.0:
        return WSRecoveryStatus(
            can_recover=False,
            cooldown_minutes=0
        )

    # Check event drop
    event_drop_count = market_data.get_ws_event_drop_count()

    if event_drop_count != 0:
        return WSRecoveryStatus(
            can_recover=False,
            cooldown_minutes=0
        )

    # Recovery 조건 충족
    return WSRecoveryStatus(
        can_recover=True,
        cooldown_minutes=5
    )

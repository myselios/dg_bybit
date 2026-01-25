"""
tests/unit/test_ws_health.py

Gate: WS Health 구현 검증 (Phase 1)

Purpose:
  FLOW Section 2.4 기반 WS health 판단이 올바르게 동작하는지 검증한다.

  - heartbeat timeout > 10s → degraded_mode=True
  - event drop count >= 3 → degraded_mode=True
  - degraded duration >= 60s → HALT (manual reset)
  - WS recovery → degraded_mode=False + 5min cooldown

Failure Impact:
  - WS health 미작동 → 불완전한 데이터로 거래 지속
  - DEGRADED 미감지 → 이벤트 유실 상황에서 주문 실행
  - HALT 미작동 → 장기 degraded 상황에서 위험 증가

Execution:
  pytest tests/unit/test_ws_health.py -v
"""

import time
from infrastructure.exchange.fake_market_data import FakeMarketData
from application.ws_health import check_ws_health, check_ws_recovery, check_degraded_timeout


def test_heartbeat_timeout_10s_enters_degraded():
    """
    heartbeat timeout > 10s이면 degraded_mode=True.

    Given: heartbeat timeout = 11s
    When: check_ws_health 호출
    Then: is_degraded=True, duration_s >= 10

    FLOW: docs/constitution/FLOW.md Section 2.4
    """
    fake_data = FakeMarketData()
    fake_data.inject_ws_event(heartbeat_ok=False, event_drop_count=0)

    status = check_ws_health(fake_data)

    assert status.is_degraded is True, "heartbeat timeout > 10s should enter degraded"
    assert "heartbeat" in status.reason.lower() or "timeout" in status.reason.lower()


def test_event_drop_count_3_enters_degraded():
    """
    event drop count >= 3이면 degraded_mode=True.

    Given: event_drop_count = 5
    When: check_ws_health 호출
    Then: is_degraded=True

    FLOW: docs/constitution/FLOW.md Section 2.4
    """
    fake_data = FakeMarketData()
    fake_data.inject_ws_event(heartbeat_ok=True, event_drop_count=5)

    status = check_ws_health(fake_data)

    assert status.is_degraded is True, "event drop >= 3 should enter degraded"
    assert "drop" in status.reason.lower() or "event" in status.reason.lower()


def test_degraded_duration_60s_returns_halt():
    """
    degraded 지속 60s 이상이면 HALT 권고.

    Given: degraded_started_at = 현재 - 61s
    When: check_degraded_timeout 호출
    Then: should_halt=True

    FLOW: docs/constitution/FLOW.md Section 2.4
    Policy: docs/specs/account_builder_policy.md Section 7.2
    """
    fake_data = FakeMarketData()

    degraded_started_at = time.time() - 61.0  # 61초 전
    should_halt = check_degraded_timeout(fake_data, degraded_started_at)

    assert should_halt is True, "degraded duration >= 60s should trigger HALT"


def test_ws_recovery_exits_degraded():
    """
    WS recovery 조건 충족 시 degraded_mode=False.

    Given: heartbeat OK AND event drop == 0
    When: check_ws_recovery 호출
    Then: can_recover=True

    FLOW: docs/constitution/FLOW.md Section 2.4
    """
    fake_data = FakeMarketData()
    fake_data.inject_ws_event(heartbeat_ok=True, event_drop_count=0)

    recovery = check_ws_recovery(fake_data)

    assert recovery.can_recover is True, "heartbeat OK + drop 0 should allow recovery"


def test_ws_recovery_sets_5min_cooldown():
    """
    WS recovery 후 5분 cooldown 설정.

    Given: recovery 조건 충족
    When: check_ws_recovery 호출
    Then: cooldown_minutes=5

    Policy: docs/specs/account_builder_policy.md Section 7.3
    """
    fake_data = FakeMarketData()
    fake_data.inject_ws_event(heartbeat_ok=True, event_drop_count=0)

    recovery = check_ws_recovery(fake_data)

    assert recovery.cooldown_minutes == 5, "WS recovery must set 5min cooldown"

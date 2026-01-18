"""
tests/unit/test_emergency.py

Gate: Emergency Check 구현 검증 (Phase 1)

Purpose:
  Policy Section 7 기반 emergency 판단이 올바르게 동작하는지 검증한다.

  - price_drop_1m <= -10% → COOLDOWN
  - price_drop_5m <= -20% → COOLDOWN
  - balance anomaly (equity <= 0 OR stale > 30s) → HALT
  - latency_rest >= 5.0s → emergency_block=True

Failure Impact:
  - Emergency 미작동 → 급락/장애 상황에서 주문 계속 실행
  - HALT/COOLDOWN 오판 → 정상 상황에서 거래 중단
  - Auto-recovery 미작동 → 수동 개입 필요

Execution:
  pytest tests/unit/test_emergency.py -v
"""

import time
from infrastructure.exchange.fake_market_data import FakeMarketData
from application.emergency import check_emergency, check_recovery


def test_price_drop_1m_exceeds_threshold_enters_halt():
    """
    price_drop_1m <= -10%이면 HALT 진입 (FLOW Section 5 준수).

    Given: price_drop_1m = -12% (threshold 초과)
    When: check_emergency 호출
    Then: is_halt=True, is_blocked=False

    FLOW: docs/constitution/FLOW.md Section 5 (Emergency Priority)
    """
    fake_data = FakeMarketData()
    fake_data.inject_price_drop(pct_1m=-0.12, pct_5m=-0.05)

    status = check_emergency(fake_data)

    assert status.is_halt is True, "price_drop_1m <= -10% should trigger HALT"
    assert status.is_blocked is False, "price drop triggers HALT, not block"
    assert "price_drop_1m" in status.reason.lower()


def test_price_drop_5m_exceeds_threshold_enters_halt():
    """
    price_drop_5m <= -20%이면 HALT 진입 (FLOW Section 5 준수).

    Given: price_drop_5m = -22% (threshold 초과)
    When: check_emergency 호출
    Then: is_halt=True

    FLOW: docs/constitution/FLOW.md Section 5 (Emergency Priority)
    """
    fake_data = FakeMarketData()
    fake_data.inject_price_drop(pct_1m=-0.05, pct_5m=-0.22)

    status = check_emergency(fake_data)

    assert status.is_halt is True, "price_drop_5m <= -20% should trigger HALT"
    assert status.is_blocked is False
    assert "price_drop_5m" in status.reason.lower()


def test_price_drop_both_below_threshold_no_action():
    """
    price_drop이 threshold 미달이면 emergency 없음.

    Given: price_drop_1m = -5%, price_drop_5m = -10% (안전)
    When: check_emergency 호출
    Then: is_halt=False, is_blocked=False

    FLOW: 정상 변동성 허용
    """
    fake_data = FakeMarketData()
    fake_data.inject_price_drop(pct_1m=-0.05, pct_5m=-0.10)

    status = check_emergency(fake_data)

    assert status.is_halt is False, "price drop below threshold should not trigger"
    assert status.is_blocked is False
    assert status.reason == ""


def test_balance_anomaly_zero_equity_halts():
    """
    equity <= 0이면 HALT (balance anomaly).

    Given: equity_btc = 0.0
    When: check_emergency 호출
    Then: is_halt=True, is_cooldown=False

    Policy: docs/specs/account_builder_policy.md Section 7.1
    Criticality: equity <= 0 = 청산 또는 API 오류 → 즉시 중단
    """
    fake_data = FakeMarketData()
    fake_data.inject_balance_anomaly()  # equity = 0

    status = check_emergency(fake_data)

    assert status.is_halt is True, "equity <= 0 should trigger HALT"
    assert status.is_blocked is False, "balance anomaly is HALT, not block"
    assert "equity" in status.reason.lower() or "balance" in status.reason.lower()


def test_balance_anomaly_stale_timestamp_halts():
    """
    balance timestamp > 30s stale이면 HALT.

    Given: balance stale = 35초
    When: check_emergency 호출
    Then: is_halt=True

    Policy: docs/specs/account_builder_policy.md Section 7.1
    Criticality: stale > 30s = API 장애 → 신뢰 불가 → 중단
    """
    fake_data = FakeMarketData()
    fake_data.inject_stale_balance(stale_seconds=35.0)

    status = check_emergency(fake_data)

    assert status.is_halt is True, "balance stale > 30s should trigger HALT"
    assert "stale" in status.reason.lower() or "timestamp" in status.reason.lower()


def test_latency_exceeds_5s_sets_emergency_block():
    """
    latency_rest >= 5.0s이면 emergency_block=True (State 변경 없음).

    Given: latency_rest_p95 = 6.0s (threshold 초과)
    When: check_emergency 호출
    Then: is_blocked=True, is_halt=False, is_cooldown=False

    Policy: docs/specs/account_builder_policy.md Section 7.2
    Difference: emergency_block은 진입 차단만, State는 유지
    """
    fake_data = FakeMarketData()
    fake_data.inject_latency(value_s=6.0)

    status = check_emergency(fake_data)

    assert status.is_blocked is True, "latency >= 5.0s should set emergency_block"
    assert status.is_halt is False, "latency block is not HALT"
    assert "latency" in status.reason.lower()


def test_auto_recovery_after_5_consecutive_minutes():
    """
    Auto-recovery: drop_1m > -5% AND drop_5m > -10% for 5분.

    Given: COOLDOWN 상태, price_drop 5분간 정상
    When: check_recovery 호출
    Then: can_recover=True

    Policy: docs/specs/account_builder_policy.md Section 7.3
    Note: "5 consecutive minutes" 체크는 orchestrator에서 수행,
          여기서는 현재 drop이 recovery threshold 미달인지만 체크
    """
    fake_data = FakeMarketData()
    fake_data.inject_price_drop(pct_1m=-0.03, pct_5m=-0.08)  # 안전 범위

    cooldown_started_at = time.time() - 301.0  # 5분 1초 전 (5분 경과)
    recovery = check_recovery(fake_data, cooldown_started_at)

    assert recovery.can_recover is True, "price normalized for 5min should allow recovery"
    assert recovery.cooldown_minutes == 30, "auto-recovery should set 30min cooldown"


def test_auto_recovery_sets_30min_cooldown():
    """
    Auto-recovery 후 30분 cooldown 설정.

    Given: recovery 조건 충족
    When: check_recovery 호출
    Then: cooldown_minutes=30

    Policy: docs/specs/account_builder_policy.md Section 7.3
    """
    fake_data = FakeMarketData()
    fake_data.inject_price_drop(pct_1m=-0.02, pct_5m=-0.05)

    cooldown_started_at = time.time() - 301.0
    recovery = check_recovery(fake_data, cooldown_started_at)

    assert recovery.cooldown_minutes == 30, "auto-recovery must set 30min cooldown"

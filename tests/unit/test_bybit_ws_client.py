"""
tests/unit/test_bybit_ws_client.py
Bybit WebSocket Client - Contract Tests (네트워크 호출 0)

SSOT:
- task_plan.md Phase 7: Real API Integration (WS client 골격)
- FLOW.md Section 2.5: Event Processing (WS execution events)

테스트 범위:
1. subscribe topic 정확성 (execution.inverse)
2. disconnect/reconnect → DEGRADED 플래그
3. ping-pong timeout 처리
4. WS queue maxsize + overflow 정책 (실거래 함정 1)
5. Clock 주입 (determinism) (실거래 함정 2)
6. Testnet WSS URL 강제 assert (실거래 함정 3)
7. API key 누락 → 프로세스 시작 거부

금지:
- ❌ 실제 WS 연결 (connect 금지)
- ❌ Mainnet 엔드포인트 접근
"""

import time
from typing import Callable
from unittest.mock import Mock, patch, MagicMock
import pytest


def test_subscribe_topic_correctness_inverse():
    """
    Subscribe topic 정확성 (execution.inverse)

    SSOT: docs/plans/task_plan.md Phase 7 - subscribe topic 정확성

    검증:
    - Inverse futures는 execution.inverse topic 사용
    - Subscribe payload가 Bybit 스펙 만족
    """
    from infrastructure.exchange.bybit_ws_client import BybitWsClient

    # Given: WS client (Inverse category)
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url="wss://stream-testnet.bybit.com/v5/private",
        clock=fake_clock,
        category="inverse",
    )

    # When: Subscribe payload 생성
    subscribe_payload = client.get_subscribe_payload()

    # Then: topic이 execution.inverse
    assert "op" in subscribe_payload
    assert subscribe_payload["op"] == "subscribe"
    assert "args" in subscribe_payload
    assert "execution.inverse" in subscribe_payload["args"]


def test_subscribe_topic_correctness_linear():
    """
    Subscribe topic 정확성 (execution.linear)

    SSOT: docs/plans/task_plan.md Phase 7 - subscribe topic 정확성

    검증:
    - Linear futures는 execution.linear topic 사용
    - Subscribe payload가 Bybit 스펙 만족
    """
    from infrastructure.exchange.bybit_ws_client import BybitWsClient

    # Given: WS client (Linear category, default)
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url="wss://stream-testnet.bybit.com/v5/private",
        clock=fake_clock,
        category="linear",
    )

    # When: Subscribe payload 생성
    subscribe_payload = client.get_subscribe_payload()

    # Then: topic이 execution.linear
    assert "op" in subscribe_payload
    assert subscribe_payload["op"] == "subscribe"
    assert "args" in subscribe_payload
    assert "execution.linear" in subscribe_payload["args"]


def test_disconnect_triggers_degraded_flag():
    """
    Disconnect → DEGRADED 플래그 설정

    SSOT: docs/plans/task_plan.md Phase 7 - disconnect/reconnect 시 DEGRADED 플래그 설정

    검증:
    - WS 연결 끊김 → is_degraded() = True
    - DEGRADED 진입 시각 기록
    """
    from infrastructure.exchange.bybit_ws_client import BybitWsClient

    # Given: WS client
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url="wss://stream-testnet.bybit.com/v5/private",
        clock=fake_clock,
    )

    # When: Disconnect 발생 (시뮬레이션)
    client.on_disconnect()

    # Then: DEGRADED 플래그 설정
    assert client.is_degraded() is True
    assert client.get_degraded_entered_at() is not None


def test_reconnect_clears_degraded_flag():
    """
    Reconnect → DEGRADED 플래그 해제

    SSOT: docs/plans/task_plan.md Phase 7 - disconnect/reconnect 시 DEGRADED 플래그 설정

    검증:
    - Disconnect → DEGRADED = True
    - Reconnect → DEGRADED = False
    """
    from infrastructure.exchange.bybit_ws_client import BybitWsClient

    # Given: WS client (DEGRADED 상태)
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url="wss://stream-testnet.bybit.com/v5/private",
        clock=fake_clock,
    )
    client.on_disconnect()
    assert client.is_degraded() is True

    # When: Reconnect 성공 (시뮬레이션)
    client.on_reconnect()

    # Then: DEGRADED 플래그 해제
    assert client.is_degraded() is False
    assert client.get_degraded_entered_at() is None


def test_ping_pong_timeout_triggers_degraded():
    """
    Ping-pong timeout → DEGRADED 플래그

    SSOT: docs/plans/task_plan.md Phase 7 - ping-pong timeout 처리

    검증:
    - 마지막 pong 수신 후 20초 경과 → DEGRADED
    - Bybit private stream 요구사항 (max_active_time)
    """
    from infrastructure.exchange.bybit_ws_client import BybitWsClient

    # Given: WS client (fake clock)
    api_key = "test_key"
    api_secret = "test_secret"
    current_time = 1640000000.0
    fake_clock = lambda: current_time

    client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url="wss://stream-testnet.bybit.com/v5/private",
        clock=fake_clock,
        pong_timeout=20.0,  # 20초
    )

    # Given: Pong 수신 (초기 상태)
    client.on_pong_received()
    assert client.is_degraded() is False

    # When: 21초 경과 (fake clock 진행)
    current_time += 21.0
    client.check_pong_timeout()

    # Then: DEGRADED 플래그 설정
    assert client.is_degraded() is True


def test_ws_queue_maxsize_overflow_policy():
    """
    WS queue maxsize + overflow 정책 (실거래 함정 1)

    SSOT: docs/plans/task_plan.md Phase 7 - WS queue maxsize + overflow 정책 구현

    검증:
    - 큐 maxsize 설정 (예: 1000)
    - Overflow 시 가장 오래된 메시지 드랍
    - Drop count 추적
    """
    from infrastructure.exchange.bybit_ws_client import BybitWsClient

    # Given: WS client (maxsize=3)
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url="wss://stream-testnet.bybit.com/v5/private",
        clock=fake_clock,
        queue_maxsize=3,  # 최대 3개
    )

    # When: 4개 메시지 추가 (overflow)
    client.enqueue_message({"id": 1})
    client.enqueue_message({"id": 2})
    client.enqueue_message({"id": 3})
    client.enqueue_message({"id": 4})  # Overflow → 가장 오래된 메시지(id=1) 드랍

    # Then: 큐 크기 = 3 (maxsize 유지)
    assert client.get_queue_size() == 3

    # Then: Drop count = 1
    assert client.get_drop_count() == 1

    # Then: 큐에 남은 메시지는 id=2, 3, 4
    messages = []
    while client.get_queue_size() > 0:
        messages.append(client.dequeue_message())
    assert [m["id"] for m in messages] == [2, 3, 4]


def test_testnet_wss_url_enforced():
    """
    Testnet WSS URL 강제 assert (실거래 함정 3)

    SSOT: docs/plans/task_plan.md Phase 7 - testnet base_url 강제 assert

    검증:
    - Mainnet WSS URL → FatalConfigError
    - Testnet WSS URL → 통과
    """
    from infrastructure.exchange.bybit_ws_client import BybitWsClient, FatalConfigError

    # Given: API key/secret
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    # When/Then: Mainnet URL → FatalConfigError
    with pytest.raises(FatalConfigError, match="mainnet access forbidden before Phase 9"):
        BybitWsClient(
            api_key=api_key,
            api_secret=api_secret,
            wss_url="wss://stream.bybit.com/v5/private",  # Mainnet (금지)
            clock=fake_clock,
        )

    # When/Then: Testnet URL → 통과
    client = BybitWsClient(
        api_key=api_key,
        api_secret=api_secret,
        wss_url="wss://stream-testnet.bybit.com/v5/private",  # Testnet (허용)
        clock=fake_clock,
    )
    assert client.wss_url == "wss://stream-testnet.bybit.com/v5/private"


def test_missing_api_key_prevents_ws_start():
    """
    API key 누락 → WS client 시작 거부 (fail-fast)

    SSOT: docs/plans/task_plan.md Phase 7 - 키 누락 시 프로세스 시작 거부

    검증:
    - API key 누락 → FatalConfigError (프로세스 시작 불가)
    - API secret 누락 → FatalConfigError
    """
    from infrastructure.exchange.bybit_ws_client import BybitWsClient, FatalConfigError

    # Given: 누락된 API key
    fake_clock = lambda: 1640000000.0

    # When/Then: API key 누락 → FatalConfigError
    with pytest.raises(FatalConfigError, match="API key is required"):
        BybitWsClient(
            api_key="",  # 빈 문자열 (누락)
            api_secret="test_secret",
            wss_url="wss://stream-testnet.bybit.com/v5/private",
            clock=fake_clock,
        )

    # When/Then: API secret 누락 → FatalConfigError
    with pytest.raises(FatalConfigError, match="API secret is required"):
        BybitWsClient(
            api_key="test_key",
            api_secret="",  # 빈 문자열 (누락)
            wss_url="wss://stream-testnet.bybit.com/v5/private",
            clock=fake_clock,
        )

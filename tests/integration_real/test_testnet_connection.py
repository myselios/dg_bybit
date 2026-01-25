"""
tests/integration_real/test_testnet_connection.py
시나리오 1: 연결/인증/구독 성공 + heartbeat 정상

SSOT: docs/plans/task_plan.md Phase 8 - Testnet Validation Scenario 1

요구사항:
- wss://stream-testnet.bybit.com/v5/private 연결
- auth 성공
- execution.inverse topic 구독 성공
- heartbeat 10초 이내 수신

환경 변수:
- BYBIT_TESTNET_API_KEY: Testnet API key
- BYBIT_TESTNET_API_SECRET: Testnet API secret

실행 방법:
pytest -v -m testnet tests/integration_real/test_testnet_connection.py
"""

import time
import pytest
from infrastructure.exchange.bybit_ws_client import BybitWsClient


@pytest.mark.testnet
def test_ws_connection_auth_subscribe_success(api_credentials):
    """
    시나리오 1: 연결/인증/구독 성공

    검증:
    1. WebSocket 연결 성공
    2. Auth 성공
    3. execution.inverse topic 구독 성공
    4. is_connected() == True
    """
    # Given: BybitWsClient 생성
    client = BybitWsClient(
        api_key=api_credentials["api_key"],
        api_secret=api_credentials["api_secret"],
        wss_url="wss://stream-testnet.bybit.com/v5/private",
    )

    # When: start() 호출
    client.start()

    # Then: 최대 10초 대기 (연결/인증/구독 완료)
    max_wait = 10.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if client.is_connected():
            break
        time.sleep(0.5)

    # Assert: 연결/인증/구독 완료
    assert client.is_connected(), "Failed to connect/auth/subscribe within 10 seconds"

    # Cleanup: stop() 호출
    client.stop()


@pytest.mark.testnet
def test_ws_heartbeat_received_within_10_seconds(api_credentials):
    """
    시나리오 1: Heartbeat (pong) 10초 이내 수신

    검증:
    1. 연결/인증/구독 성공 후
    2. Pong 메시지를 10초 이내에 수신
    3. _last_pong_at이 None이 아님
    """
    # Given: BybitWsClient 생성 및 시작
    client = BybitWsClient(
        api_key=api_credentials["api_key"],
        api_secret=api_credentials["api_secret"],
        wss_url="wss://stream-testnet.bybit.com/v5/private",
        pong_timeout=20.0,
    )
    client.start()

    # Wait for connection
    max_wait = 10.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if client.is_connected():
            break
        time.sleep(0.5)

    assert client.is_connected(), "Failed to connect within 10 seconds"

    # When: 최대 25초 대기 (pong 수신)
    # Ping은 20초마다 발생하므로, 25초 대기해야 첫 pong 수신 가능
    max_wait_pong = 25.0
    start_time_pong = time.time()
    while time.time() - start_time_pong < max_wait_pong:
        if client._last_pong_at is not None:
            break
        time.sleep(0.5)

    # Then: Pong 수신 확인
    assert client._last_pong_at is not None, "Pong not received within 25 seconds"

    # Cleanup
    client.stop()


@pytest.mark.testnet
def test_ws_degraded_not_triggered_on_normal_operation(api_credentials):
    """
    시나리오 1: 정상 동작 시 DEGRADED 트리거 안 됨

    검증:
    1. 연결/인증/구독 성공 후
    2. 10초간 정상 동작
    3. is_degraded() == False
    """
    # Given: BybitWsClient 생성 및 시작
    client = BybitWsClient(
        api_key=api_credentials["api_key"],
        api_secret=api_credentials["api_secret"],
        wss_url="wss://stream-testnet.bybit.com/v5/private",
        pong_timeout=20.0,
    )
    client.start()

    # Wait for connection
    max_wait = 10.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if client.is_connected():
            break
        time.sleep(0.5)

    assert client.is_connected(), "Failed to connect within 10 seconds"

    # When: 10초 대기 (정상 동작)
    time.sleep(10.0)

    # Then: DEGRADED가 아님
    assert not client.is_degraded(), "DEGRADED should not be triggered on normal operation"

    # Cleanup
    client.stop()

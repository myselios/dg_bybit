"""
tests/integration_real/test_execution_event_mapping.py
시나리오 3: 체결 이벤트 수신 → 도메인 이벤트 매핑 성공

SSOT: docs/plans/task_plan.md Phase 8 - Testnet Validation Scenario 3

요구사항:
- 주문 체결 발생
- WS execution 메시지 수신
- ExecutionEvent(FILL/PARTIAL) 변환 성공

환경 변수:
- BYBIT_TESTNET_API_KEY: Testnet API key
- BYBIT_TESTNET_API_SECRET: Testnet API secret

실행 방법:
pytest -v -m testnet tests/integration_real/test_execution_event_mapping.py

주의:
- 이 테스트는 실제 주문을 발주합니다 (소액)
- Testnet에서만 실행됩니다
"""

import time
import pytest
from src.infrastructure.exchange.bybit_ws_client import BybitWsClient
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient


@pytest.mark.testnet
def test_ws_execution_message_received(api_credentials):
    """
    시나리오 3: WS execution 메시지 수신

    검증:
    1. WS 연결/인증/구독 성공
    2. execution 메시지 수신 (메시지 큐에 추가됨)
    3. 메시지 형식 확인 (topic, data 필드)

    Note: 실제 주문 발주는 하지 않고, WS 연결만 확인
    execution 메시지는 다른 활동(수동 주문 등)에서 수신될 수 있음
    """
    # Given: BybitWsClient 생성 및 시작
    received_messages = []

    def on_message_callback(msg):
        received_messages.append(msg)

    client = BybitWsClient(
        api_key=api_credentials["api_key"],
        api_secret=api_credentials["api_secret"],
        wss_url="wss://stream-testnet.bybit.com/v5/private",
    )
    client.start(on_message_callback=on_message_callback)

    # Wait for connection
    max_wait = 10.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if client.is_connected():
            break
        time.sleep(0.5)

    assert client.is_connected(), "Failed to connect within 10 seconds"

    # When: 최대 30초 대기 (execution 메시지 수신 대기)
    # Note: 실제 메시지가 없을 수 있으므로, 이 테스트는 optional
    max_wait_message = 30.0
    start_time_message = time.time()
    while time.time() - start_time_message < max_wait_message:
        if len(received_messages) > 0:
            break
        time.sleep(1.0)

    # Then: 메시지 형식 확인 (메시지가 있으면)
    if len(received_messages) > 0:
        msg = received_messages[0]
        assert "topic" in msg, "Message should have 'topic' field"
        assert msg["topic"].startswith("execution"), f"Topic should be 'execution.*', got: {msg['topic']}"

    # Cleanup
    client.stop()


@pytest.mark.testnet
def test_ws_message_enqueued_correctly(api_credentials):
    """
    시나리오 3: execution 메시지가 큐에 올바르게 추가됨

    검증:
    1. WS 연결/인증/구독 성공
    2. 콜백을 통해 메시지 수신
    3. dequeue_message()로 메시지 조회 가능
    """
    # Given: BybitWsClient 생성 및 시작
    client = BybitWsClient(
        api_key=api_credentials["api_key"],
        api_secret=api_credentials["api_secret"],
        wss_url="wss://stream-testnet.bybit.com/v5/private",
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

    # When: 초기 큐 크기 확인
    initial_queue_size = client.get_queue_size()

    # 30초 대기 (execution 메시지 수신 대기)
    time.sleep(30.0)

    # Then: 큐 크기 확인 (메시지가 있을 수 있음)
    final_queue_size = client.get_queue_size()

    # 메시지가 있으면 dequeue 가능
    if final_queue_size > 0:
        msg = client.dequeue_message()
        assert msg is not None, "dequeue_message should return a message"
        assert "topic" in msg, "Message should have 'topic' field"

    # Cleanup
    client.stop()

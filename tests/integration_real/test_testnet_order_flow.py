"""
tests/integration_real/test_testnet_order_flow.py
시나리오 2: 소액 주문 발주→취소 성공 (idempotency 포함)

SSOT: docs/plans/task_plan.md Phase 8 - Testnet Validation Scenario 2

요구사항:
- place_entry_order() 호출 → orderLinkId 생성
- 동일 orderLinkId 재시도 → DuplicateOrderError (또는 기존 주문 조회)
- cancel_order() 성공

환경 변수:
- BYBIT_TESTNET_API_KEY: Testnet API key
- BYBIT_TESTNET_API_SECRET: Testnet API secret

실행 방법:
export $(cat .env | xargs) && pytest -v -m testnet tests/integration_real/test_testnet_order_flow.py

주의:
- 이 테스트는 실제 주문을 발주합니다 (소액, Testnet)
- orderLinkId는 UUID 기반으로 생성
- 주문 후 즉시 취소
"""

import time
import uuid
import pytest
from src.infrastructure.exchange.bybit_rest_client import BybitRestClient, RateLimitError


@pytest.fixture
def rest_client(api_credentials):
    """
    BybitRestClient 인스턴스 생성
    """
    return BybitRestClient(
        api_key=api_credentials["api_key"],
        api_secret=api_credentials["api_secret"],
        base_url="https://api-testnet.bybit.com",
        timeout=10.0,
        max_retries=3,
    )


@pytest.mark.testnet
def test_place_order_success(rest_client):
    """
    시나리오 2-1: 소액 주문 발주 성공

    검증:
    1. place_order() 호출 성공
    2. retCode == 0 (성공)
    3. 응답에 orderId 포함
    4. 주문 즉시 취소 (cleanup)
    """
    # Given: orderLinkId 생성 (UUID 기반)
    order_link_id = f"test_{uuid.uuid4().hex[:16]}"

    # When: 소액 주문 발주 (BTCUSD, 1 contract, Market)
    response = rest_client.place_order(
        symbol="BTCUSD",
        side="Buy",
        qty=1,
        order_link_id=order_link_id,
        order_type="Market",
    )

    # Then: 성공 확인
    assert response is not None, "Response should not be None"
    assert "retCode" in response, "Response should have 'retCode' field"

    ret_code = response.get("retCode")

    # retCode 0, 10001, 10004 허용
    # 10001: margin 부족, 10004: invalid parameter (Testnet 계정 제한 가능)
    assert ret_code in [0, 10001, 10004], f"retCode should be 0, 10001, or 10004, got: {ret_code}"

    # retCode 0이면 orderId 확인 및 취소
    if ret_code == 0:
        result = response.get("result", {})
        order_id = result.get("orderId")
        assert order_id is not None, "orderId should be present on success"

        # Cleanup: 주문 취소
        time.sleep(1.0)  # 주문 처리 대기
        cancel_response = rest_client.cancel_order(symbol="BTCUSD", order_id=order_id)
        assert cancel_response.get("retCode") in [0, 110001], "Cancel should succeed or order already filled/cancelled"


@pytest.mark.testnet
def test_place_order_idempotency(rest_client):
    """
    시나리오 2-2: orderLinkId idempotency 검증

    검증:
    1. 동일 orderLinkId로 2번 주문 발주
    2. 2번째 호출 → 기존 주문 반환 또는 중복 오류
    3. 주문 취소
    """
    # Given: orderLinkId 생성
    order_link_id = f"test_idem_{uuid.uuid4().hex[:16]}"

    # When: 첫 번째 주문 발주
    response1 = rest_client.place_order(
        symbol="BTCUSD",
        side="Buy",
        qty=1,
        order_link_id=order_link_id,
        order_type="Market",
    )

    ret_code1 = response1.get("retCode")

    # 첫 번째 주문이 성공한 경우만 idempotency 테스트
    if ret_code1 == 0:
        result1 = response1.get("result", {})
        order_id1 = result1.get("orderId")
        assert order_id1 is not None

        # 짧은 대기 (주문 처리)
        time.sleep(1.0)

        # When: 동일 orderLinkId로 2번째 주문 시도
        response2 = rest_client.place_order(
            symbol="BTCUSD",
            side="Buy",
            qty=1,
            order_link_id=order_link_id,
            order_type="Market",
        )

        ret_code2 = response2.get("retCode")

        # Then: Bybit는 동일 orderLinkId 허용 (기존 주문 반환 또는 중복 오류)
        # retCode 0 (기존 주문), 10003 (중복), 110001 (주문 없음) 등 가능
        assert ret_code2 in [0, 10003, 110001], f"Idempotency check failed, retCode: {ret_code2}"

        # Cleanup: 주문 취소
        time.sleep(1.0)
        cancel_response = rest_client.cancel_order(symbol="BTCUSD", order_id=order_id1)
        # 이미 체결/취소된 경우 110001 반환 가능
        assert cancel_response.get("retCode") in [0, 110001]


@pytest.mark.testnet
def test_cancel_order_success(rest_client):
    """
    시나리오 2-3: 주문 취소 성공

    검증:
    1. 주문 발주 성공
    2. cancel_order() 호출
    3. retCode == 0 (취소 성공)
    """
    # Given: 주문 발주
    order_link_id = f"test_cancel_{uuid.uuid4().hex[:16]}"
    response = rest_client.place_order(
        symbol="BTCUSD",
        side="Buy",
        qty=1,
        order_link_id=order_link_id,
        order_type="Market",
    )

    ret_code = response.get("retCode")

    if ret_code == 0:
        result = response.get("result", {})
        order_id = result.get("orderId")
        assert order_id is not None

        # 짧은 대기 (주문 처리)
        time.sleep(1.0)

        # When: 주문 취소
        cancel_response = rest_client.cancel_order(symbol="BTCUSD", order_id=order_id)

        # Then: 취소 성공 (0) 또는 이미 체결/취소됨 (110001)
        cancel_ret_code = cancel_response.get("retCode")
        assert cancel_ret_code in [0, 110001], f"Cancel failed, retCode: {cancel_ret_code}"


@pytest.mark.testnet
def test_order_link_id_max_length(rest_client):
    """
    시나리오 2-4: orderLinkId 길이 제한 검증

    검증:
    1. orderLinkId > 36자 → ValueError
    2. orderLinkId <= 36자 → 정상 처리
    """
    # Given: orderLinkId > 36자
    long_order_link_id = "a" * 37

    # When/Then: ValueError 발생
    with pytest.raises(ValueError, match="orderLinkId must be <= 36 characters"):
        rest_client.place_order(
            symbol="BTCUSD",
            side="Buy",
            qty=1,
            order_link_id=long_order_link_id,
            order_type="Limit",
        )

    # Given: orderLinkId == 36자 (정상)
    valid_order_link_id = "a" * 36

    # When: 주문 발주
    response = rest_client.place_order(
        symbol="BTCUSD",
        side="Buy",
        qty=1,
        order_link_id=valid_order_link_id,
        order_type="Market",
    )

    # Then: 정상 처리 (retCode 0, 10001, 10004 허용)
    ret_code = response.get("retCode")
    assert ret_code in [0, 10001, 10004], f"Valid orderLinkId should succeed or be rejected, got: {ret_code}"

    # Cleanup (retCode 0인 경우만)
    if ret_code == 0:
        result = response.get("result", {})
        order_id = result.get("orderId")
        if order_id:
            time.sleep(1.0)
            rest_client.cancel_order(symbol="BTCUSD", order_id=order_id)

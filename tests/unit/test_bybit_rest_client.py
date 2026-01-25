"""
tests/unit/test_bybit_rest_client.py
Bybit REST Client - Contract Tests (네트워크 호출 0)

SSOT:
- task_plan.md Phase 7: Real API Integration (클라이언트 골격)
- FLOW.md Section 6: Fee Tracking (REST API 호출)

테스트 범위:
1. 서명 생성 determinism
2. Bybit 스펙 만족 (payload 검증)
3. Rate limit 헤더 처리 (X-Bapi-*)
4. retCode 10006 → backoff
5. Timeout/retry 정책
6. Testnet base_url 강제 assert
7. API key 누락 → 프로세스 시작 거부
8. Clock 주입 (determinism)
9. orderLinkId <= 36자
10. Cancel order payload 검증

금지:
- ❌ 실제 네트워크 호출 (DNS resolve 포함)
- ❌ Mainnet 엔드포인트 접근
"""

import time
from typing import Callable
from unittest.mock import Mock, patch
import pytest


def test_generate_signature_is_deterministic():
    """
    서명 생성이 deterministic (동일 입력 → 동일 서명)

    SSOT: docs/plans/task_plan.md Phase 7 - 서명 생성이 deterministic

    검증:
    - 동일한 timestamp + params → 동일한 서명
    - HMAC SHA256 사용
    """
    from infrastructure.exchange.bybit_rest_client import BybitRestClient

    # Given: API key/secret + 고정 timestamp
    api_key = "test_api_key"
    api_secret = "test_api_secret"
    timestamp = 1640000000000  # 고정 timestamp

    # Given: Clock injection (deterministic timestamp)
    fake_clock = lambda: timestamp / 1000.0

    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com",
        clock=fake_clock,
    )

    # When: 동일한 params로 서명 2번 생성
    params = {"symbol": "BTCUSD", "side": "Buy", "qty": 100}
    signature_1 = client._generate_signature(timestamp, params)
    signature_2 = client._generate_signature(timestamp, params)

    # Then: 서명이 동일 (deterministic)
    assert signature_1 == signature_2
    assert isinstance(signature_1, str)
    assert len(signature_1) > 0


def test_place_order_payload_satisfies_bybit_spec():
    """
    Place order payload가 Bybit 스펙 만족

    SSOT: docs/plans/task_plan.md Phase 7 - 요청 payload가 Bybit 스펙 만족

    검증:
    - 필수 필드: symbol, side, orderType, qty, timeInForce
    - orderLinkId 존재 (idempotency)
    - category="inverse" (코인마진드)
    """
    from infrastructure.exchange.bybit_rest_client import BybitRestClient

    # Given: REST client (네트워크 호출 mock)
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com",
        clock=fake_clock,
    )

    # When: place_order() 호출 (mock response)
    with patch("requests.post") as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}  # 빈 딕셔너리 (rate limit 헤더 없음)
        mock_response.json.return_value = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"orderId": "test_order_123"},
        }
        mock_post.return_value = mock_response

        order_link_id = "test_link_123"
        client.place_order(
            symbol="BTCUSD",
            side="Buy",
            qty=100,
            order_link_id=order_link_id,
        )

        # Then: 요청 payload 검증
        call_kwargs = mock_post.call_args.kwargs
        # POST 요청은 data= 키에 JSON 문자열로 전송됨 (V5 API)
        request_data = call_kwargs.get("data", "{}")
        import json
        request_json = json.loads(request_data)

        # 필수 필드 존재
        assert request_json["symbol"] == "BTCUSD"
        assert request_json["side"] == "Buy"
        assert request_json["orderType"] == "Market"  # Default
        assert request_json["qty"] == "100"  # V5 API: qty는 string
        assert request_json["timeInForce"] == "GoodTillCancel"  # Default
        assert request_json["orderLinkId"] == order_link_id
        assert request_json["category"] == "linear"  # Default (V5 Linear USDT)


def test_order_link_id_max_length_36_chars():
    """
    orderLinkId <= 36자 검증 (Bybit 스펙)

    SSOT: docs/plans/task_plan.md Phase 7 - orderLinkId<=36 등

    검증:
    - orderLinkId > 36자 → ValueError
    - orderLinkId <= 36자 → 통과
    """
    from infrastructure.exchange.bybit_rest_client import BybitRestClient

    # Given: REST client
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com",
        clock=fake_clock,
    )

    # When/Then: orderLinkId > 36자 → ValueError
    with pytest.raises(ValueError, match="orderLinkId must be <= 36 characters"):
        client.place_order(
            symbol="BTCUSD",
            side="Buy",
            qty=100,
            order_link_id="a" * 37,  # 37자 (초과)
        )

    # When/Then: orderLinkId = 36자 → 통과 (mock response)
    with patch("requests.post") as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}  # 빈 딕셔너리
        mock_response.json.return_value = {"retCode": 0, "result": {}}
        mock_post.return_value = mock_response

        client.place_order(
            symbol="BTCUSD",
            side="Buy",
            qty=100,
            order_link_id="a" * 36,  # 36자 (정확히 max)
        )
        # No exception raised


def test_rate_limit_headers_parsed_correctly():
    """
    Rate limit 헤더 처리 로직 (가짜 헤더 주입)

    SSOT: docs/plans/task_plan.md Phase 7 - Rate limit 헤더 처리 로직

    검증:
    - X-Bapi-Limit-Status 파싱
    - X-Bapi-Limit-Reset-Timestamp 파싱
    - 남은 요청 수 / 리셋 시각 추출
    """
    from infrastructure.exchange.bybit_rest_client import BybitRestClient

    # Given: REST client
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com",
        clock=fake_clock,
    )

    # When: Rate limit 헤더 포함한 응답 (mock)
    with patch("requests.post") as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            "X-Bapi-Limit-Status": "119",  # 남은 요청 수
            "X-Bapi-Limit-Reset-Timestamp": "1640000060000",  # 리셋 시각 (60초 후)
        }
        mock_response.json.return_value = {"retCode": 0, "result": {}}
        mock_post.return_value = mock_response

        result = client.place_order(
            symbol="BTCUSD",
            side="Buy",
            qty=100,
            order_link_id="test_link",
        )

        # Then: Rate limit 정보 추출 (client.last_rate_limit_info)
        rate_limit_info = client.get_last_rate_limit_info()
        assert rate_limit_info is not None
        assert rate_limit_info["remaining"] == 119
        assert rate_limit_info["reset_timestamp"] == 1640000060000


def test_retcode_10006_triggers_backoff():
    """
    retCode 10006 → backoff 동작

    SSOT: docs/plans/task_plan.md Phase 7 - retCode 10006 → backoff 동작

    검증:
    - retCode 10006 (rate limit exceeded)
    - RateLimitError 발생
    - retry_after 정보 포함
    """
    from infrastructure.exchange.bybit_rest_client import BybitRestClient, RateLimitError

    # Given: REST client
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com",
        clock=fake_clock,
    )

    # When: retCode 10006 응답 (mock)
    with patch("requests.post") as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            "X-Bapi-Limit-Reset-Timestamp": "1640000060000",  # 60초 후 리셋
        }
        mock_response.json.return_value = {
            "retCode": 10006,
            "retMsg": "Too many visits",
        }
        mock_post.return_value = mock_response

        # Then: RateLimitError 발생
        with pytest.raises(RateLimitError) as exc_info:
            client.place_order(
                symbol="BTCUSD",
                side="Buy",
                qty=100,
                order_link_id="test_link",
            )

        # retry_after 정보 포함
        error = exc_info.value
        assert error.retry_after is not None
        assert error.retry_after == 60.0  # 60초 대기


def test_timeout_triggers_retry():
    """
    Timeout → retry 동작

    SSOT: docs/plans/task_plan.md Phase 7 - Timeout/retry 정책

    검증:
    - Timeout 발생 시 재시도
    - 최대 3회 재시도
    - 3회 실패 시 TimeoutError 발생
    """
    from infrastructure.exchange.bybit_rest_client import BybitRestClient
    import requests

    # Given: REST client
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com",
        clock=fake_clock,
        timeout=5.0,
        max_retries=3,
    )

    # When: Timeout 발생 (mock)
    with patch("requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.Timeout("Connection timeout")

        # Then: TimeoutError 발생 (3회 재시도 후)
        with pytest.raises(requests.exceptions.Timeout):
            client.place_order(
                symbol="BTCUSD",
                side="Buy",
                qty=100,
                order_link_id="test_link",
            )

        # 3회 재시도 검증
        assert mock_post.call_count == 3


def test_testnet_base_url_enforced():
    """
    Testnet base_url 강제 assert (mainnet 접근 차단)

    SSOT: docs/plans/task_plan.md Phase 7 - testnet base_url 강제 assert

    검증:
    - Mainnet URL → FatalConfigError
    - Testnet URL → 통과
    """
    from infrastructure.exchange.bybit_rest_client import BybitRestClient, FatalConfigError

    # Given: API key/secret
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    # When/Then: Mainnet URL → FatalConfigError
    with pytest.raises(FatalConfigError, match="mainnet access forbidden before Phase 9"):
        BybitRestClient(
            api_key=api_key,
            api_secret=api_secret,
            base_url="https://api.bybit.com",  # Mainnet (금지)
            clock=fake_clock,
        )

    # When/Then: Testnet URL → 통과
    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com",  # Testnet (허용)
        clock=fake_clock,
    )
    assert client.base_url == "https://api-testnet.bybit.com"


def test_missing_api_key_prevents_process_start():
    """
    API key 누락 → 프로세스 시작 거부 (fail-fast)

    SSOT: docs/plans/task_plan.md Phase 7 - 키 누락 시 프로세스 시작 거부

    검증:
    - API key 누락 → FatalConfigError (프로세스 시작 불가)
    - API secret 누락 → FatalConfigError
    """
    from infrastructure.exchange.bybit_rest_client import BybitRestClient, FatalConfigError

    # Given: 누락된 API key
    fake_clock = lambda: 1640000000.0

    # When/Then: API key 누락 → FatalConfigError
    with pytest.raises(FatalConfigError, match="API key is required"):
        BybitRestClient(
            api_key="",  # 빈 문자열 (누락)
            api_secret="test_secret",
            base_url="https://api-testnet.bybit.com",
            clock=fake_clock,
        )

    # When/Then: API secret 누락 → FatalConfigError
    with pytest.raises(FatalConfigError, match="API secret is required"):
        BybitRestClient(
            api_key="test_key",
            api_secret="",  # 빈 문자열 (누락)
            base_url="https://api-testnet.bybit.com",
            clock=fake_clock,
        )


def test_clock_injection_for_deterministic_timestamp():
    """
    Clock 주입 (deterministic timestamp)

    SSOT: docs/plans/task_plan.md Phase 7 - Clock 주입 (fake clock 테스트 가능)

    검증:
    - Fake clock 주입 시 timestamp가 고정
    - 서명에 clock timestamp 사용
    """
    from infrastructure.exchange.bybit_rest_client import BybitRestClient

    # Given: Fake clock (고정 timestamp)
    fixed_timestamp = 1640000000.0
    fake_clock = lambda: fixed_timestamp

    api_key = "test_key"
    api_secret = "test_secret"

    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com",
        clock=fake_clock,
    )

    # When: _get_timestamp() 호출
    timestamp_ms = client._get_timestamp()

    # Then: Fake clock의 timestamp 사용 (고정)
    assert timestamp_ms == int(fixed_timestamp * 1000)

    # When: 다시 호출해도 동일 (deterministic)
    timestamp_ms_2 = client._get_timestamp()
    assert timestamp_ms_2 == timestamp_ms


def test_cancel_order_payload_satisfies_bybit_spec():
    """
    Cancel order payload가 Bybit 스펙 만족

    SSOT: docs/plans/task_plan.md Phase 7 - 요청 payload가 Bybit 스펙 만족

    검증:
    - 필수 필드: symbol, orderId (또는 orderLinkId)
    - category="inverse"
    """
    from infrastructure.exchange.bybit_rest_client import BybitRestClient

    # Given: REST client
    api_key = "test_key"
    api_secret = "test_secret"
    fake_clock = lambda: 1640000000.0

    client = BybitRestClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://api-testnet.bybit.com",
        clock=fake_clock,
    )

    # When: cancel_order() 호출 (mock response)
    with patch("requests.post") as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}  # 빈 딕셔너리
        mock_response.json.return_value = {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"orderId": "cancel_order_123"},
        }
        mock_post.return_value = mock_response

        client.cancel_order(
            symbol="BTCUSD",
            order_id="test_order_123",
        )

        # Then: 요청 payload 검증
        call_kwargs = mock_post.call_args.kwargs
        # POST 요청은 data= 키에 JSON 문자열로 전송됨 (V5 API)
        request_data = call_kwargs.get("data", "{}")
        import json
        request_json = json.loads(request_data)

        # 필수 필드 존재
        assert request_json["symbol"] == "BTCUSD"
        assert request_json["orderId"] == "test_order_123"
        assert request_json["category"] == "linear"  # Default (V5 Linear USDT)

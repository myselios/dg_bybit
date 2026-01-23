"""
src/infrastructure/exchange/bybit_rest_client.py
Bybit REST API Client (골격만, Contract tests only)

SSOT:
- task_plan.md Phase 7: Real API Integration (클라이언트 골격)
- FLOW.md Section 6: Fee Tracking (REST API 호출)

원칙:
1. 실제 네트워크 호출 금지 (Phase 7에서는 contract tests만)
2. Testnet base_url 강제 assert (mainnet 접근 차단)
3. API key 누락 → 프로세스 시작 거부 (fail-fast)
4. Clock 주입 (deterministic timestamp)
5. Rate limit 헤더 기반 throttle (X-Bapi-*)

Exports:
- BybitRestClient: REST API client
- FatalConfigError: 설정 오류 (프로세스 시작 불가)
- RateLimitError: Rate limit 초과
"""

import hashlib
import hmac
import time
from typing import Callable, Dict, Any, Optional
import requests


class FatalConfigError(Exception):
    """
    설정 오류 (프로세스 시작 불가)

    SSOT: task_plan.md Phase 7 - 키 누락 시 프로세스 시작 거부
    """

    pass


class RateLimitError(Exception):
    """
    Rate limit 초과

    SSOT: task_plan.md Phase 7 - retCode 10006 → backoff 동작
    """

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class BybitRestClient:
    """
    Bybit REST API Client (골격만, Contract tests only)

    SSOT: task_plan.md Phase 7
    - 서명 생성 deterministic
    - Bybit 스펙 만족 (payload 검증)
    - Rate limit 헤더 처리 (X-Bapi-*)
    - retCode 10006 → backoff
    - Timeout/retry 정책
    - Testnet base_url 강제 assert
    - API key 누락 → 프로세스 시작 거부
    - Clock 주입 (determinism)
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str,
        clock: Optional[Callable[[], float]] = None,
        timeout: float = 5.0,
        max_retries: int = 3,
    ):
        """
        Bybit REST Client 초기화

        Args:
            api_key: API key (필수)
            api_secret: API secret (필수)
            base_url: API base URL (testnet 강제)
            clock: Timestamp 생성 함수 (기본: time.time)
            timeout: 요청 타임아웃 (초)
            max_retries: 최대 재시도 횟수

        Raises:
            FatalConfigError: API key/secret 누락 또는 mainnet URL
        """
        # API key/secret 검증 (fail-fast)
        if not api_key:
            raise FatalConfigError("API key is required")
        if not api_secret:
            raise FatalConfigError("API secret is required")

        # Testnet base_url 강제 assert (mainnet 접근 차단)
        if "api-testnet.bybit.com" not in base_url:
            raise FatalConfigError("mainnet access forbidden before Phase 9")

        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.clock = clock or time.time
        self.timeout = timeout
        self.max_retries = max_retries

        # Rate limit 정보 추적
        self._last_rate_limit_info: Optional[Dict[str, Any]] = None

    def _get_timestamp(self) -> int:
        """
        현재 timestamp (milliseconds)

        Returns:
            int: timestamp (ms)

        SSOT: task_plan.md Phase 7 - Clock 주입 (determinism)
        """
        return int(self.clock() * 1000)

    def _generate_signature(self, timestamp: int, params: Dict[str, Any]) -> str:
        """
        HMAC SHA256 서명 생성

        Args:
            timestamp: timestamp (ms)
            params: 요청 파라미터

        Returns:
            str: HMAC SHA256 서명

        SSOT: task_plan.md Phase 7 - 서명 생성이 deterministic
        """
        # Bybit 서명 스펙: timestamp + api_key + params_str
        # params_str: 알파벳 순으로 정렬된 key=value 문자열
        params_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        payload = f"{timestamp}{self.api_key}{params_str}"

        # HMAC SHA256
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    def _parse_rate_limit_headers(self, headers: Dict[str, str]) -> None:
        """
        Rate limit 헤더 파싱

        Args:
            headers: 응답 헤더

        SSOT: task_plan.md Phase 7 - Rate limit 헤더 처리 로직
        """
        remaining = headers.get("X-Bapi-Limit-Status")
        reset_timestamp = headers.get("X-Bapi-Limit-Reset-Timestamp")

        if remaining is not None and reset_timestamp is not None:
            self._last_rate_limit_info = {
                "remaining": int(remaining),
                "reset_timestamp": int(reset_timestamp),
            }

    def get_last_rate_limit_info(self) -> Optional[Dict[str, Any]]:
        """
        마지막 rate limit 정보 반환

        Returns:
            Optional[Dict]: Rate limit 정보 (remaining, reset_timestamp)
        """
        return self._last_rate_limit_info

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        HTTP 요청 수행 (timeout/retry 포함)

        Args:
            method: HTTP method (POST, GET 등)
            endpoint: API endpoint
            params: 요청 파라미터

        Returns:
            Dict: 응답 JSON

        Raises:
            RateLimitError: retCode 10006 (rate limit)
            requests.exceptions.Timeout: Timeout (max_retries 초과)
        """
        params = params or {}
        url = f"{self.base_url}{endpoint}"
        timestamp = self._get_timestamp()

        # 서명 생성
        signature = self._generate_signature(timestamp, params)

        # 헤더 구성
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": str(timestamp),
            "Content-Type": "application/json",
        }

        # Retry loop
        for attempt in range(self.max_retries):
            try:
                if method == "POST":
                    response = requests.post(
                        url,
                        json=params,
                        headers=headers,
                        timeout=self.timeout,
                    )
                else:
                    response = requests.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=self.timeout,
                    )

                # Rate limit 헤더 파싱
                self._parse_rate_limit_headers(response.headers)

                # 응답 처리
                response_json = response.json()

                # retCode 10006 → RateLimitError
                if response_json.get("retCode") == 10006:
                    retry_after = 60.0  # 기본값 60초
                    if self._last_rate_limit_info is not None:
                        reset_timestamp = self._last_rate_limit_info.get("reset_timestamp", 0)
                        current_timestamp = self._get_timestamp()
                        retry_after = (reset_timestamp - current_timestamp) / 1000.0
                    raise RateLimitError("Rate limit exceeded", retry_after=retry_after)

                return response_json

            except requests.exceptions.Timeout:
                # 마지막 시도에서 실패하면 예외 발생
                if attempt == self.max_retries - 1:
                    raise
                # 재시도 (다음 루프)
                continue

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        order_link_id: str,
        order_type: str = "Market",
        time_in_force: str = "GoodTillCancel",
    ) -> Dict[str, Any]:
        """
        주문 발주

        Args:
            symbol: 심볼 (예: BTCUSD)
            side: Buy 또는 Sell
            qty: 수량 (contracts)
            order_link_id: orderLinkId (idempotency)
            order_type: 주문 타입 (기본: Market)
            time_in_force: 유효 기간 (기본: GoodTillCancel)

        Returns:
            Dict: 응답 JSON

        Raises:
            ValueError: orderLinkId > 36자
            RateLimitError: Rate limit 초과

        SSOT: task_plan.md Phase 7 - 요청 payload가 Bybit 스펙 만족
        """
        # orderLinkId <= 36자 검증
        if len(order_link_id) > 36:
            raise ValueError("orderLinkId must be <= 36 characters")

        # Bybit 스펙 payload
        params = {
            "category": "inverse",  # 코인마진드
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "timeInForce": time_in_force,
            "orderLinkId": order_link_id,
        }

        return self._make_request("POST", "/v5/order/create", params)

    def cancel_order(
        self,
        symbol: str,
        order_id: str,
    ) -> Dict[str, Any]:
        """
        주문 취소

        Args:
            symbol: 심볼 (예: BTCUSD)
            order_id: 주문 ID

        Returns:
            Dict: 응답 JSON

        SSOT: task_plan.md Phase 7 - 요청 payload가 Bybit 스펙 만족
        """
        params = {
            "category": "inverse",
            "symbol": symbol,
            "orderId": order_id,
        }

        return self._make_request("POST", "/v5/order/cancel", params)

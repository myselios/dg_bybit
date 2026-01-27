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
import os
from typing import Callable, Dict, Any, Optional
import requests


class FatalConfigError(Exception):
    """
    설정 오류 (프로세스 시작 불가)

    SSOT: docs/plans/task_plan.md Phase 7 - 키 누락 시 프로세스 시작 거부
    """

    pass


class RateLimitError(Exception):
    """
    Rate limit 초과

    SSOT: docs/plans/task_plan.md Phase 7 - retCode 10006 → backoff 동작
    """

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class BybitRestClient:
    """
    Bybit REST API Client (골격만, Contract tests only)

    SSOT: docs/plans/task_plan.md Phase 7
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

        # Phase 12b: Mainnet 접근 허용 (BYBIT_TESTNET=false 확인)
        # Testnet mode: api-testnet.bybit.com 강제
        # Mainnet mode: api.bybit.com 허용 (BYBIT_TESTNET=false일 때만)
        testnet_mode = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

        if testnet_mode and "api-testnet.bybit.com" not in base_url:
            raise FatalConfigError(
                "BYBIT_TESTNET=true but base_url is not Testnet. "
                "Use 'https://api-testnet.bybit.com' for Testnet."
            )

        if not testnet_mode and "api.bybit.com" not in base_url:
            raise FatalConfigError(
                "BYBIT_TESTNET=false but base_url is not Mainnet. "
                "Use 'https://api.bybit.com' for Mainnet."
            )

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

        SSOT: docs/plans/task_plan.md Phase 7 - Clock 주입 (determinism)
        """
        return int(self.clock() * 1000)

    def _generate_signature(self, timestamp: int, params: Dict[str, Any], method: str = "GET") -> str:
        """
        HMAC SHA256 서명 생성 (Bybit V5 API)

        Args:
            timestamp: timestamp (ms)
            params: 요청 파라미터
            method: HTTP method ("GET" or "POST")

        Returns:
            str: HMAC SHA256 서명

        SSOT: docs/plans/task_plan.md Phase 7 - 서명 생성이 deterministic
        Bybit V5 API Signature Spec:
        - GET: timestamp + apiKey + recvWindow + queryString
        - POST: timestamp + apiKey + recvWindow + JSON_BODY
        """
        recv_window = 5000  # Default 5000ms

        if method == "POST":
            # POST: JSON body 사용
            import json
            params_str = json.dumps(params, separators=(',', ':'), sort_keys=True)
        else:
            # GET: Query string 사용
            params_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))

        payload = f"{timestamp}{self.api_key}{recv_window}{params_str}"

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

        SSOT: docs/plans/task_plan.md Phase 7 - Rate limit 헤더 처리 로직
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
        signature = self._generate_signature(timestamp, params, method)

        # 헤더 구성
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": str(timestamp),
            "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type": "application/json",
        }

        # Retry loop
        for attempt in range(self.max_retries):
            try:
                if method == "POST":
                    # POST: JSON body를 직렬화해서 전송 (서명과 동일한 형식)
                    import json
                    json_body = json.dumps(params, separators=(',', ':'), sort_keys=True)
                    response = requests.post(
                        url,
                        data=json_body,
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
        price: Optional[str] = None,
        category: str = "linear",
    ) -> Dict[str, Any]:
        """
        주문 발주

        Args:
            symbol: 심볼 (예: BTCUSDT for Linear, BTCUSD for Inverse)
            side: Buy 또는 Sell
            qty: 수량 (contracts)
            order_link_id: orderLinkId (idempotency)
            order_type: 주문 타입 (기본: Market)
            time_in_force: 유효 기간 (기본: GoodTillCancel)
            price: 주문 가격 (Limit 주문 시 필수)
            category: 카테고리 (기본: linear)

        Returns:
            Dict: 응답 JSON

        Raises:
            ValueError: orderLinkId > 36자 또는 Limit 주문에 price 없음
            RateLimitError: Rate limit 초과

        SSOT: docs/plans/task_plan.md Phase 7 - 요청 payload가 Bybit 스펙 만족
        ADR-0002: Linear USDT Migration (category="linear" 기본값)
        """
        # orderLinkId <= 36자 검증
        if len(order_link_id) > 36:
            raise ValueError("orderLinkId must be <= 36 characters")

        # Limit 주문에는 price 필수
        if order_type == "Limit" and price is None:
            raise ValueError("Limit order requires price")

        # Bybit 스펙 payload
        params = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),  # Bybit API는 string으로 받음
            "timeInForce": time_in_force,
            "orderLinkId": order_link_id,
        }

        # Limit 주문이면 price 추가
        if price is not None:
            params["price"] = price

        return self._make_request("POST", "/v5/order/create", params)

    def cancel_order(
        self,
        symbol: str,
        order_id: str,
        category: str = "linear",
    ) -> Dict[str, Any]:
        """
        주문 취소

        Args:
            symbol: 심볼 (예: BTCUSDT for Linear, BTCUSD for Inverse)
            order_id: 주문 ID
            category: 카테고리 (기본: linear)

        Returns:
            Dict: 응답 JSON

        SSOT: docs/plans/task_plan.md Phase 7 - 요청 payload가 Bybit 스펙 만족
        ADR-0002: Linear USDT Migration (category="linear" 기본값)
        """
        params = {
            "category": category,
            "symbol": symbol,
            "orderId": order_id,
        }

        return self._make_request("POST", "/v5/order/cancel", params)

    # ========================================================================
    # Phase 12a-1: Market Data Query Methods
    # ========================================================================

    def get_tickers(
        self,
        category: str = "inverse",
        symbol: str = "BTCUSD",
    ) -> Dict[str, Any]:
        """
        시장 데이터 조회 (Mark price, Index price, Funding rate)

        Args:
            category: 카테고리 (기본: inverse)
            symbol: 심볼 (기본: BTCUSD)

        Returns:
            Dict: 응답 JSON
                {
                    "result": {
                        "list": [{
                            "symbol": "BTCUSD",
                            "markPrice": "50000.50",
                            "indexPrice": "50001.00",
                            "fundingRate": "0.0001"
                        }]
                    }
                }

        SSOT: docs/plans/task_plan.md Phase 12a-1 - REST API Integration
        """
        params = {
            "category": category,
            "symbol": symbol,
        }

        return self._make_request("GET", "/v5/market/tickers", params)

    def get_open_orders(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
        orderId: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        미체결 주문 조회 (Phase 12a-4c: REST API polling fallback용)

        Args:
            category: 카테고리 (기본: linear)
            symbol: 심볼 (Optional)
            orderId: 주문 ID 필터 (Optional)
            limit: 조회 개수 (기본: 50)

        Returns:
            Dict: 응답 JSON
                {
                    "result": {
                        "list": [
                            {
                                "orderId": "...",
                                "orderLinkId": "...",
                                "orderStatus": "New" | "PartiallyFilled" | "Filled",
                                ...
                            }
                        ]
                    }
                }

        SSOT: docs/plans/task_plan.md Phase 12a-4c - REST API polling fallback
        """
        params = {
            "category": category,
            "limit": limit,
        }

        if symbol is not None:
            params["symbol"] = symbol

        if orderId is not None:
            params["orderId"] = orderId

        return self._make_request("GET", "/v5/order/realtime", params)

    def get_wallet_balance(
        self,
        accountType: str = "CONTRACT",
        coin: str = "BTC",
    ) -> Dict[str, Any]:
        """
        계정 Equity 조회

        Args:
            accountType: 계정 타입 (기본: CONTRACT)
            coin: 코인 (기본: BTC)

        Returns:
            Dict: 응답 JSON
                {
                    "result": {
                        "list": [{
                            "coin": [{
                                "coin": "BTC",
                                "equity": "0.0025",
                                "walletBalance": "0.0024",
                                "unrealisedPnl": "0.0001"
                            }]
                        }]
                    }
                }

        SSOT: docs/plans/task_plan.md Phase 12a-1 - REST API Integration
        """
        params = {
            "accountType": accountType,
            "coin": coin,
        }

        return self._make_request("GET", "/v5/account/wallet-balance", params)

    def get_position(
        self,
        category: str = "inverse",
        symbol: str = "BTCUSD",
    ) -> Dict[str, Any]:
        """
        현재 포지션 조회

        Args:
            category: 카테고리 (기본: inverse)
            symbol: 심볼 (기본: BTCUSD)

        Returns:
            Dict: 응답 JSON
                {
                    "result": {
                        "list": [{
                            "symbol": "BTCUSD",
                            "side": "Buy",
                            "size": "100",
                            "avgPrice": "49500.00",
                            "unrealisedPnl": "0.00020"
                        }]
                    }
                }

        SSOT: docs/plans/task_plan.md Phase 12a-1 - REST API Integration
        """
        params = {
            "category": category,
            "symbol": symbol,
        }

        return self._make_request("GET", "/v5/position/list", params)

    def get_execution_list(
        self,
        category: str = "inverse",
        symbol: Optional[str] = None,
        orderId: Optional[str] = None,  # Phase 12a-4c: orderId 필터 지원
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        거래 내역 조회 (PnL, Loss streak 계산용)

        Args:
            category: 카테고리 (기본: inverse)
            symbol: 심볼 (Optional, 미지정 시 전체 조회)
            orderId: 주문 ID 필터 (Phase 12a-4c: REST API polling fallback용)
            limit: 조회 개수 (기본: 50)

        Returns:
            Dict: 응답 JSON
                {
                    "result": {
                        "list": [
                            {"closedPnl": "5.0", "symbol": "BTCUSD"},
                            {"closedPnl": "-3.0", "symbol": "BTCUSD"}
                        ]
                    }
                }

        SSOT: docs/plans/task_plan.md Phase 12a-1 - REST API Integration
        """
        params = {
            "category": category,
            "limit": limit,
        }

        if symbol is not None:
            params["symbol"] = symbol

        if orderId is not None:
            params["orderId"] = orderId

        return self._make_request("GET", "/v5/execution/list", params)

    def get_kline(
        self,
        category: str = "inverse",
        symbol: str = "BTCUSD",
        interval: str = "60",
        limit: int = 200,
    ) -> Dict[str, Any]:
        """
        Kline/캔들스틱 데이터 조회 (ATR/Regime 계산용)

        Args:
            category: 카테고리 (기본: inverse)
            symbol: 심볼 (기본: BTCUSD)
            interval: 간격 (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
            limit: 조회 개수 (기본: 200, 최대: 1000)

        Returns:
            Dict: 응답 JSON
                {
                    "result": {
                        "list": [
                            [
                                "1622534400000",  # startTime
                                "50000.00",       # openPrice
                                "50100.00",       # highPrice
                                "49900.00",       # lowPrice
                                "50050.00",       # closePrice
                                "1000000",        # volume
                                "20.00"           # turnover
                            ],
                            ...
                        ]
                    }
                }

        SSOT: docs/plans/task_plan.md Phase 12a-2 - Market Data Provider 통합
        """
        params = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }

        return self._make_request("GET", "/v5/market/kline", params)

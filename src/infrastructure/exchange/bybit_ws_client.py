"""
src/infrastructure/exchange/bybit_ws_client.py
Bybit WebSocket Client (골격만, Contract tests only)

SSOT:
- task_plan.md Phase 7: Real API Integration (WS client 골격)
- FLOW.md Section 2.5: Event Processing (WS execution events)

원칙:
1. 실제 WS 연결 금지 (Phase 7에서는 contract tests만)
2. Testnet WSS URL 강제 assert (mainnet 접근 차단)
3. API key 누락 → 프로세스 시작 거부 (fail-fast)
4. WS queue maxsize + overflow 정책 (실거래 함정 1)
5. Clock 주입 (determinism) (실거래 함정 2)
6. Ping-pong timeout 처리

Exports:
- BybitWsClient: WebSocket client
- FatalConfigError: 설정 오류 (프로세스 시작 불가)
"""

import time
import hmac
import hashlib
import json
import os
import threading
from typing import Callable, Optional, Dict, Any
from collections import deque
import websocket  # websocket-client 라이브러리

# FatalConfigError는 bybit_rest_client에서 import
from infrastructure.exchange.bybit_rest_client import FatalConfigError


class BybitWsClient:
    """
    Bybit WebSocket Client (골격만, Contract tests only)

    SSOT: docs/plans/task_plan.md Phase 7
    - subscribe topic 정확성 (execution.inverse)
    - disconnect/reconnect → DEGRADED 플래그
    - ping-pong timeout 처리
    - WS queue maxsize + overflow 정책 (실거래 함정 1)
    - Clock 주입 (determinism) (실거래 함정 2)
    - Testnet WSS URL 강제 assert (실거래 함정 3)
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        wss_url: str,
        clock: Optional[Callable[[], float]] = None,
        pong_timeout: float = 20.0,
        queue_maxsize: int = 1000,
        category: str = "linear",
    ):
        """
        Bybit WS Client 초기화

        Args:
            api_key: API key (필수)
            api_secret: API secret (필수)
            wss_url: WebSocket URL (testnet 강제)
            clock: Timestamp 생성 함수 (기본: time.time)
            pong_timeout: Pong timeout (초, 기본: 20.0)
            queue_maxsize: 메시지 큐 최대 크기 (기본: 1000)
            category: Futures category ("linear" or "inverse", 기본: "linear")

        Raises:
            FatalConfigError: API key/secret 누락 또는 mainnet URL
        """
        # API key/secret 검증 (fail-fast)
        if not api_key:
            raise FatalConfigError("API key is required")
        if not api_secret:
            raise FatalConfigError("API secret is required")

        # Phase 12b: Mainnet 접근 허용 (BYBIT_TESTNET=false 확인)
        # Testnet mode: stream-testnet.bybit.com 강제
        # Mainnet mode: stream.bybit.com 허용 (BYBIT_TESTNET=false일 때만)
        testnet_mode = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

        if testnet_mode and "stream-testnet.bybit.com" not in wss_url:
            raise FatalConfigError(
                "BYBIT_TESTNET=true but wss_url is not Testnet. "
                "Use 'wss://stream-testnet.bybit.com/v5/private' for Testnet."
            )

        if not testnet_mode and "stream.bybit.com" not in wss_url:
            raise FatalConfigError(
                "BYBIT_TESTNET=false but wss_url is not Mainnet. "
                "Use 'wss://stream.bybit.com/v5/private' for Mainnet."
            )

        self.api_key = api_key
        self.api_secret = api_secret
        self.wss_url = wss_url
        self.clock = clock or time.time
        self.pong_timeout = pong_timeout
        self.queue_maxsize = queue_maxsize
        self.category = category

        # DEGRADED 상태 추적
        self._degraded = False
        self._degraded_entered_at: Optional[float] = None

        # Ping-pong 추적
        self._last_pong_at: Optional[float] = None

        # 메시지 큐 (FIFO, maxsize 제한)
        self._message_queue: deque = deque(maxlen=queue_maxsize)
        self._drop_count = 0  # Overflow로 드랍된 메시지 수

        # WebSocket 연결 상태
        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._running = False
        self._authenticated = False
        self._subscribed = False
        self._on_message_callback: Optional[Callable[[Dict[str, Any]], None]] = None

        # Ping thread
        self._ping_thread: Optional[threading.Thread] = None

    def get_subscribe_payload(self) -> Dict[str, Any]:
        """
        Subscribe payload 생성 (execution.{category} topic)

        Returns:
            Dict: Subscribe payload

        SSOT: docs/plans/task_plan.md Phase 7 - subscribe topic 정확성
        Bybit V5 WebSocket Execution Topics:
        - Linear: "execution.linear" (USDT-margined futures)
        - Inverse: "execution.inverse" (Coin-margined futures)
        """
        topic = f"execution.{self.category}"
        return {
            "op": "subscribe",
            "args": [topic],
        }

    def on_disconnect(self) -> None:
        """
        Disconnect 이벤트 처리 (DEGRADED 플래그 설정)

        SSOT: docs/plans/task_plan.md Phase 7 - disconnect/reconnect 시 DEGRADED 플래그 설정
        """
        self._degraded = True
        self._degraded_entered_at = self.clock()

    def on_reconnect(self) -> None:
        """
        Reconnect 이벤트 처리 (DEGRADED 플래그 해제)

        SSOT: docs/plans/task_plan.md Phase 7 - disconnect/reconnect 시 DEGRADED 플래그 설정
        """
        self._degraded = False
        self._degraded_entered_at = None

    def is_degraded(self) -> bool:
        """
        DEGRADED 상태 확인

        Returns:
            bool: DEGRADED 상태이면 True
        """
        return self._degraded

    def get_degraded_entered_at(self) -> Optional[float]:
        """
        DEGRADED 진입 시각 반환

        Returns:
            Optional[float]: DEGRADED 진입 시각 (timestamp)
        """
        return self._degraded_entered_at

    def on_pong_received(self) -> None:
        """
        Pong 수신 이벤트 처리

        SSOT: docs/plans/task_plan.md Phase 7 - ping-pong timeout 처리
        """
        self._last_pong_at = self.clock()

    def check_pong_timeout(self) -> None:
        """
        Pong timeout 체크 (timeout 발생 시 DEGRADED)

        SSOT: docs/plans/task_plan.md Phase 7 - ping-pong timeout 처리
        Bybit private stream 요구사항: max_active_time
        """
        if self._last_pong_at is None:
            # 아직 pong을 받지 못한 경우 (초기 상태)
            return

        elapsed = self.clock() - self._last_pong_at
        if elapsed >= self.pong_timeout:
            # Timeout 발생 → DEGRADED
            self._degraded = True
            if self._degraded_entered_at is None:
                self._degraded_entered_at = self.clock()

    def enqueue_message(self, message: Dict[str, Any]) -> None:
        """
        메시지 큐에 추가 (overflow 시 가장 오래된 메시지 드랍)

        Args:
            message: WS 메시지

        SSOT: docs/plans/task_plan.md Phase 7 - WS queue maxsize + overflow 정책
        실거래 함정 1: 큐가 무한히 쌓이면 메모리 터짐
        """
        if len(self._message_queue) >= self.queue_maxsize:
            # Overflow → 가장 오래된 메시지 드랍
            self._message_queue.popleft()
            self._drop_count += 1

        self._message_queue.append(message)

    def dequeue_message(self) -> Optional[Dict[str, Any]]:
        """
        메시지 큐에서 제거 (FIFO)

        Returns:
            Optional[Dict]: 메시지 (큐가 비어있으면 None)
        """
        if len(self._message_queue) == 0:
            return None
        return self._message_queue.popleft()

    def get_queue_size(self) -> int:
        """
        메시지 큐 크기 반환

        Returns:
            int: 큐 크기
        """
        return len(self._message_queue)

    def get_drop_count(self) -> int:
        """
        Overflow로 드랍된 메시지 수 반환

        Returns:
            int: Drop count
        """
        return self._drop_count

    def _generate_auth_signature(self, expires: int) -> str:
        """
        Auth 서명 생성 (HMAC-SHA256)

        Args:
            expires: Expiration timestamp (milliseconds)

        Returns:
            str: Hex-encoded signature

        SSOT: Bybit V5 WebSocket Auth
        서명 문자열: "GET/realtime{expires}"
        """
        # Bybit 공식 문서: https://bybit-exchange.github.io/docs/v5/ws/connect
        signature_payload = f"GET/realtime{expires}"
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _send_auth(self) -> None:
        """
        Auth 메시지 전송

        SSOT: Bybit V5 WebSocket Auth
        메시지: {"op": "auth", "args": [api_key, expires, signature]}
        """
        if not self._ws:
            return

        expires = int(self.clock() * 1000) + 10000  # 현재 시각 + 10초 (milliseconds)
        signature = self._generate_auth_signature(expires)

        auth_message = {
            "op": "auth",
            "args": [self.api_key, expires, signature],
        }
        self._ws.send(json.dumps(auth_message))

    def _send_subscribe(self) -> None:
        """
        Subscribe 메시지 전송 (execution.inverse topic)

        SSOT: Bybit V5 WebSocket Private Execution
        메시지: {"op": "subscribe", "args": ["execution.inverse"]}
        """
        if not self._ws:
            return

        subscribe_message = self.get_subscribe_payload()
        self._ws.send(json.dumps(subscribe_message))

    def _send_ping(self) -> None:
        """
        Ping 메시지 전송 (클라이언트 → 서버)

        SSOT: Bybit V5 WebSocket Heartbeat
        메시지: {"op": "ping"}
        클라이언트가 ping 전송 (권장 20초마다)
        """
        if not self._ws or not self._running:
            return

        ping_message = {"op": "ping"}
        try:
            self._ws.send(json.dumps(ping_message))
        except Exception:
            # Ping 전송 실패 (연결 끊김) → DEGRADED
            self._degraded = True
            if self._degraded_entered_at is None:
                self._degraded_entered_at = self.clock()

    def _ping_loop(self) -> None:
        """
        Ping loop (background thread, 20초마다 ping 전송)

        SSOT: Bybit V5 WebSocket Heartbeat
        권장 주기: 20초
        무활동 10분 시 서버가 연결 종료
        """
        while self._running:
            time.sleep(20.0)  # 20초 대기
            if self._running:
                self._send_ping()

    def _on_ws_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        """
        WebSocket 메시지 수신 콜백

        Args:
            ws: WebSocketApp 인스턴스
            message: 수신된 메시지 (JSON string)

        SSOT: Bybit V5 WebSocket Message Types
        - op=auth 응답: {"success": true, "op": "auth"}
        - op=subscribe 응답: {"success": true, "op": "subscribe"}
        - op=pong 응답: {"success": true, "op": "pong"}
        - execution 메시지: {"topic": "execution.inverse", "data": [...]}
        """
        try:
            msg = json.loads(message)
        except json.JSONDecodeError:
            # Invalid JSON → 무시
            return

        # Debug logging (temporary)
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"WS message received: {msg}")

        op = msg.get("op")
        success = msg.get("success")

        # Auth 응답 처리
        if op == "auth" and success:
            self._authenticated = True
            # Auth 성공 → Subscribe 전송
            self._send_subscribe()
            return

        # Subscribe 응답 처리
        if op == "subscribe" and success:
            self._subscribed = True
            return

        # Pong 응답 처리
        if op == "pong":
            self.on_pong_received()
            return

        # Execution 메시지 처리 (topic 기반)
        topic = msg.get("topic")
        if topic and topic.startswith("execution"):
            # 메시지 큐에 추가
            self.enqueue_message(msg)
            # 콜백 호출 (있으면)
            if self._on_message_callback:
                self._on_message_callback(msg)
            return

    def _on_ws_open(self, ws: websocket.WebSocketApp) -> None:
        """
        WebSocket 연결 성공 콜백

        Args:
            ws: WebSocketApp 인스턴스

        SSOT: Bybit V5 WebSocket Connection
        연결 성공 → Auth 전송
        """
        # Auth 전송
        self._send_auth()

    def _on_ws_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        """
        WebSocket 에러 콜백

        Args:
            ws: WebSocketApp 인스턴스
            error: Exception

        SSOT: docs/plans/task_plan.md Phase 7 - error 발생 시 DEGRADED
        """
        self._degraded = True
        if self._degraded_entered_at is None:
            self._degraded_entered_at = self.clock()

    def _on_ws_close(
        self, ws: websocket.WebSocketApp, close_status_code: int, close_msg: str
    ) -> None:
        """
        WebSocket 연결 종료 콜백

        Args:
            ws: WebSocketApp 인스턴스
            close_status_code: Close status code
            close_msg: Close message

        SSOT: docs/plans/task_plan.md Phase 7 - close 발생 시 DEGRADED
        """
        self._degraded = True
        if self._degraded_entered_at is None:
            self._degraded_entered_at = self.clock()
        self._authenticated = False
        self._subscribed = False

    def start(self, on_message_callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        """
        WebSocket 연결 시작 (background thread)

        Args:
            on_message_callback: 메시지 수신 콜백 (Optional)

        SSOT: docs/plans/task_plan.md Phase 8 - Thread 모델
        - Main Thread: start() → WS Thread 시작
        - WS Thread: connect → auth → subscribe → recv_loop
        - Ping Thread: 20초마다 ping 전송
        """
        if self._running:
            # 이미 실행 중
            return

        self._running = True
        self._on_message_callback = on_message_callback

        # WebSocketApp 생성
        self._ws = websocket.WebSocketApp(
            self.wss_url,
            on_open=self._on_ws_open,
            on_message=self._on_ws_message,
            on_error=self._on_ws_error,
            on_close=self._on_ws_close,
        )

        # WS Thread 시작
        self._ws_thread = threading.Thread(target=self._ws.run_forever, daemon=True)
        self._ws_thread.start()

        # Ping Thread 시작
        self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self._ping_thread.start()

    def stop(self) -> None:
        """
        WebSocket 연결 종료 (thread join timeout=5.0)

        SSOT: docs/plans/task_plan.md Phase 8 - stop() 메서드
        """
        if not self._running:
            return

        self._running = False

        # WebSocket 연결 종료
        if self._ws:
            self._ws.close()

        # Thread join (timeout=5.0)
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5.0)

        if self._ping_thread and self._ping_thread.is_alive():
            self._ping_thread.join(timeout=5.0)

        # 상태 초기화
        self._ws = None
        self._ws_thread = None
        self._ping_thread = None
        self._authenticated = False
        self._subscribed = False

    def is_connected(self) -> bool:
        """
        연결/인증/구독 완료 여부 확인

        Returns:
            bool: 연결/인증/구독 모두 완료되면 True

        SSOT: docs/plans/task_plan.md Phase 8 - is_connected() 메서드
        """
        return self._running and self._authenticated and self._subscribed

    # ========================================================================
    # Phase 12a-1: Execution Event Retrieval
    # ========================================================================

    def get_execution_events(self) -> list:
        """
        WS로 수신한 execution event 목록 반환 (소비 후 clear)

        Returns:
            list: execution event 목록 (dict 형식)
                [
                    {
                        "symbol": "BTCUSD",
                        "orderId": "abc123",
                        "orderLinkId": "grid_xyz_l",
                        "side": "Buy",
                        "execType": "Trade",
                        "execQty": "100",
                        "execPrice": "49800.00",
                        "orderQty": "100",
                        "execFee": "0.00001",
                        "execTime": "1706000000000"
                    },
                    ...
                ]

        SSOT: docs/plans/task_plan.md Phase 12a-1 - WebSocket Integration
        """
        events = []

        # Queue에서 모든 메시지 가져오기 (FIFO 순서)
        while self._message_queue:
            try:
                msg = self._message_queue.popleft()

                # execution.{category} topic 필터링
                expected_topic = f"execution.{self.category}"
                if msg.get("topic") == expected_topic:
                    data = msg.get("data", [])
                    # data는 list 형식 (1개 이상의 execution event)
                    for event in data:
                        events.append(event)
            except IndexError:
                # Queue가 비어있으면 종료
                break

        return events

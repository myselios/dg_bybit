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
from typing import Callable, Optional, Dict, Any, List
from collections import deque

# FatalConfigError는 bybit_rest_client에서 import
from infrastructure.exchange.bybit_rest_client import FatalConfigError


class BybitWsClient:
    """
    Bybit WebSocket Client (골격만, Contract tests only)

    SSOT: task_plan.md Phase 7
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

        Raises:
            FatalConfigError: API key/secret 누락 또는 mainnet URL
        """
        # API key/secret 검증 (fail-fast)
        if not api_key:
            raise FatalConfigError("API key is required")
        if not api_secret:
            raise FatalConfigError("API secret is required")

        # Testnet WSS URL 강제 assert (mainnet 접근 차단)
        if "stream-testnet.bybit.com" not in wss_url:
            raise FatalConfigError("mainnet access forbidden before Phase 9")

        self.api_key = api_key
        self.api_secret = api_secret
        self.wss_url = wss_url
        self.clock = clock or time.time
        self.pong_timeout = pong_timeout
        self.queue_maxsize = queue_maxsize

        # DEGRADED 상태 추적
        self._degraded = False
        self._degraded_entered_at: Optional[float] = None

        # Ping-pong 추적
        self._last_pong_at: Optional[float] = None

        # 메시지 큐 (FIFO, maxsize 제한)
        self._message_queue: deque = deque(maxlen=queue_maxsize)
        self._drop_count = 0  # Overflow로 드랍된 메시지 수

    def get_subscribe_payload(self) -> Dict[str, Any]:
        """
        Subscribe payload 생성 (execution.inverse topic)

        Returns:
            Dict: Subscribe payload

        SSOT: task_plan.md Phase 7 - subscribe topic 정확성
        """
        return {
            "op": "subscribe",
            "args": ["execution.inverse"],
        }

    def on_disconnect(self) -> None:
        """
        Disconnect 이벤트 처리 (DEGRADED 플래그 설정)

        SSOT: task_plan.md Phase 7 - disconnect/reconnect 시 DEGRADED 플래그 설정
        """
        self._degraded = True
        self._degraded_entered_at = self.clock()

    def on_reconnect(self) -> None:
        """
        Reconnect 이벤트 처리 (DEGRADED 플래그 해제)

        SSOT: task_plan.md Phase 7 - disconnect/reconnect 시 DEGRADED 플래그 설정
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

        SSOT: task_plan.md Phase 7 - ping-pong timeout 처리
        """
        self._last_pong_at = self.clock()

    def check_pong_timeout(self) -> None:
        """
        Pong timeout 체크 (timeout 발생 시 DEGRADED)

        SSOT: task_plan.md Phase 7 - ping-pong timeout 처리
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

        SSOT: task_plan.md Phase 7 - WS queue maxsize + overflow 정책
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

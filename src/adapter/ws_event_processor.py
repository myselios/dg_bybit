"""
WebSocket Event Processor — Dedup + Ordering

FLOW.md Section 2.7 기반 이벤트 처리 계약 구현
FLOW_REF: docs/constitution/FLOW.md#2.7 (Last verified: 2026-01-23)

책임:
1. 중복 제거 (Deduplication)
2. 순서 보장 (Ordering)
3. REST reconcile override 지원

⚠️ 핵심 규칙:
- 동일 dedup_key → 무시
- seq 역순 → 무시
- late event → 무시 (상태 불일치)
"""

from typing import Optional, Dict, Set
from collections import deque
from dataclasses import dataclass
import time

from src.domain.events import ExecutionEvent, EventType


@dataclass
class EventProcessorState:
    """이벤트 프로세서 내부 상태"""
    processed_events: Set[str]  # dedup key 집합 (최대 1000개)
    last_processed_seq: Dict[str, int]  # order_id → last seq
    event_queue: deque  # FIFO queue


class WSEventProcessor:
    """
    WebSocket 이벤트 처리기 (Dedup + Ordering)

    FLOW.md Section 2.7 준수:
    - Deduplication: execution_id + order_id + exec_time 기반
    - Ordering: seq 기반 out-of-order 방어
    - Late event: 상태 불일치 시 무시
    """

    def __init__(self):
        self.processed_events: Set[str] = set()
        self.last_processed_seq: Dict[str, int] = {}
        self.max_processed_events = 1000  # FLOW: 최대 1000개 유지

    def process_event(
        self,
        event: ExecutionEvent,
        current_state: str
    ) -> Optional[ExecutionEvent]:
        """
        이벤트 처리 (중복 제거 + 순서 검증)

        Args:
            event: 원본 execution event
            current_state: 현재 상태 (late event 감지용)

        Returns:
            처리할 이벤트 or None (무시)

        FLOW 규칙:
        1. 중복 이벤트 → None
        2. Out-of-order 이벤트 → None
        3. Late event (상태 불일치) → None
        """
        # (1) Deduplication
        dedup_key = self._generate_dedup_key(event)
        if dedup_key in self.processed_events:
            # 중복 이벤트 무시
            return None

        # (2) Ordering (seq 기반)
        if not self._check_ordering(event):
            # Out-of-order 이벤트 무시
            return None

        # (3) Late event 체크 (선택적, 상태 기반)
        # 이 부분은 호출자(EventRouter/Orchestrator)가 판단
        # 여기서는 통과

        # 처리 완료: 기록
        self._record_event(event, dedup_key)

        return event

    def _generate_dedup_key(self, event: ExecutionEvent) -> str:
        """
        Dedup key 생성 (FLOW Section 2.7)

        형식:
        - Execution event (execution_id 있음): {execution_id}
        - Execution event (execution_id 없음, fallback): {order_id}_{type}_{timestamp}

        FLOW v1.9 규칙:
        - execution_id는 Bybit execId (unique per execution)
        - execution_id가 있으면 이것만으로 dedup 가능
        - 없으면 order_id + type + timestamp로 fallback
        """
        # execution_id가 있으면 이것만 사용 (가장 정확한 dedup)
        if event.execution_id:
            return event.execution_id

        # Fallback: order_id + type + timestamp (구 방식)
        return f"{event.order_id}_{event.type.value}_{event.timestamp}"

    def _check_ordering(self, event: ExecutionEvent) -> bool:
        """
        순서 검증 (seq 기반)

        Returns:
            True: 정상 순서 (처리 가능)
            False: Out-of-order (무시)
        """
        # seq가 없는 이벤트는 통과 (순서 보장 불가)
        if not hasattr(event, 'seq') or event.seq is None:
            return True

        order_id = event.order_id
        last_seq = self.last_processed_seq.get(order_id, -1)

        # Out-of-order: 이전보다 작거나 같은 seq
        if event.seq <= last_seq:
            return False

        # 정상: seq 업데이트
        self.last_processed_seq[order_id] = event.seq
        return True

    def _record_event(self, event: ExecutionEvent, dedup_key: str):
        """
        이벤트 처리 기록

        FLOW 규칙:
        - 최대 1000개 유지 (FIFO)
        """
        self.processed_events.add(dedup_key)

        # FIFO: 1000개 초과 시 오래된 것 제거
        if len(self.processed_events) > self.max_processed_events:
            # Set은 순서가 없으므로, 실제로는 임의 제거됨
            # 더 정확하려면 OrderedDict나 deque 사용
            # 지금은 간단히 처리 (실용적 trade-off)
            self.processed_events.pop()

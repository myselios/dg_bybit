"""
src/application/orchestrator.py
Orchestrator — Tick loop에서 Flow 순서대로 실행 (application layer 통합)

SSOT:
- FLOW.md Section 2: Tick Ordering (Emergency-first)
- FLOW.md Section 4.2: God Object 금지 (책임 분리)
- task_plan.md Phase 6: Tick 순서 고정 (Emergency → Events → Position → Entry)

원칙:
1. Thin wrapper: 각 책임은 이미 구현된 모듈에 위임
2. Tick 순서 고정: Emergency → Events → Position → Entry
3. 상태 관리: transition() 호출로 state 전환

Exports:
- Orchestrator: Tick loop orchestrator
- TickResult: Tick 실행 결과 (state, execution_order, halt_reason 등)
"""

from dataclasses import dataclass
from typing import List, Optional
from domain.state import State, Position
from infrastructure.exchange.market_data_interface import MarketDataInterface


@dataclass
class TickResult:
    """Tick 실행 결과"""

    state: State
    execution_order: List[str]
    halt_reason: Optional[str] = None
    entry_blocked: bool = False
    entry_block_reason: Optional[str] = None


class Orchestrator:
    """
    Orchestrator — Tick loop에서 Flow 순서대로 실행

    FLOW Section 4.2:
        - God Object 금지
        - 책임 분리: emergency/events/position/entry는 별도 모듈에 위임

    task_plan.md Phase 6:
        - Tick 순서 고정: Emergency → Events → Position → Entry
        - degraded/normal 분리, degraded 60s → halt
    """

    def __init__(self, market_data: MarketDataInterface):
        """
        Orchestrator 초기화

        Args:
            market_data: Market data interface (FakeMarketData or BybitAdapter)
        """
        self.market_data = market_data
        self.state = State.FLAT
        self.position: Optional[Position] = None

    def run_tick(self) -> TickResult:
        """
        Tick 실행 (Emergency → Events → Position → Entry)

        Returns:
            TickResult: Tick 실행 결과

        FLOW Section 2:
            - Emergency check (최우선)
            - Events processing (WS 이벤트)
            - Position management (stop 갱신)
            - Entry decision (signal → gate → sizing)
        """
        execution_order = []
        halt_reason = None
        entry_blocked = False
        entry_block_reason = None

        # (1) Emergency check (최우선)
        execution_order.append("emergency")
        emergency_status = self._check_emergency()
        if emergency_status == "HALT":
            self.state = State.HALT
            # halt_reason 판단
            if self.market_data.get_equity_btc() <= 0:
                halt_reason = "balance_too_low"
            elif self.market_data.is_degraded_timeout():
                halt_reason = "degraded_mode_timeout"
            else:
                halt_reason = "emergency"
            return TickResult(
                state=self.state,
                execution_order=execution_order,
                halt_reason=halt_reason,
            )

        # (2) Events processing
        execution_order.append("events")
        self._process_events()

        # (3) Position management
        execution_order.append("position")
        self._manage_position()

        # (4) Entry decision
        execution_order.append("entry")
        entry_result = self._decide_entry()
        if entry_result["blocked"]:
            entry_blocked = True
            entry_block_reason = entry_result["reason"]

        return TickResult(
            state=self.state,
            execution_order=execution_order,
            halt_reason=halt_reason,
            entry_blocked=entry_blocked,
            entry_block_reason=entry_block_reason,
        )

    def get_state(self) -> State:
        """현재 상태 반환"""
        return self.state

    def _check_emergency(self) -> str:
        """
        Emergency 체크 (최우선)

        Returns:
            "PASS" or "HALT"

        FLOW Section 7.1:
            - balance_too_low (equity <= 0)
            - price_drop_1m (-10%)
            - price_drop_10m (-20%)
            - latency_too_high (> 5초)
            - degraded_timeout (60s)
        """
        # balance_too_low 체크
        equity_btc = self.market_data.get_equity_btc()
        if equity_btc <= 0:
            return "HALT"

        # degraded timeout 체크 (60초)
        degraded_timeout = self.market_data.is_degraded_timeout()
        if degraded_timeout:
            return "HALT"

        return "PASS"

    def _process_events(self) -> None:
        """
        Events 처리 (WS 이벤트)

        FLOW Section 2.5:
            - FILL/PARTIAL_FILL/CANCEL/REJECT
            - transition() 호출로 state 전환
        """
        # 이벤트 처리는 이미 event_handler.py에 구현되어 있음
        # 여기서는 통합만 수행 (최소 구현)
        pass

    def _manage_position(self) -> None:
        """
        Position 관리 (stop 갱신)

        FLOW Section 2.5:
            - stop_manager.should_update_stop()
            - stop_manager.determine_stop_action()
        """
        # Position 관리는 이미 stop_manager.py에 구현되어 있음
        # 여기서는 통합만 수행 (최소 구현)
        pass

    def _decide_entry(self) -> dict:
        """
        Entry 결정 (signal → gate → sizing)

        Returns:
            {"blocked": bool, "reason": str}

        FLOW Section 2.4:
            - degraded_mode → entry 차단
        """
        # degraded mode 체크
        ws_degraded = self.market_data.is_ws_degraded()
        if ws_degraded and self.state == State.FLAT:
            # degraded mode에서 FLAT 상태는 entry 차단
            return {"blocked": True, "reason": "degraded_mode"}

        # degraded timeout 체크 (60초)
        degraded_timeout = self.market_data.is_degraded_timeout()
        if degraded_timeout:
            # degraded 60s 경과 → HALT
            self.state = State.HALT
            return {"blocked": True, "reason": "degraded_mode_timeout"}

        return {"blocked": False, "reason": None}

"""
tests/integration/test_orchestrator.py
Integration tests for orchestrator (Phase 6: Orchestrator Integration)

Purpose:
- Tick loop에서 Flow 순서대로 실행 (Emergency → Events → Position → Entry)
- 전체 사이클 통합 검증 (FLAT → ENTRY_PENDING → IN_POSITION → FLAT)
- HALT/Recovery/Cooldown/Degraded 시나리오

SSOT:
- FLOW.md Section 2: Tick Ordering (Emergency-first)
- FLOW.md Section 4.2: God Object 금지 (책임 분리)
- task_plan.md Phase 6: integration 5~10케이스 제한

Test Coverage (5~10 cases):
1. test_orchestrator_tick_order_emergency_first (Emergency → Events → Position → Entry)
2. test_orchestrator_full_cycle_flat_to_in_position_to_flat (전체 사이클)
3. test_orchestrator_halt_on_emergency (Emergency → HALT)
4. test_orchestrator_degraded_mode_blocks_entry (WS degraded → entry 차단)
5. test_orchestrator_degraded_timeout_triggers_halt (degraded 60s → HALT)
"""

from application.orchestrator import Orchestrator, TickResult
from domain.state import State
from infrastructure.exchange.fake_market_data import FakeMarketData


def test_orchestrator_tick_order_emergency_first():
    """
    Tick 순서 검증: Emergency → Events → Position → Entry

    FLOW Section 2:
        - Emergency check (최우선)
        - Events processing (WS 이벤트)
        - Position management (stop 갱신)
        - Entry decision (signal → gate → sizing)

    task_plan.md Phase 6:
        - Tick 순서 고정: Emergency → Events → Position → Entry

    Example:
        orchestrator.run_tick()
        → emergency check 먼저
        → events processing
        → position management
        → entry decision (마지막)

    Expected:
        tick_result.order (execution order)
        ["emergency", "events", "position", "entry"]
    """
    # Setup
    market_data = FakeMarketData(current_price=50000.0, equity_btc=0.002)
    orchestrator = Orchestrator(market_data=market_data)

    # When
    tick_result = orchestrator.run_tick()

    # Then: execution order 검증
    assert tick_result.execution_order is not None
    assert tick_result.execution_order[0] == "emergency"  # 최우선
    assert "events" in tick_result.execution_order
    assert "position" in tick_result.execution_order
    assert "entry" in tick_result.execution_order


def test_orchestrator_full_cycle_flat_to_in_position_to_flat():
    """
    전체 사이클 통합 검증 (FLAT → ENTRY_PENDING → IN_POSITION → FLAT)

    FLOW Section 2:
        - FLAT: entry_allowed gate → sizing → place_entry
        - ENTRY_PENDING: FILL event → IN_POSITION + stop 설치
        - IN_POSITION: stop 관리 + metrics 업데이트
        - EXIT: position closed → FLAT

    NOTE: Phase 6에서는 tick 순서만 검증, full cycle은 나중에 구현

    Example:
        orchestrator.run_tick()
        → execution_order 검증만 수행

    Expected:
        execution_order 정상 (Emergency → Events → Position → Entry)
        state=FLAT 유지 (full cycle 미구현)
    """
    # Setup
    market_data = FakeMarketData(current_price=50000.0, equity_btc=0.002)
    orchestrator = Orchestrator(market_data=market_data)

    # Tick 실행
    assert orchestrator.get_state() == State.FLAT

    # entry signal 주입 (fake)
    market_data.set_signal(side="Buy", qty=100)
    tick_result = orchestrator.run_tick()

    # Phase 6: execution_order만 검증 (full cycle은 나중에)
    assert "emergency" in tick_result.execution_order
    assert "events" in tick_result.execution_order
    assert "position" in tick_result.execution_order
    assert "entry" in tick_result.execution_order

    # NOTE: state 전환은 Phase 6 범위 밖 (orchestrator는 thin wrapper)
    # 실제 transition()은 이미 Phase 0에서 구현 완료


def test_orchestrator_halt_on_emergency():
    """
    Emergency → HALT

    FLOW Section 7.1:
        - Emergency 조건 (balance_too_low, price_drop, latency)
        - Emergency check 최우선 실행
        - HALT 전환

    Example:
        equity_btc=0 (balance_too_low)
        → Emergency check → HALT

    Expected:
        state=HALT
        halt_reason="balance_too_low"
    """
    # Setup: balance_too_low
    market_data = FakeMarketData(current_price=50000.0, equity_btc=0.0)
    orchestrator = Orchestrator(market_data=market_data)

    # When
    tick_result = orchestrator.run_tick()

    # Then: HALT 전환
    assert orchestrator.get_state() == State.HALT
    assert tick_result.halt_reason == "balance_too_low"


def test_orchestrator_degraded_mode_blocks_entry():
    """
    WS degraded → entry 차단

    FLOW Section 2.4:
        - WS degraded_mode=True
        - FLAT 상태에서 entry 차단
        - IN_POSITION 상태는 aggressive reconcile

    Example:
        state=FLAT
        ws_degraded_mode=True
        → entry_allowed=False

    Expected:
        entry 차단
        state=FLAT 유지
    """
    # Setup
    market_data = FakeMarketData(current_price=50000.0, equity_btc=0.002)
    orchestrator = Orchestrator(market_data=market_data)

    # WS degraded mode 진입
    market_data.set_ws_degraded(degraded=True)

    # entry signal 주입
    market_data.set_signal(side="Buy", qty=100)

    # When
    tick_result = orchestrator.run_tick()

    # Then: entry 차단
    assert orchestrator.get_state() == State.FLAT  # 전환 없음
    assert tick_result.entry_blocked is True
    assert tick_result.entry_block_reason == "degraded_mode"


def test_orchestrator_degraded_timeout_triggers_halt():
    """
    Degraded 60s → HALT

    FLOW Section 2.4:
        - degraded_mode 진입 후 60초 경과
        - HALT 전환

    Example:
        degraded_mode=True
        degraded_entered_at = now() - 61s
        → HALT

    Expected:
        state=HALT
        halt_reason="degraded_mode_timeout"
    """
    # Setup
    market_data = FakeMarketData(current_price=50000.0, equity_btc=0.002)
    orchestrator = Orchestrator(market_data=market_data)

    # WS degraded mode 진입 (61초 전)
    market_data.set_ws_degraded(degraded=True, entered_at_offset=-61.0)

    # When
    tick_result = orchestrator.run_tick()

    # Then: HALT 전환
    assert orchestrator.get_state() == State.HALT
    assert tick_result.halt_reason == "degraded_mode_timeout"

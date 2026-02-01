"""
src/application/entry_allowed.py
Entry gates (FLOW Section 2, Policy Section 5)

Purpose:
- 7 gates + one-way mode 검증 (총 8 gates)
- Reject 이유코드 반환
- Gate 순서 고정 (Policy/Flow 충돌 금지)

SSOT:
- FLOW.md Section 2: Tick Execution Flow, Gate 순서
- Policy.md Section 5: Stage Parameters (EV gate, ATR, max trades, maker-only)

Gate 순서 (task_plan.md:433-441):
1) HALT/COOLDOWN 상태
2) cooldown timeout / max trades per day
3) stage params (leverage, loss budget)
4) volatility (ATR)
5) EV gate
6) maker/taker policy
7) winrate/streak multiplier
8) one-way mode

Design Decisions:
- 각 gate는 독립적으로 검증 가능
- Reject reason은 명확한 코드 (로그 Intent 생성용)
- Gate 순서는 "빠른 실패" 우선 (HALT → COOLDOWN → ...)
"""

from dataclasses import dataclass
from domain.state import State


@dataclass
class StageParams:
    """
    Stage 파라미터 (Policy Section 5)

    Attributes:
        max_trades_per_day: 최대 거래 횟수/일 (예: 10)
        atr_pct_24h_min: 최소 ATR (pct, 예: 0.02 = 2%)
        ev_fee_multiple_k: EV gate 계수 (예: 2.0)
        maker_only_default: Maker-only 모드 (예: True)
    """
    max_trades_per_day: int
    atr_pct_24h_min: float
    ev_fee_multiple_k: float
    maker_only_default: bool


@dataclass
class SignalContext:
    """
    Signal context (EV gate용)

    Attributes:
        expected_profit_usd: 예상 수익 (USD, Grid spacing 기반)
        estimated_fee_usd: 예상 수수료 (USD, Maker/Taker 구분)
        is_maker: Maker 주문 여부 (True = Maker, False = Taker)
    """
    expected_profit_usd: float
    estimated_fee_usd: float
    is_maker: bool


@dataclass
class EntryDecision:
    """
    Entry 허용 여부 결정

    Attributes:
        allowed: 진입 허용 여부
        reject_reason: 거절 사유 (allowed=False일 때만, 로그용)
    """
    allowed: bool
    reject_reason: str | None = None


def check_entry_allowed(
    state: State,
    stage: StageParams,
    trades_today: int,
    atr_pct_24h: float,
    signal: SignalContext,
    winrate: float,
    position_mode: str,
    cooldown_until: float | None,
    current_time: float | None = None,
) -> EntryDecision:
    """
    Entry gates 검증 (8 gates)

    Args:
        state: 현재 상태 (State enum)
        stage: Stage 파라미터 (Policy Section 5)
        trades_today: 오늘 거래 횟수
        atr_pct_24h: 24시간 ATR (pct, 예: 0.03 = 3%)
        signal: Signal 컨텍스트 (expected_profit_usd, estimated_fee_usd, is_maker)
        winrate: 현재 winrate (0.0~1.0)
        position_mode: Position mode ("MergedSingle" = one-way, "BothSide" = hedge)
        cooldown_until: COOLDOWN timeout 시각 (None이면 cooldown 아님)
        current_time: 현재 시각 (cooldown 검증용)

    Returns:
        EntryDecision: 진입 허용 여부 + 거절 사유

    Gate 순서:
        1) HALT 상태 → REJECT
        2a) COOLDOWN (timeout 전) → REJECT
        2b) max_trades_per_day 초과 → REJECT
        3) stage params 검증 (현재는 생략, 추후 확장)
        4) ATR < 임계치 → REJECT
        5) EV gate (expected_profit < fee * K) → REJECT
        6) maker-only 위반 → REJECT
        7) winrate gate (현재는 생략, 추후 확장)
        8) one-way mode 위반 → REJECT

    FLOW Section 2: Gate 순서는 고정 (Policy/Flow 충돌 금지)
    """
    # Gate 1: HALT 상태
    if state == State.HALT:
        return EntryDecision(allowed=False, reject_reason="state_halt")

    # Gate 2a: COOLDOWN timeout 전
    if state == State.COOLDOWN:
        if cooldown_until is not None and current_time is not None:
            if current_time < cooldown_until:
                return EntryDecision(allowed=False, reject_reason="cooldown_active")

    # Gate 2b: max_trades_per_day 초과
    if trades_today >= stage.max_trades_per_day:
        return EntryDecision(allowed=False, reject_reason="max_trades_per_day_exceeded")

    # Gate 3: stage params 검증 (현재는 생략)
    # TODO: leverage 검증, loss budget 검증 등

    # Gate 4: ATR < 임계치
    if atr_pct_24h < stage.atr_pct_24h_min:
        return EntryDecision(allowed=False, reject_reason="atr_too_low")

    # Gate 5: EV gate
    min_expected_profit = signal.estimated_fee_usd * stage.ev_fee_multiple_k
    if signal.expected_profit_usd < min_expected_profit:
        return EntryDecision(allowed=False, reject_reason="ev_insufficient")

    # Gate 6: maker-only 위반
    if stage.maker_only_default and not signal.is_maker:
        return EntryDecision(allowed=False, reject_reason="maker_only_violation")

    # Gate 7: winrate gate (현재는 생략)
    # TODO: soft gate (size 감소), hard gate (HALT)

    # Gate 8: one-way mode 위반
    if position_mode != "MergedSingle":
        return EntryDecision(allowed=False, reject_reason="hedge_mode_detected")

    # 모든 gate 통과
    return EntryDecision(allowed=True, reject_reason=None)

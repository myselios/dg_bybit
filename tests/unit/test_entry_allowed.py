"""
tests/unit/test_entry_allowed.py
Unit tests for entry_allowed gates (FLOW Section 2, Policy Section 5)

Purpose:
- 7 gates + one-way mode 검증 (총 8 gates)
- Reject 이유코드 반환 검증
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

Test Coverage:
1. Gate 1: HALT 상태 → REJECT
2. Gate 2a: COOLDOWN (timeout 전) → REJECT
3. Gate 2b: COOLDOWN (timeout 후) → ALLOW
4. Gate 2c: max_trades_per_day 초과 → REJECT
5. Gate 3: stage params 검증 (leverage 초과 등)
6. Gate 4: ATR < 임계치 → REJECT
7. Gate 5: EV gate (expected_profit < fee * K) → REJECT
8. Gate 6: maker-only 위반 → REJECT
9. Gate 7a: winrate soft gate (size 감소)
10. Gate 7b: winrate hard gate → HALT
11. Gate 8: one-way mode 위반 (hedge 감지) → REJECT
12. All gates pass → ALLOW
"""

from dataclasses import dataclass
from src.domain.state import State
from src.application.entry_allowed import check_entry_allowed, EntryDecision


@dataclass
class StageParams:
    """Stage 파라미터 (Policy Section 5)"""
    stage_id: int
    equity_usd_min: float
    equity_usd_max: float | None
    default_leverage: float
    max_loss_usd_cap: float
    loss_pct_cap: float
    ev_fee_multiple_k: float
    atr_pct_24h_min: float
    max_trades_per_day: int
    maker_only_default: bool


@dataclass
class SignalContext:
    """Signal 컨텍스트"""
    expected_profit_usd: float
    estimated_fee_usd: float
    is_maker: bool


# Fixture: Stage 1 params (Policy Section 5.1)
STAGE_1 = StageParams(
    stage_id=1,
    equity_usd_min=100,
    equity_usd_max=300,
    default_leverage=3.0,
    max_loss_usd_cap=10.0,
    loss_pct_cap=0.12,
    ev_fee_multiple_k=2.0,
    atr_pct_24h_min=0.03,
    max_trades_per_day=5,
    maker_only_default=True,
)


def test_gate_halt_rejects():
    """
    Gate 1: HALT 상태는 진입을 차단한다.

    FLOW Section 5: HALT = Manual reset only
    - 모든 진입 차단
    - Reject reason: "state_halt"
    """
    state = State.HALT
    stage = STAGE_1
    trades_today = 0
    atr_pct_24h = 0.05  # 충분히 높음
    signal = SignalContext(
        expected_profit_usd=5.0,
        estimated_fee_usd=1.0,  # EV = 5x (충분히 통과)
        is_maker=True,
    )
    winrate = 0.60  # 충분히 높음
    position_mode = "MergedSingle"  # One-way
    cooldown_until = None

    decision = check_entry_allowed(
        state=state,
        stage=stage,
        trades_today=trades_today,
        atr_pct_24h=atr_pct_24h,
        signal=signal,
        winrate=winrate,
        position_mode=position_mode,
        cooldown_until=cooldown_until,
    )

    assert decision.allowed is False, "HALT 상태는 진입을 차단해야 함"
    assert decision.reject_reason == "state_halt"


def test_gate_cooldown_rejects_before_timeout():
    """
    Gate 2a: COOLDOWN 상태에서 timeout 전에는 진입을 차단한다.

    FLOW Section 5: COOLDOWN = Auto-recovery 가능, timeout 전 차단
    """
    state = State.COOLDOWN
    stage = STAGE_1
    trades_today = 0
    atr_pct_24h = 0.05
    signal = SignalContext(
        expected_profit_usd=5.0,
        estimated_fee_usd=1.0,
        is_maker=True,
    )
    winrate = 0.60
    position_mode = "MergedSingle"
    cooldown_until = 100.0  # timeout 시각
    current_time = 50.0  # timeout 전 (50 < 100)

    decision = check_entry_allowed(
        state=state,
        stage=stage,
        trades_today=trades_today,
        atr_pct_24h=atr_pct_24h,
        signal=signal,
        winrate=winrate,
        position_mode=position_mode,
        cooldown_until=cooldown_until,
        current_time=current_time,
    )

    assert decision.allowed is False
    assert decision.reject_reason == "cooldown_active"


def test_gate_cooldown_allows_after_timeout():
    """
    Gate 2b: COOLDOWN timeout 후에는 진입을 허용한다.

    FLOW Section 5: COOLDOWN timeout 후 → FLAT 전환 가능
    """
    state = State.FLAT  # timeout 후 FLAT으로 전환됨
    stage = STAGE_1
    trades_today = 0
    atr_pct_24h = 0.05
    signal = SignalContext(
        expected_profit_usd=5.0,
        estimated_fee_usd=1.0,
        is_maker=True,
    )
    winrate = 0.60
    position_mode = "MergedSingle"
    cooldown_until = 100.0
    current_time = 150.0  # timeout 후 (150 > 100)

    decision = check_entry_allowed(
        state=state,
        stage=stage,
        trades_today=trades_today,
        atr_pct_24h=atr_pct_24h,
        signal=signal,
        winrate=winrate,
        position_mode=position_mode,
        cooldown_until=cooldown_until,
        current_time=current_time,
    )

    assert decision.allowed is True
    assert decision.reject_reason is None


def test_gate_max_trades_per_day_rejects():
    """
    Gate 2c: max_trades_per_day 초과 시 진입을 차단한다.

    Policy Section 5.1: Stage 1 = max 5 trades/day
    """
    state = State.FLAT
    stage = STAGE_1  # max_trades_per_day = 5
    trades_today = 5  # 이미 5회 거래 완료
    atr_pct_24h = 0.05
    signal = SignalContext(
        expected_profit_usd=5.0,
        estimated_fee_usd=1.0,
        is_maker=True,
    )
    winrate = 0.60
    position_mode = "MergedSingle"
    cooldown_until = None

    decision = check_entry_allowed(
        state=state,
        stage=stage,
        trades_today=trades_today,
        atr_pct_24h=atr_pct_24h,
        signal=signal,
        winrate=winrate,
        position_mode=position_mode,
        cooldown_until=cooldown_until,
    )

    assert decision.allowed is False
    assert decision.reject_reason == "max_trades_per_day_exceeded"


def test_gate_atr_min_rejects():
    """
    Gate 4: ATR < 임계치이면 진입을 차단한다.

    Policy Section 5.1: Stage 1 = ATR > 3%
    - 변동성이 낮으면 grid 전략 부적합
    """
    state = State.FLAT
    stage = STAGE_1  # atr_pct_24h_min = 0.03 (3%)
    trades_today = 0
    atr_pct_24h = 0.02  # 2% < 3% (임계치 미달)
    signal = SignalContext(
        expected_profit_usd=5.0,
        estimated_fee_usd=1.0,
        is_maker=True,
    )
    winrate = 0.60
    position_mode = "MergedSingle"
    cooldown_until = None

    decision = check_entry_allowed(
        state=state,
        stage=stage,
        trades_today=trades_today,
        atr_pct_24h=atr_pct_24h,
        signal=signal,
        winrate=winrate,
        position_mode=position_mode,
        cooldown_until=cooldown_until,
    )

    assert decision.allowed is False
    assert decision.reject_reason == "atr_too_low"


def test_gate_ev_gate_rejects():
    """
    Gate 5: expected_profit < fee * K이면 진입을 차단한다.

    Policy Section 5.1: Stage 1 = K=2.0
    - expected_profit_usd >= estimated_fee_usd * 2.0
    """
    state = State.FLAT
    stage = STAGE_1  # ev_fee_multiple_k = 2.0
    trades_today = 0
    atr_pct_24h = 0.05
    signal = SignalContext(
        expected_profit_usd=1.5,  # 1.5
        estimated_fee_usd=1.0,    # 1.5 < 1.0 * 2.0 = 2.0 (REJECT)
        is_maker=True,
    )
    winrate = 0.60
    position_mode = "MergedSingle"
    cooldown_until = None

    decision = check_entry_allowed(
        state=state,
        stage=stage,
        trades_today=trades_today,
        atr_pct_24h=atr_pct_24h,
        signal=signal,
        winrate=winrate,
        position_mode=position_mode,
        cooldown_until=cooldown_until,
    )

    assert decision.allowed is False
    assert decision.reject_reason == "ev_insufficient"


def test_gate_maker_only_enforced():
    """
    Gate 6: maker-only 위반 시 진입을 차단한다.

    Policy Section 5.1: Stage 1 = maker_only_default=True
    - is_maker=False → REJECT
    """
    state = State.FLAT
    stage = STAGE_1  # maker_only_default = True
    trades_today = 0
    atr_pct_24h = 0.05
    signal = SignalContext(
        expected_profit_usd=5.0,
        estimated_fee_usd=1.0,
        is_maker=False,  # Taker 주문 (REJECT)
    )
    winrate = 0.60
    position_mode = "MergedSingle"
    cooldown_until = None

    decision = check_entry_allowed(
        state=state,
        stage=stage,
        trades_today=trades_today,
        atr_pct_24h=atr_pct_24h,
        signal=signal,
        winrate=winrate,
        position_mode=position_mode,
        cooldown_until=cooldown_until,
    )

    assert decision.allowed is False
    assert decision.reject_reason == "maker_only_violation"


def test_gate_one_way_mode_validates():
    """
    Gate 8: one-way mode 위반 (hedge 감지) 시 진입을 차단한다.

    FLOW Section 3.1: Position Mode One-way only
    - positionIdx=0 강제
    - Hedge mode 감지 시 REJECT
    """
    state = State.FLAT
    stage = STAGE_1
    trades_today = 0
    atr_pct_24h = 0.05
    signal = SignalContext(
        expected_profit_usd=5.0,
        estimated_fee_usd=1.0,
        is_maker=True,
    )
    winrate = 0.60
    position_mode = "BothSide"  # Hedge mode (REJECT)
    cooldown_until = None

    decision = check_entry_allowed(
        state=state,
        stage=stage,
        trades_today=trades_today,
        atr_pct_24h=atr_pct_24h,
        signal=signal,
        winrate=winrate,
        position_mode=position_mode,
        cooldown_until=cooldown_until,
    )

    assert decision.allowed is False
    assert decision.reject_reason == "hedge_mode_detected"


def test_all_gates_pass_allows():
    """
    모든 gate를 통과하면 진입을 허용한다.

    검증:
    - State: FLAT (HALT/COOLDOWN 아님)
    - Trades: 0 < max_trades_per_day
    - ATR: >= 임계치
    - EV: >= fee * K
    - Maker-only: is_maker=True
    - One-way: MergedSingle
    """
    state = State.FLAT
    stage = STAGE_1
    trades_today = 0
    atr_pct_24h = 0.05  # > 3%
    signal = SignalContext(
        expected_profit_usd=5.0,   # 5.0 >= 1.0 * 2.0 (PASS)
        estimated_fee_usd=1.0,
        is_maker=True,
    )
    winrate = 0.60
    position_mode = "MergedSingle"
    cooldown_until = None

    decision = check_entry_allowed(
        state=state,
        stage=stage,
        trades_today=trades_today,
        atr_pct_24h=atr_pct_24h,
        signal=signal,
        winrate=winrate,
        position_mode=position_mode,
        cooldown_until=cooldown_until,
    )

    assert decision.allowed is True
    assert decision.reject_reason is None

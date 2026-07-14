"""
src/application/entry_coordinator.py
Entry Flow Coordination Helpers (Phase 11b)

Purpose:
- Helper functions for Entry Flow (Stage params, Signal context, Sizing params)
- Reduce orchestrator.py LOC (God Object refactoring)
- Keep entry logic testable and modular

SSOT:
- FLOW.md Section 2.4: Entry Decision Flow
- account_builder_policy.md Section 5: Stage Parameters
- account_builder_policy.md Section 10: Position Sizing

Design:
- Pure functions (no state mutation)
- Accept necessary parameters explicitly
- Return typed dataclasses (StageParams, SignalContext, SizingParams)
"""

from typing import Optional

from application.entry_allowed import StageParams, SignalContext
from application.signal_generator import Signal
from application.sizing import SizingParams
from application.stop_manager import calculate_stop_distance_pct
from infrastructure.exchange.market_data_interface import MarketDataInterface


def get_stage_id(equity_usdt: float) -> int:
    """Equity 기반 Stage ID 판별 (Policy Section 4).

    Stage 1: < $300, Stage 2: $300~$700, Stage 3: >= $700.
    """
    if equity_usdt < 300:
        return 1
    if equity_usdt < 700:
        return 2
    return 3


def get_stage_leverage(equity_usdt: float) -> float:
    """Equity 기반 Stage 레버리지 (Policy Section 5, 코드 기준).

    Stage 1/2: 5x, Stage 3: 3x. 사이징과 거래소 set_leverage가 동일 값을 쓰도록 단일 소스.
    """
    return 3.0 if get_stage_id(equity_usdt) == 3 else 5.0


def get_stage_params() -> StageParams:
    """
    Stage 파라미터 반환 (Policy Section 5)

    Returns:
        StageParams: Stage 파라미터 객체

    현재는 Stage 1 고정 (추후 동적 변경)

    Policy:
    - max_trades_per_day: 15 (Stage 1, 2026-03-20: 10→15 공격 파라미터 복원)
    - atr_pct_24h_min: 2% (ATR gate)
    - ev_fee_multiple_k: 2.0 (EV gate)
    - maker_only_default: True (Maker-only 전략)
    """
    return StageParams(
        max_trades_per_day=15,
        atr_pct_24h_min=0.02,  # 2%
        ev_fee_multiple_k=2.0,
        maker_only_default=True,
    )


def build_signal_context(signal: Signal, grid_spacing: float) -> SignalContext:
    """
    Signal context 생성 (EV gate용)

    Args:
        signal: Signal 객체 (signal_generator.Signal)
        grid_spacing: Grid spacing (USD, e.g., 200.0)

    Returns:
        SignalContext: Signal context 객체

    Grid spacing 기반 예상 수익 계산:
    - Expected profit: grid_spacing / entry_price (BTC) * entry_price (USD) = grid_spacing (USD)
    - Fee: qty / entry_price (BTC) * fee_rate * entry_price (USD) ≈ qty * fee_rate (USD approx)

    Policy:
    - Fee rate: 0.01% (Maker-only 전략)
    - Expected profit: Grid spacing (e.g., 200.0 USD)
    """
    # Fee 추정 (Maker: 0.01%, Taker: 0.06%)
    fee_rate = 0.0001  # Maker-only 전략
    estimated_fee_usd = (signal.qty / signal.price) * fee_rate * signal.price

    # Expected profit (Grid spacing)
    expected_profit_usd = grid_spacing

    return SignalContext(
        expected_profit_usd=expected_profit_usd,
        estimated_fee_usd=estimated_fee_usd,
        is_maker=True,  # Maker-only 전략
    )


def build_signal_context_with_rr_gate(
    signal: Signal,
    grid_spacing: float,
    stop_loss_usd: float,
    min_rr_ratio: float = 1.5,
) -> Optional[SignalContext]:
    """
    R:R 게이트 포함 Signal context 생성 (Wave4 EV gate 강화)

    Args:
        signal: Signal 객체
        grid_spacing: Grid spacing (USD, 예상 수익)
        stop_loss_usd: 예상 손실 USD
        min_rr_ratio: 최소 R:R 비율 (기본 1.5)

    Returns:
        SignalContext if R:R >= min_rr_ratio, else None (진입 차단)

    Policy:
    - R:R = expected_profit / stop_loss_usd >= 1.5 이어야 진입 허용
    - stop_loss_usd=0이면 ZeroDivision 방지를 위해 차단
    """
    if stop_loss_usd <= 0:
        return None

    rr_ratio = grid_spacing / stop_loss_usd
    if rr_ratio < min_rr_ratio:
        return None

    return build_signal_context(signal, grid_spacing)


def build_sizing_params(signal: Signal, market_data: MarketDataInterface, atr: float = 0.0) -> SizingParams:
    """
    Sizing 파라미터 생성 (Linear USDT)

    Args:
        signal: Signal 객체 (signal_generator.Signal)
        market_data: Market data interface (equity_usdt 필요)

    Returns:
        SizingParams: Sizing 파라미터 객체

    Policy (Linear USDT):
    - Max loss budget: Stage별 (max_loss_usd_cap, loss_pct_cap 중 작은 값)
    - Stop distance: 3%
    - Leverage: Stage별 (Stage 1/2: 5x, Stage 3: 3x)
    - Fee rate: 0.01% (Maker)
    - Tick size: 0.5 (Bybit BTCUSDT)
    - Lot size: 1 contract (Bybit Linear BTCUSDT)
    - Contract size: 0.001 BTC per contract

    Stage 1 공격 설정 (2026-03-20 갱신):
    - Stage 1 (< $300): max_loss_usd_cap=$15, loss_pct_cap=15%
    - Stage 2 ($300~$700): max_loss_usd_cap=$30, loss_pct_cap=10%
    - Stage 3 (>= $700): max_loss_usd_cap=$45, loss_pct_cap=8%
    """
    # Equity USDT (Linear USDT-Margined)
    equity_usdt = market_data.get_equity_usdt()

    # Stage 판별 (Policy Section 4)
    if equity_usdt < 300:
        # Stage 1: Expansion ($100 → $300)
        max_loss_usd_cap = 15.0
        loss_pct_cap = 0.15
    elif equity_usdt < 700:
        # Stage 2: Acceleration ($300 → $700)
        max_loss_usd_cap = 30.0
        loss_pct_cap = 0.10
    else:
        # Stage 3: Preservation ($700 → $1,000)
        max_loss_usd_cap = 45.0
        loss_pct_cap = 0.08

    # Leverage: Stage별 단일 소스 (Stage 1/2: 5x, Stage 3: 3x)
    leverage = get_stage_leverage(equity_usdt)

    # Max loss USDT: min(usd_cap, equity * pct_cap)
    # Codex Review Fix #3: 고정 cap과 % cap 중 작은 값 사용
    max_loss_usdt = min(max_loss_usd_cap, equity_usdt * loss_pct_cap)

    # Direction (Buy → LONG, Sell → SHORT)
    direction = "LONG" if signal.side == "Buy" else "SHORT"

    # Stop distance — stop_manager와 동일 단일 소스 (Policy Sec 10.1.1: ATR*0.7, clamp 0.5%~2.0%)
    stop_distance_pct = calculate_stop_distance_pct(signal.price, atr if atr > 0 else None)

    # Fee rate (Maker: 0.01%)
    fee_rate = 0.0001

    # Tick/Lot size (Bybit Linear BTCUSDT)
    tick_size = 0.5
    qty_step = 1
    contract_size = 0.001  # 1 contract = 0.001 BTC

    # FIX 2026-03-07: Add available_usdt parameter
    available_usdt = market_data.get_available_usdt()
    
    return SizingParams(
        max_loss_usdt=max_loss_usdt,
        entry_price_usd=signal.price,
        stop_distance_pct=stop_distance_pct,
        leverage=leverage,
        equity_usdt=equity_usdt,
        available_usdt=available_usdt,  # FIX: Required parameter added
        fee_rate=fee_rate,
        direction=direction,
        qty_step=qty_step,
        tick_size=tick_size,
        contract_size=contract_size,
    )


def generate_signal_id() -> str:
    """
    Signal ID 생성 (타임스탬프 기반)

    Returns:
        str: Signal ID (예: "1737700000")

    Grid trading에서 각 신호를 추적하기 위한 고유 ID
    """
    import time

    timestamp = int(time.time())
    return f"{timestamp}"

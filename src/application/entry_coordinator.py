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

from src.application.entry_allowed import StageParams, SignalContext
from src.application.signal_generator import Signal
from src.application.sizing import SizingParams
from src.infrastructure.exchange.market_data_interface import MarketDataInterface


def get_stage_params() -> StageParams:
    """
    Stage 파라미터 반환 (Policy Section 5)

    Returns:
        StageParams: Stage 파라미터 객체

    현재는 Stage 1 고정 (추후 동적 변경)

    Policy:
    - max_trades_per_day: 10 (Stage 1)
    - atr_pct_24h_min: 2% (ATR gate)
    - ev_fee_multiple_k: 2.0 (EV gate)
    - maker_only_default: True (Maker-only 전략)
    """
    return StageParams(
        max_trades_per_day=10,
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


def build_sizing_params(signal: Signal, market_data: MarketDataInterface) -> SizingParams:
    """
    Sizing 파라미터 생성 (Linear USDT)

    Args:
        signal: Signal 객체 (signal_generator.Signal)
        market_data: Market data interface (equity_usdt 필요)

    Returns:
        SizingParams: Sizing 파라미터 객체

    Policy (Linear USDT):
    - Max loss budget: 1% equity per trade
    - Stop distance: 3%
    - Leverage: 3x (Stage 1)
    - Fee rate: 0.01% (Maker)
    - Tick size: 0.5 (Bybit BTCUSDT)
    - Lot size: 1 contract (Bybit Linear BTCUSDT)
    - Contract size: 0.001 BTC per contract
    """
    # Equity USDT (Linear USDT-Margined)
    equity_usdt = market_data.get_equity_usdt()

    # Max loss USDT (loss budget = 1% equity per trade)
    max_loss_usdt = equity_usdt * 0.01

    # Direction (Buy → LONG, Sell → SHORT)
    direction = "LONG" if signal.side == "Buy" else "SHORT"

    # Stop distance pct (3%)
    stop_distance_pct = 0.03

    # Leverage (Stage 1 = 3x)
    leverage = 3.0

    # Fee rate (Maker: 0.01%)
    fee_rate = 0.0001

    # Tick/Lot size (Bybit Linear BTCUSDT)
    tick_size = 0.5
    qty_step = 1
    contract_size = 0.001  # 1 contract = 0.001 BTC

    return SizingParams(
        max_loss_usdt=max_loss_usdt,
        entry_price_usd=signal.price,
        stop_distance_pct=stop_distance_pct,
        leverage=leverage,
        equity_usdt=equity_usdt,
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

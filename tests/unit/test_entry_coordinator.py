"""
tests/unit/test_entry_coordinator.py

Gate: entry_coordinator 헬퍼 함수 단위 테스트

Purpose:
- get_stage_params(), build_signal_context(), build_sizing_params(),
  generate_signal_id() 검증
- Stage 분기 (Stage 1/2/3)별 파라미터 검증
- ATR 기반 stop distance 검증

Execution:
  pytest tests/unit/test_entry_coordinator.py -v
"""

import pytest
from unittest.mock import MagicMock
from application.entry_coordinator import (
    get_stage_params,
    build_signal_context,
    build_sizing_params,
    generate_signal_id,
)
from application.signal_generator import Signal


def _make_signal(side="Buy", price=50000.0, qty=3):
    """Helper: Signal 객체 생성."""
    return Signal(side=side, price=price, qty=qty)


def _make_market_data(equity_usdt=105.0, available_usdt=100.0):
    """Helper: MarketDataInterface mock 생성."""
    md = MagicMock()
    md.get_equity_usdt.return_value = equity_usdt
    md.get_available_usdt.return_value = available_usdt
    return md


# ============================================================
# get_stage_params()
# ============================================================


def test_stage_params_returns_correct_max_trades():
    """Stage 1 max_trades_per_day = 15."""
    params = get_stage_params()
    assert params.max_trades_per_day == 15


def test_stage_params_returns_correct_atr_gate():
    """ATR gate: 2%."""
    params = get_stage_params()
    assert params.atr_pct_24h_min == pytest.approx(0.02)


def test_stage_params_returns_correct_ev_multiple():
    """EV fee multiple k = 2.0."""
    params = get_stage_params()
    assert params.ev_fee_multiple_k == pytest.approx(2.0)


def test_stage_params_maker_only_default_true():
    """Maker-only 전략 기본값 = True."""
    params = get_stage_params()
    assert params.maker_only_default is True


# ============================================================
# build_signal_context()
# ============================================================


def test_signal_context_expected_profit_equals_grid_spacing():
    """expected_profit_usd는 grid_spacing과 동일."""
    signal = _make_signal(price=50000.0, qty=3)
    ctx = build_signal_context(signal, grid_spacing=200.0)
    assert ctx.expected_profit_usd == pytest.approx(200.0)


def test_signal_context_is_maker_true():
    """is_maker = True (Maker-only 전략)."""
    signal = _make_signal()
    ctx = build_signal_context(signal, grid_spacing=150.0)
    assert ctx.is_maker is True


def test_signal_context_fee_calculation():
    """Fee 계산: qty/price * 0.0001 * price = qty * 0.0001."""
    signal = _make_signal(price=50000.0, qty=10)
    ctx = build_signal_context(signal, grid_spacing=200.0)
    # estimated_fee = (10 / 50000) * 0.0001 * 50000 = 10 * 0.0001 = 0.001
    assert ctx.estimated_fee_usd == pytest.approx(0.001)


def test_signal_context_with_different_grid_spacing():
    """다른 grid_spacing → expected_profit 변경."""
    signal = _make_signal()
    ctx = build_signal_context(signal, grid_spacing=500.0)
    assert ctx.expected_profit_usd == pytest.approx(500.0)


# ============================================================
# build_sizing_params() — Stage 분기
# ============================================================


def test_sizing_stage1_leverage():
    """Stage 1 (equity < 300) → leverage 5x."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data(equity_usdt=100.0)
    params = build_sizing_params(signal, md)
    assert params.leverage == pytest.approx(5.0)


def test_sizing_stage1_max_loss():
    """Stage 1 → max_loss = min(15, 100*0.15) = 15."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data(equity_usdt=100.0)
    params = build_sizing_params(signal, md)
    assert params.max_loss_usdt == pytest.approx(15.0)


def test_sizing_stage1_max_loss_pct_cap_lower():
    """Stage 1, equity=50 → max_loss = min(15, 50*0.15) = min(15, 7.5) = 7.5."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data(equity_usdt=50.0)
    params = build_sizing_params(signal, md)
    assert params.max_loss_usdt == pytest.approx(7.5)


def test_sizing_stage2_leverage():
    """Stage 2 (300 <= equity < 700) → leverage 5x."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data(equity_usdt=400.0)
    params = build_sizing_params(signal, md)
    assert params.leverage == pytest.approx(5.0)


def test_sizing_stage2_max_loss():
    """Stage 2, equity=400 → max_loss = min(30, 400*0.10) = 30."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data(equity_usdt=400.0)
    params = build_sizing_params(signal, md)
    assert params.max_loss_usdt == pytest.approx(30.0)


def test_sizing_stage2_pct_cap_lower():
    """Stage 2, equity=200 아닌 350 → min(30, 350*0.10=35) = 30."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data(equity_usdt=350.0)
    params = build_sizing_params(signal, md)
    assert params.max_loss_usdt == pytest.approx(30.0)


def test_sizing_stage3_leverage():
    """Stage 3 (equity >= 700) → leverage 3x."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data(equity_usdt=800.0)
    params = build_sizing_params(signal, md)
    assert params.leverage == pytest.approx(3.0)


def test_sizing_stage3_max_loss():
    """Stage 3, equity=800 → max_loss = min(45, 800*0.08=64) = 45."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data(equity_usdt=800.0)
    params = build_sizing_params(signal, md)
    assert params.max_loss_usdt == pytest.approx(45.0)


def test_sizing_stage3_pct_cap_lower():
    """Stage 3, equity=500 아닌 700 → min(45, 700*0.08=56) = 45."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data(equity_usdt=700.0)
    params = build_sizing_params(signal, md)
    assert params.max_loss_usdt == pytest.approx(45.0)


# ============================================================
# build_sizing_params() — Direction
# ============================================================


def test_sizing_buy_signal_returns_long():
    """side='Buy' → direction='LONG'."""
    signal = _make_signal(side="Buy")
    md = _make_market_data()
    params = build_sizing_params(signal, md)
    assert params.direction == "LONG"


def test_sizing_sell_signal_returns_short():
    """side='Sell' → direction='SHORT'."""
    signal = _make_signal(side="Sell")
    md = _make_market_data()
    params = build_sizing_params(signal, md)
    assert params.direction == "SHORT"


# ============================================================
# build_sizing_params() — Stop distance (ATR 기반)
# ============================================================


def test_sizing_atr_based_stop_distance():
    """정책 단일화(ATR*0.7, clamp 0.5%~2.0%): ATR=500, price=50000 → 350/50000=0.007."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data()
    params = build_sizing_params(signal, md, atr=500.0)
    # raw = (500 * 0.7) / 50000 = 0.007, within [0.005, 0.020]
    assert params.stop_distance_pct == pytest.approx(0.007)


def test_sizing_atr_stop_clamp_min():
    """ATR very small → clamp to 0.5% min (Policy Sec 10.1.1)."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data()
    params = build_sizing_params(signal, md, atr=100.0)
    # raw = (100 * 0.7) / 50000 = 0.0014, clamped to 0.005
    assert params.stop_distance_pct == pytest.approx(0.005)


def test_sizing_atr_stop_clamp_max():
    """ATR very large → clamp to 2.0% max (Policy Sec 10.1.1)."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data()
    params = build_sizing_params(signal, md, atr=5000.0)
    # raw = (5000 * 0.7) / 50000 = 0.07, clamped to 0.020
    assert params.stop_distance_pct == pytest.approx(0.020)


def test_sizing_atr_zero_uses_fallback():
    """ATR=0 → fallback stop distance 1.0%."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data()
    params = build_sizing_params(signal, md, atr=0.0)
    assert params.stop_distance_pct == pytest.approx(0.01)


def test_sizing_no_atr_arg_uses_fallback():
    """ATR 미지정 (default 0.0) → fallback stop distance 1.0%."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data()
    params = build_sizing_params(signal, md)
    assert params.stop_distance_pct == pytest.approx(0.01)


# ============================================================
# build_sizing_params() — Fixed params
# ============================================================


def test_sizing_fee_rate():
    """Fee rate = 0.01% (Maker)."""
    signal = _make_signal()
    md = _make_market_data()
    params = build_sizing_params(signal, md)
    assert params.fee_rate == pytest.approx(0.0001)


def test_sizing_tick_size():
    """Tick size = 0.5 (Bybit BTCUSDT)."""
    signal = _make_signal()
    md = _make_market_data()
    params = build_sizing_params(signal, md)
    assert params.tick_size == pytest.approx(0.5)


def test_sizing_qty_step():
    """Qty step = 1 contract."""
    signal = _make_signal()
    md = _make_market_data()
    params = build_sizing_params(signal, md)
    assert params.qty_step == 1


def test_sizing_contract_size():
    """Contract size = 0.001 BTC."""
    signal = _make_signal()
    md = _make_market_data()
    params = build_sizing_params(signal, md)
    assert params.contract_size == pytest.approx(0.001)


def test_sizing_entry_price():
    """entry_price_usd = signal.price."""
    signal = _make_signal(price=42000.0)
    md = _make_market_data()
    params = build_sizing_params(signal, md)
    assert params.entry_price_usd == pytest.approx(42000.0)


def test_sizing_equity_usdt_passthrough():
    """equity_usdt는 market_data에서 그대로 전달."""
    signal = _make_signal()
    md = _make_market_data(equity_usdt=250.0)
    params = build_sizing_params(signal, md)
    assert params.equity_usdt == pytest.approx(250.0)


def test_sizing_available_usdt_passthrough():
    """available_usdt는 market_data에서 그대로 전달."""
    signal = _make_signal()
    md = _make_market_data(available_usdt=80.0)
    params = build_sizing_params(signal, md)
    assert params.available_usdt == pytest.approx(80.0)


# ============================================================
# build_sizing_params() — Stage boundary values
# ============================================================


def test_sizing_boundary_stage1_to_stage2():
    """equity=300 → Stage 2 (equity < 300 is Stage 1)."""
    signal = _make_signal()
    md = _make_market_data(equity_usdt=300.0)
    params = build_sizing_params(signal, md)
    # Stage 2: leverage=5, max_loss_usd_cap=30
    assert params.leverage == pytest.approx(5.0)
    assert params.max_loss_usdt == pytest.approx(30.0)


def test_sizing_boundary_stage2_to_stage3():
    """equity=700 → Stage 3 (equity < 700 is Stage 2)."""
    signal = _make_signal()
    md = _make_market_data(equity_usdt=700.0)
    params = build_sizing_params(signal, md)
    # Stage 3: leverage=3
    assert params.leverage == pytest.approx(3.0)


def test_sizing_boundary_stage1_max():
    """equity=299.99 → still Stage 1."""
    signal = _make_signal()
    md = _make_market_data(equity_usdt=299.99)
    params = build_sizing_params(signal, md)
    assert params.leverage == pytest.approx(5.0)
    # max_loss = min(15, 299.99 * 0.15) = 15
    assert params.max_loss_usdt == pytest.approx(15.0)


# ============================================================
# generate_signal_id()
# ============================================================


def test_generate_signal_id_returns_string():
    """Signal ID는 문자열 반환."""
    sid = generate_signal_id()
    assert isinstance(sid, str)


def test_generate_signal_id_is_numeric():
    """Signal ID는 정수 타임스탬프 문자열."""
    sid = generate_signal_id()
    assert sid.isdigit()


def test_generate_signal_id_is_reasonable_timestamp():
    """Signal ID는 합리적 범위의 타임스탬프."""
    import time
    sid = generate_signal_id()
    ts = int(sid)
    now = int(time.time())
    # 1초 이내 차이
    assert abs(ts - now) <= 1


# ============================================================
# build_sizing_params() — SL 단일화 (ATR * 0.7, clamp 0.5%~2.0%, Policy Sec 10.1.1)
# stop_manager.calculate_stop_distance_pct와 동일 소스
# ============================================================


def test_sizing_atr_based_stop_distance_mid_range():
    """ATR=1000, price=50000 → raw = (1000*0.7)/50000 = 0.014, within [0.005, 0.020]."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data()
    params = build_sizing_params(signal, md, atr=1000.0)
    # raw = (1000 * 0.7) / 50000 = 0.014, unclamped
    assert params.stop_distance_pct == pytest.approx(0.014)


def test_sizing_atr_stop_unified_clamp_min():
    """ATR very small → clamp to 0.5% min (Policy Sec 10.1.1)."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data()
    params = build_sizing_params(signal, md, atr=100.0)
    # raw = (100 * 0.7) / 50000 = 0.0014, clamped to 0.005
    assert params.stop_distance_pct == pytest.approx(0.005)


def test_sizing_atr_stop_unified_clamp_max():
    """ATR very large → clamp to 2.0% max (Policy Sec 10.1.1)."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data()
    params = build_sizing_params(signal, md, atr=5000.0)
    # raw = (5000 * 0.7) / 50000 = 0.07, clamped to 0.020
    assert params.stop_distance_pct == pytest.approx(0.020)


def test_sizing_atr_within_unified_range():
    """ATR=500, price=50000 → raw = (500*0.7)/50000 = 0.007, within [0.005, 0.020]."""
    signal = _make_signal(price=50000.0, qty=3)
    md = _make_market_data()
    params = build_sizing_params(signal, md, atr=500.0)
    # raw = (500 * 0.7) / 50000 = 0.007, unclamped
    assert params.stop_distance_pct == pytest.approx(0.007)


# ============================================================
# build_signal_context_with_rr_gate() — R:R 게이트 (min_rr_ratio >= 1.5)
# ============================================================


def test_rr_gate_passes_when_ratio_above_threshold():
    """R:R >= 1.5이면 build_signal_context_with_rr_gate 정상 반환."""
    from application.entry_coordinator import build_signal_context_with_rr_gate
    signal = _make_signal(price=50000.0, qty=3)
    # grid_spacing=200 (expected profit), stop_loss_usd=100 → R:R=2.0 >= 1.5
    ctx = build_signal_context_with_rr_gate(signal, grid_spacing=200.0, stop_loss_usd=100.0)
    assert ctx is not None
    assert ctx.expected_profit_usd == pytest.approx(200.0)


def test_rr_gate_blocks_when_ratio_below_threshold():
    """R:R < 1.5이면 None 반환 (진입 차단)."""
    from application.entry_coordinator import build_signal_context_with_rr_gate
    signal = _make_signal(price=50000.0, qty=3)
    # grid_spacing=100 (expected profit), stop_loss_usd=100 → R:R=1.0 < 1.5
    ctx = build_signal_context_with_rr_gate(signal, grid_spacing=100.0, stop_loss_usd=100.0)
    assert ctx is None


def test_rr_gate_passes_at_exactly_threshold():
    """R:R = 1.5이면 통과 (경계값)."""
    from application.entry_coordinator import build_signal_context_with_rr_gate
    signal = _make_signal(price=50000.0, qty=3)
    # grid_spacing=150, stop_loss_usd=100 → R:R=1.5 (정확히 경계)
    ctx = build_signal_context_with_rr_gate(signal, grid_spacing=150.0, stop_loss_usd=100.0)
    assert ctx is not None


def test_rr_gate_blocks_zero_stop_loss():
    """stop_loss_usd=0이면 None 반환 (ZeroDivision 방지)."""
    from application.entry_coordinator import build_signal_context_with_rr_gate
    signal = _make_signal(price=50000.0, qty=3)
    ctx = build_signal_context_with_rr_gate(signal, grid_spacing=200.0, stop_loss_usd=0.0)
    assert ctx is None

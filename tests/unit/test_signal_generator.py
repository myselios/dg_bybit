"""
tests/unit/test_signal_generator.py

Phase 11: Signal Generator 테스트 (Grid 전략)

DoD:
- Grid-based signal generation (간단한 구현)
- ATR 기반 grid spacing 계산
- Last fill price 기반 grid level 결정
"""

import pytest
from dataclasses import asdict


# Test 1: Grid up - 가격 상승 시 매도 신호
def test_grid_up_generates_sell_signal():
    """
    Grid up: 현재 가격이 last_fill_price + grid_spacing 이상이면 Sell 신호
    """
    from src.application.signal_generator import generate_signal, Signal

    current_price = 50100.0
    last_fill_price = 50000.0
    grid_spacing = 100.0

    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
    )

    assert signal is not None
    assert signal.side == "Sell"
    assert signal.price == current_price


# Test 2: Grid down - 가격 하락 시 매수 신호
def test_grid_down_generates_buy_signal():
    """
    Grid down: 현재 가격이 last_fill_price - grid_spacing 이하이면 Buy 신호
    """
    from src.application.signal_generator import generate_signal

    current_price = 49900.0
    last_fill_price = 50000.0
    grid_spacing = 100.0

    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
    )

    assert signal is not None
    assert signal.side == "Buy"
    assert signal.price == current_price


# Test 3: No signal - grid 범위 내에서는 신호 없음
def test_no_signal_within_grid_range():
    """
    현재 가격이 grid 범위 내(last_fill_price ± grid_spacing)이면 신호 없음
    """
    from src.application.signal_generator import generate_signal

    current_price = 50050.0  # grid 범위 내
    last_fill_price = 50000.0
    grid_spacing = 100.0

    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
    )

    assert signal is None


# Test 4: ATR 기반 grid spacing 계산
def test_calculate_grid_spacing_from_atr():
    """
    Grid spacing = ATR * multiplier (기본 2.0)
    """
    from src.application.signal_generator import calculate_grid_spacing

    atr = 50.0
    multiplier = 2.0

    grid_spacing = calculate_grid_spacing(atr=atr, multiplier=multiplier)

    assert grid_spacing == 100.0  # 50 * 2 = 100


# Test 5: Grid spacing multiplier 조정
def test_calculate_grid_spacing_with_custom_multiplier():
    """
    Grid spacing multiplier를 조정할 수 있다
    """
    from src.application.signal_generator import calculate_grid_spacing

    atr = 50.0
    multiplier = 3.0

    grid_spacing = calculate_grid_spacing(atr=atr, multiplier=multiplier)

    assert grid_spacing == 150.0  # 50 * 3 = 150


# Test 6: 경계값 - 정확히 grid spacing만큼 떨어진 경우 (Buy)
def test_grid_boundary_exact_buy():
    """
    현재 가격이 정확히 last_fill_price - grid_spacing이면 Buy 신호
    """
    from src.application.signal_generator import generate_signal

    current_price = 49900.0
    last_fill_price = 50000.0
    grid_spacing = 100.0

    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
    )

    assert signal is not None
    assert signal.side == "Buy"


# Test 7: 경계값 - 정확히 grid spacing만큼 떨어진 경우 (Sell)
def test_grid_boundary_exact_sell():
    """
    현재 가격이 정확히 last_fill_price + grid_spacing이면 Sell 신호
    """
    from src.application.signal_generator import generate_signal

    current_price = 50100.0
    last_fill_price = 50000.0
    grid_spacing = 100.0

    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
    )

    assert signal is not None
    assert signal.side == "Sell"


# Test 8: Signal에 qty 포함
def test_signal_contains_qty():
    """
    Signal에 qty 필드가 포함되어야 한다
    """
    from src.application.signal_generator import generate_signal

    current_price = 50100.0
    last_fill_price = 50000.0
    grid_spacing = 100.0
    qty = 100  # contracts

    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        qty=qty,
    )

    assert signal is not None
    assert signal.qty == 100


# Test 9: 초기 상태 (last_fill_price = None) - 첫 진입 신호
def test_initial_entry_signal_when_no_last_fill():
    """
    last_fill_price가 None이면 (FLAT 상태), 진입 신호를 생성하지 않는다.
    (진입은 다른 로직에서 처리)
    """
    from src.application.signal_generator import generate_signal

    current_price = 50000.0
    last_fill_price = None
    grid_spacing = 100.0

    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
    )

    # last_fill_price가 None이면 grid 신호 생성 불가
    assert signal is None


# Test 10: 여러 grid level 떨어진 경우
def test_multiple_grid_levels_away():
    """
    여러 grid level 떨어져도 신호는 1번만 생성 (다음 grid로 진입)
    """
    from src.application.signal_generator import generate_signal

    current_price = 50300.0  # 3 grid levels up
    last_fill_price = 50000.0
    grid_spacing = 100.0

    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
    )

    assert signal is not None
    assert signal.side == "Sell"
    # 신호는 1번만 (다음 grid 진입)

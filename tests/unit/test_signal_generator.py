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


# Test 9: Regime-Aware Initial Entry (Phase 13c)
def test_initial_entry_signal_when_no_last_fill():
    """
    Phase 13c: Regime-Aware Initial Entry

    Trend regime: MA slope 방향 우선
    Range regime: Funding 극단값만 허용
    """
    from src.application.signal_generator import generate_signal

    current_price = 50000.0
    last_fill_price = None
    grid_spacing = 100.0

    # Case 1: Trend Up (ma_slope >= 0.5%) → Buy
    signal_trend_up = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=0.6,  # Trend up
        funding_rate=0.001,  # Ignored in trend
    )
    assert signal_trend_up is not None
    assert signal_trend_up.side == "Buy"

    # Case 2: Trend Down (ma_slope <= -0.5%) → Sell
    signal_trend_down = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=-0.8,  # Trend down
        funding_rate=-0.001,  # Ignored in trend
    )
    assert signal_trend_down is not None
    assert signal_trend_down.side == "Sell"

    # Case 3: Range + Funding 극단 (> 1%) → Sell
    signal_range_extreme = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=0.2,  # Range
        funding_rate=0.015,  # 1.5% (극단)
    )
    assert signal_range_extreme is not None
    assert signal_range_extreme.side == "Sell"

    # Case 4: Range + Funding 낮음 + 약한 방향성 → None (차단)
    # T_RANGE_ENTRY=0.5%로 상향됨 (ranging 0% 승률 실적 반영, 2026-03-13)
    # 0.1%는 T_RANGE_ENTRY(0.5%) 미달 → 진입 보류
    signal_range_mild = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=0.1,  # Range, 약한 방향성 (< T_RANGE_ENTRY=0.5%)
        funding_rate=0.0005,  # 0.05% (극단 아님)
    )
    assert signal_range_mild is None  # T_RANGE_ENTRY=0.5% 미달 → 차단

    # Case 5: Range + Funding 낮음 + dead flat → None (진입 보류)
    signal_dead_flat = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=0.01,  # Dead flat (< 0.02%)
        funding_rate=0.0005,  # 0.05% (극단 아님)
    )
    assert signal_dead_flat is None  # 완전 무방향 → 진입 보류


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


# Test 11: Regime-Aware Entry with Real Market Scenario (Phase 13c)
def test_initial_entry_regime_aware_realistic():
    """
    Phase 13c: Regime-Aware Entry (Realistic Scenarios)

    하락 추세 + 음수 Funding (숏 과열):
    - Trend regime → MA slope 우선 → Sell
    - Funding은 무시 (Trend에서는 방향 고정)
    """
    from src.application.signal_generator import generate_signal

    current_price = 104000.0
    last_fill_price = None  # 첫 진입
    grid_spacing = 2000.0

    # Scenario: 하락 추세 (-0.8%) + 음수 Funding (-0.007)
    # MA slope 우선 → Sell
    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=-0.8,  # 하락 추세
        funding_rate=-0.007,  # 숏 과열 (역추세 유혹)
    )
    assert signal is not None, "Trend regime should generate signal"
    assert signal.side == "Sell", "Trend down → Sell (Funding ignored)"
    assert signal.price == current_price

    # Scenario 2: Range + 극단 Funding → Funding 방향
    signal2 = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=0.1,  # Range
        funding_rate=-0.012,  # -1.2% (극단)
    )
    assert signal2 is not None
    assert signal2.side == "Buy"  # 음수 funding → Buy


# ========== Wave 3: Grid 역추세 방지 테스트 ==========


def test_grid_sell_blocked_in_strong_uptrend():
    """
    Wave 3: Grid Sell 신호 + 강한 상승 추세 → None (차단)

    시나리오: BTC 상승 추세 (ma_slope=0.6%) + 가격이 grid_up 도달 → 원래는 Sell
    → 하지만 추세가 상승이므로 SHORT 진입은 역추세 → 차단해야 함

    Given: last_fill_price=69000, price=69200(grid_up), ma_slope=0.6%(상승 추세)
    When: generate_signal()
    Then: None (Sell 차단)
    """
    from src.application.signal_generator import generate_signal, T_TREND

    last_fill_price = 69000.0
    grid_spacing = 115.0
    current_price = last_fill_price + grid_spacing + 1  # grid_up 도달

    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=T_TREND + 0.1,  # 강한 상승 추세
        funding_rate=0.0001,
    )
    assert signal is None, (
        f"Grid Sell in strong uptrend (ma={T_TREND+0.1}%) should be blocked, got {signal}"
    )


def test_grid_buy_blocked_in_strong_downtrend():
    """
    Wave 3: Grid Buy 신호 + 강한 하락 추세 → None (차단)

    시나리오: BTC 하락 추세 (ma_slope=-0.6%) + 가격이 grid_down 도달 → 원래는 Buy
    → 하지만 추세가 하락이므로 LONG 진입은 역추세 → 차단해야 함

    Given: last_fill_price=69000, price=68884(grid_down), ma_slope=-0.6%(하락 추세)
    When: generate_signal()
    Then: None (Buy 차단)
    """
    from src.application.signal_generator import generate_signal, T_TREND

    last_fill_price = 69000.0
    grid_spacing = 115.0
    current_price = last_fill_price - grid_spacing - 1  # grid_down 도달

    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=-(T_TREND + 0.1),  # 강한 하락 추세
        funding_rate=-0.0001,
    )
    assert signal is None, (
        f"Grid Buy in strong downtrend (ma={-(T_TREND+0.1)}%) should be blocked, got {signal}"
    )


def test_grid_sell_allowed_in_neutral_or_down_trend():
    """
    Wave 3: Grid Sell 신호 + 중립/하락 추세 → 허용

    ma_slope이 T_TREND 미만이면 Grid Sell 허용.
    """
    from src.application.signal_generator import generate_signal, T_TREND

    last_fill_price = 69000.0
    grid_spacing = 115.0
    current_price = last_fill_price + grid_spacing + 1

    # 중립 추세 → 허용
    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=0.1,  # 중립
        funding_rate=0.0001,
    )
    assert signal is not None, "Grid Sell in neutral trend should be allowed"
    assert signal.side == "Sell"

    # 하락 추세 → Sell 허용 (추세 방향과 일치)
    signal2 = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=-(T_TREND + 0.1),  # 강한 하락 추세에서도 Sell은 허용
        funding_rate=-0.0001,
    )
    assert signal2 is not None, "Grid Sell in downtrend should be allowed"
    assert signal2.side == "Sell"


def test_grid_buy_allowed_in_neutral_or_up_trend():
    """
    Wave 3: Grid Buy 신호 + 중립/상승 추세 → 허용
    """
    from src.application.signal_generator import generate_signal, T_TREND

    last_fill_price = 69000.0
    grid_spacing = 115.0
    current_price = last_fill_price - grid_spacing - 1

    # 중립 → 허용
    signal = generate_signal(
        current_price=current_price,
        last_fill_price=last_fill_price,
        grid_spacing=grid_spacing,
        ma_slope_pct=0.1,
        funding_rate=0.0001,
    )
    assert signal is not None, "Grid Buy in neutral trend should be allowed"
    assert signal.side == "Buy"


# ========== S4: SL Sizing ATR*0.7 정합성 ==========


class TestSizingParamsStopDistance:
    """S4: build_sizing_params의 stop_distance_pct가 ATR*0.8 기반인지 검증

    Wave4 변경: ATR*0.7→ATR*0.8, clamp(0.5%~2.0%)→(0.4%~1.5%)
    """

    def test_build_sizing_params_uses_atr08(self):
        """build_sizing_params stop_distance_pct가 ATR*0.8 기반인지 검증

        atr=1000, price=70000
        기대: ATR*0.8/price = 800/70000 ≈ 0.01143 → clamp(0.4%,1.5%) → 0.01143
        """
        from application.entry_coordinator import build_sizing_params
        from application.signal_generator import Signal
        from unittest.mock import MagicMock

        # Arrange
        signal = Signal(side="Buy", price=70000.0, qty=1)
        market_data = MagicMock()
        market_data.get_equity_usdt.return_value = 139.0
        market_data.get_available_usdt.return_value = 139.0
        atr = 1000.0

        # Act
        params = build_sizing_params(signal, market_data, atr=atr)

        # Assert: ATR*0.8 기반 → 800/70000 ≈ 0.01143, within [0.004, 0.015]
        import pytest
        assert params.stop_distance_pct == pytest.approx(800.0 / 70000.0, abs=1e-6)

    def test_build_sizing_params_stop_distance_clamped(self):
        """극단값에서도 clamp(0.4%~1.5%) 적용

        atr=100 (매우 작음), price=70000
        ATR*0.8/price = 80/70000 ≈ 0.00114 → clamp 하한 → 0.004 (0.4%)
        """
        from application.entry_coordinator import build_sizing_params
        from application.signal_generator import Signal
        from unittest.mock import MagicMock

        # Arrange
        signal = Signal(side="Buy", price=70000.0, qty=1)
        market_data = MagicMock()
        market_data.get_equity_usdt.return_value = 139.0
        market_data.get_available_usdt.return_value = 139.0
        atr = 100.0  # 매우 작은 ATR

        # Act
        params = build_sizing_params(signal, market_data, atr=atr)

        # Assert: ATR*0.8/price = 80/70000 ≈ 0.00114 → clamp → 0.004
        assert params.stop_distance_pct == pytest.approx(0.004)

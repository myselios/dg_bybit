"""
tests/unit/test_threshold_calibrator.py

S6 ThresholdCalibrator — TDD RED 단계
핵심 버그: T_TREND=0.4%, T_RANGE_ENTRY=0.4% 하드코딩으로
실제 ma_slope(max ~0.04%)가 절대 도달 불가 → 진입 신호 0건

ThresholdCalibrator는 kline 데이터의 ma_slope 분포에서
적응적 임계값을 계산하여 이 문제를 해결한다.
"""

import pytest
from dataclasses import FrozenInstanceError
from src.application.market_regime import Kline


# ---------------------------------------------------------------------------
# Helper: BTC-like kline 데이터 생성
# ---------------------------------------------------------------------------
def _make_btc_klines(base_price: float = 84000.0, count: int = 100) -> list:
    """
    실제 BTC 15분봉과 유사한 kline 데이터 생성.
    가격 변동 폭: ±0.02~0.05% per candle (일반적 ranging 시장)
    """
    import math
    klines = []
    price = base_price
    for i in range(count):
        # 작은 사인파 + 노이즈로 현실적 가격 변동 시뮬레이션
        delta_pct = 0.0003 * math.sin(i * 0.3) + 0.0001 * ((-1) ** i)
        price = price * (1 + delta_pct)
        high = price * 1.0002
        low = price * 0.9998
        klines.append(Kline(close=price, high=high, low=low))
    return klines


def _make_trending_klines(base_price: float = 84000.0, count: int = 100) -> list:
    """
    강한 상승 추세 kline 데이터 생성.
    매 캔들 +0.05% (15분봉 기준 시간당 +0.2%)
    """
    klines = []
    price = base_price
    for i in range(count):
        price = price * 1.0005
        high = price * 1.0003
        low = price * 0.9997
        klines.append(Kline(close=price, high=high, low=low))
    return klines


# ===========================================================================
# Test 1: calibrate()가 ThresholdConfig를 반환하는지 확인
# ===========================================================================
def test_calibrate_returns_threshold_config():
    """calibrate()는 ThresholdConfig(t_trend, t_range_entry)를 반환해야 한다."""
    from src.application.threshold_calibrator import ThresholdCalibrator, ThresholdConfig

    # Arrange
    calibrator = ThresholdCalibrator(ma_period=20, percentile=85.0)
    klines = _make_btc_klines(count=100)

    # Act
    config = calibrator.calibrate(klines)

    # Assert
    assert isinstance(config, ThresholdConfig)
    assert config.t_trend > 0
    assert config.t_range_entry > 0


# ===========================================================================
# Test 2: 실제 BTC 데이터 패턴에서 t_trend < 0.4% (하드코딩 값보다 낮아야 함)
# ===========================================================================
def test_calibrate_p85_below_hardcoded_0_4():
    """
    실제 BTC ranging 시장의 ma_slope 분포에서 P85는 0.4%보다
    훨씬 작아야 한다. 이것이 핵심 버그의 수정 검증.
    """
    from src.application.threshold_calibrator import ThresholdCalibrator

    # Arrange
    calibrator = ThresholdCalibrator(ma_period=20, percentile=85.0)
    klines = _make_btc_klines(base_price=84000.0, count=100)

    # Act
    config = calibrator.calibrate(klines)

    # Assert — 핵심: t_trend가 하드코딩된 0.4%보다 훨씬 작아야 한다
    assert config.t_trend < 0.4, (
        f"t_trend={config.t_trend}% >= 0.4%: "
        f"하드코딩 임계값과 동일하면 진입 신호 0건 버그가 재현됨"
    )


# ===========================================================================
# Test 3: t_range_entry = t_trend * 0.25
# ===========================================================================
def test_calibrate_t_range_entry_is_quarter_of_t_trend():
    """t_range_entry는 t_trend의 25%여야 한다 (Range 진입 허용 범위 확대)."""
    from src.application.threshold_calibrator import ThresholdCalibrator

    # Arrange
    calibrator = ThresholdCalibrator(ma_period=20, percentile=85.0)
    klines = _make_btc_klines(count=100)

    # Act
    config = calibrator.calibrate(klines)

    # Assert
    expected_range_entry = config.t_trend * 0.25
    assert abs(config.t_range_entry - expected_range_entry) < 1e-10, (
        f"t_range_entry={config.t_range_entry} != t_trend*0.25={expected_range_entry}"
    )


# ===========================================================================
# Test 4: 최솟값 클램프 — t_trend >= 0.005%
# ===========================================================================
def test_calibrate_minimum_clamp():
    """
    완전 횡보 시장(가격 변동 거의 없음)에서도
    t_trend는 최솟값 0.005% 이상이어야 한다.
    """
    from src.application.threshold_calibrator import ThresholdCalibrator

    # Arrange — 거의 변동 없는 flat klines
    flat_klines = [Kline(close=84000.0, high=84000.1, low=83999.9)
                   for _ in range(100)]
    calibrator = ThresholdCalibrator(ma_period=20, percentile=85.0)

    # Act
    config = calibrator.calibrate(flat_klines)

    # Assert — 최솟값 클램프
    assert config.t_trend >= 0.005, (
        f"t_trend={config.t_trend}% < 0.005%: 최솟값 클램프가 작동하지 않음"
    )
    assert config.t_range_entry >= 0.005 * 0.25, (
        f"t_range_entry={config.t_range_entry}% < {0.005 * 0.25}%: "
        f"t_range_entry 최솟값도 보장되어야 함"
    )


# ===========================================================================
# Test 5: kline 부족 시 ValueError
# ===========================================================================
def test_calibrate_insufficient_klines_raises():
    """ma_period + 1개 미만의 kline으로 calibrate하면 ValueError."""
    from src.application.threshold_calibrator import ThresholdCalibrator

    # Arrange
    calibrator = ThresholdCalibrator(ma_period=20, percentile=85.0)
    insufficient_klines = [Kline(close=84000.0) for _ in range(15)]

    # Act & Assert
    with pytest.raises(ValueError, match="[Ii]nsufficient"):
        calibrator.calibrate(insufficient_klines)


# ===========================================================================
# Test 6: generate_signal이 ThresholdConfig를 받아 사용
# ===========================================================================
def test_signal_generator_uses_threshold_config():
    """
    generate_signal에 threshold_config 파라미터를 전달하면
    하드코딩 T_TREND 대신 해당 config의 값을 사용해야 한다.
    """
    from src.application.signal_generator import generate_signal
    from src.application.threshold_calibrator import ThresholdConfig

    # Arrange — 낮은 threshold로 설정
    config = ThresholdConfig(t_trend=0.03, t_range_entry=0.0075)

    # Act — ma_slope=0.04%: 하드코딩 0.4%에는 미달이지만 config 0.03%는 초과
    signal = generate_signal(
        current_price=84000.0,
        last_fill_price=None,
        grid_spacing=100.0,
        qty=1,
        funding_rate=0.0001,
        ma_slope_pct=0.04,
        threshold_config=config,
    )

    # Assert — threshold_config를 사용하므로 trend 진입 신호 발생
    assert signal is not None
    assert signal.side == "Buy"
    assert signal.price == 84000.0


# ===========================================================================
# Test 7: 낮은 threshold로 실제 진입 가능 확인
# ===========================================================================
def test_signal_generator_enters_with_calibrated_low_threshold():
    """
    실제 BTC ma_slope 범위(~0.02-0.04%)에서
    calibrated threshold를 사용하면 Range 진입도 가능해야 한다.
    """
    from src.application.signal_generator import generate_signal
    from src.application.threshold_calibrator import ThresholdConfig

    # Arrange — 실제 calibrate 결과와 유사한 낮은 threshold
    config = ThresholdConfig(t_trend=0.05, t_range_entry=0.0125)

    # Act — Range 진입: ma_slope=0.02% (t_range_entry=0.0125% 초과)
    signal = generate_signal(
        current_price=84000.0,
        last_fill_price=None,
        grid_spacing=100.0,
        qty=1,
        funding_rate=0.0001,
        ma_slope_pct=0.02,
        threshold_config=config,
    )

    # Assert — Range 진입 (약한 방향성 → MA 방향 진입)
    assert signal is not None
    assert signal.side == "Buy"
    assert signal.qty == 1


# ===========================================================================
# Test 8: ThresholdConfig는 불변(frozen dataclass)
# ===========================================================================
def test_threshold_config_immutable():
    """ThresholdConfig는 frozen dataclass이므로 속성 변경 시 에러."""
    from src.application.threshold_calibrator import ThresholdConfig

    # Arrange
    config = ThresholdConfig(t_trend=0.05, t_range_entry=0.0125)

    # Act & Assert — frozen이므로 변경 불가
    with pytest.raises(FrozenInstanceError):
        config.t_trend = 0.1

    # 값 검증
    assert config.t_trend == 0.05
    assert config.t_range_entry == 0.0125

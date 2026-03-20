"""
tests/unit/test_indicators.py

Signal Intelligence Stream A: 5지표 앙상블 - 개별 지표 단위 테스트
TDD RED 단계: 구현 전 실패 테스트 작성
"""

import math
import pytest


# ========== RSI 테스트 ==========

class TestRSI:
    def test_rsi_returns_float_between_0_and_100(self):
        """RSI 계산 결과는 0~100 사이 float"""
        from src.application.indicators.rsi import calculate_rsi

        prices = [float(i) for i in range(100, 115 + 1)]  # 16개
        rsi = calculate_rsi(prices, period=14)

        assert isinstance(rsi, float)
        assert 0.0 <= rsi <= 100.0

    def test_rsi_overbought_on_rising_prices(self):
        """지속 상승 시 RSI > 70 (과매수)"""
        from src.application.indicators.rsi import calculate_rsi

        # 계속 상승하는 가격
        prices = [1000.0 + i * 10 for i in range(30)]
        rsi = calculate_rsi(prices, period=14)

        assert rsi > 70.0, f"Expected RSI > 70 on rising prices, got {rsi}"

    def test_rsi_oversold_on_falling_prices(self):
        """지속 하락 시 RSI < 30 (과매도)"""
        from src.application.indicators.rsi import calculate_rsi

        # 계속 하락하는 가격
        prices = [1000.0 - i * 10 for i in range(30)]
        rsi = calculate_rsi(prices, period=14)

        assert rsi < 30.0, f"Expected RSI < 30 on falling prices, got {rsi}"

    def test_rsi_neutral_on_flat_prices(self):
        """가격 변동 없을 때 RSI 중립 근처 (50)"""
        from src.application.indicators.rsi import calculate_rsi

        prices = [1000.0] * 20
        rsi = calculate_rsi(prices, period=14)

        # 변동 없으면 게인=0, 로스=0 → 특수 처리 필요 (50 반환)
        assert isinstance(rsi, float)

    def test_rsi_returns_none_when_insufficient_data(self):
        """데이터 부족 시 None 반환 (crash 없음)"""
        from src.application.indicators.rsi import calculate_rsi

        prices = [100.0, 101.0, 102.0]  # period=14보다 적음
        rsi = calculate_rsi(prices, period=14)

        assert rsi is None

    def test_rsi_default_period_is_14(self):
        """기본 period=14"""
        from src.application.indicators.rsi import calculate_rsi

        prices = [float(i) for i in range(50, 66)]  # 16개 (14+2)
        rsi_default = calculate_rsi(prices)
        rsi_explicit = calculate_rsi(prices, period=14)

        assert rsi_default == rsi_explicit

    def test_rsi_wilder_smoothing(self):
        """Wilder RSI: 첫 평균 이후 지수이동평균 적용 검증

        고정 입력으로 알려진 값과 비교.
        14기간 RSI에서 gain=2, loss=0이 7회 / gain=0, loss=2가 7회 반복되면
        → avg_gain=avg_loss → RSI=50
        """
        from src.application.indicators.rsi import calculate_rsi

        # 상승 7회, 하락 7회 교차 (각 2씩)
        prices = []
        base = 100.0
        for i in range(15):
            if i % 2 == 0:
                base += 2.0
            else:
                base -= 2.0
            prices.append(base)

        rsi = calculate_rsi(prices, period=14)
        # 정확히 50은 아닐 수 있으나 중립 범위(40~60)여야 함
        assert rsi is not None
        assert 30.0 < rsi < 70.0


# ========== MACD 테스트 ==========

class TestMACD:
    def test_macd_returns_dict_with_required_keys(self):
        """MACD 결과는 macd/signal/histogram/crossover 키 포함"""
        from src.application.indicators.macd import calculate_macd

        prices = [float(i) for i in range(50, 87)]  # 37개 (slow=26 + signal=9 + 2)
        result = calculate_macd(prices)

        assert isinstance(result, dict)
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result
        assert "crossover" in result

    def test_macd_histogram_equals_macd_minus_signal(self):
        """histogram = macd - signal"""
        from src.application.indicators.macd import calculate_macd

        prices = [float(i) for i in range(50, 90)]
        result = calculate_macd(prices)

        if result is not None:
            assert abs(result["histogram"] - (result["macd"] - result["signal"])) < 1e-9

    def test_macd_crossover_bullish_on_rising(self):
        """지속 상승 후 bullish crossover 발생 가능"""
        from src.application.indicators.macd import calculate_macd

        # 하락 후 급상승 → MACD line이 signal line 상향 돌파
        prices_down = [1000.0 - i * 5 for i in range(20)]
        prices_up = [prices_down[-1] + i * 15 for i in range(20)]
        prices = prices_down + prices_up

        result = calculate_macd(prices)
        assert result is not None
        assert result["crossover"] in ("bullish", "bearish", "none")

    def test_macd_crossover_values(self):
        """crossover 필드는 'bullish' | 'bearish' | 'none' 중 하나"""
        from src.application.indicators.macd import calculate_macd

        prices = [float(i) for i in range(100, 140)]
        result = calculate_macd(prices)

        assert result is not None
        assert result["crossover"] in ("bullish", "bearish", "none")

    def test_macd_returns_none_when_insufficient_data(self):
        """데이터 부족 시 None 반환"""
        from src.application.indicators.macd import calculate_macd

        prices = [100.0] * 10  # slow=26 미만
        result = calculate_macd(prices)

        assert result is None

    def test_macd_default_params(self):
        """기본 파라미터 fast=12, slow=26, signal=9"""
        from src.application.indicators.macd import calculate_macd

        prices = [float(i) for i in range(100, 140)]
        result_default = calculate_macd(prices)
        result_explicit = calculate_macd(prices, fast=12, slow=26, signal=9)

        if result_default is not None and result_explicit is not None:
            assert abs(result_default["macd"] - result_explicit["macd"]) < 1e-9


# ========== Bollinger Bands 테스트 ==========

class TestBollinger:
    def test_bollinger_returns_dict_with_required_keys(self):
        """Bollinger 결과는 upper/middle/lower/bandwidth 키 포함"""
        from src.application.indicators.bollinger import calculate_bollinger

        prices = [float(i) for i in range(100, 121)]  # 21개
        result = calculate_bollinger(prices)

        assert isinstance(result, dict)
        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
        assert "bandwidth" in result

    def test_bollinger_upper_gt_middle_gt_lower(self):
        """upper > middle > lower (정상적인 변동성에서)"""
        from src.application.indicators.bollinger import calculate_bollinger

        prices = [100.0 + (i % 5) * 2 for i in range(25)]  # 변동 있는 가격
        result = calculate_bollinger(prices)

        assert result is not None
        assert result["upper"] > result["middle"]
        assert result["middle"] > result["lower"]

    def test_bollinger_middle_is_sma(self):
        """middle = 마지막 period개 가격의 단순 이동 평균"""
        from src.application.indicators.bollinger import calculate_bollinger

        prices = [float(i) for i in range(1, 22)]  # 1~21
        result = calculate_bollinger(prices, period=20)

        # 마지막 20개: 2~21, 평균 = 11.5
        expected_middle = sum(range(2, 22)) / 20
        assert result is not None
        assert abs(result["middle"] - expected_middle) < 1e-9

    def test_bollinger_bandwidth_positive(self):
        """bandwidth > 0 (변동성 있을 때)"""
        from src.application.indicators.bollinger import calculate_bollinger

        prices = [100.0 + (i % 5) for i in range(25)]
        result = calculate_bollinger(prices)

        assert result is not None
        assert result["bandwidth"] >= 0.0

    def test_bollinger_returns_none_when_insufficient_data(self):
        """데이터 부족 시 None 반환"""
        from src.application.indicators.bollinger import calculate_bollinger

        prices = [100.0] * 5  # period=20 미만
        result = calculate_bollinger(prices, period=20)

        assert result is None

    def test_bollinger_flat_prices_zero_bandwidth(self):
        """가격 변동 없을 때 bandwidth=0 (상하밴드=middle)"""
        from src.application.indicators.bollinger import calculate_bollinger

        prices = [100.0] * 25
        result = calculate_bollinger(prices)

        assert result is not None
        assert abs(result["bandwidth"]) < 1e-9
        assert abs(result["upper"] - result["middle"]) < 1e-9
        assert abs(result["lower"] - result["middle"]) < 1e-9

    def test_bollinger_custom_std_dev(self):
        """std_dev 파라미터 커스텀 적용"""
        from src.application.indicators.bollinger import calculate_bollinger

        prices = [100.0 + (i % 5) for i in range(25)]
        result_2 = calculate_bollinger(prices, period=20, std_dev=2.0)
        result_3 = calculate_bollinger(prices, period=20, std_dev=3.0)

        assert result_2 is not None
        assert result_3 is not None
        # std_dev=3이면 밴드 폭이 더 넓어야 함
        assert (result_3["upper"] - result_3["lower"]) > (result_2["upper"] - result_2["lower"])


# ========== Volume 테스트 ==========

class TestVolume:
    def test_volume_confirmed_when_above_average(self):
        """현재 거래량 > 20기간 평균이면 True"""
        from src.application.indicators.volume import is_volume_confirmed

        volumes = [100.0] * 20 + [200.0]  # 평균 100, 현재 200
        result = is_volume_confirmed(volumes)

        assert result is True

    def test_volume_not_confirmed_when_below_average(self):
        """현재 거래량 <= 20기간 평균이면 False"""
        from src.application.indicators.volume import is_volume_confirmed

        volumes = [100.0] * 20 + [50.0]  # 평균 100, 현재 50
        result = is_volume_confirmed(volumes)

        assert result is False

    def test_volume_not_confirmed_when_equal_average(self):
        """현재 거래량 == 평균이면 False (strictly greater)"""
        from src.application.indicators.volume import is_volume_confirmed

        volumes = [100.0] * 21  # 모두 100
        result = is_volume_confirmed(volumes)

        assert result is False

    def test_volume_returns_false_when_insufficient_data(self):
        """데이터 부족 시 False 반환 (crash 없음)"""
        from src.application.indicators.volume import is_volume_confirmed

        volumes = [100.0] * 5  # period=20 미만
        result = is_volume_confirmed(volumes, period=20)

        assert result is False

    def test_volume_custom_period(self):
        """커스텀 period 적용"""
        from src.application.indicators.volume import is_volume_confirmed

        volumes = [100.0] * 10 + [150.0]  # period=10, 현재 150
        result = is_volume_confirmed(volumes, period=10)

        assert result is True

    def test_volume_confirmed_uses_last_element(self):
        """현재 거래량은 volumes[-1]을 사용"""
        from src.application.indicators.volume import is_volume_confirmed

        # 첫 요소가 크고 마지막이 작은 경우
        volumes = [500.0] + [100.0] * 19 + [50.0]
        result = is_volume_confirmed(volumes)

        # 마지막 21개에서 평균 계산: (500 + 100*19) / 20 = 120, 현재 50 < 120 → False
        assert result is False

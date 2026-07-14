"""
tests/unit/test_breakout.py

Wave 4 Stream C: Breakout 지표 단위 테스트
TDD RED → GREEN 순서로 작성.
"""

import pytest


class TestCalculateBreakout:
    def test_long_breakout_when_close_above_highest_high_with_high_volume(self):
        """Close > 최근 20개 high 최댓값 + volume > avg*1.5 → long_breakout=True"""
        from src.application.indicators.breakout import calculate_breakout

        highs = [100.0] * 20
        lows = [90.0] * 20
        prices = [99.0] * 20 + [101.0]  # close가 high 100.0 돌파
        volumes = [100.0] * 20 + [160.0]  # avg=100, 현재=160 > 100*1.5=150

        result = calculate_breakout(prices, highs, lows, volumes)

        assert result["long_breakout"] is True
        assert result["short_breakout"] is False

    def test_short_breakout_when_close_below_lowest_low_with_high_volume(self):
        """Close < 최근 20개 low 최솟값 + volume > avg*1.5 → short_breakout=True"""
        from src.application.indicators.breakout import calculate_breakout

        highs = [100.0] * 20
        lows = [90.0] * 20
        prices = [91.0] * 20 + [89.0]  # close가 low 90.0 하향 돌파
        volumes = [100.0] * 20 + [160.0]  # avg=100, 현재=160 > 150

        result = calculate_breakout(prices, highs, lows, volumes)

        assert result["short_breakout"] is True
        assert result["long_breakout"] is False

    def test_no_breakout_when_volume_insufficient(self):
        """가격은 돌파했으나 volume < avg*1.5 → 거짓 돌파 필터 → 모두 False"""
        from src.application.indicators.breakout import calculate_breakout

        highs = [100.0] * 20
        lows = [90.0] * 20
        prices = [99.0] * 20 + [101.0]  # high 돌파
        volumes = [100.0] * 20 + [120.0]  # avg=100, 현재=120 < 150 → 필터

        result = calculate_breakout(prices, highs, lows, volumes)

        assert result["long_breakout"] is False
        assert result["short_breakout"] is False

    def test_no_breakout_when_price_stays_within_range(self):
        """가격이 레인지 안에 있으면 False"""
        from src.application.indicators.breakout import calculate_breakout

        highs = [100.0] * 20
        lows = [90.0] * 20
        prices = [95.0] * 21  # 레인지 중간
        volumes = [100.0] * 20 + [200.0]

        result = calculate_breakout(prices, highs, lows, volumes)

        assert result["long_breakout"] is False
        assert result["short_breakout"] is False

    def test_returns_zero_scores_when_no_breakout(self):
        """돌파 없으면 long_score=0, short_score=0"""
        from src.application.indicators.breakout import calculate_breakout

        highs = [100.0] * 20
        lows = [90.0] * 20
        prices = [95.0] * 21
        volumes = [100.0] * 21

        result = calculate_breakout(prices, highs, lows, volumes)

        assert result["long_score"] == 0
        assert result["short_score"] == 0

    def test_returns_one_score_on_long_breakout(self):
        """Long breakout 시 long_score=1, short_score=0"""
        from src.application.indicators.breakout import calculate_breakout

        highs = [100.0] * 20
        lows = [90.0] * 20
        prices = [99.0] * 20 + [101.0]
        volumes = [100.0] * 20 + [200.0]

        result = calculate_breakout(prices, highs, lows, volumes)

        assert result["long_score"] == 1
        assert result["short_score"] == 0

    def test_returns_one_score_on_short_breakout(self):
        """Short breakout 시 short_score=1, long_score=0"""
        from src.application.indicators.breakout import calculate_breakout

        highs = [100.0] * 20
        lows = [90.0] * 20
        prices = [91.0] * 20 + [89.0]
        volumes = [100.0] * 20 + [200.0]

        result = calculate_breakout(prices, highs, lows, volumes)

        assert result["short_score"] == 1
        assert result["long_score"] == 0

    def test_graceful_fallback_when_insufficient_data(self):
        """데이터 부족 시 crash 없이 zero 반환"""
        from src.application.indicators.breakout import calculate_breakout

        prices = [100.0] * 5
        highs = [101.0] * 5
        lows = [99.0] * 5
        volumes = [100.0] * 5

        result = calculate_breakout(prices, highs, lows, volumes)

        assert result["long_breakout"] is False
        assert result["short_breakout"] is False
        assert result["long_score"] == 0
        assert result["short_score"] == 0

    def test_graceful_fallback_when_empty_lists(self):
        """빈 리스트 입력 시 crash 없이 zero 반환"""
        from src.application.indicators.breakout import calculate_breakout

        result = calculate_breakout([], [], [], [])

        assert result["long_breakout"] is False
        assert result["short_breakout"] is False

    def test_volume_multiplier_boundary_at_exactly_1_5x(self):
        """volume == avg * 1.5 경계값: strictly greater 아니면 False"""
        from src.application.indicators.breakout import calculate_breakout

        highs = [100.0] * 20
        lows = [90.0] * 20
        prices = [99.0] * 20 + [101.0]
        volumes = [100.0] * 20 + [150.0]  # 정확히 1.5배 → strictly greater 아니면 False

        result = calculate_breakout(prices, highs, lows, volumes)

        # 정확히 1.5배는 필터 통과하지 않음 (strictly greater 요구)
        assert result["long_breakout"] is False

    def test_uses_last_20_candles_for_range(self):
        """최근 20개 캔들만 레인지 계산에 사용"""
        from src.application.indicators.breakout import calculate_breakout

        # 오래된 캔들은 high=200으로 매우 높지만 최근 20개는 100
        old_highs = [200.0] * 10
        recent_highs = [100.0] * 20
        highs = old_highs + recent_highs

        old_lows = [50.0] * 10
        recent_lows = [90.0] * 20
        lows = old_lows + recent_lows

        # 30개 이상의 가격 데이터
        prices = [95.0] * 29 + [101.0]  # 최근 20개 high(100) 돌파
        volumes = [100.0] * 29 + [200.0]

        result = calculate_breakout(prices, highs, lows, volumes)

        # 최근 20개 기준으로는 101 > 100 → long breakout
        assert result["long_breakout"] is True

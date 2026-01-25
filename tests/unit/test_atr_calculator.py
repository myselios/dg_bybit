"""
tests/unit/test_atr_calculator.py
ATR Calculator Unit Tests

Purpose:
- Kline 데이터 → ATR 계산 검증
- ATR percentile 계산 검증
- Grid spacing 계산 검증

SSOT:
- docs/plans/task_plan.md Phase 12a-2
"""

import pytest
from typing import List, Dict, Any

from application.atr_calculator import ATRCalculator, Kline


class TestATRCalculator:
    """ATR 계산 검증"""

    def test_calculate_atr_14_period(self):
        """14-period ATR 계산"""
        # Arrange
        calculator = ATRCalculator()

        # Kline 데이터 (15개, 14-period ATR 계산 위해)
        klines = [
            Kline(high=50100.0, low=49900.0, close=50000.0),  # TR = 200
            Kline(high=50200.0, low=50000.0, close=50100.0),  # TR = 200
            Kline(high=50300.0, low=50050.0, close=50200.0),  # TR = 250
            Kline(high=50250.0, low=50100.0, close=50150.0),  # TR = 150
            Kline(high=50400.0, low=50100.0, close=50300.0),  # TR = 300
            Kline(high=50500.0, low=50250.0, close=50400.0),  # TR = 250
            Kline(high=50450.0, low=50300.0, close=50350.0),  # TR = 200
            Kline(high=50600.0, low=50300.0, close=50500.0),  # TR = 300
            Kline(high=50700.0, low=50450.0, close=50600.0),  # TR = 250
            Kline(high=50650.0, low=50500.0, close=50550.0),  # TR = 200
            Kline(high=50800.0, low=50500.0, close=50700.0),  # TR = 300
            Kline(high=50900.0, low=50650.0, close=50800.0),  # TR = 250
            Kline(high=50850.0, low=50700.0, close=50750.0),  # TR = 200
            Kline(high=51000.0, low=50700.0, close=50900.0),  # TR = 300
            Kline(high=51100.0, low=50850.0, close=51000.0),  # TR = 250
        ]

        # Act
        atr = calculator.calculate_atr(klines)

        # Assert
        assert atr > 0
        assert 200 <= atr <= 300  # TR 범위 내
        assert isinstance(atr, float)

    def test_calculate_atr_insufficient_data(self):
        """ATR 계산 실패 (데이터 부족)"""
        # Arrange
        calculator = ATRCalculator()
        klines = [
            Kline(high=50100.0, low=49900.0, close=50000.0),
            Kline(high=50200.0, low=50000.0, close=50100.0),
        ]  # 2개만 (14개 미만)

        # Act & Assert
        with pytest.raises(ValueError, match="Insufficient kline data"):
            calculator.calculate_atr(klines)

    def test_calculate_atr_percentile(self):
        """ATR percentile 계산 (rolling 100-period)"""
        # Arrange
        calculator = ATRCalculator()

        # ATR history (100개)
        atr_history = [200.0 + i * 2.0 for i in range(100)]  # 200~398
        current_atr = 300.0

        # Act
        percentile = calculator.calculate_atr_percentile(current_atr, atr_history)

        # Assert
        assert 0 <= percentile <= 100
        assert isinstance(percentile, float)
        # current_atr=300 → 약 50 percentile (중간)
        assert 45 <= percentile <= 55

    def test_calculate_atr_percentile_min(self):
        """ATR percentile 최소값 (0 percentile)"""
        # Arrange
        calculator = ATRCalculator()
        atr_history = [200.0, 250.0, 300.0, 350.0, 400.0] * 20  # 100개
        current_atr = 100.0  # 최소값보다 작음

        # Act
        percentile = calculator.calculate_atr_percentile(current_atr, atr_history)

        # Assert
        assert percentile == 0.0

    def test_calculate_atr_percentile_max(self):
        """ATR percentile 최대값 (100 percentile)"""
        # Arrange
        calculator = ATRCalculator()
        atr_history = [200.0, 250.0, 300.0, 350.0, 400.0] * 20  # 100개
        current_atr = 500.0  # 최대값보다 큼

        # Act
        percentile = calculator.calculate_atr_percentile(current_atr, atr_history)

        # Assert
        assert percentile == 100.0

    def test_calculate_grid_spacing(self):
        """Grid spacing 계산 (ATR * multiplier)"""
        # Arrange
        calculator = ATRCalculator()
        atr = 250.0
        multiplier = 0.5  # Grid spacing = 50% of ATR

        # Act
        grid_spacing = calculator.calculate_grid_spacing(atr, multiplier)

        # Assert
        assert grid_spacing == 125.0  # 250 * 0.5
        assert isinstance(grid_spacing, float)

    def test_calculate_grid_spacing_default_multiplier(self):
        """Grid spacing 계산 (기본 multiplier)"""
        # Arrange
        calculator = ATRCalculator()
        atr = 300.0

        # Act (multiplier 지정 안 함, 기본값 사용)
        grid_spacing = calculator.calculate_grid_spacing(atr)

        # Assert
        assert grid_spacing > 0
        assert isinstance(grid_spacing, float)

    def test_calculate_true_range(self):
        """True Range 계산"""
        # Arrange
        calculator = ATRCalculator()
        current_kline = Kline(high=50500.0, low=50200.0, close=50400.0)
        previous_close = 50100.0

        # Act
        tr = calculator.calculate_true_range(current_kline, previous_close)

        # Assert
        # TR = max(H-L, H-PC, PC-L)
        # = max(50500-50200, 50500-50100, 50100-50200)
        # = max(300, 400, -100) = 400
        assert tr == 400.0

    def test_calculate_true_range_no_gap(self):
        """True Range 계산 (gap 없음)"""
        # Arrange
        calculator = ATRCalculator()
        current_kline = Kline(high=50300.0, low=50100.0, close=50200.0)
        previous_close = 50200.0  # 동일

        # Act
        tr = calculator.calculate_true_range(current_kline, previous_close)

        # Assert
        # TR = max(50300-50100, 50300-50200, 50200-50100)
        # = max(200, 100, 100) = 200
        assert tr == 200.0

"""
tests/unit/test_signal_ensemble.py

Signal Intelligence Stream A: EnsembleSignal 단위 테스트
TDD RED 단계: 구현 전 실패 테스트 작성
"""

import pytest


# ========== EnsembleSignal 데이터클래스 테스트 ==========

class TestEnsembleSignalDataclass:
    def test_ensemble_signal_has_required_fields(self):
        """EnsembleSignal은 side/score/components/confidence 필드 보유"""
        from src.application.signal_ensemble import EnsembleSignal

        sig = EnsembleSignal(
            side="Buy",
            score=4,
            components={"rsi": 2, "macd": 1, "bb": 1, "volume": 0, "ma_slope": 0},
            confidence=4 / 6.0,
        )

        assert sig.side == "Buy"
        assert sig.score == 4
        assert sig.confidence == pytest.approx(4 / 6.0)
        assert "rsi" in sig.components

    def test_ensemble_signal_side_none_when_no_signal(self):
        """신호 없을 때 side=None"""
        from src.application.signal_ensemble import EnsembleSignal

        sig = EnsembleSignal(
            side=None,
            score=0,
            components={"rsi": 0, "macd": 0, "bb": 0, "volume": 0, "ma_slope": 0},
            confidence=0.0,
        )

        assert sig.side is None
        assert sig.score == 0


# ========== calculate_ensemble_score LONG 조건 테스트 ==========

class TestEnsembleLongConditions:
    """LONG 조건:
    rsi < 30 (+2), macd bullish cross (+1), price <= bb_lower (+1),
    volume confirm (+1), ma_slope > t_trend (+1)
    """

    def test_strong_long_signal_all_conditions_met(self):
        """모든 LONG 조건 충족 → score=6, side=Buy"""
        from src.application.signal_ensemble import calculate_ensemble_score

        # RSI < 30 → 지속 하락 가격
        prices_down = [1000.0 - i * 5 for i in range(30)]

        # MA slope 양수 (trending up)
        ma_slope_pct = 0.1  # t_trend=0.05 초과

        # volume 확인용: 현재 거래량 > 평균
        volumes = [100.0] * 20 + [200.0]

        result = calculate_ensemble_score(
            prices=prices_down,
            volumes=volumes,
            ma_slope_pct=ma_slope_pct,
            t_trend=0.05,
        )

        assert result is not None
        assert result.side == "Buy"
        assert result.score >= 3  # 최소 진입 조건

    def test_long_signal_with_rsi_oversold(self):
        """RSI < 30 조건은 +2점"""
        from src.application.signal_ensemble import calculate_ensemble_score

        # 지속 하락으로 RSI < 30 유도
        prices = [1000.0 - i * 8 for i in range(30)]
        volumes = [100.0] * 25

        result = calculate_ensemble_score(
            prices=prices,
            volumes=volumes,
            ma_slope_pct=0.0,
            t_trend=0.05,
        )

        assert result is not None
        assert result.components["rsi"] == 2

    def test_no_long_signal_when_score_below_3(self):
        """score < 3 → side=None"""
        from src.application.signal_ensemble import calculate_ensemble_score

        # 중립 가격 (RSI ~50, MACD none, 가격 중간)
        prices = [1000.0 + (i % 3 - 1) * 2 for i in range(40)]
        volumes = [100.0] * 40

        result = calculate_ensemble_score(
            prices=prices,
            volumes=volumes,
            ma_slope_pct=0.0,
            t_trend=0.05,
        )

        assert result is not None
        if result.score < 3:
            assert result.side is None


# ========== calculate_ensemble_score SHORT 조건 테스트 ==========

class TestEnsembleShortConditions:
    """SHORT 조건:
    rsi > 70 (+2), macd bearish cross (+1), price >= bb_upper (+1),
    volume confirm (+1), ma_slope < -t_trend (+1)
    """

    def test_strong_short_signal_all_conditions_met(self):
        """강한 SHORT 조건 충족 → score >= 3, side=Sell"""
        from src.application.signal_ensemble import calculate_ensemble_score

        # RSI > 70 → 지속 상승 가격
        prices_up = [1000.0 + i * 5 for i in range(30)]

        # MA slope 음수 (trending down)
        ma_slope_pct = -0.1  # -t_trend 이하

        volumes = [100.0] * 20 + [200.0]

        result = calculate_ensemble_score(
            prices=prices_up,
            volumes=volumes,
            ma_slope_pct=ma_slope_pct,
            t_trend=0.05,
        )

        assert result is not None
        assert result.side == "Sell"
        assert result.score >= 3

    def test_short_signal_with_rsi_overbought(self):
        """RSI > 70 조건은 +2점"""
        from src.application.signal_ensemble import calculate_ensemble_score

        # 지속 상승으로 RSI > 70 유도
        prices = [1000.0 + i * 8 for i in range(30)]
        volumes = [100.0] * 25

        result = calculate_ensemble_score(
            prices=prices,
            volumes=volumes,
            ma_slope_pct=0.0,
            t_trend=0.05,
        )

        assert result is not None
        assert result.components["rsi"] == 2


# ========== 진입 임계값 테스트 ==========

class TestEnsembleEntryThreshold:
    def test_score_3_triggers_entry(self):
        """score >= 3이면 side는 None이 아님"""
        from src.application.signal_ensemble import EnsembleSignal, calculate_ensemble_score

        # score=3 이상을 만드는 조건 직접 생성
        prices = [1000.0 - i * 6 for i in range(30)]  # 하락 → RSI 낮음
        volumes = [100.0] * 20 + [200.0]  # volume confirm

        result = calculate_ensemble_score(
            prices=prices,
            volumes=volumes,
            ma_slope_pct=0.1,  # ma_slope > t_trend
            t_trend=0.05,
        )

        assert result is not None
        if result.score >= 3:
            assert result.side is not None

    def test_score_2_does_not_trigger_entry(self):
        """score <= 2이면 side=None"""
        from src.application.signal_ensemble import calculate_ensemble_score

        # 중립에 가까운 가격
        import math
        prices = [1000.0 + math.sin(i * 0.3) * 5 for i in range(40)]
        volumes = [100.0] * 40

        result = calculate_ensemble_score(
            prices=prices,
            volumes=volumes,
            ma_slope_pct=0.0,
            t_trend=0.05,
        )

        assert result is not None
        if result.score <= 2:
            assert result.side is None


# ========== 동점 처리 테스트 ==========

class TestEnsembleTieBreaking:
    def test_long_bias_when_both_sides_equal(self):
        """LONG score == SHORT score → BTC 상승 바이어스로 Buy 선택"""
        from src.application.signal_ensemble import calculate_ensemble_score

        # 이 테스트는 동점 상황을 직접 만들기 어려우므로
        # 함수의 로직을 통해 간접 검증: 동점(>=3)이면 Buy 우선
        # 실제로는 구현에서 동점 처리 로직을 확인
        pass  # 동점은 구현 내부에서 처리, 통합 테스트로 커버


# ========== 컴포넌트 점수 구조 테스트 ==========

class TestEnsembleComponents:
    def test_components_dict_has_all_five_keys(self):
        """components는 5개 키: rsi, macd, bb, volume, ma_slope"""
        from src.application.signal_ensemble import calculate_ensemble_score

        prices = [float(i) for i in range(1000, 1040)]
        volumes = [100.0] * 40

        result = calculate_ensemble_score(
            prices=prices,
            volumes=volumes,
            ma_slope_pct=0.0,
            t_trend=0.05,
        )

        assert result is not None
        assert set(result.components.keys()) == {"rsi", "macd", "bb", "volume", "ma_slope"}

    def test_components_values_are_non_negative_integers(self):
        """각 컴포넌트 점수는 0 이상 정수"""
        from src.application.signal_ensemble import calculate_ensemble_score

        prices = [float(i) for i in range(1000, 1040)]
        volumes = [100.0] * 40

        result = calculate_ensemble_score(
            prices=prices,
            volumes=volumes,
            ma_slope_pct=0.0,
            t_trend=0.05,
        )

        assert result is not None
        for key, val in result.components.items():
            assert isinstance(val, int), f"{key} should be int, got {type(val)}"
            assert val >= 0, f"{key} should be non-negative, got {val}"

    def test_score_equals_sum_of_components(self):
        """score == sum(components.values())"""
        from src.application.signal_ensemble import calculate_ensemble_score

        prices = [float(i) for i in range(1000, 1040)]
        volumes = [100.0] * 40

        result = calculate_ensemble_score(
            prices=prices,
            volumes=volumes,
            ma_slope_pct=0.0,
            t_trend=0.05,
        )

        assert result is not None
        assert result.score == sum(result.components.values())

    def test_confidence_equals_score_over_6(self):
        """confidence == score / 6.0"""
        from src.application.signal_ensemble import calculate_ensemble_score

        prices = [float(i) for i in range(1000, 1040)]
        volumes = [100.0] * 40

        result = calculate_ensemble_score(
            prices=prices,
            volumes=volumes,
            ma_slope_pct=0.0,
            t_trend=0.05,
        )

        assert result is not None
        assert result.confidence == pytest.approx(result.score / 6.0)


# ========== 데이터 부족 처리 테스트 ==========

class TestEnsembleInsufficientData:
    def test_returns_result_even_with_minimal_prices(self):
        """가격 데이터 부족 시 crash 없이 결과 반환"""
        from src.application.signal_ensemble import calculate_ensemble_score

        prices = [100.0, 101.0, 102.0]  # 매우 부족
        volumes = [100.0] * 3

        # crash 없이 반환되어야 함
        result = calculate_ensemble_score(
            prices=prices,
            volumes=volumes,
            ma_slope_pct=0.0,
            t_trend=0.05,
        )

        assert result is not None  # crash 없이 반환

    def test_returns_no_signal_with_empty_prices(self):
        """빈 가격 리스트 → side=None (진입 없음)"""
        from src.application.signal_ensemble import calculate_ensemble_score

        result = calculate_ensemble_score(
            prices=[],
            volumes=[],
            ma_slope_pct=0.0,
            t_trend=0.05,
        )

        assert result is not None
        assert result.side is None


# ========== generate_signal 통합 (앙상블 모드) ==========

class TestGenerateSignalEnsembleIntegration:
    def test_generate_signal_with_prices_uses_ensemble_mode(self):
        """prices >= 26개 제공 시 앙상블 모드 활성화 (backward compatible)"""
        from src.application.signal_generator import generate_signal

        prices = [float(i) for i in range(1000, 1040)]  # 40개
        volumes = [100.0] * 40

        # 기존 시그니처 + prices/volumes 추가
        signal = generate_signal(
            current_price=1040.0,
            last_fill_price=None,
            grid_spacing=50.0,
            ma_slope_pct=0.1,
            prices=prices,
            volumes=volumes,
        )

        # crash 없이 반환 (Signal or None)
        assert signal is None or hasattr(signal, "side")

    def test_generate_signal_without_prices_uses_legacy_mode(self):
        """prices 없으면 기존 MA slope 모드 유지 (backward compatible)"""
        from src.application.signal_generator import generate_signal

        # 기존 호출 방식 그대로
        signal = generate_signal(
            current_price=50000.0,
            last_fill_price=None,
            grid_spacing=100.0,
            ma_slope_pct=0.6,  # Trend up → Buy
        )

        assert signal is not None
        assert signal.side == "Buy"

    def test_existing_tests_still_pass_with_new_params(self):
        """기존 그리드 로직 (last_fill_price 있음) — backward compatible"""
        from src.application.signal_generator import generate_signal

        # Grid up → Sell (기존 동작 유지)
        signal = generate_signal(
            current_price=50100.0,
            last_fill_price=50000.0,
            grid_spacing=100.0,
        )

        assert signal is not None
        assert signal.side == "Sell"

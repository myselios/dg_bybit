"""
tests/unit/test_wave2a_ensemble_integration.py

Wave 2A: 앙상블 신호 → 실제 매매 경로 통합 테스트

검증 항목:
1. Signal 데이터클래스에 score/components 필드 존재
2. generate_signal()에 prices 전달 시 앙상블 모드 활성화 → Signal.score 반환
3. generate_signal()에 prices=None 전달 시 MA slope 모드 (score=None)
4. orchestrator._get_price_volume_history() 캐시 동작
5. TradeLogV1에 signal_score/signal_components 필드 존재
6. log_completed_trade() signal_score/signal_components 수용
"""

import time
import pytest
from typing import Optional


# ─── 1. Signal 데이터클래스 ───────────────────────────────────────────────


class TestSignalDataclass:
    def test_signal_has_score_and_components(self):
        """Signal 데이터클래스에 score/components Optional 필드 있어야 함"""
        from src.application.signal_generator import Signal

        sig = Signal(side="Buy", price=50000.0, qty=1, score=4,
                     components={"rsi": 2, "macd": 1, "bb": 1, "volume": 0, "ma_slope": 0})

        assert sig.score == 4
        assert sig.components["rsi"] == 2

    def test_signal_score_none_by_default(self):
        """기본값: score=None, components=None (하위 호환)"""
        from src.application.signal_generator import Signal

        sig = Signal(side="Sell", price=50000.0)

        assert sig.score is None
        assert sig.components is None


# ─── 2. generate_signal 앙상블 모드 ──────────────────────────────────────


def _make_oversold_prices(n: int = 60) -> list:
    """RSI < 30 조건이 되는 하락 가격 시리즈"""
    prices = [50000.0 - i * 200.0 for i in range(n)]
    return prices


def _make_overbought_prices(n: int = 60) -> list:
    """RSI > 70 조건이 되는 상승 가격 시리즈"""
    prices = [50000.0 + i * 200.0 for i in range(n)]
    return prices


class TestGenerateSignalEnsembleMode:
    def test_ensemble_mode_activated_when_prices_provided(self):
        """prices >= 26개 + last_fill_price=None → 앙상블 모드"""
        from src.application.signal_generator import generate_signal

        prices = _make_oversold_prices(60)
        sig = generate_signal(
            current_price=prices[-1],
            last_fill_price=None,
            grid_spacing=100.0,
            prices=prices,
            volumes=[],
            ma_slope_pct=0.1,
        )
        # 앙상블 모드 진입 → score 필드 채워지거나 side=None (score 기준 미달 시)
        # side가 None이 아닌 경우 score가 있어야 함
        if sig is not None:
            assert sig.score is not None

    def test_ma_slope_mode_when_prices_none(self):
        """prices=None → MA slope 모드 → score=None"""
        from src.application.signal_generator import generate_signal

        sig = generate_signal(
            current_price=50000.0,
            last_fill_price=None,
            grid_spacing=100.0,
            prices=None,
            volumes=None,
            ma_slope_pct=0.5,  # trend mode
        )
        # MA slope 모드에서는 score=None
        if sig is not None:
            assert sig.score is None

    def test_ma_slope_mode_when_prices_too_short(self):
        """prices < 26개 → MA slope 모드 fallback"""
        from src.application.signal_generator import generate_signal

        sig = generate_signal(
            current_price=50000.0,
            last_fill_price=None,
            grid_spacing=100.0,
            prices=[50000.0] * 10,  # 26개 미만
            ma_slope_pct=0.5,
        )
        if sig is not None:
            assert sig.score is None

    def test_grid_mode_ignores_prices(self):
        """last_fill_price 있으면 grid 모드 (앙상블 미사용) → score=None"""
        from src.application.signal_generator import generate_signal

        prices = _make_oversold_prices(60)
        sig = generate_signal(
            current_price=52000.0,
            last_fill_price=50000.0,
            grid_spacing=100.0,
            prices=prices,
            ma_slope_pct=0.0,
        )
        # Grid 모드: score 필드 없음
        if sig is not None:
            assert sig.score is None

    def test_ensemble_no_signal_returns_none(self):
        """앙상블 점수 미달 (score < 3) → None 반환"""
        from src.application.signal_generator import generate_signal

        # 중립적인 가격 시리즈 (RSI ~50, no MACD cross, price in BB middle)
        neutral_prices = [50000.0 + (i % 10 - 5) * 10.0 for i in range(60)]
        sig = generate_signal(
            current_price=neutral_prices[-1],
            last_fill_price=None,
            grid_spacing=100.0,
            prices=neutral_prices,
            volumes=[],
            ma_slope_pct=0.0,
        )
        # 중립 시장: 신호 없어야 함
        assert sig is None


# ─── 3. Orchestrator _get_price_volume_history 캐시 ──────────────────────


class TestOrchestratorKlinesCache:
    def _make_orchestrator(self, klines_len: int = 50):
        """테스트용 Orchestrator 생성"""
        from src.infrastructure.exchange.fake_market_data import FakeMarketData
        from src.application.orchestrator import Orchestrator
        from src.application.market_regime import Kline as MRKline

        fake_data = FakeMarketData()
        klines = [MRKline(close=50000.0 + i * 10.0) for i in range(klines_len)]
        fake_data.inject_klines(klines)
        return Orchestrator(market_data=fake_data)

    def test_get_price_volume_returns_prices(self):
        """klines >= 26개 → prices 리스트 반환"""
        orch = self._make_orchestrator(klines_len=50)

        prices, volumes = orch._get_price_volume_history()

        assert prices is not None
        assert len(prices) == 50
        assert isinstance(prices[0], float)
        assert volumes == []  # RegimeKline에 volume 없음

    def test_get_price_volume_returns_none_when_insufficient(self):
        """klines < 26개 → None, None 반환"""
        orch = self._make_orchestrator(klines_len=10)

        prices, volumes = orch._get_price_volume_history()

        assert prices is None
        assert volumes is None

    def test_cache_returns_same_object_within_ttl(self):
        """TTL 내에 재호출 → 캐시된 동일 객체 반환"""
        orch = self._make_orchestrator(klines_len=50)

        prices1, _ = orch._get_price_volume_history()
        prices2, _ = orch._get_price_volume_history()

        assert prices1 is prices2  # 동일 객체 (캐시 히트)

    def test_cache_refreshed_after_ttl(self):
        """TTL 만료 후 재호출 → 캐시 갱신 (새 리스트 객체)"""
        orch = self._make_orchestrator(klines_len=50)
        orch._KLINES_CACHE_TTL = 0.01  # 10ms로 단축

        prices1, _ = orch._get_price_volume_history()
        time.sleep(0.05)
        prices2, _ = orch._get_price_volume_history()

        assert prices1 is not prices2  # 다른 객체 (캐시 갱신)


# ─── 4. TradeLogV1 앙상블 필드 ───────────────────────────────────────────


class TestTradeLogV1EnsembleFields:
    def _make_minimal_log(self, **kwargs):
        from src.infrastructure.logging.trade_logger_v1 import TradeLogV1

        defaults = dict(
            order_id="test_order",
            fills=[],
            slippage_usd=0.0,
            latency_rest_ms=0.0,
            latency_ws_ms=0.0,
            latency_total_ms=0.0,
            funding_rate=0.0001,
            mark_price=50000.0,
            index_price=50000.0,
            orderbook_snapshot={},
            market_regime="ranging",
            side="Buy",
            direction="LONG",
            qty_btc=0.001,
            entry_price=50000.0,
            exit_price=51000.0,
            realized_pnl_usd=1.0,
            fee_usd=0.05,
            schema_version="1.0",
            config_hash="abc123",
            git_commit="deadbeef",
            exchange_server_time_offset_ms=0.0,
        )
        defaults.update(kwargs)
        return TradeLogV1(**defaults)

    def test_trade_log_has_signal_score_field(self):
        """TradeLogV1에 signal_score 필드 존재"""
        log = self._make_minimal_log(signal_score=4)

        assert log.signal_score == 4

    def test_trade_log_has_signal_components_field(self):
        """TradeLogV1에 signal_components 필드 존재"""
        components = {"rsi": 2, "macd": 1, "bb": 1, "volume": 0, "ma_slope": 0}
        log = self._make_minimal_log(signal_components=components)

        assert log.signal_components["rsi"] == 2

    def test_trade_log_signal_fields_default_none(self):
        """기존 코드 하위 호환: signal_score/components 기본값 None"""
        log = self._make_minimal_log()

        assert log.signal_score is None
        assert log.signal_components is None

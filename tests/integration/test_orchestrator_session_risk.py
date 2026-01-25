"""
tests/integration/test_orchestrator_session_risk.py
Integration tests for Orchestrator + Session Risk Policy

Purpose:
- Session Risk Policy가 Orchestrator에서 정상 작동하는지 검증
- Daily/Weekly Loss Cap, Loss Streak Kill, Fee/Slippage Anomaly 통합 테스트

SSOT:
- task_plan.md Phase 9c: Orchestrator Integration
- FLOW.md Section 2: Tick Ordering (Emergency-first)
- session_risk.py: Session Risk Policy 4개

Test Coverage:
1. daily_loss_cap_triggers_halt (Daily loss cap → HALT)
2. weekly_loss_cap_triggers_cooldown (Weekly loss cap → COOLDOWN)
3. loss_streak_3_triggers_halt (3연패 → HALT)
4. fee_anomaly_triggers_halt (Fee spike 2회 연속 → HALT)
5. slippage_anomaly_triggers_halt (Slippage spike 3회/10분 → HALT)
"""

import time
from typing import Optional, List, Dict, Any
from application.orchestrator import Orchestrator
from domain.state import State
from infrastructure.exchange.market_data_interface import MarketDataInterface


class FakeMarketDataWithSessionRisk(MarketDataInterface):
    """
    Session Risk 테스트용 Fake Market Data

    daily_pnl, weekly_pnl, loss_streak 등을 설정할 수 있음
    """

    def __init__(self):
        self.equity_btc = 0.01
        self.btc_mark_price_usd = 100000.0
        self.ws_degraded = False
        self.degraded_start_time = None

        # Session Risk 관련
        self.daily_realized_pnl_usd = 0.0
        self.weekly_realized_pnl_usd = 0.0
        self.loss_streak_count = 0
        self.fee_ratio_history = []
        self.slippage_history = []

        # Phase 9d: Slippage anomaly test용 timestamp 설정
        self.current_timestamp = time.time()  # Default: 현재 시각

    def get_equity_btc(self) -> float:
        return self.equity_btc

    def get_equity_usdt(self) -> float:
        """계정 Equity (USDT) — Linear USDT-Margined"""
        # Linear USDT: equity_usdt = equity_btc * mark_price (근사)
        return self.equity_btc * self.btc_mark_price_usd

    def get_btc_mark_price_usd(self) -> float:
        return self.btc_mark_price_usd

    def is_ws_degraded(self) -> bool:
        return self.ws_degraded

    def is_degraded_timeout(self) -> bool:
        # 60초 경과 여부 (simplified)
        if self.degraded_start_time is None:
            return False
        return (self.degraded_start_time > 60.0)

    # MarketDataInterface Protocol 필수 메서드
    def get_mark_price(self) -> float:
        return self.btc_mark_price_usd

    def get_rest_latency_p95_1m(self) -> float:
        return 0.15  # Safe default

    def get_ws_last_heartbeat_ts(self) -> float:
        return time.time()

    def get_ws_event_drop_count(self) -> int:
        return 0

    def get_timestamp(self) -> float:
        return self.current_timestamp

    # Session Risk Protocol 메서드
    def get_daily_realized_pnl_usd(self) -> Optional[float]:
        return self.daily_realized_pnl_usd

    def get_weekly_realized_pnl_usd(self) -> Optional[float]:
        return self.weekly_realized_pnl_usd

    def get_loss_streak_count(self) -> Optional[int]:
        return self.loss_streak_count

    def get_fee_ratio_history(self) -> Optional[List[float]]:
        return self.fee_ratio_history if self.fee_ratio_history else None

    def get_slippage_history(self) -> Optional[List[Dict[str, Any]]]:
        return self.slippage_history if self.slippage_history else None

    def get_position(self) -> Dict[str, Any]:
        """현재 Position 정보 (Default: 포지션 없음)"""
        return {"size": "0", "side": "None", "avgPrice": "0"}


def test_daily_loss_cap_triggers_halt():
    """
    시나리오: Daily loss cap 초과 → HALT

    검증:
    - equity_usd = $1000, daily_pnl = -$60 (-6%)
    - daily_loss_cap = 5% → 초과
    - Orchestrator.run_tick() → state = HALT
    - halt_reason = "daily_loss_cap_exceeded"
    """
    # Given: equity $1000, daily_pnl = -$60 (-6%), cap = 5%
    market_data = FakeMarketDataWithSessionRisk()
    market_data.equity_btc = 0.01  # 0.01 BTC
    market_data.btc_mark_price_usd = 100000.0  # $1000 equity
    market_data.daily_realized_pnl_usd = -60.0  # -6% equity

    orchestrator = Orchestrator(market_data)
    orchestrator.daily_loss_cap_pct = 5.0  # 5% cap

    # When: run_tick()
    result = orchestrator.run_tick()

    # Then: HALT + halt_reason
    assert result.state == State.HALT
    assert result.halt_reason == "daily_loss_cap_exceeded"
    assert "emergency" in result.execution_order


def test_weekly_loss_cap_triggers_cooldown():
    """
    시나리오: Weekly loss cap 초과 → COOLDOWN

    검증:
    - equity_usd = $1000, weekly_pnl = -$150 (-15%)
    - weekly_loss_cap = 12.5% → 초과
    - Orchestrator.run_tick() → state = HALT
    - halt_reason = "weekly_loss_cap_exceeded"
    """
    # Given: equity $1000, weekly_pnl = -$150 (-15%), cap = 12.5%
    market_data = FakeMarketDataWithSessionRisk()
    market_data.equity_btc = 0.01  # 0.01 BTC
    market_data.btc_mark_price_usd = 100000.0  # $1000 equity
    market_data.weekly_realized_pnl_usd = -150.0  # -15% equity

    orchestrator = Orchestrator(market_data)
    orchestrator.weekly_loss_cap_pct = 12.5  # 12.5% cap

    # When: run_tick()
    result = orchestrator.run_tick()

    # Then: HALT + halt_reason
    assert result.state == State.HALT
    assert result.halt_reason == "weekly_loss_cap_exceeded"
    assert "emergency" in result.execution_order


def test_loss_streak_3_triggers_halt():
    """
    시나리오: Loss streak 3연패 → HALT

    검증:
    - loss_streak_count = 3
    - Orchestrator.run_tick() → state = HALT
    - halt_reason = "loss_streak_3_halt"
    """
    # Given: loss_streak_count = 3
    market_data = FakeMarketDataWithSessionRisk()
    market_data.equity_btc = 0.01
    market_data.loss_streak_count = 3

    orchestrator = Orchestrator(market_data)

    # When: run_tick()
    result = orchestrator.run_tick()

    # Then: HALT + halt_reason
    assert result.state == State.HALT
    assert result.halt_reason == "loss_streak_3_halt"
    assert "emergency" in result.execution_order


def test_fee_anomaly_triggers_halt():
    """
    시나리오: Fee spike 2회 연속 → HALT

    검증:
    - fee_ratio_history = [1.6, 1.7] (threshold 1.5 초과)
    - Orchestrator.run_tick() → state = HALT
    - halt_reason = "fee_spike_consecutive"
    """
    # Given: fee_ratio_history = [1.6, 1.7], threshold = 1.5
    market_data = FakeMarketDataWithSessionRisk()
    market_data.equity_btc = 0.01
    market_data.fee_ratio_history = [1.6, 1.7]

    orchestrator = Orchestrator(market_data)
    orchestrator.fee_spike_threshold = 1.5

    # When: run_tick()
    result = orchestrator.run_tick()

    # Then: HALT + halt_reason
    assert result.state == State.HALT
    assert result.halt_reason == "fee_spike_consecutive"
    assert "emergency" in result.execution_order


def test_slippage_anomaly_triggers_halt():
    """
    시나리오: Slippage spike 3회/10분 → HALT

    검증:
    - slippage_history = [{"slippage_usd": -2.1, "timestamp": T}, ...]
    - 3회/10분 window 내 spike → HALT
    - halt_reason = "slippage_spike_3_times"
    """
    # Given: slippage spike 3회, 10분 내
    market_data = FakeMarketDataWithSessionRisk()
    market_data.equity_btc = 0.01
    market_data.slippage_history = [
        {"slippage_usd": -2.1, "timestamp": 1737600000.0},
        {"slippage_usd": -2.5, "timestamp": 1737600200.0},  # 3분 20초 후
        {"slippage_usd": -3.0, "timestamp": 1737600400.0},  # 6분 40초 후
    ]
    # Phase 9d: market_data.current_timestamp 설정 (orchestrator가 get_timestamp()로 가져감)
    market_data.current_timestamp = 1737600500.0  # 최근 spike 이후 1분 40초

    orchestrator = Orchestrator(market_data)
    orchestrator.slippage_threshold_usd = 2.0
    orchestrator.slippage_window_seconds = 600.0  # 10분

    # When: run_tick() (orchestrator가 current_timestamp를 market_data에서 가져옴)
    result = orchestrator.run_tick()

    # Then: HALT + halt_reason
    assert result.state == State.HALT
    assert result.halt_reason == "slippage_spike_3_times"
    assert "emergency" in result.execution_order

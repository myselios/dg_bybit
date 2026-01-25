"""
tests/unit/test_orchestrator_position_recovery.py
Orchestrator Position Recovery — Startup 시 기존 포지션 감지

목적:
- Orchestrator가 startup 시 기존 포지션을 감지하고 State를 IN_POSITION으로 설정
- FLAT 상태로 시작하지 않도록 수정

테스트 시나리오:
1. Position 없음 → State.FLAT
2. Position 있음 (Buy) → State.IN_POSITION
3. Position 있음 (Sell) → State.IN_POSITION

SSOT:
- FLOW.md Section 4.1: State Recovery
- CLAUDE.md Section 5.7: Self-Verification (Position detection)
"""

import pytest
from src.application.orchestrator import Orchestrator
from src.domain.state import State, Direction, Position


class FakeMarketDataWithPosition:
    """Fake MarketDataInterface with position support"""

    def __init__(self, position_size: float = 0.0, position_side: str = "None", avg_price: float = 0.0):
        """
        Args:
            position_size: Position size (BTC 단위)
            position_side: "Buy", "Sell", "None"
            avg_price: Average entry price
        """
        self.position_size = position_size
        self.position_side = position_side
        self.avg_price = avg_price

        # MarketDataInterface 필수 필드
        self._mark_price = 50000.0
        self._equity_usdt = 1000.0
        self._timestamp = 1705612800.0
        self._ws_last_heartbeat_ts = 1705612800.0
        self._ws_event_drop_count = 0
        self._atr = 100.0
        self._last_fill_price = 49800.0
        self._trades_today = 0
        self._atr_pct_24h = 0.03
        self._winrate = 0.5
        self._position_mode = "MergedSingle"

    def get_position(self) -> dict:
        """
        현재 Position 반환 (Bybit API 구조)

        Returns:
            dict: Position data (size=0이면 포지션 없음)
        """
        if self.position_size == 0:
            return {"size": "0", "side": "None", "avgPrice": "0"}

        return {
            "size": str(self.position_size),
            "side": self.position_side,
            "avgPrice": str(self.avg_price),
        }

    # MarketDataInterface 구현 (최소)
    def get_mark_price(self) -> float:
        return self._mark_price

    def get_equity_usdt(self) -> float:
        return self._equity_usdt

    def get_rest_latency_p95_1m(self) -> float:
        return 0.15

    def get_ws_last_heartbeat_ts(self) -> float:
        return self._ws_last_heartbeat_ts

    def get_ws_event_drop_count(self) -> int:
        return self._ws_event_drop_count

    def get_timestamp(self) -> float:
        return self._timestamp

    def get_btc_mark_price_usd(self) -> float:
        return self._mark_price

    def get_daily_realized_pnl_usd(self):
        return 0.0

    def get_weekly_realized_pnl_usd(self):
        return 0.0

    def get_loss_streak_count(self):
        return 0

    def get_fee_ratio_history(self):
        return None

    def get_slippage_history(self):
        return None

    def is_degraded_timeout(self) -> bool:
        return False

    def is_ws_degraded(self) -> bool:
        return False

    def get_current_price(self) -> float:
        return self._mark_price

    def get_atr(self):
        return self._atr

    def get_last_fill_price(self):
        return self._last_fill_price

    def get_trades_today(self) -> int:
        return self._trades_today

    def get_atr_pct_24h(self) -> float:
        return self._atr_pct_24h

    def get_winrate(self) -> float:
        return self._winrate

    def get_position_mode(self) -> str:
        return self._position_mode

    def get_fill_events(self):
        return []


def test_position_recovery_no_position():
    """Position 없음 → State.FLAT"""
    # Given: Position 없음
    market_data = FakeMarketDataWithPosition(position_size=0.0)

    # When: Orchestrator 초기화
    orchestrator = Orchestrator(market_data=market_data)

    # Then: State = FLAT
    assert orchestrator.state == State.FLAT
    assert orchestrator.position is None


def test_position_recovery_buy_position():
    """Position 있음 (Buy) → State.IN_POSITION"""
    # Given: Buy position 존재 (0.146 BTC @ $85,074)
    market_data = FakeMarketDataWithPosition(
        position_size=0.146,
        position_side="Buy",
        avg_price=85074.19,
    )

    # When: Orchestrator 초기화
    orchestrator = Orchestrator(market_data=market_data)

    # Then: State = IN_POSITION, Position 설정
    assert orchestrator.state == State.IN_POSITION
    assert orchestrator.position is not None
    assert orchestrator.position.direction == Direction.LONG
    assert orchestrator.position.qty == 0.146
    assert orchestrator.position.entry_price == 85074.19


def test_position_recovery_sell_position():
    """Position 있음 (Sell) → State.IN_POSITION"""
    # Given: Sell position 존재 (0.05 BTC @ $84,000)
    market_data = FakeMarketDataWithPosition(
        position_size=0.05,
        position_side="Sell",
        avg_price=84000.0,
    )

    # When: Orchestrator 초기화
    orchestrator = Orchestrator(market_data=market_data)

    # Then: State = IN_POSITION, Position 설정
    assert orchestrator.state == State.IN_POSITION
    assert orchestrator.position is not None
    assert orchestrator.position.direction == Direction.SHORT
    assert orchestrator.position.qty == 0.05
    assert orchestrator.position.entry_price == 84000.0

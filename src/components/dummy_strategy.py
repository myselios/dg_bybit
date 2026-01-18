"""더미 Strategy 구현 - 테스트용"""

from ..interfaces.strategy import IStrategy
from ..models.trading_context import MarketData, StrategySignal, TradeDirection


class DummyStrategy(IStrategy):
    """
    더미 Strategy

    목적: EV_FRAMEWORK 차단 로직 검증용
    행동: 항상 LONG 신호 발생
    """

    def analyze(self, market_data: MarketData) -> StrategySignal:
        """항상 진입 신호 반환"""
        return StrategySignal(
            direction=TradeDirection.LONG,
            entry_valid=True,
            confidence=0.8,
            context_tag="TEST_SIGNAL"
        )

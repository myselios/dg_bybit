"""Strategy Interface"""

from abc import ABC, abstractmethod
from ..models.trading_context import MarketData, StrategySignal


class IStrategy(ABC):
    """
    Strategy 인터페이스

    책임:
    - 시장 해석
    - 기회 포착
    - 방향성 판단

    금지:
    - 포지션 크기 결정
    - 손절/익절 가격 결정
    - 실행 방식 결정
    """

    @abstractmethod
    def analyze(self, market_data: MarketData) -> StrategySignal:
        """
        시장 분석 및 신호 생성

        Args:
            market_data: 시장 데이터

        Returns:
            StrategySignal: 거래 방향 및 유효성
        """
        pass

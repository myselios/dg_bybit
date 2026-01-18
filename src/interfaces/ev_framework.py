"""EV_FRAMEWORK Interface"""

from abc import ABC, abstractmethod
from ..models.trading_context import StrategySignal, MarketData, EVResult


class IEVFramework(ABC):
    """
    EV_FRAMEWORK 인터페이스

    지위: Strategy 위의 절대 게이트

    책임:
    - 트레이드의 기대값(EV) 계산
    - +300% 이상 수익 가능성 판정
    - Account Builder 기준 충족 여부 검증
    - EV 미달 트레이드 차단

    금지:
    - 진입 타이밍 결정
    - 포지션 크기 결정
    - 리스크 한도 설정
    """

    @abstractmethod
    def evaluate(self, signal: StrategySignal, market_data: MarketData) -> EVResult:
        """
        트레이드 기대값 평가

        Args:
            signal: Strategy 신호
            market_data: 시장 데이터

        Returns:
            EVResult: PASS/REJECT 및 기대 R-multiple
        """
        pass

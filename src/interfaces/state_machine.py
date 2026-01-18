"""State Machine Interface"""

from abc import ABC, abstractmethod
from ..models.trading_context import TradingContext, TradingState


class IStateMachine(ABC):
    """
    State Machine 인터페이스

    지위: 모든 컴포넌트의 행동을 통제

    책임:
    - 상태 전환 결정
    - 상태별 허용 행동 정의
    - 실패/성공 흐름 강제
    """

    @abstractmethod
    def get_current_state(self) -> TradingState:
        """현재 상태 반환"""
        pass

    @abstractmethod
    def transition(self, context: TradingContext) -> TradingState:
        """
        상태 전환 수행

        Args:
            context: 현재 거래 컨텍스트

        Returns:
            TradingState: 다음 상태
        """
        pass

    @abstractmethod
    def can_enter_trade(self) -> bool:
        """현재 상태에서 진입 가능한지 확인"""
        pass

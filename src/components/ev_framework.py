"""EV_FRAMEWORK 구현"""

from ..interfaces.ev_framework import IEVFramework
from ..models.trading_context import (
    StrategySignal,
    MarketData,
    EVResult,
    EVDecision,
    TradeDirection,
)


class EVFramework(IEVFramework):
    """
    EV_FRAMEWORK 구현

    Account Builder 기준:
    - Win Probability >= 15%
    - Expected R-multiple >= 3.0 (+300%)
    - EV = (P_win × R_win) - (P_loss × R_loss) > 0
    """

    def __init__(
        self,
        min_win_probability: float = 0.15,
        min_r_multiple: float = 3.0,
        avg_loss_r: float = 0.25,
    ):
        """
        Args:
            min_win_probability: 최소 승률 (기본 15%)
            min_r_multiple: 최소 R-multiple (기본 3.0 = +300%)
            avg_loss_r: 평균 손실 R (기본 0.25 = -25%)
        """
        self.min_win_probability = min_win_probability
        self.min_r_multiple = min_r_multiple
        self.avg_loss_r = avg_loss_r

    def evaluate(self, signal: StrategySignal, market_data: MarketData) -> EVResult:
        """트레이드 기대값 평가"""

        # 신호가 유효하지 않으면 즉시 거부
        if not signal.entry_valid or signal.direction == TradeDirection.NONE:
            return EVResult(
                decision=EVDecision.REJECT,
                expected_r_multiple=0.0,
                win_probability=0.0,
                rejection_reason="Invalid signal",
            )

        # 예상 승률 계산 (더미: confidence 기반)
        win_probability = self._estimate_win_probability(signal, market_data)

        # 예상 R-multiple 계산 (더미: 변동성 기반)
        expected_r_multiple = self._estimate_r_multiple(signal, market_data)

        # EV 계산
        ev = self._calculate_ev(win_probability, expected_r_multiple)

        # 기준 충족 여부 판정
        if win_probability < self.min_win_probability:
            return EVResult(
                decision=EVDecision.REJECT,
                expected_r_multiple=expected_r_multiple,
                win_probability=win_probability,
                rejection_reason=f"Win probability {win_probability:.1%} < {self.min_win_probability:.1%}",
            )

        if expected_r_multiple < self.min_r_multiple:
            return EVResult(
                decision=EVDecision.REJECT,
                expected_r_multiple=expected_r_multiple,
                win_probability=win_probability,
                rejection_reason=f"R-multiple {expected_r_multiple:.1f} < {self.min_r_multiple:.1f}",
            )

        if ev <= 0:
            return EVResult(
                decision=EVDecision.REJECT,
                expected_r_multiple=expected_r_multiple,
                win_probability=win_probability,
                rejection_reason=f"Negative EV: {ev:.3f}",
            )

        # 모든 기준 통과
        return EVResult(
            decision=EVDecision.PASS,
            expected_r_multiple=expected_r_multiple,
            win_probability=win_probability,
            rejection_reason=None,
        )

    def _estimate_win_probability(
        self, signal: StrategySignal, market_data: MarketData
    ) -> float:
        """
        승률 추정 (더미 구현)

        실제 구현에서는:
        - 백테스트 통계
        - 현재 시장 조건
        - 전략 성과 이력
        """
        # 더미: confidence를 승률로 직접 사용
        return signal.confidence * 0.5  # 최대 50%

    def _estimate_r_multiple(
        self, signal: StrategySignal, market_data: MarketData
    ) -> float:
        """
        기대 R-multiple 추정 (더미 구현)

        실제 구현에서는:
        - ATR 기반 목표가 계산
        - 변동성 확장 가능성
        - 추세 강도
        """
        # 더미: ATR 비율로 추정 (더 보수적으로 조정)
        atr_ratio = market_data.atr / market_data.price

        # ATR이 3% 미만이면 낮은 R-multiple
        if atr_ratio < 0.03:
            estimated_r = atr_ratio * 100 * 2  # 낮은 승수
        else:
            estimated_r = atr_ratio * 100 * 5  # 높은 승수

        return min(estimated_r, 15.0)  # 최대 15R로 제한

    def _calculate_ev(self, win_probability: float, r_multiple: float) -> float:
        """
        기대값 계산

        EV = (P_win × R_win) - (P_loss × R_loss)
        """
        p_win = win_probability
        p_loss = 1 - win_probability
        r_win = r_multiple
        r_loss = self.avg_loss_r

        ev = (p_win * r_win) - (p_loss * r_loss)
        return ev

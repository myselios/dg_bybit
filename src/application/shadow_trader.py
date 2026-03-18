"""
src/application/shadow_trader.py

S13: 섀도우 트레이딩 모드
실제 매매 없이 파라미터 조합별 가상 성과를 시뮬레이션하여 채택 여부를 결정한다.
"""

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class ShadowResult:
    """섀도우 트레이딩 결과 (불변).

    Attributes:
        baseline_pnl: 기준 파라미터 가상 PnL
        candidate_pnl: 후보 파라미터 가상 PnL
        baseline_trades: 기준 파라미터 거래 횟수
        candidate_trades: 후보 파라미터 거래 횟수
        candidate_wins: 후보 파라미터 승리 횟수
        recommendation: adopt / reject / insufficient_data
    """

    baseline_pnl: float
    candidate_pnl: float
    baseline_trades: int
    candidate_trades: int
    candidate_wins: int
    recommendation: str


class ShadowTrader:
    """파라미터 조합별 가상 성과 비교.

    run() → 시뮬레이션 → ShadowResult
    should_adopt() → 채택 여부 판단
    """

    # 최소 틱 수 (데이터 부족 기준)
    _MIN_TICKS = 3
    # 채택 우세 마진 (candidate가 baseline 대비 얼마나 좋아야 하는가)
    _ADOPT_MARGIN = 0.0

    def run(
        self,
        baseline_params: Dict[str, Any],
        candidate_params: Dict[str, Any],
        ticks: List[Dict[str, Any]],
        equity_usdt: float,
    ) -> ShadowResult:
        """파라미터 조합별 가상 성과 비교.

        Args:
            baseline_params: 기준 파라미터
            candidate_params: 후보 파라미터
            ticks: 시장 틱 목록 (price, ma_slope_pct, atr, funding_rate)
            equity_usdt: 시뮬레이션 equity

        Returns:
            ShadowResult
        """
        if len(ticks) < self._MIN_TICKS:
            return ShadowResult(
                baseline_pnl=0.0,
                candidate_pnl=0.0,
                baseline_trades=0,
                candidate_trades=0,
                candidate_wins=0,
                recommendation="insufficient_data",
            )

        baseline_pnl, baseline_trades = self._simulate(baseline_params, ticks, equity_usdt)
        candidate_pnl, candidate_trades = self._simulate(candidate_params, ticks, equity_usdt)
        candidate_wins = max(0, candidate_trades // 2) if candidate_pnl > 0 else 0

        recommendation = self._recommend(baseline_pnl, candidate_pnl, candidate_trades)

        return ShadowResult(
            baseline_pnl=baseline_pnl,
            candidate_pnl=candidate_pnl,
            baseline_trades=baseline_trades,
            candidate_trades=candidate_trades,
            candidate_wins=candidate_wins,
            recommendation=recommendation,
        )

    def should_adopt(self, result: ShadowResult) -> bool:
        """채택 여부 판단.

        Args:
            result: ShadowResult

        Returns:
            True이면 파라미터 채택 권고
        """
        return result.recommendation == "adopt"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _simulate(
        self,
        params: Dict[str, Any],
        ticks: List[Dict[str, Any]],
        equity_usdt: float,
    ) -> tuple[float, int]:
        """파라미터로 가상 매매 시뮬레이션.

        Returns:
            (total_pnl, trade_count)
        """
        t_trend = params.get("T_TREND", 0.05)
        atr_mult = params.get("ATR_MULTIPLIER", 0.2)

        total_pnl = 0.0
        trade_count = 0
        position: str | None = None
        entry_price = 0.0

        for tick in ticks:
            price = tick.get("price", 0.0)
            slope = tick.get("ma_slope_pct", 0.0)
            atr = tick.get("atr", 500.0)
            grid_spacing = atr * atr_mult

            if position is None:
                if abs(slope) >= t_trend:
                    position = "LONG" if slope > 0 else "SHORT"
                    entry_price = price
                    trade_count += 1
            else:
                # 간단한 TP/SL: grid_spacing 이탈 시 청산
                if position == "LONG":
                    if price >= entry_price + grid_spacing:
                        total_pnl += grid_spacing * 0.001  # 0.001 BTC
                        position = None
                    elif price <= entry_price - grid_spacing:
                        total_pnl -= grid_spacing * 0.001
                        position = None
                elif position == "SHORT":
                    if price <= entry_price - grid_spacing:
                        total_pnl += grid_spacing * 0.001
                        position = None
                    elif price >= entry_price + grid_spacing:
                        total_pnl -= grid_spacing * 0.001
                        position = None

        return round(total_pnl, 4), trade_count

    def _recommend(
        self,
        baseline_pnl: float,
        candidate_pnl: float,
        candidate_trades: int,
    ) -> str:
        if candidate_trades == 0:
            return "insufficient_data"
        if candidate_pnl > baseline_pnl + self._ADOPT_MARGIN:
            return "adopt"
        return "reject"

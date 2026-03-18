"""
src/application/agents/market_analyst_agent.py

S11: 시장 분석 에이전트 — MA slope 기반 레짐 판별
"""

import time

from application.agents.agent_message import AgentMessage

# 추세 판별 임계값 (% 단위)
_TREND_THRESHOLD = 0.1


class MarketAnalystAgent:
    """MA slope와 ATR을 분석하여 시장 레짐을 판별하는 에이전트.

    analyze() → AgentMessage(msg_type='regime_update')
    payload: {regime: trending_up|trending_down|ranging, atr_pct: float}
    """

    def analyze(self, ma_slope_pct: float, atr_pct: float) -> AgentMessage:
        """시장 레짐 분석.

        Args:
            ma_slope_pct: MA slope (% 단위)
            atr_pct: ATR (% 단위)

        Returns:
            AgentMessage(msg_type='regime_update')
        """
        regime = self._classify_regime(ma_slope_pct)
        return AgentMessage(
            from_agent="market_analyst",
            to_agent="strategy",
            msg_type="regime_update",
            payload={"regime": regime, "atr_pct": atr_pct, "ma_slope_pct": ma_slope_pct},
            timestamp=time.time(),
        )

    def _classify_regime(self, ma_slope_pct: float) -> str:
        if ma_slope_pct >= _TREND_THRESHOLD:
            return "trending_up"
        if ma_slope_pct <= -_TREND_THRESHOLD:
            return "trending_down"
        return "ranging"

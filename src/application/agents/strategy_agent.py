"""
src/application/agents/strategy_agent.py

S11: 전략 에이전트 — 레짐 메시지 기반 매매 방향 결정
"""

import time
from typing import Optional

from application.agents.agent_message import AgentMessage


class StrategyAgent:
    """레짐 분석 결과를 바탕으로 매매 방향(signal)을 결정하는 에이전트.

    decide() → AgentMessage(msg_type='signal')
    payload: {direction: LONG|SHORT|NONE, ...}
    """

    def decide(
        self,
        regime_msg: AgentMessage,
        current_price: float,
        last_fill_price: Optional[float],
    ) -> AgentMessage:
        """매매 방향 결정.

        Args:
            regime_msg: MarketAnalystAgent에서 받은 레짐 메시지
            current_price: 현재 가격
            last_fill_price: 마지막 체결 가격 (None이면 FLAT)

        Returns:
            AgentMessage(msg_type='signal')
        """
        regime = regime_msg.payload.get("regime", "ranging")
        direction = self._determine_direction(regime)

        return AgentMessage(
            from_agent="strategy",
            to_agent="risk",
            msg_type="signal",
            payload={
                "direction": direction,
                "current_price": current_price,
                "last_fill_price": last_fill_price,
                "regime": regime,
            },
            timestamp=time.time(),
        )

    def _determine_direction(self, regime: str) -> str:
        if regime == "trending_up":
            return "LONG"
        if regime == "trending_down":
            return "SHORT"
        return "NONE"

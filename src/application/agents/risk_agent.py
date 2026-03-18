"""
src/application/agents/risk_agent.py

S11: 리스크 에이전트 — equity 기반 거래 승인/거부
"""

import time

from application.agents.agent_message import AgentMessage

# 최소 equity 기준 (USDT)
_MIN_EQUITY_USDT = 10.0


class RiskAgent:
    """리스크 검증 에이전트.

    신호(signal) 메시지를 받아 equity 수준에 따라 거래 승인 여부를 결정한다.
    validate() → AgentMessage(msg_type='risk_validated')
    payload: {approved: bool, reason: str (거부 시), ...}
    """

    def validate(self, signal_msg: AgentMessage, equity_usdt: float) -> AgentMessage:
        """리스크 검증.

        Args:
            signal_msg: StrategyAgent에서 받은 signal 메시지
            equity_usdt: 현재 사용 가능한 equity (USDT)

        Returns:
            AgentMessage(msg_type='risk_validated')
        """
        direction = signal_msg.payload.get("direction", "NONE")

        approved, reason = self._check_risk(equity_usdt, direction)

        payload: dict = {"approved": approved, "direction": direction}
        if not approved:
            payload["reason"] = reason

        return AgentMessage(
            from_agent="risk",
            to_agent="orchestrator",
            msg_type="risk_validated",
            payload=payload,
            timestamp=time.time(),
        )

    def _check_risk(self, equity_usdt: float, direction: str) -> tuple[bool, str]:
        if direction == "NONE":
            return False, "no signal"
        if equity_usdt < _MIN_EQUITY_USDT:
            return False, f"equity too low: {equity_usdt:.2f} USDT (min {_MIN_EQUITY_USDT})"
        return True, ""

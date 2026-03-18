"""
src/application/agents/agent_message.py

S11: 에이전트 간 통신 메시지 (불변 frozen dataclass)
"""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class AgentMessage:
    """에이전트 간 메시지 프로토콜.

    Attributes:
        from_agent: 발신 에이전트 이름
        to_agent: 수신 에이전트 이름
        msg_type: 메시지 타입 (예: regime_update, signal, risk_validated)
        payload: 메시지 페이로드 (타입에 따라 내용 다름)
        timestamp: Unix 타임스탬프 (초)
    """

    from_agent: str
    to_agent: str
    msg_type: str
    payload: Dict[str, Any]
    timestamp: float

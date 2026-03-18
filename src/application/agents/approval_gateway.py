"""
src/application/agents/approval_gateway.py
Human-in-the-Loop 파라미터 변경 승인 게이트웨이

TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 없으면 minor는 자동승인, major는 거부 (안전 모드).
"""
from dataclasses import dataclass
from enum import Enum

MAJOR_THRESHOLD_PCT = 50.0  # 50% 이상 변경 → Major


class ChangeType(Enum):
    MINOR = "minor"
    MAJOR = "major"


@dataclass(frozen=True)
class ParamChange:
    param_name: str
    old_value: float
    new_value: float


class ApprovalGateway:
    def classify_change(self, change: ParamChange) -> ChangeType:
        if change.old_value == 0:
            return ChangeType.MAJOR
        pct_change = abs(change.new_value - change.old_value) / abs(change.old_value) * 100.0
        return ChangeType.MAJOR if pct_change >= MAJOR_THRESHOLD_PCT else ChangeType.MINOR

    def auto_approve(self, change: ParamChange) -> bool:
        """
        Minor → True (자동승인)
        Major + Telegram 없음 → False (거부)
        Major + Telegram 있음 → False (사람 확인 필요, 별도 UI 구현)
        """
        change_type = self.classify_change(change)
        if change_type == ChangeType.MINOR:
            return True
        return False  # Major는 항상 수동 승인 필요

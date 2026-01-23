"""
src/infrastructure/safety/alert.py
Alert System — Notification system (log only)

Purpose:
- Alert 발생 시 로그 출력 (현재 log only)
- 추후 Slack/Discord 연동 (Phase 10+)

SSOT:
- config/safety_limits.yaml: alert.log_only
- task_plan.md Phase 9c: 기존 안전장치

Exports:
- Alert: Alert system (log only)
"""

import logging

logger = logging.getLogger(__name__)


class Alert:
    """
    Alert System — Notification system (log only)

    Usage:
        alert = Alert()
        alert.send("HALT", "daily_loss_cap_exceeded")
    """

    def __init__(self, log_only: bool = True):
        """
        Alert 초기화

        Args:
            log_only: True이면 로그만 출력, False이면 외부 알림 (현재 미구현)
        """
        self.log_only = log_only

    def send(self, level: str, message: str) -> None:
        """
        Alert 전송

        Args:
            level: Alert 레벨 ("INFO", "WARNING", "HALT")
            message: Alert 메시지

        Note:
            현재는 로그만 출력, 추후 Slack/Discord 연동
        """
        if self.log_only:
            if level == "HALT":
                logger.critical(f"[ALERT:{level}] {message}")
            elif level == "WARNING":
                logger.warning(f"[ALERT:{level}] {message}")
            else:
                logger.info(f"[ALERT:{level}] {message}")
        else:
            # 추후 Slack/Discord 연동 (Phase 10+)
            logger.warning(f"[ALERT:{level}] {message} (external notification not implemented)")

"""
src/infrastructure/safety/__init__.py
Safety Infrastructure (Kill Switch, Alert, Rollback)

Purpose:
- Kill Switch: Manual halt mechanism
- Alert: Notification system (현재 log only)
- Rollback: Rollback protocol (현재 미구현)

SSOT:
- task_plan.md Phase 9c: Orchestrator Integration + 기존 안전장치
- config/safety_limits.yaml: Safety configuration

Exports:
- KillSwitch: Manual halt mechanism
- Alert: Alert system (log only)
- RollbackProtocol: Rollback protocol (placeholder)
"""

from .killswitch import KillSwitch
from .alert import Alert
from .rollback_protocol import RollbackProtocol

__all__ = ["KillSwitch", "Alert", "RollbackProtocol"]

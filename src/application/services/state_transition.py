"""
⚠️ DEPRECATED: Use src/application/transition.py instead

이 파일은 하위 호환성을 위한 wrapper입니다.
모든 전이 로직은 src/application/transition.py로 이동했습니다.

Migration:
- from application.services.state_transition import transition
  → from application.transition import transition
"""

# Re-export from the new location
from application.transition import (
    transition,
    is_entry_allowed,
)
from domain.intent import (
    TransitionIntents,
    StopIntent,
    HaltIntent,
    CancelOrderIntent,
    LogIntent
)

__all__ = [
    'transition',
    'is_entry_allowed',
    'TransitionIntents',
    'StopIntent',
    'HaltIntent',
    'CancelOrderIntent',
    'LogIntent'
]

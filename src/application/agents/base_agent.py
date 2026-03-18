"""Base Agent Protocol — stub for S7 agent framework."""

from typing import Protocol, Any


class BaseAgent(Protocol):
    """Protocol that all agents must implement."""

    def analyze(self, data: dict) -> Any:
        """Analyze input data and return a result."""
        ...

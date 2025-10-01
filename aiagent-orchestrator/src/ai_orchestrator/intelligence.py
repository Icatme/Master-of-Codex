"""Intelligence layer for orchestrator analysis."""
from __future__ import annotations

from typing import Dict, Protocol


class AnalysisProvider(Protocol):
    """Protocol for analysis providers."""

    def analyze(self, output: str) -> Dict[str, str]:  # noqa: D401
        """Analyze output and return a result."""


class DeepSeekProvider:
    """Placeholder DeepSeek provider implementation."""

    def analyze(self, output: str) -> Dict[str, str]:
        """Placeholder analyze method."""
        _ = output
        return {"status": "unknown", "reasoning": ""}

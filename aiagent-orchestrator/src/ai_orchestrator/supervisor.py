"""Supervisor core implementing the orchestrator state machine."""
from __future__ import annotations

from enum import Enum
from typing import Protocol


class OrchestratorState(Enum):
    """Placeholder enumeration for supervisor states."""

    INITIALIZING = "initializing"


class State(Protocol):
    """Protocol for state handlers."""

    def handle(self, context: "OrchestratorContext") -> None:  # noqa: D401
        """Handle the state logic."""


class OrchestratorContext:
    """Placeholder orchestrator context."""

    def __init__(self) -> None:
        self._state: OrchestratorState = OrchestratorState.INITIALIZING

    def run(self) -> None:
        """Placeholder run loop."""
        _ = self._state

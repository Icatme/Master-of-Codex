"""Supervisor core implementing the orchestrator state machine."""
from __future__ import annotations

import logging
from enum import Enum
from typing import Protocol

from .config import OrchestratorConfig


class OrchestratorState(Enum):
    """Placeholder enumeration for supervisor states."""

    INITIALIZING = "initializing"


class State(Protocol):
    """Protocol for state handlers."""

    def handle(self, context: "OrchestratorContext") -> None:  # noqa: D401
        """Handle the state logic."""


class OrchestratorContext:
    """Placeholder orchestrator context."""

    def __init__(self, config: OrchestratorConfig) -> None:
        self._state: OrchestratorState = OrchestratorState.INITIALIZING
        self._config = config
        self._logger = logging.getLogger(__name__)

    def run(self) -> None:
        """Placeholder run loop."""

        self._logger.debug("Current state: %s", self._state.value)

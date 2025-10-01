"""Workflow supervision utilities."""
from __future__ import annotations

from .config import WorkflowConfig


class WorkflowManager:
    """Provide workflow prompts sourced from configuration."""

    def __init__(self, config: WorkflowConfig) -> None:
        self._config = config

    def get_initial_prompt(self) -> str:
        """Return the initial workflow prompt."""

        return self._config.initial_prompt

    def get_continue_prompt(self) -> str:
        """Return the prompt used to continue the workflow."""

        return self._config.continue_prompt

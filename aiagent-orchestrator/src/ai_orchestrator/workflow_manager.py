"""Workflow supervision utilities."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkflowManager:
    """Placeholder workflow manager."""

    initial_prompt: str = ""
    continue_prompt: str = ""

    def get_initial_prompt(self) -> str:
        """Return the initial prompt."""
        return self.initial_prompt

    def get_continue_prompt(self) -> str:
        """Return the continue prompt."""
        return self.continue_prompt

"""Configuration utilities for the AIAgent-Orchestrator."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class OrchestratorConfig:
    """Placeholder data structure for orchestrator configuration."""

    raw: Dict[str, Any]


def load_config(path: Path) -> OrchestratorConfig:
    """Placeholder configuration loader."""
    _ = path
    return OrchestratorConfig(raw={})

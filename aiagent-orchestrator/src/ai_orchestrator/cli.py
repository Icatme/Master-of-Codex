"""Command-line interface for the AIAgent-Orchestrator."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import NoReturn

import typer

from .config import OrchestratorConfig, load_config
from .supervisor import OrchestratorContext

app = typer.Typer(help="AIAgent-Orchestrator command-line interface")


def _configure_logging() -> None:
    """Set up a basic logging configuration for CLI execution."""

    logging.basicConfig(level=logging.INFO)


@app.command()
def run(
    config_path: Path = typer.Option(
        Path("config.yml"),
        "--config",
        "-c",
        help="Path to the orchestrator configuration file.",
        show_default=True,
    ),
) -> None:
    """Start the orchestrator using the provided configuration."""

    _configure_logging()
    logger = logging.getLogger(__name__)

    resolved_path = config_path.expanduser()

    try:
        config: OrchestratorConfig = load_config(resolved_path)
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error), param_hint="--config") from error
    except ValueError as error:
        raise typer.BadParameter(f"Invalid configuration: {error}", param_hint="--config") from error

    logger.info("Launching orchestrator with command: %s", " ".join(config.ai_coder.command))

    context = OrchestratorContext(config)
    context.run()


def main() -> NoReturn:
    """Entrypoint for executing the Typer application."""

    app()


if __name__ == "__main__":
    main()

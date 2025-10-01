"""Module entrypoint for running the Typer CLI.

作为模块入口，负责在命令行中启动 Typer 应用。"""
from __future__ import annotations

from .cli import main


if __name__ == "__main__":
    # 当以 ``python -m ai_orchestrator`` 执行时，直接运行 Typer 应用。
    main()

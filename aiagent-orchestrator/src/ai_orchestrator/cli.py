"""Command-line interface for the AIAgent-Orchestrator.

AIAgent-Orchestrator 的命令行接口，负责启动和调度编排器。"""
from __future__ import annotations

import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import NoReturn, Optional

import typer

from .config import OrchestratorConfig, load_config
from .supervisor import OrchestratorContext

app = typer.Typer(help="AIAgent-Orchestrator command-line interface")


def _configure_logging() -> None:
    """Set up a basic logging configuration for CLI execution.

    为命令行执行配置基础的日志行为，确保调试信息可以输出到终端。
    """

    # 这里使用 ``basicConfig`` 简化配置，默认输出到标准输出。
    logging.basicConfig(level=logging.INFO)


@app.command()
def run(
    library_path: Optional[Path] = typer.Argument(
        None,
        help=(
            "Path to the target repository that the monitored AI tool should operate on. "
            "When provided, the orchestrator changes into this directory before loading "
            "the configuration and overrides the AI tool working directory.\n"
            "指定被监管 AI 工具需要操作的代码仓库路径。提供后，编排器会先切换到该目录，"
            "再加载配置文件，并覆盖 AI 工具的工作目录。"
        ),
    ),
    config_path: Path = typer.Option(
        Path("config.yml"),
        "--config",
        "-c",
        help="Path to the orchestrator configuration file.",
        show_default=True,
    ),
) -> None:
    """Start the orchestrator using the provided configuration.

    根据传入的配置文件初始化编排器的各个组件，并启动主循环。
    """

    _configure_logging()
    logger = logging.getLogger(__name__)

    repo_root: Optional[Path] = None

    if library_path is not None:
        candidate = library_path.expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if not candidate.exists():
            raise typer.BadParameter(
                f"Repository path does not exist: {candidate}",
                param_hint="library_path",
            )
        if not candidate.is_dir():
            raise typer.BadParameter(
                f"Repository path must be a directory: {candidate}",
                param_hint="library_path",
            )

        os.chdir(candidate)
        repo_root = candidate
        logger.info("Changed working directory to %s", candidate)

    # 支持 ``~`` 等路径缩写，方便在不同平台上运行。
    resolved_path = config_path.expanduser()
    if not resolved_path.is_absolute():
        resolved_path = (Path.cwd() / resolved_path).resolve()

    try:
        # 解析配置文件并转换为结构化的数据类。
        config: OrchestratorConfig = load_config(resolved_path)
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error), param_hint="--config") from error
    except ValueError as error:
        raise typer.BadParameter(f"Invalid configuration: {error}", param_hint="--config") from error

    if repo_root is not None:
        current_dir = config.ai_coder.working_directory
        if current_dir and current_dir != repo_root:
            logger.info(
                "Overriding configured working directory %s with CLI argument %s",
                current_dir,
                repo_root,
            )
        else:
            logger.info("Using repository path %s as working directory", repo_root)

        config = replace(
            config,
            ai_coder=replace(config.ai_coder, working_directory=repo_root),
        )

    logger.info("Launching orchestrator with command: %s", " ".join(config.ai_coder.command))

    # 构造状态机上下文并运行整个生命周期。
    context = OrchestratorContext(config)
    context.run()


def main() -> NoReturn:
    """Entrypoint for executing the Typer application.

    Typer 会自动解析命令行参数并调用注册的命令函数。
    """

    app()


if __name__ == "__main__":
    main()

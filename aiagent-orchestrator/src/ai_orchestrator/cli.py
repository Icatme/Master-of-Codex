"""Command-line interface for the AIAgent-Orchestrator.

AIAgent-Orchestrator 的命令行接口，负责启动和调度编排器。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import NoReturn

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

    # 支持 ``~`` 等路径缩写，方便在不同平台上运行。
    resolved_path = config_path.expanduser()

    try:
        # 解析配置文件并转换为结构化的数据类。
        config: OrchestratorConfig = load_config(resolved_path)
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error), param_hint="--config") from error
    except ValueError as error:
        raise typer.BadParameter(f"Invalid configuration: {error}", param_hint="--config") from error

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

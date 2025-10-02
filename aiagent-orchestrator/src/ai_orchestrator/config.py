"""Configuration utilities for the AIAgent-Orchestrator.

配置相关的工具函数与数据结构，用于驱动整个编排器。"""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass(frozen=True)
class AICoderConfig:
    """Configuration for the monitored AI coding tool.

    针对被监管的 AI 编码工具的核心配置，包括启动命令及状态标识。
    """

    command: List[str]
    completion_indicator: str
    response_timeout: int
    working_indicator: Optional[str] = None
    working_directory: Optional[Path] = None


@dataclass(frozen=True)
class WorkflowConfig:
    """Configuration for workflow supervision prompts.

    包含编排器在不同阶段发送给子进程的提示词内容。
    """

    initial_prompt: str
    continue_prompt: str


@dataclass(frozen=True)
class AnalysisConfig:
    """Configuration for the intelligence layer.

    描述是否启用外部推理模型以及所需的提供商信息。
    """

    provider: Optional[str] = None
    model: Optional[str] = None
    enabled: bool = False


@dataclass(frozen=True)
class OrchestratorConfig:
    """Complete configuration for the orchestrator.

    汇总所有子配置，方便在运行时进行统一访问。
    """

    ai_coder: AICoderConfig
    workflow: WorkflowConfig
    analysis: AnalysisConfig
    raw: Dict[str, Any]


def _normalise_command(command: Any) -> List[str]:
    """Convert the configured command into an argument list.

    将 ``command`` 转换为 ``subprocess`` 可接受的参数列表，兼容字符串或列表两种形式。
    """

    if isinstance(command, list) and all(isinstance(item, str) for item in command):
        return command
    if isinstance(command, str) and command.strip():
        return shlex.split(command)
    raise ValueError("'command' must be a non-empty string or list of strings")


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML content from ``path`` and ensure it is a mapping.

    读取 YAML 配置并校验顶层结构为字典，便于后续字段解析。
    """

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        # ``safe_load`` 可避免执行不安全的 YAML 标签。
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError("Configuration file must define a mapping at the top level")

    return data


def _resolve_working_directory(
    config_path: Path, working_directory_raw: Optional[str]
) -> Optional[Path]:
    """Resolve the optional working directory relative to ``config_path``.

    若配置文件提供了 ``working_directory`` 字段，则需要将其转换为 ``Path`` 对象，
    并校验其是否为已存在的目录。若该字段缺失，则返回 ``None``。
    """

    if working_directory_raw is None:
        return None

    if not isinstance(working_directory_raw, str) or not working_directory_raw.strip():
        raise ValueError("'working_directory' must be a non-empty string when provided")

    candidate = Path(working_directory_raw).expanduser()
    if not candidate.is_absolute():
        candidate = (config_path.parent / candidate).resolve()

    if not candidate.exists():
        raise ValueError(f"Configured working directory does not exist: {candidate}")
    if not candidate.is_dir():
        raise ValueError(
            f"Configured working directory must be a directory: {candidate}"
        )

    return candidate


def load_config(path: Path) -> OrchestratorConfig:
    """Load and validate the orchestrator configuration from ``path``.

    完成配置文件读取、字段校验，并封装为数据类对象，方便其它模块消费。
    """

    raw_config = _load_yaml(path)

    try:
        # 确保三个关键配置段落全部存在。
        ai_coder_data = raw_config["ai_coder"]
        workflow_data = raw_config["workflow"]
        analysis_data = raw_config["analysis"]
    except KeyError as error:
        missing_key = error.args[0]
        raise ValueError(f"Missing required configuration section: {missing_key}") from error

    if not isinstance(ai_coder_data, dict):
        raise ValueError("'ai_coder' section must be a mapping")
    if not isinstance(workflow_data, dict):
        raise ValueError("'workflow' section must be a mapping")
    if not isinstance(analysis_data, dict):
        raise ValueError("'analysis' section must be a mapping")

    command = _normalise_command(ai_coder_data.get("command"))
    completion_indicator = ai_coder_data.get("completion_indicator")
    response_timeout = ai_coder_data.get("response_timeout")
    working_indicator = ai_coder_data.get("working_indicator")
    working_directory_raw = ai_coder_data.get("working_directory")

    if not isinstance(completion_indicator, str) or not completion_indicator.strip():
        raise ValueError("'completion_indicator' must be a non-empty string")
    if not isinstance(response_timeout, int) or response_timeout <= 0:
        raise ValueError("'response_timeout' must be a positive integer")
    if working_indicator is not None and not isinstance(working_indicator, str):
        raise ValueError("'working_indicator' must be a string when provided")

    working_directory = _resolve_working_directory(path, working_directory_raw)

    ai_coder_config = AICoderConfig(
        command=command,
        completion_indicator=completion_indicator,
        response_timeout=response_timeout,
        working_indicator=working_indicator,
        working_directory=working_directory,
    )

    initial_prompt = workflow_data.get("initial_prompt")
    continue_prompt = workflow_data.get("continue_prompt")

    if not isinstance(initial_prompt, str) or not initial_prompt.strip():
        raise ValueError("'initial_prompt' must be a non-empty string")
    if not isinstance(continue_prompt, str) or not continue_prompt.strip():
        raise ValueError("'continue_prompt' must be a non-empty string")

    workflow_config = WorkflowConfig(
        initial_prompt=initial_prompt,
        continue_prompt=continue_prompt,
    )

    enabled = analysis_data.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("'enabled' must be a boolean value when provided")

    provider_raw = analysis_data.get("provider")
    model_raw = analysis_data.get("model")

    provider: Optional[str]
    model: Optional[str]

    if enabled:
        if not isinstance(provider_raw, str) or not provider_raw.strip():
            raise ValueError("'provider' must be a non-empty string when analysis is enabled")
        if not isinstance(model_raw, str) or not model_raw.strip():
            raise ValueError("'model' must be a non-empty string when analysis is enabled")
        provider = provider_raw
        model = model_raw
    else:
        provider = provider_raw if isinstance(provider_raw, str) and provider_raw.strip() else None
        model = model_raw if isinstance(model_raw, str) and model_raw.strip() else None

    analysis_config = AnalysisConfig(provider=provider, model=model, enabled=enabled)

    return OrchestratorConfig(
        ai_coder=ai_coder_config,
        workflow=workflow_config,
        analysis=analysis_config,
        raw=raw_config,
    )

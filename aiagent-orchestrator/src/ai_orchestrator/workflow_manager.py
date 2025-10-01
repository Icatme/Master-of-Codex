"""Workflow supervision utilities.

工作流管理模块，集中提供初始与继续提示词。"""
from __future__ import annotations

from .config import WorkflowConfig


class WorkflowManager:
    """Provide workflow prompts sourced from configuration.

    简单封装配置对象，避免其他模块直接依赖原始数据类。
    """

    def __init__(self, config: WorkflowConfig) -> None:
        self._config = config

    def get_initial_prompt(self) -> str:
        """Return the initial workflow prompt.

        返回在工作流开始时发送给 AI 工具的提示词。
        """

        return self._config.initial_prompt

    def get_continue_prompt(self) -> str:
        """Return the prompt used to continue the workflow.

        在分析判定需要继续执行时调用。
        """

        return self._config.continue_prompt

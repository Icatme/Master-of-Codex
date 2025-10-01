"""Intelligence layer for orchestrator analysis.

智能分析层负责与外部推理模型交互，用于判断工作流是否应继续。"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional

try:
    from openai import OpenAI
except ImportError as error:  # pragma: no cover - dependency not installed during tests
    OpenAI = None  # type: ignore[assignment]
    _import_error = error
else:  # pragma: no cover - executed when dependency available
    _import_error = None


AnalysisResult = Dict[str, str]


class AnalysisProvider(ABC):
    """Abstract base class for intelligence providers.

    所有智能分析实现需要继承该抽象基类并实现 :meth:`analyze`。"""

    @abstractmethod
    def analyze(self, output: str) -> AnalysisResult:
        """Analyze the ``output`` from the monitored process.

        对被监管进程的输出进行分析，返回结构化的决策结果。
        """


@dataclass
class DeepSeekProvider(AnalysisProvider):
    """DeepSeek implementation of the :class:`AnalysisProvider` protocol.

    基于 DeepSeek Reasoner 模型的具体实现，使用 OpenAI 兼容 SDK 发送请求。
    """

    model: str
    base_url: str = "https://api.deepseek.com"
    api_key: Optional[str] = None

    def __post_init__(self) -> None:
        if OpenAI is None or _import_error is not None:  # pragma: no cover - informative failure path
            raise RuntimeError(
                "openai package is required to use DeepSeekProvider"
            ) from _import_error

        key = self.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY environment variable must be set for DeepSeekProvider"
            )

        # 将凭据和基地址传入 OpenAI 客户端，随后重复使用该实例。
        self._client = OpenAI(api_key=key, base_url=self.base_url)
        self._logger = logging.getLogger(__name__)

    def analyze(self, output: str) -> AnalysisResult:
        """Analyze process ``output`` using DeepSeek's reasoning model.

        通过构造提示词调用 DeepSeek 推理模型，并解析返回的 JSON 结果。
        """

        prompt = self._build_prompt(output)
        response = self._client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": "你是一位资深的软件工程项目经理。你的任务是根据一个AI编码助手的终端输出来评估它的工作进展。",
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        }
                    ],
                },
            ],
            response_format={"type": "json_object"},
        )

        raw_content = self._extract_response_text(response)
        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError as error:
            self._logger.error("Failed to parse DeepSeek response: %s", raw_content)
            raise ValueError("DeepSeek response was not valid JSON") from error

        status = payload.get("status")
        reasoning = payload.get("reasoning", "")

        if status not in {"continue", "finished", "error"}:
            raise ValueError("DeepSeek response missing required 'status' field")

        if not isinstance(reasoning, str):
            raise ValueError("DeepSeek response 'reasoning' field must be a string")

        result: AnalysisResult = {"status": status, "reasoning": reasoning}
        self._logger.debug("DeepSeek analysis result: %s", result)
        return result

    def _build_prompt(self, output: str) -> str:
        """Construct the prompt delivered to the DeepSeek model.

        将终端输出嵌入中文上下文，提醒模型给出继续或完成的判断。
        """

        return (
            "该AI助手正在自主地根据项目内的AGENTS.md文件执行一系列任务。"
            "它刚刚完成了一个阶段，并输出了以下内容：\n\n"
            f"{output}\n\n"
            "请分析所提供的终端输出。判断AI是已经彻底完成了所有任务，"
            "还是仅仅完成了一个中间步骤需要继续，或是遇到了无法解决的错误。"
            "请仅以一个JSON对象作为回应，该对象包含两个键：'status'（字符串，"
            "值为'continue'、'finished'或'error'之一）和'reasoning'（字符串，简要解释你的判断依据）。"
        )

    def _extract_response_text(self, response: object) -> str:
        """Extract the textual payload from a DeepSeek API response.

        DeepSeek 的响应结构可能因 SDK 版本而异，因此这里做了多重兼容处理。
        """

        # The OpenAI SDK provides ``output_text`` when JSON mode is used.
        # 当使用 JSON 模式时，``output_text`` 一般直接包含完整文本。
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        # Fallback for responses exposing ``output`` items.
        # 某些返回结构将文本拆分成 ``output`` 列表，需要逐项拼接。
        output_items = getattr(response, "output", None)
        if isinstance(output_items, list):  # pragma: no cover - depends on SDK structure
            fragments = []
            for item in output_items:
                content = getattr(item, "content", None)
                if isinstance(content, list) and content:
                    text = getattr(content[0], "text", None)
                    if isinstance(text, str):
                        fragments.append(text)
            if fragments:
                return "".join(fragments)

        raise ValueError("DeepSeek response did not contain textual content")

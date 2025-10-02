"""Super lightweight single-file implementation of the AIAgent-Orchestrator.

为了便于分发和维护，将原先分散在多个模块中的实现合并到一个
Python 文件中，同时保留原有的核心功能：配置加载、子进程管理、
工作流监督、智能分析以及 Typer 命令行接口。
"""
from __future__ import annotations

import json
import logging
import os
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, NoReturn, Optional, Protocol, TextIO, Tuple

import typer
import yaml

try:  # pragma: no cover - optional dependency during tests
    from openai import OpenAI
except ImportError as error:  # pragma: no cover - dependency may be missing
    OpenAI = None  # type: ignore[assignment]
    _openai_import_error = error
else:  # pragma: no cover - executed when dependency available
    _openai_import_error = None

try:  # pragma: no cover - pty is unavailable on Windows
    import pty
except ImportError:  # pragma: no cover - handled gracefully at runtime
    pty = None  # type: ignore[assignment]

if os.name == "nt":  # pragma: no cover - executed only on Windows
    try:
        from winpty import PtyProcess
    except ImportError:  # pragma: no cover - optional runtime dependency
        PtyProcess = None  # type: ignore[assignment]
else:  # pragma: no cover - ensures attribute exists for type checking
    PtyProcess = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Configuration utilities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AICoderConfig:
    """Configuration for the monitored AI coding tool."""

    command: List[str]
    completion_indicator: str
    response_timeout: int
    working_indicator: Optional[str] = None
    use_pty: bool = False
    mirror_output: bool = True


@dataclass(frozen=True)
class WorkflowConfig:
    """Configuration for workflow supervision prompts."""

    initial_prompt: str
    continue_prompt: str


@dataclass(frozen=True)
class AnalysisConfig:
    """Configuration for the intelligence layer."""

    provider: Optional[str] = None
    model: Optional[str] = None
    enabled: bool = False


@dataclass(frozen=True)
class OrchestratorConfig:
    """Complete configuration for the orchestrator."""

    ai_coder: AICoderConfig
    workflow: WorkflowConfig
    analysis: AnalysisConfig
    raw: Dict[str, Any]


DEFAULT_CONFIG_FILENAME = "config.yml"
DEFAULT_CONFIG_CONTENT: Dict[str, Any] = {
    "ai_coder": {
        "command": "codex",
        "working_indicator": "Esc to interrupt",
        "completion_indicator": "此阶段任务已经完成",
        "response_timeout": 180,
        "use_pty": True,
        "mirror_output": True,
    },
    "workflow": {
        "initial_prompt": "根据AGENTS.md开始工作",
        "continue_prompt": "Continue.",
    },
    "analysis": {
        "enabled": False,
        "provider": "deepseek",
        "model": "deepseek-reasoner",
    },
}


def _normalise_command(command: Any) -> List[str]:
    """Convert the configured command into an argument list."""

    if isinstance(command, list) and all(isinstance(item, str) for item in command):
        return command
    if isinstance(command, str) and command.strip():
        return shlex.split(command)
    raise ValueError("'command' must be a non-empty string or list of strings")


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML content from ``path`` and ensure it is a mapping."""

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError("Configuration file must define a mapping at the top level")

    return data


def write_default_config(path: Path) -> None:
    """Generate a default configuration file at ``path``."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            DEFAULT_CONFIG_CONTENT,
            handle,
            allow_unicode=True,
            sort_keys=False,
        )


def load_config(path: Path) -> OrchestratorConfig:
    """Load and validate the orchestrator configuration from ``path``."""

    raw_config = _load_yaml(path)

    try:
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
    use_pty_raw = ai_coder_data.get("use_pty")
    mirror_output_raw = ai_coder_data.get("mirror_output", True)

    if not isinstance(completion_indicator, str) or not completion_indicator.strip():
        raise ValueError("'completion_indicator' must be a non-empty string")
    if not isinstance(response_timeout, int) or response_timeout <= 0:
        raise ValueError("'response_timeout' must be a positive integer")
    if working_indicator is not None and not isinstance(working_indicator, str):
        raise ValueError("'working_indicator' must be a string when provided")

    if use_pty_raw is None:
        command_name = Path(command[0]).name.lower()
        use_pty = command_name in {"codex"}
    elif isinstance(use_pty_raw, bool):
        use_pty = use_pty_raw
    else:
        raise ValueError("'use_pty' must be a boolean value when provided")

    if isinstance(mirror_output_raw, bool):
        mirror_output = mirror_output_raw
    else:
        raise ValueError("'mirror_output' must be a boolean value when provided")

    ai_coder_config = AICoderConfig(
        command=command,
        completion_indicator=completion_indicator,
        response_timeout=response_timeout,
        working_indicator=working_indicator,
        use_pty=use_pty,
        mirror_output=mirror_output,
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
        provider = (
            provider_raw if isinstance(provider_raw, str) and provider_raw.strip() else None
        )
        model = model_raw if isinstance(model_raw, str) and model_raw.strip() else None

    analysis_config = AnalysisConfig(provider=provider, model=model, enabled=enabled)

    return OrchestratorConfig(
        ai_coder=ai_coder_config,
        workflow=workflow_config,
        analysis=analysis_config,
        raw=raw_config,
    )


# ---------------------------------------------------------------------------
# Process interaction layer
# ---------------------------------------------------------------------------


_StreamItem = Tuple[str, str]


@dataclass
class ProcessOutput:
    """Container for captured process output."""

    source: str
    text: str

    def format(self) -> str:
        """Return a human-readable representation for logging or analysis."""

        if self.source == "stdout":
            return self.text
        return f"[{self.source}] {self.text}"


def _prepare_command_payload(command_text: str, use_pty: bool) -> bytes:
    """Return the encoded payload that mimics a human pressing Enter.

    Interactive CLI tools connected to a PTY expect carriage returns (``"\r"``)
    instead of line feeds (``"\n"``) when the Enter key is pressed. Previously
    the orchestrator always appended a newline which works for pipe based
    communication but is ignored by tools such as Codex running behind a PTY.
    Normalising the payload here ensures that we deliver the expected control
    character regardless of the transport being used.
    """

    normalised = command_text.replace("\r\n", "\n")

    if use_pty:
        trimmed = normalised.rstrip("\n")
        payload = f"{trimmed}\r"
    else:
        payload = normalised if normalised.endswith("\n") else f"{normalised}\n"

    return payload.encode("utf-8")


class ProcessManager:
    """Manage the lifecycle and I/O of the monitored AI coding tool process."""

    def __init__(
        self,
        command: List[str],
        working_directory: Optional[Path] = None,
        *,
        use_pty: bool = False,
        mirror_output: bool = True,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        if not command:
            raise ValueError("command must contain at least one argument")

        self._command = command
        self._working_directory = working_directory
        self._launch_command = self._prepare_launch_command()
        self._stdin_lock = threading.Lock()
        self._console_lock = threading.Lock()
        self._pty_backend: Optional[str] = None
        if use_pty:
            if os.name == "nt":
                if PtyProcess is None:
                    self._logger.info(
                        "PTY mode requested but PyWinPTY is unavailable; "
                        "falling back to pipe communication"
                    )
                else:
                    self._pty_backend = "pywinpty"
            else:
                if pty is None:
                    raise RuntimeError("PTY mode is not available on this platform")
                self._pty_backend = "posix"

        self._use_pty = self._pty_backend is not None
        self._using_pywinpty = self._pty_backend == "pywinpty"
        self._using_posix_pty = self._pty_backend == "posix"
        self._mirror_output = mirror_output

        self._pty_master_fd: Optional[int] = None
        self._output_queue: "queue.Queue[_StreamItem]" = queue.Queue()
        self._process: Any = self._launch_process()

        if self._using_posix_pty:
            self._stdout_thread = self._start_pty_thread()
            self._stderr_thread = self._stdout_thread
        elif self._using_pywinpty:
            self._stdout_thread = self._start_pywinpty_thread()
            self._stderr_thread = self._stdout_thread
        else:
            self._stdout_thread = self._start_stream_thread(self._process.stdout, "stdout")
            self._stderr_thread = self._start_stream_thread(self._process.stderr, "stderr")

    def _mirror_output_chunk(self, chunk: str) -> None:
        """Mirror raw output ``chunk`` to the local console when enabled."""

        if not self._mirror_output or not chunk:
            return

        with self._console_lock:
            sys.stdout.write(chunk)
            sys.stdout.flush()

    def _handle_output_line(self, source: str, text: str) -> None:
        """Push normalised ``text`` to the queue and emit a log entry."""

        self._output_queue.put((source, text))
        message = f"[{source}] {text}" if text else f"[{source}]"
        level = logging.DEBUG if self._mirror_output else logging.INFO
        self._logger.log(level, message)

    def _prepare_launch_command(self) -> List[str]:
        """Validate the configured command and resolve the executable path."""

        executable = self._command[0]
        command = list(self._command)

        def _is_explicit_path(target: str) -> bool:
            separators = [os.sep]
            if os.altsep:
                separators.append(os.altsep)
            return any(sep in target for sep in separators)

        if Path(executable).is_absolute() or _is_explicit_path(executable):
            candidate = Path(executable)
            if not candidate.exists():
                raise FileNotFoundError(
                    "Unable to start process: "
                    f"executable '{executable}' does not exist"
                )
        else:
            resolved = shutil.which(executable)
            if resolved is None:
                raise FileNotFoundError(
                    "Unable to start process: "
                    f"'{executable}' was not found on PATH. "
                    "Install the command or update 'ai_coder.command' in config.yml."
                )
            command[0] = resolved

        return command

    def _launch_process(self) -> Any:
        """Create the subprocess configured for interactive communication."""

        if self._using_posix_pty:
            if pty is None:
                raise RuntimeError("PTY module not available")

            master_fd, slave_fd = pty.openpty()
            self._pty_master_fd = master_fd
            stdin = slave_fd
            stdout = slave_fd
            stderr = slave_fd
            text_mode = False
            encoding: Optional[str] = None
            bufsize = 0
        elif self._using_pywinpty:
            if PtyProcess is None:
                raise RuntimeError("PyWinPTY is required for PTY mode on Windows")

            command_line = subprocess.list2cmdline(self._launch_command)
            spawn_kwargs: Dict[str, Any] = {}
            if self._working_directory is not None:
                spawn_kwargs["cwd"] = str(self._working_directory)

            def _spawn() -> Any:
                if not spawn_kwargs:
                    return PtyProcess.spawn(command_line)

                try:
                    return PtyProcess.spawn(command_line, **spawn_kwargs)
                except TypeError:
                    previous_dir = os.getcwd()
                    try:
                        os.chdir(spawn_kwargs["cwd"])
                        return PtyProcess.spawn(command_line)
                    finally:
                        os.chdir(previous_dir)

            try:
                child = _spawn()
            except Exception as error:  # pragma: no cover - depends on runtime environment
                raise FileNotFoundError(
                    "Unable to start process: failed to launch configured command"
                ) from error

            self._logger.debug(
                "Started PyWinPTY process with command %s", self._launch_command
            )
            return child
        else:
            stdin = subprocess.PIPE
            stdout = subprocess.PIPE
            stderr = subprocess.PIPE
            text_mode = True
            encoding = "utf-8"
            bufsize = 1

        try:
            process = subprocess.Popen(
                self._launch_command,
                cwd=str(self._working_directory) if self._working_directory else None,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                text=text_mode,
                encoding=encoding,
                bufsize=bufsize,
                close_fds=True,
            )
        except FileNotFoundError as error:
            if self._using_posix_pty and self._pty_master_fd is not None:
                os.close(self._pty_master_fd)
                self._pty_master_fd = None
            if self._using_posix_pty:
                os.close(slave_fd)
            raise FileNotFoundError(
                "Unable to start process: failed to launch configured command"
            ) from error

        if self._using_posix_pty:
            os.close(slave_fd)

        self._logger.debug(
            "Started process PID %s with command %s", process.pid, self._launch_command
        )
        return process

    def _start_stream_thread(self, stream: Optional[TextIO], source: str) -> threading.Thread:
        """Start a daemon thread to enqueue stream output."""

        if stream is None:
            raise RuntimeError("Process stream is not available")

        thread = threading.Thread(
            target=self._pump_stream,
            args=(stream, source),
            name=f"ProcessManager-{source}",
            daemon=True,
        )
        thread.start()
        return thread

    def _start_pty_thread(self) -> threading.Thread:
        """Start the background reader when using a PTY."""

        if self._pty_master_fd is None:
            raise RuntimeError("PTY master file descriptor is not available")

        thread = threading.Thread(
            target=self._pump_pty_output,
            name="ProcessManager-pty",
            daemon=True,
        )
        thread.start()
        return thread

    def _start_pywinpty_thread(self) -> threading.Thread:
        """Start the background reader when using PyWinPTY on Windows."""

        if not self._using_pywinpty:
            raise RuntimeError("Windows PTY mode is not enabled")

        thread = threading.Thread(
            target=self._pump_pywinpty_output,
            name="ProcessManager-pywinpty",
            daemon=True,
        )
        thread.start()
        return thread

    def _pump_stream(self, stream: TextIO, source: str) -> None:
        """Continuously read ``stream`` and push lines to the queue."""

        buffer = ""

        while True:
            chunk = stream.read(1)
            if chunk == "":
                break

            self._mirror_output_chunk(chunk)
            buffer += chunk
            if chunk in "\r\n":
                cleaned = buffer.rstrip("\r\n")
                self._handle_output_line(source, cleaned)
                buffer = ""

        if buffer:
            cleaned = buffer.rstrip("\r\n")
            self._handle_output_line(source, cleaned)

        stream.close()
        self._logger.debug("Stream %s closed", source)

    def _pump_pty_output(self) -> None:
        """Read data from the PTY master descriptor and enqueue lines."""

        if self._pty_master_fd is None:
            raise RuntimeError("PTY master file descriptor is not available")

        buffer = ""
        source = "stdout"

        while True:
            try:
                chunk = os.read(self._pty_master_fd, 1024)
            except OSError as error:
                self._logger.debug("PTY read failed: %s", error)
                break

            if not chunk:
                break

            text = chunk.decode("utf-8", errors="replace")
            self._mirror_output_chunk(text)
            buffer += text

            lines = buffer.splitlines(keepends=True)
            if lines and not lines[-1].endswith(("\n", "\r")):
                buffer = lines.pop()
            else:
                buffer = ""

            for line in lines:
                cleaned = line.rstrip("\r\n")
                self._handle_output_line(source, cleaned)

        if buffer:
            cleaned = buffer.rstrip("\r\n")
            if cleaned:
                self._handle_output_line(source, cleaned)

        self._logger.debug("PTY stream closed")

    def _pump_pywinpty_output(self) -> None:
        """Read data from the PyWinPTY session and enqueue lines."""

        if not self._using_pywinpty:
            raise RuntimeError("Windows PTY mode is not enabled")

        buffer = ""
        source = "stdout"

        while True:
            try:
                try:
                    chunk = self._process.read(1024)
                except TypeError:
                    chunk = self._process.read()
            except EOFError:
                break
            except Exception as error:  # pragma: no cover - depends on runtime
                self._logger.debug("PyWinPTY read error: %s", error)
                break

            if not chunk:
                if not self._is_process_running():
                    break
                time.sleep(0.05)
                continue

            self._mirror_output_chunk(chunk)
            buffer += chunk
            lines = buffer.splitlines(keepends=True)
            if lines and not lines[-1].endswith(("\n", "\r")):
                buffer = lines.pop()
            else:
                buffer = ""

            for line in lines:
                cleaned = line.rstrip("\r\n")
                self._handle_output_line(source, cleaned)

        if buffer:
            cleaned = buffer.rstrip("\r\n")
            if cleaned:
                self._handle_output_line(source, cleaned)

        self._logger.debug("PyWinPTY stream closed")

    def _is_process_running(self) -> bool:
        """Return ``True`` if the underlying process is still running."""

        if self._using_pywinpty:
            try:
                return bool(self._process.isalive())
            except Exception:  # pragma: no cover - defensive fallback
                return False
        return self._process.poll() is None

    def _get_return_code(self) -> Optional[int]:
        """Return the process exit status when available."""

        if self._using_pywinpty:
            exit_status = getattr(self._process, "exitstatus", None)
            if exit_status is not None:
                return int(exit_status)
            signal_status = getattr(self._process, "signalstatus", None)
            if signal_status is not None:
                return int(signal_status)
            return None
        return self._process.returncode

    def send_command(self, command_text: str) -> None:
        """Write ``command_text`` to the subprocess stdin."""

        if not self._is_process_running():
            raise RuntimeError("Cannot send command: process has terminated")

        with self._stdin_lock:
            if self._using_posix_pty:
                if self._pty_master_fd is None:
                    raise RuntimeError("PTY master file descriptor is not available")
                os.write(
                    self._pty_master_fd,
                    _prepare_command_payload(command_text, use_pty=True),
                )
            elif self._using_pywinpty:
                try:
                    payload = _prepare_command_payload(command_text, use_pty=True)
                    self._process.write(payload.decode("utf-8"))
                except Exception as error:  # pragma: no cover - depends on runtime
                    raise RuntimeError("Failed to send command via PyWinPTY") from error
            else:
                if self._process.stdin is None:
                    raise RuntimeError("Process stdin is not available")
                payload = _prepare_command_payload(command_text, use_pty=False)
                self._process.stdin.write(payload.decode("utf-8"))
                self._process.stdin.flush()

        self._logger.debug("Sent command to process: %s", command_text)

    def await_completion(
        self,
        completion_indicator: str,
        working_indicator: Optional[str],
        timeout: int,
    ) -> str:
        """Wait until ``completion_indicator`` is observed in process output."""

        if timeout <= 0:
            raise ValueError("timeout must be a positive integer")

        captured: list[str] = []
        deadline = time.monotonic() + timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for completion indicator")

            try:
                source, text = self._output_queue.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError("No output received before timeout") from error

            captured.append(ProcessOutput(source=source, text=text).format())

            if working_indicator and working_indicator in text:
                deadline = time.monotonic() + timeout

            if completion_indicator in text:
                return "\n".join(captured)

            if not self._is_process_running() and self._output_queue.empty():
                code = self._get_return_code()
                raise RuntimeError(
                    f"Process exited unexpectedly with code {code if code is not None else 'unknown'}"
                )

    def terminate(self) -> None:
        """Terminate the subprocess gracefully."""

        if self._using_pywinpty:
            if not self._is_process_running():
                try:
                    self._process.close()
                except Exception:  # pragma: no cover - depends on runtime
                    pass
                return

            self._logger.debug("Terminating PyWinPTY process")
            try:
                self._process.terminate()
            except Exception:  # pragma: no cover - depends on runtime
                pass
            try:
                self._process.close()
            except Exception:  # pragma: no cover - depends on runtime
                pass
            return

        if not self._is_process_running():
            if self._using_posix_pty and self._pty_master_fd is not None:
                os.close(self._pty_master_fd)
                self._pty_master_fd = None
            return

        self._logger.debug("Terminating process PID %s", self._process.pid)
        self._process.terminate()

        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._logger.warning("Process did not terminate gracefully; killing")
            self._process.kill()
            self._process.wait()

        if self._using_posix_pty and self._pty_master_fd is not None:
            os.close(self._pty_master_fd)
            self._pty_master_fd = None


# ---------------------------------------------------------------------------
# Workflow supervision helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Intelligence layer
# ---------------------------------------------------------------------------


AnalysisResult = Dict[str, str]


class AnalysisProvider(ABC):
    """Abstract base class for intelligence providers."""

    @abstractmethod
    def analyze(self, output: str) -> AnalysisResult:
        """Analyze the ``output`` from the monitored process."""


@dataclass
class DeepSeekProvider(AnalysisProvider):
    """DeepSeek implementation of the :class:`AnalysisProvider` protocol."""

    model: str
    base_url: str = "https://api.deepseek.com"
    api_key: Optional[str] = None

    def __post_init__(self) -> None:
        if OpenAI is None or _openai_import_error is not None:
            raise RuntimeError(
                "openai package is required to use DeepSeekProvider"
            ) from _openai_import_error

        key = self.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY environment variable must be set for DeepSeekProvider"
            )

        self._client = OpenAI(api_key=key, base_url=self.base_url)
        self._logger = logging.getLogger(__name__)

    def analyze(self, output: str) -> AnalysisResult:
        """Analyze process ``output`` using DeepSeek's reasoning model."""

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
        """Construct the prompt delivered to the DeepSeek model."""

        return (
            "该AI助手正在自主地根据项目内的AGENTS.md文件执行一系列任务。"
            "它刚刚完成了一个阶段，并输出了以下内容：\n\n"
            f"{output}\n\n"
            "请分析所提供的终端输出。判断AI是已经彻底完成了所有任务，"
            "还是仅仅完成了一个中间步骤需要继续，或是遇到了无法解决的错误。"
            "请仅以一个JSON对象作为回应，该对象包含两个键：'status'（字符串，"
            "为'continue'、'finished'或'error'之一）和'reasoning'（字符串，简要解释你的判断依据）。"
        )

    def _extract_response_text(self, response: object) -> str:
        """Extract the textual payload from a DeepSeek API response."""

        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text

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


# ---------------------------------------------------------------------------
# Supervisor core (state machine)
# ---------------------------------------------------------------------------


class OrchestratorState(Enum):
    """Enumeration of all orchestrator lifecycle states."""

    INITIALIZING = "initializing"
    SENDING_INITIAL_PROMPT = "sending_initial_prompt"
    AWAITING_COMPLETION = "awaiting_completion"
    ANALYZING_RESPONSE = "analyzing_response"
    SENDING_CONTINUE_PROMPT = "sending_continue_prompt"
    TASK_SUCCESSFUL = "task_successful"
    TASK_FAILED = "task_failed"
    SHUTTING_DOWN = "shutting_down"


class State(Protocol):
    """Protocol for concrete state handlers."""

    def handle(self, context: "OrchestratorContext") -> None:
        """Execute the state logic using ``context``."""


class OrchestratorContext:
    """State-driven supervisor coordinating orchestrator components."""

    def __init__(
        self, config: OrchestratorConfig, working_directory: Optional[Path] = None
    ) -> None:
        self._config = config
        self._logger = logging.getLogger(__name__)
        self._state_enum: OrchestratorState = OrchestratorState.INITIALIZING
        self._running = False
        self._working_directory = working_directory

        self.process_manager = ProcessManager(
            config.ai_coder.command,
            working_directory=working_directory,
            use_pty=config.ai_coder.use_pty,
            mirror_output=config.ai_coder.mirror_output,
        )
        self.workflow_manager = WorkflowManager(config.workflow)
        self.analysis_provider = self._create_analysis_provider()

        self.latest_output: str = ""
        self.latest_analysis: Optional[AnalysisResult] = None
        self._outcome_status: Optional[str] = None
        self._outcome_reason: Optional[str] = None
        self.failure_reason: Optional[str] = None

        self._states: Dict[OrchestratorState, State] = {
            OrchestratorState.INITIALIZING: InitializingState(),
            OrchestratorState.SENDING_INITIAL_PROMPT: SendingInitialPromptState(),
            OrchestratorState.AWAITING_COMPLETION: AwaitingCompletionState(),
            OrchestratorState.ANALYZING_RESPONSE: AnalyzingResponseState(),
            OrchestratorState.SENDING_CONTINUE_PROMPT: SendingContinuePromptState(),
            OrchestratorState.TASK_SUCCESSFUL: TaskSuccessfulState(),
            OrchestratorState.TASK_FAILED: TaskFailedState(),
            OrchestratorState.SHUTTING_DOWN: ShuttingDownState(),
        }

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @property
    def config(self) -> OrchestratorConfig:
        return self._config

    @property
    def working_directory(self) -> Optional[Path]:
        return self._working_directory

    def _create_analysis_provider(self) -> Optional[AnalysisProvider]:
        if not self._config.analysis.enabled:
            self._logger.info("Analysis provider disabled in configuration")
            return None

        if not self._config.analysis.provider or not self._config.analysis.model:
            raise ValueError(
                "Analysis provider and model must be configured when analysis is enabled"
            )

        provider_name = self._config.analysis.provider.lower()
        if provider_name != "deepseek":
            raise ValueError(f"Unsupported analysis provider: {self._config.analysis.provider}")

        return DeepSeekProvider(model=self._config.analysis.model)

    def run(self) -> None:
        self._running = True
        while self._running:
            state_enum = self._state_enum
            state = self._states[state_enum]
            self._logger.debug("Handling state: %s", state_enum.value)

            try:
                state.handle(self)
            except Exception as error:  # pragma: no cover - defensive guard
                self.record_failure(f"Unhandled error in state {state_enum.value}: {error}")
                self._logger.exception("Unhandled error in state %s", state_enum.value)
                self.transition_to(OrchestratorState.TASK_FAILED)

    def transition_to(self, new_state: OrchestratorState) -> None:
        if new_state not in self._states:
            raise ValueError(f"Unknown orchestrator state: {new_state!r}")

        self._logger.debug(
            "Transitioning from %s to %s", self._state_enum.value, new_state.value
        )
        self._state_enum = new_state

    def stop(self) -> None:
        self._running = False

    def set_outcome(self, status: str, reasoning: str) -> None:
        self._outcome_status = status
        self._outcome_reason = reasoning

    def record_failure(self, reason: str) -> None:
        self.failure_reason = reason

    @property
    def outcome_status(self) -> Optional[str]:
        return self._outcome_status

    @property
    def outcome_reason(self) -> Optional[str]:
        return self._outcome_reason


class InitializingState:
    """Prepare the orchestrator before sending commands."""

    _logging_configured: bool = False

    def handle(self, context: OrchestratorContext) -> None:
        self._ensure_logging(context)
        context.logger.info("Initializing orchestrator components")
        context.transition_to(OrchestratorState.SENDING_INITIAL_PROMPT)

    def _ensure_logging(self, context: OrchestratorContext) -> None:
        if self._logging_configured:
            return

        log_path = (context.working_directory or Path.cwd()) / "orchestrator.log"

        formatter = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

        self._logging_configured = True


class SendingInitialPromptState:
    """Send the initial workflow prompt to the managed process."""

    def handle(self, context: OrchestratorContext) -> None:
        prompt = context.workflow_manager.get_initial_prompt()
        context.logger.info("Sending initial prompt to process")

        try:
            context.process_manager.send_command(prompt)
        except Exception as error:
            context.record_failure(f"Failed to send initial prompt: {error}")
            context.transition_to(OrchestratorState.TASK_FAILED)
            return

        context.latest_output = ""
        context.transition_to(OrchestratorState.AWAITING_COMPLETION)


class AwaitingCompletionState:
    """Monitor the process output until completion is detected."""

    def handle(self, context: OrchestratorContext) -> None:
        ai_config = context.config.ai_coder
        context.logger.info("Awaiting completion indicator from process")

        try:
            output = context.process_manager.await_completion(
                completion_indicator=ai_config.completion_indicator,
                working_indicator=ai_config.working_indicator,
                timeout=ai_config.response_timeout,
            )
        except TimeoutError as error:
            context.record_failure(str(error))
            context.transition_to(OrchestratorState.TASK_FAILED)
            return
        except RuntimeError as error:
            context.record_failure(str(error))
            context.transition_to(OrchestratorState.TASK_FAILED)
            return

        context.latest_output = output
        context.transition_to(OrchestratorState.ANALYZING_RESPONSE)


class AnalyzingResponseState:
    """Use the intelligence layer to interpret captured output."""

    def handle(self, context: OrchestratorContext) -> None:
        if not context.latest_output:
            context.record_failure("No output available for analysis")
            context.transition_to(OrchestratorState.TASK_FAILED)
            return

        provider = context.analysis_provider
        if provider is None:
            context.logger.info(
                "Analysis disabled; assuming workflow completed successfully"
            )
            context.set_outcome("finished", "Analysis disabled in configuration")
            context.transition_to(OrchestratorState.TASK_SUCCESSFUL)
            return

        try:
            result = provider.analyze(context.latest_output)
        except Exception as error:
            context.record_failure(f"Analysis failed: {error}")
            context.transition_to(OrchestratorState.TASK_FAILED)
            return

        context.latest_analysis = result
        status = result.get("status")
        reasoning = result.get("reasoning", "")

        if status == "finished":
            context.set_outcome("finished", reasoning)
            context.transition_to(OrchestratorState.TASK_SUCCESSFUL)
        elif status == "continue":
            context.set_outcome("continue", reasoning)
            context.transition_to(OrchestratorState.SENDING_CONTINUE_PROMPT)
        elif status == "error":
            context.record_failure(reasoning or "Analysis reported an error")
            context.transition_to(OrchestratorState.TASK_FAILED)
        else:
            context.record_failure(
                f"Unexpected analysis status '{status}' received from provider"
            )
            context.transition_to(OrchestratorState.TASK_FAILED)


class SendingContinuePromptState:
    """Send the continue prompt when more work is required."""

    def handle(self, context: OrchestratorContext) -> None:
        prompt = context.workflow_manager.get_continue_prompt()
        context.logger.info("Sending continue prompt to process")

        try:
            context.process_manager.send_command(prompt)
        except Exception as error:
            context.record_failure(f"Failed to send continue prompt: {error}")
            context.transition_to(OrchestratorState.TASK_FAILED)
            return

        context.latest_output = ""
        context.transition_to(OrchestratorState.AWAITING_COMPLETION)


class TaskSuccessfulState:
    """Handle successful completion of the workflow."""

    def handle(self, context: OrchestratorContext) -> None:
        reasoning = context.outcome_reason or ""
        if reasoning:
            context.logger.info("Workflow completed successfully: %s", reasoning)
        else:
            context.logger.info("Workflow completed successfully")
        context.transition_to(OrchestratorState.SHUTTING_DOWN)


class TaskFailedState:
    """Handle terminal failure conditions."""

    def handle(self, context: OrchestratorContext) -> None:
        reason = context.failure_reason or context.outcome_reason or "Unknown failure"
        context.logger.error("Workflow failed: %s", reason)
        context.transition_to(OrchestratorState.SHUTTING_DOWN)


class ShuttingDownState:
    """Terminate the managed process and end the run loop."""

    def handle(self, context: OrchestratorContext) -> None:
        context.logger.info("Shutting down orchestrator")
        try:
            context.process_manager.terminate()
        except Exception as error:  # pragma: no cover - defensive guard
            context.logger.warning("Error while terminating process: %s", error)

        context.stop()


# ---------------------------------------------------------------------------
# Typer command-line interface
# ---------------------------------------------------------------------------


app = typer.Typer(help="AIAgent-Orchestrator command-line interface")


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO)


@app.command()
def run(
    config_path: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help=(
            "Path to the orchestrator configuration file. Defaults to"
            f" {DEFAULT_CONFIG_FILENAME} inside the workspace when omitted."
        ),
        show_default=False,
    ),
    workspace_path: Path = typer.Option(
        Path.cwd(),
        "--path",
        "-p",
        help="Working directory used when invoking the AI coding tool.",
        show_default=True,
    ),
) -> None:
    """Start the orchestrator using the provided configuration."""

    _configure_logging()
    logger = logging.getLogger(__name__)

    workspace = workspace_path.expanduser()

    if not workspace.exists():
        raise typer.BadParameter(
            f"Workspace directory does not exist: {workspace}", param_hint="--path"
        )
    if not workspace.is_dir():
        raise typer.BadParameter(
            f"Workspace path is not a directory: {workspace}",
            param_hint="--path",
        )

    workspace = workspace.resolve()

    if config_path is None:
        resolved_path = (workspace / DEFAULT_CONFIG_FILENAME).resolve()
        if not resolved_path.exists():
            try:
                write_default_config(resolved_path)
            except OSError as error:
                raise typer.BadParameter(
                    f"Unable to create default configuration at {resolved_path}: {error}",
                    param_hint="--config",
                ) from error
            logger.info("Generated default configuration: %s", resolved_path)
        else:
            logger.info("Using existing default configuration: %s", resolved_path)
    else:
        resolved_path = config_path.expanduser()
        if not resolved_path.is_absolute():
            resolved_path = (workspace / resolved_path).resolve()
        else:
            resolved_path = resolved_path.resolve()
        logger.info("Using configuration file: %s", resolved_path)

    try:
        config: OrchestratorConfig = load_config(resolved_path)
    except FileNotFoundError as error:
        raise typer.BadParameter(str(error), param_hint="--config") from error
    except ValueError as error:
        raise typer.BadParameter(f"Invalid configuration: {error}", param_hint="--config") from error

    logger.info("Using workspace directory: %s", workspace)
    logger.info("Launching orchestrator with command: %s", " ".join(config.ai_coder.command))

    context = OrchestratorContext(config, working_directory=workspace)
    context.run()


def main() -> NoReturn:
    """Entrypoint for executing the Typer application."""

    app()


__all__ = [
    "DEFAULT_CONFIG_CONTENT",
    "DEFAULT_CONFIG_FILENAME",
    "AICoderConfig",
    "AnalysisConfig",
    "AnalysisProvider",
    "AnalysisResult",
    "DeepSeekProvider",
    "OrchestratorConfig",
    "OrchestratorContext",
    "OrchestratorState",
    "ProcessManager",
    "WorkflowConfig",
    "WorkflowManager",
    "app",
    "load_config",
    "main",
    "run",
    "write_default_config",
]


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    main()

"""Process interaction layer for the orchestrator."""
from __future__ import annotations

import logging
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, TextIO


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


class ProcessManager:
    """Manage the lifecycle and I/O of the monitored AI coding tool process."""

    def __init__(self, command: List[str], working_directory: Optional[Path] = None) -> None:
        self._logger = logging.getLogger(__name__)
        if not command:
            raise ValueError("command must contain at least one argument")

        self._command = command
        self._working_directory = working_directory
        self._process: subprocess.Popen[str] = self._launch_process()
        self._output_queue: "queue.Queue[_StreamItem]" = queue.Queue()
        self._stdout_thread = self._start_stream_thread(self._process.stdout, "stdout")
        self._stderr_thread = self._start_stream_thread(self._process.stderr, "stderr")
        self._stdin_lock = threading.Lock()

    def _launch_process(self) -> subprocess.Popen[str]:
        """Create the subprocess configured for interactive communication."""

        try:
            process = subprocess.Popen(
                self._command,
                cwd=str(self._working_directory) if self._working_directory else None,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"Unable to start process: '{self._command[0]}' not found"
            ) from error

        self._logger.debug("Started process PID %s with command %s", process.pid, self._command)
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

    def _pump_stream(self, stream: TextIO, source: str) -> None:
        """Continuously read ``stream`` and push lines to the queue."""

        for line in iter(stream.readline, ""):
            cleaned = line.rstrip("\r\n")
            self._output_queue.put((source, cleaned))
        stream.close()
        self._logger.debug("Stream %s closed", source)

    def send_command(self, command_text: str) -> None:
        """Write ``command_text`` to the subprocess stdin."""

        if self._process.poll() is not None:
            raise RuntimeError("Cannot send command: process has terminated")

        if self._process.stdin is None:
            raise RuntimeError("Process stdin is not available")

        payload = command_text if command_text.endswith("\n") else f"{command_text}\n"

        with self._stdin_lock:
            self._process.stdin.write(payload)
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

            if self._process.poll() is not None and self._output_queue.empty():
                raise RuntimeError(
                    f"Process exited unexpectedly with code {self._process.returncode}"
                )

    def terminate(self) -> None:
        """Terminate the subprocess gracefully."""

        if self._process.poll() is not None:
            return

        self._logger.debug("Terminating process PID %s", self._process.pid)
        self._process.terminate()

        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._logger.warning("Process did not terminate gracefully; killing")
            self._process.kill()
            self._process.wait()


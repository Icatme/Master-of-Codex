"""Tests covering Windows-specific behaviour of :mod:`ai_orchestrator`."""

from __future__ import annotations

import logging
import sys
import time

import pytest

import ai_orchestrator


def test_windows_pty_fallback(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Ensure PTY mode gracefully falls back when wexpect is unavailable on Windows."""

    monkeypatch.setattr(ai_orchestrator.os, "name", "nt", raising=False)
    monkeypatch.setattr(ai_orchestrator, "wexpect", None, raising=False)

    caplog.set_level(logging.INFO)

    monkeypatch.setattr(ai_orchestrator.Path, "exists", lambda self: True, raising=False)

    command = [sys.executable, "-c", "import time; time.sleep(0.1)"]
    manager = ai_orchestrator.ProcessManager(command, use_pty=True)

    try:
        assert manager._pty_backend is None  # type: ignore[attr-defined]
        assert not manager._use_pty
        assert any(
            "PTY mode requested but not supported" in message for message in caplog.messages
        )
    finally:
        manager.terminate()
        time.sleep(0.05)

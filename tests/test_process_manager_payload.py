"""Unit tests for command payload normalisation."""

from ai_orchestrator import _prepare_command_payload


def test_prepare_payload_for_pipe_appends_newline() -> None:
    payload = _prepare_command_payload("run task", use_pty=False)
    assert payload == b"run task\n"


def test_prepare_payload_for_pipe_preserves_existing_newline() -> None:
    payload = _prepare_command_payload("status\n", use_pty=False)
    assert payload == b"status\n"


def test_prepare_payload_for_pty_uses_carriage_return() -> None:
    payload = _prepare_command_payload("analyze", use_pty=True)
    assert payload == b"analyze\r"


def test_prepare_payload_for_pty_trims_trailing_newline() -> None:
    payload = _prepare_command_payload("help\n", use_pty=True)
    assert payload == b"help\r"

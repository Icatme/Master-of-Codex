"""Tests covering configuration loading behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_orchestrator import DEFAULT_CONFIG_FILENAME, load_config


def _write_config(path: Path) -> Path:
    path.write_text(
        """\
ai_coder:
  command: python -c "print('ready')"
  completion_indicator: done
  response_timeout: 5
workflow:
  initial_prompt: start
  continue_prompt: continue
analysis:
  enabled: false
""",
        encoding="utf-8",
    )
    return path


def test_load_config_defaults_enable_mirroring(tmp_path: Path) -> None:
    """Mirror output should default to ``True`` when omitted."""

    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    _write_config(config_path)

    config = load_config(config_path)

    assert config.ai_coder.mirror_output is True


def test_load_config_rejects_non_boolean_mirror_output(tmp_path: Path) -> None:
    """Non-boolean ``mirror_output`` values should raise a :class:`ValueError`."""

    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    config_path.write_text(
        """\
ai_coder:
  command: python -c "print('ready')"
  completion_indicator: done
  response_timeout: 5
  mirror_output: "yes"
workflow:
  initial_prompt: start
  continue_prompt: continue
analysis:
  enabled: false
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_config(config_path)


def test_load_config_allows_disabling_timeout_with_zero(tmp_path: Path) -> None:
    """Setting ``response_timeout`` to zero should disable the timeout."""

    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    config_path.write_text(
        """\
ai_coder:
  command: python -c "print('ready')"
  completion_indicator: done
  response_timeout: 0
workflow:
  initial_prompt: start
  continue_prompt: continue
analysis:
  enabled: false
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.ai_coder.response_timeout is None


def test_load_config_allows_missing_timeout(tmp_path: Path) -> None:
    """Omitting ``response_timeout`` should default to no timeout."""

    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    config_path.write_text(
        """\
ai_coder:
  command: python -c "print('ready')"
  completion_indicator: done
workflow:
  initial_prompt: start
  continue_prompt: continue
analysis:
  enabled: false
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.ai_coder.response_timeout is None

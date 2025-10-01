# AIAgent-Orchestrator

AIAgent-Orchestrator is a Python command-line tool that supervises other AI coding CLIs. It watches the tool's streamed output for configured "working" and "completion" indicators, then asks an external reasoning model whether to keep the workflow going. The implementation follows the architecture captured in [Python%20AI%20编码工具自动化设计.md](../Python%20AI%20编码工具自动化设计.md).

## Features

- **Process interaction layer** built on `subprocess.Popen`, background threads, and a queue to collect non-blocking stdout/stderr streams.
- **Workflow supervision module** that provides configurable initial and continue prompts.
- **Intelligence layer** that can call DeepSeek's `deepseek-reasoner` model via the OpenAI-compatible SDK to decide whether to continue.
- **Supervisor core** implemented with the State pattern to coordinate initialization, prompt delivery, output monitoring, analysis, and shutdown. Logging is written to both the console and `orchestrator.log`.

## Project layout

```
aiagent-orchestrator/
├── pyproject.toml
├── requirements.txt
├── src/
│   └── ai_orchestrator/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── intelligence.py
│       ├── process_manager.py
│       ├── supervisor.py
│       └── workflow_manager.py
└── tests/
    ├── __init__.py
    └── manual/
        ├── fake_ai_tool.py
        └── manual_test_config.yml
```

## Installation

1. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

2. Install the project dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. (Optional) Install the package in editable mode for local development:

   ```bash
   pip install -e .
   ```

## Configuration

The orchestrator is configured with a YAML file. The schema matches the design document and looks like the example below:

```yaml
# config.yml
ai_coder:
  command: "codex"
  working_indicator: "Esc to interrupt"
  completion_indicator: "此阶段任务已经完成"
  response_timeout: 180

workflow:
  initial_prompt: "根据AGENTS.md开始工作"
  continue_prompt: "Continue."

analysis:
  enabled: true
  provider: "deepseek"
  model: "deepseek-reasoner"
```

Key notes:

- `command` can be either a string or a list of arguments. The loader splits strings with `shlex.split`.
- When `analysis.enabled` is `true`, set the `DEEPSEEK_API_KEY` environment variable (or pass `api_key` to `DeepSeekProvider`).
- When the analysis layer is disabled, the orchestrator assumes the workflow is finished once the completion indicator appears.

Pass the configuration path with the CLI option `--config /path/to/config.yml`. If omitted, `config.yml` in the current working directory is used.

## Running the CLI

After installing dependencies and preparing a configuration file, start the orchestrator via Typer. Either install the package (e.g. `pip install -e .`) or set `PYTHONPATH=src` before invoking the module.

```bash
PYTHONPATH=src python -m ai_orchestrator --config config.yml
```

The CLI configures logging on start-up. Messages are printed to stdout and appended to `orchestrator.log`.

## Manual test workflow

A lightweight manual integration test is provided under `tests/manual/`. It exercises the entire orchestrator loop against a simulated AI coding tool.

1. Ensure the analysis layer is disabled or provide a DeepSeek API key. The bundled config disables analysis.
2. From the project root, run the orchestrator with the manual test configuration (set `PYTHONPATH=src` if the package is not installed):

   ```bash
   PYTHONPATH=src python -m ai_orchestrator --config tests/manual/manual_test_config.yml
   ```

3. The fake tool prints a short sequence of messages, including the configured completion indicator. The orchestrator should log the prompts being sent, capture the output, and exit successfully after writing `orchestrator.log`.

Inspect the generated log file and console output to verify the control loop is functioning as expected.

## Troubleshooting

- **Process fails to start** – confirm the command in `ai_coder.command` is available on your PATH. The orchestrator raises `FileNotFoundError` if the executable cannot be launched.
- **Timeout waiting for completion** – increase `response_timeout` or verify the completion indicator string matches the tool's output exactly.
- **DeepSeek analysis errors** – ensure `openai` is installed, `DEEPSEEK_API_KEY` is set, and the configured model is supported.

## License

This project is licensed under the MIT License. See [LICENSE](../LICENSE) for details.

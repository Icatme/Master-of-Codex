# AIAgent-Orchestrator

AIAgent-Orchestrator is a Python command-line tool that supervises other AI coding CLIs. It watches the tool's streamed output for configured "working" and "completion" indicators, then asks an external reasoning model whether to keep the workflow going. The implementation follows the architecture captured in [Python%20AI%20编码工具自动化设计.md](../Python%20AI%20编码工具自动化设计.md).

**AIAgent-Orchestrator** 是一个用于监管其他 AI 编码命令行工具的 Python 命令行应用。它会实时监听被监管工具的输出，根据配置的“工作中”与“完成”指示信息判断进展，并在需要时调用外部推理模型来决定是否继续推进任务。项目的架构细节可参考《[Python AI 编码工具自动化设计.md](../Python%20AI%20编码工具自动化设计.md)》文档。

## Features

- **Process interaction layer** built on `subprocess.Popen`, background threads, and a queue to collect non-blocking stdout/stderr streams.
- **Workflow supervision module** that provides configurable initial and continue prompts.
- **Intelligence layer** that can call DeepSeek's `deepseek-reasoner` model via the OpenAI-compatible SDK to decide whether to continue.
- **Supervisor core** implemented with the State pattern to coordinate initialization, prompt delivery, output monitoring, analysis, and shutdown. Logging is written to both the console and `orchestrator.log`.

## 功能亮点

- **进程交互层**：基于 `subprocess.Popen`、后台线程与队列，实现对子进程标准输出与标准错误的无阻塞监听。
- **工作流监管模块**：提供可配置的初始提示与继续提示，统一管理交互内容。
- **智能分析层**：可选地调用 DeepSeek 的 `deepseek-reasoner` 模型，自动判断是否继续执行后续步骤。
- **监督核心**：通过状态模式协调初始化、提示发送、输出监听、结果分析与收尾，日志会同时写入终端和 `orchestrator.log` 文件。

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

## 安装步骤

1. 创建并激活虚拟环境：

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows 平台使用 .venv\Scripts\activate
   ```

2. 安装项目依赖：

   ```bash
   pip install -r requirements.txt
   ```

3. （可选）以开发模式安装，便于本地调试：

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
  use_pty: true

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
- `use_pty` enables PTY-based interaction on POSIX systems so tools such as the Codex CLI receive keystrokes even without a real terminal. The orchestrator automatically falls back to regular pipes when PTY support is unavailable (for example on Windows).
- When `analysis.enabled` is `true`, set the `DEEPSEEK_API_KEY` environment variable (or pass `api_key` to `DeepSeekProvider`).
- When the analysis layer is disabled, the orchestrator assumes the workflow is finished once the completion indicator appears.

Pass the configuration path with the CLI option `--config /path/to/config.yml`. If omitted, `config.yml` in the current working directory is used.

## 配置说明

编排器通过 YAML 文件进行配置，结构与设计文档保持一致，示例见上文代码块。

- `command` 可以是字符串或参数列表，配置加载器会在字符串模式下自动拆分参数。
- 当 `analysis.enabled` 为 `true` 时，请设置 `DEEPSEEK_API_KEY` 环境变量（或在代码中传入 `api_key`）。
- 若禁用智能分析层，编排器在检测到完成指示后会直接判定工作流结束。

可使用 `--config /path/to/config.yml` 指定配置路径，默认读取当前工作目录下的 `config.yml`。

## Running the CLI

After installing dependencies and preparing a configuration file, start the orchestrator via Typer. Either install the package (e.g. `pip install -e .`) or set `PYTHONPATH=src` before invoking the module.

```bash
PYTHONPATH=src python -m ai_orchestrator --config config.yml
```

The CLI configures logging on start-up. Messages are printed to stdout and appended to `orchestrator.log`.

## 运行命令行

安装依赖并准备好配置文件后，可通过 Typer 启动编排器。若未安装为包，请在运行前设置 `PYTHONPATH=src`。

```bash
PYTHONPATH=src python -m ai_orchestrator --config config.yml
```

CLI 启动时会完成日志配置，信息将同时输出到终端与 `orchestrator.log`。

## Manual test workflow

A lightweight manual integration test is provided under `tests/manual/`. It exercises the entire orchestrator loop against a simulated AI coding tool.

1. Ensure the analysis layer is disabled or provide a DeepSeek API key. The bundled config disables analysis.
2. From the project root, run the orchestrator with the manual test configuration (set `PYTHONPATH=src` if the package is not installed):

   ```bash
   PYTHONPATH=src python -m ai_orchestrator --config tests/manual/manual_test_config.yml
   ```

3. The fake tool prints a short sequence of messages, including the configured completion indicator. The orchestrator should log the prompts being sent, capture the output, and exit successfully after writing `orchestrator.log`.

Inspect the generated log file and console output to verify the control loop is functioning as expected.

## 手动测试流程

`tests/manual/` 目录提供了一个轻量级的集成测试示例，可通过模拟的 AI 工具验证完整的编排流程。

1. 确保已禁用分析层，或提前配置好 DeepSeek API Key。示例配置默认禁用分析。
2. 在项目根目录运行以下命令（若未安装为包，请先设置 `PYTHONPATH=src`）：

   ```bash
   PYTHONPATH=src python -m ai_orchestrator --config tests/manual/manual_test_config.yml
   ```

3. 虚拟工具会输出一系列信息，包括配置的完成指示。编排器应记录发送的提示、捕获输出，并在写入 `orchestrator.log` 后正常退出。

请检查日志文件与终端输出，确认控制循环按预期执行。

## Troubleshooting

- **Process fails to start** – confirm the command in `ai_coder.command` is available on your PATH. The orchestrator raises `FileNotFoundError` if the executable cannot be launched.
- **Timeout waiting for completion** – increase `response_timeout` or verify the completion indicator string matches the tool's output exactly.
- **DeepSeek analysis errors** – ensure `openai` is installed, `DEEPSEEK_API_KEY` is set, and the configured model is supported.

## 常见问题排查

- **进程无法启动**：确认 `ai_coder.command` 中的可执行文件已在 PATH 中，否则会抛出 `FileNotFoundError`。
- **等待完成时超时**：可适当增大 `response_timeout`，或确认完成指示字符串与实际输出完全一致。
- **DeepSeek 分析报错**：请确保已安装 `openai` 库，并设置 `DEEPSEEK_API_KEY`，同时检查模型名称是否受支持。

## License

This project is licensed under the MIT License. See [LICENSE](../LICENSE) for details.

## 许可证

本项目采用 MIT 许可证，详情请参阅 [LICENSE](../LICENSE)。

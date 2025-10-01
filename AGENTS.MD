好的，根据我们详细的设计文档，我将为您生成两个关键文件：

1.  **`AGENTS.MD`**: 这个文件将作为给AI编码工具（如Codex）的全局指令和上下文。它描述了项目的目标、架构、编码规范和测试方法，确保AI在开发过程中遵循我们的设计原则。
2.  **`todo.md`**: 这是一个详细、分步的任务清单。AI编码工具将按照这个清单来逐一实现“AI编码助手编排器”的各个组件和功能。

-----

### AGENTS.MD

# AGENTS.MD for AIAgent-Orchestrator Project

This document provides the necessary context and guidelines for an AI coding agent to build the "AIAgent-Orchestrator" tool.

## 1\. Project Overview

The goal is to build a Python-based command-line tool named "AIAgent-Orchestrator". This tool will supervise and automate other interactive AI coding CLI tools (like Codex, Claude CLI, etc.).

Its primary function is not to feed tasks to the AI tool, but to monitor its output for a specific "completion indicator" signal. When this signal is detected, the orchestrator will use an external analysis LLM (DeepSeek Reasoner) to decide if the AI tool has finished its overall job or if it needs to be prompted to continue. This creates a "monitor-analyze-incentivize" loop, enabling the AI tool to complete complex, multi-step tasks without human intervention.
本项目设计文档为"Python AI 编码工具自动化设计.md"
工作计划位于"ToDO.md"

## 2\. Core Technologies

  - **Language**: Python 3.10+
  - **CLI Framework**: Typer
  - **Configuration**: PyYAML for `config.yml` management
  - **Process Interaction**: `subprocess.Popen` with multi-threading for robust, non-blocking I/O. Consider abstracting `pexpect` (for Linux/macOS) and `wexpect` (for Windows) for a more professional implementation.
  - **AI Analysis**: DeepSeek API, specifically the `deepseek-reasoner` model, using a compatible OpenAI Python SDK.

## 3\. Architectural Principles

The tool must be built following a modular, state-driven architecture. Adherence to the design document is critical.

  - **Modularity**: The code must be separated into four distinct components:
    1.  `Process Interaction Layer`: Manages the AI tool's subprocess.
    2.  `Workflow Supervision Module`: Provides the initial and "continue" prompts.
    3.  `Intelligence Layer`: Handles communication with the DeepSeek API for analysis.
    4.  `Supervisor Core`: The central state machine that orchestrates the entire workflow.
  - **State Pattern**: The core logic in the `Supervisor Core` must be implemented using the State design pattern. Each major operational phase (e.g., `INITIALIZING`, `AWAITING_COMPLETION`, `ANALYZING_RESPONSE`) will be its own state class.
  - **Cross-Platform Compatibility**: All code must be OS-agnostic. Use `pathlib` for all file system paths and avoid shell-specific commands.

## 4\. Coding Style and Conventions

  - **Style**: Strictly adhere to PEP 8 guidelines. Use a code formatter like Black.
  - **Type Hinting**: All function signatures and variable declarations must include type hints.
  - **Project Structure**: The project must follow the `src` layout as defined in the design document:
    src/
    └── ai\_orchestrator/
    ├── **init**.py
    ├── **main**.py
    ├── cli.py
    ├── config.py
    ├── supervisor.py
    ├── process\_manager.py
    ├── workflow\_manager.py
    └── intelligence.py
    ```
    ```
  - **Logging**: Use Python's built-in `logging` module. Do not use `print()` for debugging or status updates. Each module should get its own logger instance via `logging.getLogger(__name__)`.
  - **Error Handling**: Implement robust `try...except` blocks, especially for file I/O, subprocess management, and API calls.

## 5\. Build and Test Commands

  - **Setup**:
      - Create a virtual environment: `python -m venv.venv`
      - Activate the environment: `source.venv/bin/activate` (Linux/macOS) or `.venv\Scripts\activate` (Windows)
      - Install dependencies: `pip install -r requirements.txt`
  - **Running Tests**:
      - Tests will be placed in a top-level `tests/` directory.
      - Run tests using pytest: `pytest`

## 6\. Commit and PR Guidelines

  - **Commit Messages**: Follow the Conventional Commits specification. (e.g., `feat: implement process interaction layer`, `fix: handle subprocess termination`).
  - **Pull Requests**: Each PR should correspond to a logical unit of work, preferably one or more related tasks from the `todo.md` file.

This `AGENTS.MD` file provides a comprehensive guide for any AI agent working on this project. It ensures that the final product aligns with the established design and quality standards.

```

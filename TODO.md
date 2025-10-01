### todo.md

# Todo List for AIAgent-Orchestrator

This is a step-by-step plan to build the AIAgent-Orchestrator tool. Complete the tasks in the specified order.

## Phase 1: Project Scaffolding and Basic Setup

- [x] Create the project root directory `aiagent-orchestrator`.
- [x] Inside the root, create the `src/ai_orchestrator` directory structure.
- [x] Create empty `__init__.py` files in `src/ai_orchestrator` and `tests`.
- [x] Create the main application files with placeholder content: `cli.py`, `config.py`, `supervisor.py`, `process_manager.py`, `workflow_manager.py`, `intelligence.py`.
- [x] Create a `pyproject.toml` file. Define project metadata and add initial dependencies: `typer`, `pyyaml`, `python-dotenv`.
- [x] Create a `requirements.txt` file listing the same dependencies.
- [x] Initialize a Git repository in the root directory.
- [x] Create a `.gitignore` file to exclude `.venv`, `__pycache__`, `.env`, and other common files.

## Phase 2: Configuration and CLI Entrypoint

- [x] **`config.py`**: Implement a function to load and parse `config.yml` using `PyYAML`. Ensure it uses `yaml.safe_load()`.
- [x] **`config.py`**: Create a data class or dictionary structure to hold the configuration, matching the schema in the design document.
- [x] **`cli.py`**: Set up the main Typer application.
- [x] **`cli.py`**: Create the main `run` command that will instantiate and start the orchestrator.
- [x] **`__main__.py`**: Implement the entry point to call the Typer app from `cli.py`. This allows running the module with `python -m ai_orchestrator`.

## Phase 3: Implement Core Components (Bottom-Up)

### 3.1 Process Interaction Layer

- [x] **`process_manager.py`**: Create the `ProcessManager` class.
- [x] **`process_manager.py`**: Implement the `__init__` method to start a child process using `subprocess.Popen`. It should take the command as an argument and configure `stdin`, `stdout`, `stderr` to `subprocess.PIPE`.
- [x] **`process_manager.py`**: Implement the `send_command(command_text: str)` method. Ensure it appends a newline and flushes `stdin`.
- [x] **`process_manager.py`**: Implement the real-time, non-blocking output monitoring logic. Use a background thread and a `queue.Queue` to read `stdout` line-by-line and make it available to the main thread.
- [x] **`process_manager.py`**: Implement the `await_completion(completion_indicator: str, working_indicator: str, timeout: int)` method. This method should read from the output queue, check for the indicators, and return the captured output upon completion or raise a timeout exception.
- [x] **`process_manager.py`**: Implement the `terminate()` method for graceful shutdown of the subprocess.
- [x] **`process_manager.py`**: Add error handling for `FileNotFoundError` on startup and for unexpected process termination.

### 3.2 Workflow Supervision Module

- [x] **`workflow_manager.py`**: Create the `WorkflowManager` class.
- [x] **`workflow_manager.py`**: Implement the `__init__` method to accept the loaded configuration.
- [x] **`workflow_manager.py`**: Implement `get_initial_prompt()` and `get_continue_prompt()` methods that return the corresponding strings from the configuration.

### 3.3 Intelligence Layer

- [x] **`intelligence.py`**: Define an abstract base class `AnalysisProvider` with an `analyze(output: str) -> dict` method.
- [x] **`intelligence.py`**: Create the `DeepSeekProvider` class that inherits from `AnalysisProvider`.
- [x] **`intelligence.py`**: In `DeepSeekProvider`, implement logic to initialize the OpenAI-compatible client and load the `DEEPSEEK_API_KEY` from environment variables.
- [x] **`intelligence.py`**: Implement the `analyze` method. This method must construct the detailed prompt as specified in the design document, call the `deepseek-reasoner` model, and enforce JSON output using `response_format={'type': 'json_object'}`.
- [x] **`intelligence.py`**: Ensure the `analyze` method parses the JSON response and returns a dictionary containing `status` and `reasoning`. Add robust error handling for API calls and JSON parsing.

## Phase 4: Implement the Supervisor Core (State Machine)

- [x] **`supervisor.py`**: Define an `Enum` for all possible states (`INITIALIZING`, `SENDING_INITIAL_PROMPT`, `AWAITING_COMPLETION`, etc.).
- [x] **`supervisor.py`**: Create the abstract base class `State` with a `handle(context)` method.
- [x] **`supervisor.py`**: Create the main `OrchestratorContext` class. Its `__init__` should instantiate all core components (`ProcessManager`, `WorkflowManager`, `DeepSeekProvider`).
- [x] **`supervisor.py`**: Implement the `transition_to(new_state)` method in `OrchestratorContext`.
- [x] **`supervisor.py`**: Implement the main `run()` loop in `OrchestratorContext` that continuously calls `self._state.handle()`.
- [x] **`supervisor.py`**: Implement the `InitializingState` class. Its `handle` method should set up logging and transition to `SENDING_INITIAL_PROMPT`.
- [x] **`supervisor.py`**: Implement the `SendingInitialPromptState` class. Its `handle` method should get the initial prompt from the `WorkflowManager` and send it via the `ProcessManager`, then transition to `AWAITING_COMPLETION`.
- [x] **`supervisor.py`**: Implement the `AwaitingCompletionState` class. Its `handle` method should call `process_manager.await_completion()` and, upon success, transition to `ANALYZING_RESPONSE`.
- [x] **`supervisor.py`**: Implement the `AnalyzingResponseState` class. Its `handle` method should pass the captured output to the `IntelligenceLayer` and transition to the next state (`SENDING_CONTINUE_PROMPT`, `TASK_SUCCESSFUL`, or `TASK_FAILED`) based on the analysis result.
- [x] **`supervisor.py`**: Implement the `SendingContinuePromptState` class, which sends the "continue" prompt and transitions back to `AWAITING_COMPLETION`.
- [x] **`supervisor.py`**: Implement the terminal state classes (`TASK_SUCCESSFUL`, `TASK_FAILED`, `SHUTTING_DOWN`) that perform final actions and stop the main loop.

## Phase 5: Finalization and Documentation

- [x] Integrate the logging setup into the `InitializingState`. Ensure logs are written to both the console and a file (`orchestrator.log`).
- [x] Refine the main function in `cli.py` to correctly load the config, initialize `OrchestratorContext`, and call its `run()` method.
- [x] Write a `README.md` file for the project, explaining what the tool does, how to install it, and how to configure `config.yml`.
- [x] Manually test the complete application by running it against a simple interactive script to ensure the loop works as expected. (Tested with `PYTHONPATH=src python -m ai_orchestrator --config tests/manual/manual_test_config.yml`)
```

"""Supervisor core implementing the orchestrator state machine."""
from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, Optional, Protocol

from .config import OrchestratorConfig
from .intelligence import AnalysisProvider, AnalysisResult, DeepSeekProvider
from .process_manager import ProcessManager
from .workflow_manager import WorkflowManager


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

    def __init__(self, config: OrchestratorConfig) -> None:
        self._config = config
        self._logger = logging.getLogger(__name__)
        self._state_enum: OrchestratorState = OrchestratorState.INITIALIZING
        self._running = False

        self.process_manager = ProcessManager(config.ai_coder.command)
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
        """Return the module logger."""

        return self._logger

    @property
    def config(self) -> OrchestratorConfig:
        """Return the orchestrator configuration."""

        return self._config

    def _create_analysis_provider(self) -> Optional[AnalysisProvider]:
        """Initialise the configured analysis provider if enabled."""

        if not self._config.analysis.enabled:
            self._logger.info("Analysis provider disabled in configuration")
            return None

        provider_name = self._config.analysis.provider.lower()
        if provider_name != "deepseek":
            raise ValueError(f"Unsupported analysis provider: {self._config.analysis.provider}")

        return DeepSeekProvider(model=self._config.analysis.model)

    def run(self) -> None:
        """Start the state machine loop until termination."""

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
        """Switch the context to ``new_state``."""

        if new_state not in self._states:
            raise ValueError(f"Unknown orchestrator state: {new_state!r}")

        self._logger.debug(
            "Transitioning from %s to %s", self._state_enum.value, new_state.value
        )
        self._state_enum = new_state

    def stop(self) -> None:
        """Stop the orchestrator loop."""

        self._running = False

    def set_outcome(self, status: str, reasoning: str) -> None:
        """Store the latest outcome status and reasoning message."""

        self._outcome_status = status
        self._outcome_reason = reasoning

    def record_failure(self, reason: str) -> None:
        """Record a failure reason for later reporting."""

        self.failure_reason = reason

    @property
    def outcome_status(self) -> Optional[str]:
        """Return the latest outcome status."""

        return self._outcome_status

    @property
    def outcome_reason(self) -> Optional[str]:
        """Return the latest outcome reasoning."""

        return self._outcome_reason


class InitializingState:
    """Prepare the orchestrator before sending commands."""

    def handle(self, context: OrchestratorContext) -> None:
        context.logger.info("Initializing orchestrator components")
        context.transition_to(OrchestratorState.SENDING_INITIAL_PROMPT)


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

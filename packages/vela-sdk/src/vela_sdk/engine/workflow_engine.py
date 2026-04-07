"""Workflow state machine engine."""

import json
from typing import Any, Callable, Optional

import structlog

from vela_sdk.engine.dialog_handler import DIALOG_MODES, DialogHandler
from vela_sdk.engine.lifecycle import LifecycleChecker, _parse_duration_hours
from vela_sdk.engine.prompt_builder import PromptBuilder
from vela_sdk.engine.types import AdvanceResult, ErrorAction, WorkflowRunState, WorkflowRunStatus
from vela_sdk.schemas.resource import ResourceDefinition
from vela_sdk.schemas.workflow import (
    AnyStepDefinition,
    CaptureDefinition,
    LifecycleDefinition,
    StepType,
    WorkflowDefinition,
)
from vela_sdk.storage.protocol import WorkflowStore

logger = structlog.get_logger()


class WorkflowEngine:
    """Core workflow state machine engine.

    Works against the WorkflowStore protocol — no ORM dependency.
    All state is accessed via WorkflowRunState dataclass (dicts, not JSON strings).

    Composes DialogHandler, PromptBuilder, and LifecycleChecker for
    single-responsibility separation.
    """

    def __init__(self, store: WorkflowStore):
        self.store = store
        self._prompt_builder = PromptBuilder()
        self._dialog_handler = DialogHandler(store, self._prompt_builder)
        self._lifecycle_checker = LifecycleChecker()

    async def start_or_resume(
        self,
        workflow_def: WorkflowDefinition,
        params: Optional[dict] = None,
        project_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        parent_step_id: Optional[str] = None,
    ) -> tuple[WorkflowRunState, bool]:
        """Start a new run or resume an existing one.

        Returns (run, is_new).
        Uses identity params to find existing runs.
        """
        identity_params = {}
        if params:
            for p_def in workflow_def.params:
                if p_def.identity and p_def.name in params:
                    identity_params[p_def.name] = params[p_def.name]

        # Try to find existing run by identity
        if identity_params:
            existing = await self.store.find_by_identity(
                workflow_def.id, identity_params
            )
            if existing:
                return existing, False

        # Resolve default params
        resolved_params = {}
        if params:
            resolved_params.update(params)
        for p_def in workflow_def.params:
            if p_def.name not in resolved_params and p_def.default is not None:
                resolved_params[p_def.name] = p_def.default

        # Create new run
        first_step = workflow_def.steps[0].id if workflow_def.steps else None
        run = await self.store.create_run(
            workflow_id=workflow_def.id,
            workflow_version=workflow_def.version,
            params=resolved_params if resolved_params else None,
            project_id=project_id,
            parent_run_id=parent_run_id,
            parent_step_id=parent_step_id,
        )
        # Set the first step
        run = await self.store.update_step(run.id, first_step)

        return run, True

    async def advance(
        self,
        run: WorkflowRunState,
        workflow_def: WorkflowDefinition,
        step_output: Optional[str] = None,
        notes: Optional[str] = None,
        resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]] = None,
    ) -> AdvanceResult:
        """Advance workflow to the next step.

        Processes current step output, captures data, determines next step.
        """
        if run.status not in (WorkflowRunStatus.ACTIVE, WorkflowRunStatus.PAUSED):
            return AdvanceResult(run=run, completed=True)

        current_step = self._get_step(workflow_def, run.current_step)
        if not current_step:
            # No current step -- workflow is complete
            run = await self.store.update_step(run.id, None, status=WorkflowRunStatus.COMPLETED)
            return AdvanceResult(run=run, completed=True)

        # Dialog steps have their own advancement logic
        if current_step.type == StepType.DIALOG:
            return await self._dialog_handler.advance_dialog(
                run, workflow_def, current_step, step_output, notes,
                resolve_next_fn=self._resolve_next,
                get_step_fn=self._get_step,
                parse_step_output_fn=self._parse_step_output,
                resource_resolver=resource_resolver,
            )

        # Process captures
        state_updates: dict[str, Any] = {}
        if step_output and current_step.capture:
            output_captures = [c for c in current_step.capture if c.source == "output"]
            state_updates.update(self._parse_step_output(step_output, output_captures))

        if notes:
            state_updates["_notes"] = notes

        # Determine next step
        next_step_id = self._resolve_next(current_step, step_output, workflow_def)

        # Handle workflow step type (sub-workflow)
        if current_step.type == StepType.WORKFLOW and current_step.workflow_ref:
            run = await self.store.update_step(
                run.id, run.current_step, state_data=state_updates,
                status=WorkflowRunStatus.PAUSED,
            )
            return AdvanceResult(
                run=run,
                sub_workflow_ref=current_step.workflow_ref,
                sub_workflow_params=current_step.params_mapping,
            )

        if next_step_id:
            # Move to next step
            run = await self.store.update_step(run.id, next_step_id, state_data=state_updates)
            next_step = self._get_step(workflow_def, next_step_id)
            if next_step:
                prompt = self.assemble_prompt(workflow_def, run, next_step, resource_resolver=resource_resolver)
                return AdvanceResult(run=run, prompt=prompt)

        # No next step -- complete
        run = await self.store.update_step(
            run.id, run.current_step, state_data=state_updates,
            status=WorkflowRunStatus.COMPLETED,
        )
        return AdvanceResult(run=run, completed=True)

    # --- Delegated methods (maintain public API) ---

    def assemble_prompt(
        self,
        workflow_def: WorkflowDefinition,
        run: WorkflowRunState,
        step: Optional[AnyStepDefinition] = None,
        resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]] = None,
    ) -> str:
        """Assemble the prompt for a step."""
        if step is None:
            step = self._get_step(workflow_def, run.current_step)
        if not step:
            return ""
        return self._prompt_builder.assemble_prompt(workflow_def, run, step, resource_resolver=resource_resolver)

    def resolve_templates(self, text: str, context: dict) -> str:
        """Resolve {{variable}} templates in text."""
        return PromptBuilder.resolve_templates(text, context)

    def _build_template_context(
        self,
        workflow_def: WorkflowDefinition,
        run: WorkflowRunState,
    ) -> dict[str, Any]:
        """Build nested context dict for template resolution."""
        return PromptBuilder.build_template_context(workflow_def, run)

    @staticmethod
    def _assemble_resources(
        workflow_def: WorkflowDefinition,
        step: AnyStepDefinition,
        resource_resolver: Callable[[str], Optional[ResourceDefinition]],
    ) -> list[str]:
        """Assemble resource sections for the prompt."""
        return PromptBuilder.assemble_resources(workflow_def, step, resource_resolver)

    def validate_depends_on(
        self, run: WorkflowRunState, step: AnyStepDefinition
    ) -> tuple[bool, list[str]]:
        """Validate that all depends_on fields exist in state.

        Returns (is_valid, missing_keys).
        """
        if not step.depends_on:
            return True, []

        state = run.state_data
        missing: list[str] = []
        for dep in step.depends_on:
            for field in dep.fields:
                if field not in state:
                    missing.append(field)
        return len(missing) == 0, missing

    def handle_on_error(
        self,
        run: WorkflowRunState,
        step: AnyStepDefinition,
        error: str,
    ) -> ErrorAction:
        """Determine error handling action for a step."""
        if not step.on_error:
            return ErrorAction(action="abort", message=error)

        on_err = step.on_error
        if on_err.retry and on_err.retry > 0:
            return ErrorAction(action="retry", message=on_err.message or error)
        elif on_err.fallback:
            return ErrorAction(
                action="fallback",
                fallback_step=on_err.fallback,
                message=on_err.message or error,
            )
        return ErrorAction(action="abort", message=on_err.message or error)

    def check_lifecycle(
        self,
        run: WorkflowRunState,
        lifecycle: Optional[LifecycleDefinition],
    ) -> Optional[WorkflowRunStatus]:
        """Check if lifecycle rules require a status change."""
        return self._lifecycle_checker.check_lifecycle(run, lifecycle)

    @staticmethod
    def _get_dialog_phases(step: AnyStepDefinition):
        """Return dialog phases: explicit phases override mode lookup."""
        return DialogHandler.get_dialog_phases(step)

    @staticmethod
    def _parse_step_output(
        step_output: str | None, captures: list[CaptureDefinition]
    ) -> dict[str, Any]:
        """Parse step_output and assign per-key values.

        - If output is a JSON dict -> extract value per capture.key
        - If output is plain string and only 1 capture -> assign directly
        - If output is plain string and N captures -> assign whole string to each
        """
        if not step_output or not captures:
            return {}

        # Try JSON parse
        try:
            parsed = json.loads(step_output)
            if isinstance(parsed, dict):
                result: dict[str, Any] = {}
                for cap in captures:
                    if cap.key in parsed:
                        result[cap.key] = parsed[cap.key]
                    else:
                        # Key not in JSON -> assign whole output as fallback
                        result[cap.key] = step_output
                return result
        except (json.JSONDecodeError, ValueError):
            pass

        # Plain string
        return {cap.key: step_output for cap in captures}

    def _get_step(
        self, workflow_def: WorkflowDefinition, step_id: Optional[str]
    ) -> Optional[AnyStepDefinition]:
        """Get step definition by ID."""
        if not step_id:
            return None
        for step in workflow_def.steps:
            if step.id == step_id:
                return step
        return None

    def _resolve_next(
        self,
        current_step: AnyStepDefinition,
        output: Optional[str],
        workflow_def: WorkflowDefinition,
    ) -> Optional[str]:
        """Resolve the next step ID.

        Priority: choice option.next > step.next > sequential.
        """
        # For choice steps, check if output matches an option with a specific next
        if current_step.type == StepType.CHOICE and output and current_step.options:
            for opt in current_step.options:
                if opt.key == output and opt.next:
                    return opt.next

        # Explicit next
        if current_step.next:
            return current_step.next

        # Sequential -- find next step in definition
        step_ids = [s.id for s in workflow_def.steps]
        try:
            idx = step_ids.index(current_step.id)
            if idx + 1 < len(step_ids):
                return step_ids[idx + 1]
        except ValueError:
            pass

        return None

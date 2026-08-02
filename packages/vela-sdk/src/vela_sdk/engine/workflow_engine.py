"""Workflow state machine engine."""

import dataclasses
import json
from typing import Any, Callable, Optional

import structlog

from vela_sdk.engine.dialog_handler import DIALOG_MODES, DialogHandler
from vela_sdk.engine.lifecycle import LifecycleChecker, _parse_duration_hours
from vela_sdk.engine.prompt_builder import PromptBuilder
from vela_sdk.engine.types import AdvanceResult, ErrorAction, WorkflowRunState, WorkflowRunStatus
from vela_sdk.locale import Locale
from vela_sdk.schemas.resource import ResourceDefinition
from vela_sdk.schemas.workflow import (
    AnyStepDefinition,
    CaptureDefinition,
    LifecycleDefinition,
    McpCallStep,
    StepType,
    WorkflowDefinition,
)
from vela_sdk.sources.registry import resolve_source
from vela_sdk.sources.types import SourceContext
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
        resolved_params: Optional[dict] = None,
    ) -> tuple[WorkflowRunState, bool]:
        """Start a new run or resume an existing one.

        Returns (run, is_new).
        Uses identity params to find existing runs.

        ``resolved_params`` supplies values for params flagged ``resolve:
        True`` — already resolved by the calling app from its own context
        (analogous to how identity params are supplied). Exposed in
        templates as ``{{resolved.x}}``; wins over ``params``/defaults for
        resolve-flagged param names.
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
        final_params = {}
        if params:
            final_params.update(params)
        for p_def in workflow_def.params:
            if p_def.name not in final_params and p_def.default is not None:
                final_params[p_def.name] = p_def.default
        if resolved_params:
            for p_def in workflow_def.params:
                if p_def.resolve and p_def.name in resolved_params:
                    final_params[p_def.name] = resolved_params[p_def.name]

        # Create new run
        first_step = workflow_def.steps[0].id if workflow_def.steps else None
        run = await self.store.create_run(
            workflow_id=workflow_def.id,
            workflow_version=workflow_def.version,
            params=final_params if final_params else None,
            project_id=project_id,
            parent_run_id=parent_run_id,
            parent_step_id=parent_step_id,
        )
        # Set the first step
        run = await self.store.update_step(run.id, first_step)

        # Run the first step's `fetch` definitions (if any) now — it's the
        # only place this can happen, since `assemble_prompt` for the first
        # step is called separately by the caller after this returns.
        first_step_def = self._get_step(workflow_def, first_step) if first_step else None
        if first_step_def and first_step_def.fetch:
            on_err = first_step_def.on_error
            max_attempts = on_err.retry + 1 if on_err and on_err.retry > 0 else 1
            fetch_data: Optional[dict] = None
            last_error_message: Optional[str] = None

            for _attempt in range(max_attempts):
                try:
                    fetch_data = await self._execute_fetches(first_step_def, run, workflow_def, None, None)
                    break
                except Exception as err:  # noqa: BLE001 — surfaced via on_error
                    last_error_message = str(err)

            if fetch_data is not None:
                run = await self.store.update_step(run.id, run.current_step, state_data={"_fetch": fetch_data})
            else:
                run, _message, _fallback_step = await self._transition_on_failure(
                    run, first_step_def, workflow_def, last_error_message or "fetch failed",
                )

        return run, True

    async def advance(
        self,
        run: WorkflowRunState,
        workflow_def: WorkflowDefinition,
        step_output: Optional[str] = None,
        notes: Optional[str] = None,
        resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]] = None,
        locale: Optional[Locale] = None,
        project_data_resolver: Optional[Callable[[str], Optional[dict]]] = None,
        signal: Optional[Any] = None,
        log: Optional[Callable[..., None]] = None,
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

        # mcp_call steps make a single server-side tool call via the source
        # registry (vela_sdk.sources.registry) and auto-advance — no agent
        # round-trip. Unlike agent-executed step types, this runs in-engine,
        # so on_error (retry/fallback/abort) is applied automatically.
        if current_step.type == StepType.MCP_CALL:
            on_err = current_step.on_error
            max_attempts = on_err.retry + 1 if on_err and on_err.retry > 0 else 1
            mcp_result: Any = None
            handler_succeeded = False
            last_error_message: Optional[str] = None

            for _attempt in range(max_attempts):
                try:
                    mcp_result = await self._execute_mcp_call_step(current_step, run, workflow_def, signal, log)
                    handler_succeeded = True
                    break
                except Exception as err:  # noqa: BLE001 — surfaced via on_error
                    last_error_message = str(err)

            if not handler_succeeded:
                return await self._apply_engine_step_failure(
                    run, current_step, workflow_def, last_error_message or "mcp_call failed",
                    resource_resolver, locale, project_data_resolver,
                )

            step_output = mcp_result if isinstance(mcp_result, str) else json.dumps(mcp_result)

        # Dialog steps have their own advancement logic
        if current_step.type == StepType.DIALOG:
            async def _resolve_fetches(step, r, wf_def):
                return await self._resolve_fetches_and_apply(
                    step, r, wf_def, resource_resolver, locale, project_data_resolver, signal, log,
                )

            return await self._dialog_handler.advance_dialog(
                run, workflow_def, current_step, step_output, notes,
                resolve_next_fn=self._resolve_next,
                get_step_fn=self._get_step,
                parse_step_output_fn=self._parse_step_output,
                resource_resolver=resource_resolver,
                locale=locale,
                resolve_fetches_fn=_resolve_fetches,
                project_data_resolver=project_data_resolver,
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
            next_step = self._get_step(workflow_def, next_step_id)

            # Run this step's `fetch` definitions (if any) before landing on
            # it, so {{fetch.x}} is populated by the time its prompt is
            # assembled. `_try_resolve_fetches` no-ops fast when there's
            # nothing to fetch and no stale `_fetch` to clear.
            if next_step:
                landed_run = dataclasses.replace(
                    run, current_step=next_step_id, state_data={**run.state_data, **state_updates},
                )
                fetch_data, fetch_error = await self._try_resolve_fetches(next_step, landed_run, workflow_def, signal, log)
                if fetch_error is not None:
                    run = await self.store.update_step(run.id, next_step_id, state_data=state_updates)
                    return await self._apply_engine_step_failure(
                        run, next_step, workflow_def, fetch_error,
                        resource_resolver, locale, project_data_resolver,
                    )
                if fetch_data is not None:
                    state_updates["_fetch"] = fetch_data

            # Move to next step
            run = await self.store.update_step(run.id, next_step_id, state_data=state_updates)
            if next_step:
                prompt = self.assemble_prompt(
                    workflow_def, run, next_step, resource_resolver=resource_resolver, locale=locale,
                    project_data_resolver=project_data_resolver,
                )
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
        locale: Optional[Locale] = None,
        project_data_resolver: Optional[Callable[[str], Optional[dict]]] = None,
    ) -> str:
        """Assemble the prompt for a step."""
        if step is None:
            step = self._get_step(workflow_def, run.current_step)
        if not step:
            return ""
        return self._prompt_builder.assemble_prompt(
            workflow_def, run, step, resource_resolver=resource_resolver, locale=locale,
            project_data_resolver=project_data_resolver,
        )

    async def pause_run(
        self,
        run: WorkflowRunState,
        workflow_def: WorkflowDefinition,
    ) -> WorkflowRunState:
        """Explicitly pause an active run.

        Raises if the run isn't ACTIVE, or if ``workflow_def.lifecycle.allow_pause``
        is False. Resuming is just calling ``advance()`` again — it already
        accepts runs in PAUSED status.
        """
        if run.status != WorkflowRunStatus.ACTIVE:
            raise ValueError(f"cannot pause run '{run.id}' — status is '{run.status}', not 'active'")
        if workflow_def.lifecycle and workflow_def.lifecycle.allow_pause is False:
            raise ValueError(f"workflow '{workflow_def.id}' has lifecycle.allow_pause: False")
        return await self.store.update_step(run.id, run.current_step, status=WorkflowRunStatus.PAUSED)

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

    # --- mcp_call / fetch execution ---

    async def _execute_mcp_call_step(
        self,
        step: McpCallStep,
        run: WorkflowRunState,
        workflow_def: WorkflowDefinition,
        signal: Optional[Any],
        log: Optional[Callable[..., None]],
    ) -> Any:
        """Run the registered source handler for an mcp_call step.

        Raises ValueError if mcp_source/mcp_tool are missing, or no handler
        is registered for mcp_source.
        """
        if not step.mcp_source or not step.mcp_tool:
            raise ValueError(f"mcp_call step '{step.id}' is missing mcp_source/mcp_tool")
        handler = resolve_source(step.mcp_source)
        if not handler:
            raise ValueError(f"No handler registered for source '{step.mcp_source}' (mcp_call step '{step.id}')")

        template_ctx = PromptBuilder.build_template_context(workflow_def, run)
        resolved_params = self._resolve_vars_deep(step.mcp_params, template_ctx)
        ctx = SourceContext(signal=signal, log=log or (lambda msg, meta=None: None))
        return await handler(step.mcp_tool, resolved_params, ctx)

    async def _execute_fetches(
        self,
        step: AnyStepDefinition,
        run: WorkflowRunState,
        workflow_def: WorkflowDefinition,
        signal: Optional[Any],
        log: Optional[Callable[..., None]],
    ) -> dict[str, Any]:
        """Run every `fetch` definition on `step` via the source registry."""
        template_ctx = PromptBuilder.build_template_context(workflow_def, run)
        ctx = SourceContext(signal=signal, log=log or (lambda msg, meta=None: None))

        result: dict[str, Any] = {}
        for fetch_def in step.fetch:
            handler = resolve_source(fetch_def.source)
            if not handler:
                raise ValueError(
                    f"No handler registered for source '{fetch_def.source}' "
                    f"(fetch key '{fetch_def.key}' on step '{step.id}')"
                )
            resolved_params = self._resolve_vars_deep(fetch_def.params, template_ctx)
            result[fetch_def.key] = await handler(fetch_def.action, resolved_params, ctx)
        return result

    async def _try_resolve_fetches(
        self,
        step: AnyStepDefinition,
        run: WorkflowRunState,
        workflow_def: WorkflowDefinition,
        signal: Optional[Any],
        log: Optional[Callable[..., None]],
    ) -> tuple[Optional[dict], Optional[str]]:
        """Resolve `step.fetch` (if any), applying on_error's retry count.

        Returns (fetch_data, error_message) — exactly one is not None.
        `fetch_data` is None (no error) when the step declares no `fetch`
        and there's no stale `_fetch` to clear — zero behavior change for
        workflows that don't use `fetch`.
        """
        if not step.fetch:
            return ({} if "_fetch" in run.state_data else None), None

        on_err = step.on_error
        max_attempts = on_err.retry + 1 if on_err and on_err.retry > 0 else 1
        last_error_message: Optional[str] = None

        for _attempt in range(max_attempts):
            try:
                fetch_data = await self._execute_fetches(step, run, workflow_def, signal, log)
                return fetch_data, None
            except Exception as err:  # noqa: BLE001 — surfaced via on_error
                last_error_message = str(err)

        return None, (last_error_message or "fetch failed")

    async def _resolve_fetches_and_apply(
        self,
        step: AnyStepDefinition,
        run: WorkflowRunState,
        workflow_def: WorkflowDefinition,
        resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]],
        locale: Optional[Locale],
        project_data_resolver: Optional[Callable[[str], Optional[dict]]],
        signal: Optional[Any],
        log: Optional[Callable[..., None]],
    ) -> tuple[bool, Any]:
        """`resolve_fetches_fn` passed to `DialogHandler.advance_dialog`.

        On success, persists `_fetch` (if any) and returns (True, updated
        run). On failure, applies on_error and returns (False, AdvanceResult).
        """
        fetch_data, error = await self._try_resolve_fetches(step, run, workflow_def, signal, log)
        if error is not None:
            result = await self._apply_engine_step_failure(
                run, step, workflow_def, error, resource_resolver, locale, project_data_resolver,
            )
            return False, result
        if fetch_data is None:
            return True, run
        updated = await self.store.update_step(run.id, run.current_step, state_data={"_fetch": fetch_data})
        return True, updated

    async def _transition_on_failure(
        self,
        run: WorkflowRunState,
        step: AnyStepDefinition,
        workflow_def: WorkflowDefinition,
        error_message: str,
    ) -> tuple[WorkflowRunState, str, Optional[AnyStepDefinition]]:
        """Apply step.on_error (fallback/abort) and persist the resulting transition.

        Shared core used both by `_apply_engine_step_failure` (which also
        assembles the fallback step's prompt) and `start_or_resume`'s
        first-step `fetch` handling (which doesn't need a prompt — the
        caller assembles one separately after `start_or_resume` returns).
        """
        error_action = self.handle_on_error(run, step, error_message)
        message = error_action.message or error_message

        if error_action.action == "fallback" and error_action.fallback_step:
            fallback_step = self._get_step(workflow_def, error_action.fallback_step)
            run = await self.store.update_step(
                run.id, error_action.fallback_step, state_data={"_error": message},
            )
            return run, message, fallback_step

        # abort (default when no fallback is configured)
        run = await self.store.update_step(
            run.id, run.current_step, status=WorkflowRunStatus.CANCELLED,
            state_data={"_error": message},
        )
        return run, message, None

    async def _apply_engine_step_failure(
        self,
        run: WorkflowRunState,
        step: AnyStepDefinition,
        workflow_def: WorkflowDefinition,
        error_message: str,
        resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]],
        locale: Optional[Locale],
        project_data_resolver: Optional[Callable[[str], Optional[dict]]],
    ) -> AdvanceResult:
        """`_transition_on_failure`, plus assembling the fallback step's prompt
        (or completing the run) into an AdvanceResult."""
        updated_run, message, fallback_step = await self._transition_on_failure(
            run, step, workflow_def, error_message,
        )
        if fallback_step:
            prompt = self.assemble_prompt(
                workflow_def, updated_run, fallback_step,
                resource_resolver=resource_resolver, locale=locale,
                project_data_resolver=project_data_resolver,
            )
            return AdvanceResult(run=updated_run, prompt=prompt, error=message)
        return AdvanceResult(run=updated_run, completed=True, error=message)

    @staticmethod
    def _resolve_vars_deep(value: Any, context: dict[str, Any]) -> Any:
        """Deep-walk `value` and resolve `{{...}}` templates in every string."""
        if isinstance(value, str):
            return PromptBuilder.resolve_templates(value, context)
        if isinstance(value, list):
            return [WorkflowEngine._resolve_vars_deep(v, context) for v in value]
        if isinstance(value, dict):
            return {k: WorkflowEngine._resolve_vars_deep(v, context) for k, v in value.items()}
        return value

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

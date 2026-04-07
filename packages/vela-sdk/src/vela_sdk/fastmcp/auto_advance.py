"""Auto-advance loop logic for workflow execution."""

import json
from typing import Any, Callable, Optional

import structlog

from vela_sdk.engine.types import AdvanceResult, WorkflowRunState, WorkflowRunStatus
from vela_sdk.engine.workflow_engine import WorkflowEngine
from vela_sdk.fastmcp.elicitation import ElicitationService
from vela_sdk.fastmcp.locale import Locale, get_locale
from vela_sdk.schemas.resource import ResourceDefinition
from vela_sdk.schemas.workflow import StepType, WorkflowDefinition
from vela_sdk.storage.protocol import WorkflowStore

logger = structlog.get_logger()


def _is_automation_mode(run: WorkflowRunState) -> bool:
    """Return True if automation_mode param is set to a truthy value."""
    val = run.params.get("automation_mode")
    return val is True or val == "true" or val == 1


def step_captures_complete(step_def: Any, run: WorkflowRunState) -> bool:
    """Check if all elicitable captures for a step are present in state."""
    elicitable = [cap for cap in step_def.capture if cap.elicit != "never"]
    if not elicitable:
        return True
    return all(cap.key in run.state_data for cap in elicitable)


async def elicit_step_captures(
    ctx: Any,
    engine: WorkflowEngine,
    wf_def: WorkflowDefinition,
    run: WorkflowRunState,
    store: WorkflowStore,
    locale: Optional[Locale] = None,
) -> WorkflowRunState:
    """Run elicitation loop for the current step's captures.

    Returns the (possibly updated) run state.
    """
    if locale is None:
        locale = get_locale()

    step_def = engine._get_step(wf_def, run.current_step)
    if not step_def or not step_def.capture:
        return run

    # Dialog steps handle captures after all phases complete
    if step_def.type == StepType.DIALOG:
        return run

    for cap in step_def.capture:
        if cap.elicit == "never":
            continue
        # In automation mode: only elicit required captures, skip the rest
        if _is_automation_mode(run) and not cap.required:
            continue
        # Re-read state_data from current run (may have been updated by previous capture)
        existing_value = run.state_data.get(cap.key)
        if cap.elicit == "if_missing" and existing_value is not None:
            continue

        response_type = ElicitationService.build_response_type(cap)
        message = ElicitationService.build_message(cap)
        if existing_value is not None:
            message += locale.current_value_hint.format(existing_value=existing_value)

        try:
            elicit_result = await ctx.elicit(message, response_type)
        except Exception:
            logger.debug("elicitation.not_supported", key=cap.key)
            return run

        processed = ElicitationService.process_result(cap, elicit_result)
        if processed:
            key, value = processed
            run = await store.update_step(run.id, None, state_data={key: value})
            await store.commit()

    return run


async def auto_advance_loop(
    ctx: Any,
    engine: WorkflowEngine,
    wf_def: WorkflowDefinition,
    result: AdvanceResult,
    store: WorkflowStore,
    resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]] = None,
    locale: Optional[Locale] = None,
) -> AdvanceResult:
    """Elicit -> commit -> advance loop. Runs until a step needs agent work.

    Stops at steps that require agent work:
    - Execute steps (agent must perform task + provide output)
    - Dialog steps (multi-phase interactive)
    - Steps with incomplete captures after elicitation
    - Choice/freeform steps without captures (need agent output for branching)
    """
    while not result.completed and result.run.current_step and ctx:
        step_def = engine._get_step(wf_def, result.run.current_step)
        if not step_def:
            break

        # Execute steps always need agent work
        if step_def.type == StepType.EXECUTE:
            break

        # Dialog steps need interactive multi-phase agent work
        if step_def.type == StepType.DIALOG:
            break

        # Workflow steps delegate to sub-workflows (handled by orchestrator)
        if step_def.type == StepType.WORKFLOW:
            break

        # Steps without elicitable captures need agent output
        has_elicitable = any(c.elicit != "never" for c in step_def.capture) if step_def.capture else False
        if not has_elicitable:
            interactive_types = {StepType.CONFIRM, StepType.CHOICE, StepType.FREEFORM}
            if step_def.type not in interactive_types:
                # If this is the final step, auto-advance to complete the workflow
                next_step_id = engine._resolve_next(step_def, None, wf_def)
                if next_step_id is None:
                    result = await engine.advance(
                        result.run, wf_def, resource_resolver=resource_resolver
                    )
                    await store.commit()
            break

        result.run = await elicit_step_captures(ctx, engine, wf_def, result.run, store, locale=locale)
        if step_captures_complete(step_def, result.run):
            result = await engine.advance(
                result.run, wf_def, resource_resolver=resource_resolver
            )
            await store.commit()
        else:
            await store.commit()
            break
    return result

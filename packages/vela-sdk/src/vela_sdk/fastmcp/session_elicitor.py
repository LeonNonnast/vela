"""Session elicitation helpers — param collection and resume-or-new flows."""

from typing import Optional

import structlog
from fastmcp.server.elicitation import AcceptedElicitation

from vela_sdk.engine.types import WorkflowRunState
from vela_sdk.fastmcp.locale import Locale, get_locale
from vela_sdk.fastmcp.response_builder import build_run_options
from vela_sdk.schemas.workflow import WorkflowDefinition

logger = structlog.get_logger()


async def elicit_required_params(
    ctx,
    param_defs: list,
    locale: Optional[Locale] = None,
) -> Optional[dict]:
    """Elicit values for required params. Returns dict or None on cancel."""
    result: dict = {}
    for p_def in param_defs:
        label = p_def.label or p_def.name
        description = f" — {p_def.description}" if p_def.description else ""
        message = f"{label}{description}"
        if p_def.default is not None:
            message += f" [default: {p_def.default}]"

        try:
            elicit_result = await ctx.elicit(message, str)
        except Exception:
            logger.debug("elicitation.not_supported", key=p_def.name)
            return {}

        if isinstance(elicit_result, AcceptedElicitation) and elicit_result.data:
            result[p_def.name] = elicit_result.data
        elif p_def.default is not None:
            result[p_def.name] = p_def.default
        else:
            return None
    return result


async def elicit_session_choice(
    ctx,
    wf_def: WorkflowDefinition,
    active_runs: list[WorkflowRunState],
    locale: Optional[Locale] = None,
) -> tuple[Optional[WorkflowRunState], Optional[str]]:
    """Elicit resume-or-new choice."""
    if locale is None:
        locale = get_locale()

    options = build_run_options(wf_def, active_runs, locale=locale)

    try:
        result = await ctx.elicit(
            locale.session_choice_message.format(wf_name=wf_def.name),
            options,
        )
    except Exception:
        logger.debug("elicitation.not_supported", workflow_id=wf_def.id)
        return None, None

    if not isinstance(result, AcceptedElicitation):
        return None, None

    if result.data == "__new__":
        return None, "__new__"

    chosen_run = next((r for r in active_runs if r.id == result.data), None)
    return chosen_run, None


async def elicit_prompt_session(
    ctx,
    wf_def: WorkflowDefinition,
    active_runs: list[WorkflowRunState],
    locale: Optional[Locale] = None,
) -> tuple[Optional[WorkflowRunState], dict]:
    """Elicit session choice in prompt handler."""
    if active_runs:
        chosen_run, choice = await elicit_session_choice(ctx, wf_def, active_runs, locale=locale)
        if chosen_run:
            return chosen_run, {}
        if choice != "__new__":
            return None, {}

    required_params = [p for p in wf_def.params if p.required]
    new_params = await elicit_required_params(ctx, required_params, locale=locale)
    return None, new_params or {}


async def elicit_missing_params(
    ctx,
    wf_def: WorkflowDefinition,
    missing_params: list,
    active_runs: list[WorkflowRunState],
    existing_params: dict,
    locale: Optional[Locale] = None,
) -> Optional[dict]:
    """Elicit missing required/identity params via resume-or-new flow."""
    if active_runs:
        chosen_run, choice = await elicit_session_choice(ctx, wf_def, active_runs, locale=locale)
        if chosen_run:
            run_params = chosen_run.params
            return {
                p_def.name: run_params[p_def.name]
                for p_def in missing_params
                if p_def.name in run_params
            }
        if choice is None:
            return None if chosen_run is None else {}

    still_missing = [
        p for p in missing_params
        if p.name not in existing_params
    ]
    return await elicit_required_params(ctx, still_missing, locale=locale)

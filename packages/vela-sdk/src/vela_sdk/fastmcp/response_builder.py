"""Response building helpers for workflow tool outputs."""

import json
import logging
from typing import Any, Callable, Optional

from vela_sdk.engine.types import AdvanceResult, WorkflowRunState
from vela_sdk.engine.workflow_engine import WorkflowEngine
from vela_sdk.fastmcp.locale import Locale, get_locale
from vela_sdk.fastmcp.protocols import WorkflowResolver
from vela_sdk.schemas.workflow import AnyStepDefinition, StepType, WorkflowDefinition
from vela_sdk.storage.protocol import WorkflowStore

logger = logging.getLogger(__name__)


def to_json(obj: Any) -> str:
    """Serialize object to JSON string."""
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, default=str, ensure_ascii=False)
    return str(obj)


def run_to_dict(run: WorkflowRunState) -> dict:
    """Convert a WorkflowRunState to a dict."""
    return {
        "run_id": run.id,
        "workflow_id": run.workflow_id,
        "workflow_version": run.workflow_version,
        "current_step": run.current_step,
        "status": run.status.value if run.status else None,
        "project_id": run.project_id,
        "params": run.params,
        "state_data": run.state_data,
        "parent_run_id": run.parent_run_id,
        "started_at": str(run.started_at) if run.started_at else None,
        "updated_at": str(run.updated_at) if run.updated_at else None,
    }


def build_next_action(
    run: WorkflowRunState,
    wf_def: WorkflowDefinition,
    engine: WorkflowEngine,
    tool_name: str,
    locale: Optional[Locale] = None,
) -> str:
    """Build a clear next_action instruction based on step type and partial state.

    Args:
        run: Current workflow run state.
        wf_def: Workflow definition.
        engine: Workflow engine instance.
        tool_name: Full advance tool name (e.g. ``"vela_advance_workflow"``).
        locale: Locale for message templates.
    """
    if locale is None:
        locale = get_locale()

    if run.status and run.status.value == "completed":
        return locale.workflow_completed

    step_def = engine._get_step(wf_def, run.current_step)
    if not step_def:
        return locale.workflow_completed

    state = run.state_data

    captured = {}
    missing_keys = []
    if step_def.capture:
        for cap in step_def.capture:
            if cap.key in state:
                captured[cap.key] = state[cap.key]
            else:
                missing_keys.append(cap.key)

    partial_hint = ""
    if captured and missing_keys:
        captured_json = json.dumps(captured, ensure_ascii=False)
        partial_hint = locale.already_captured.format(
            captured_json=captured_json,
            missing_keys=", ".join(missing_keys),
        )

    has_elicitable = any(c.elicit != "never" for c in step_def.capture) if step_def.capture else False
    automation = run.params.get("automation_mode") in (True, "true", 1)

    fmt = dict(tool_name=tool_name, run_id=run.id, partial_hint=partial_hint)

    if step_def.type == StepType.EXECUTE:
        prefix_tag = locale.execute_prefix_tag if automation else ""
        return locale.execute_task_then_call.format(prefix_tag=prefix_tag, **fmt)
    elif step_def.type == StepType.DIALOG:
        dialog_phase = state.get("_dialog_phase")
        if automation:
            if not dialog_phase:
                return locale.dialog_auto_start.format(**fmt)
            else:
                return locale.dialog_auto_process.format(**fmt)
        else:
            if not dialog_phase:
                return locale.dialog_start.format(**fmt)
            else:
                return locale.dialog_converse.format(**fmt)
    elif has_elicitable:
        if automation:
            return locale.elicit_auto.format(**fmt)
        else:
            return locale.elicit_manual.format(**fmt)
    elif step_def.type == StepType.CHOICE and step_def.options:
        options_str = ", ".join(f"\"{o.key}\"" for o in step_def.options)
        if automation:
            return locale.choice_auto.format(options_str=options_str, **fmt)
        else:
            return locale.choice_manual.format(options_str=options_str, **fmt)
    elif step_def.type == StepType.CONFIRM:
        if automation:
            return locale.confirm_auto.format(**fmt)
        else:
            return locale.confirm_manual.format(**fmt)
    elif step_def.type == StepType.WORKFLOW:
        wf_ref = getattr(step_def, "workflow_ref", None) or "sub-workflow"
        return locale.sub_workflow_start.format(wf_ref=wf_ref, **fmt)
    else:
        if automation:
            return locale.fallback_auto.format(**fmt)
        else:
            return locale.fallback_manual.format(**fmt)


def build_response(
    result: AdvanceResult,
    wf_def: WorkflowDefinition,
    engine: WorkflowEngine,
    tool_name: str,
    locale: Optional[Locale] = None,
) -> dict:
    """Build unified response dict from an AdvanceResult."""
    d = {
        "run_id": result.run.id,
        "current_step": result.run.current_step,
        "status": result.run.status.value if result.run.status else None,
        "completed": result.completed,
    }
    if result.prompt:
        d["prompt"] = result.prompt
    if result.sub_workflow_ref:
        d["sub_workflow"] = {
            "ref": result.sub_workflow_ref,
            "params": result.sub_workflow_params,
        }
    d["next_action"] = build_next_action(
        result.run, wf_def, engine, tool_name, locale=locale,
    )
    return d


async def enrich_sub_workflow_response(
    response: dict,
    result: AdvanceResult,
    resolver: Optional[WorkflowResolver] = None,
    store: Optional[WorkflowStore] = None,
    locale: Optional[Locale] = None,
    *,
    tool_name: str,
) -> None:
    """Enrich *response* in-place with child workflow param schemas and active runs.

    When ``result.sub_workflow_ref`` is set this looks up the child workflow
    definition (via *resolver*) and adds:

    * ``sub_workflow.params`` — full parameter schema with *required*, *identity*,
      *default*, and *resolved_value* (resolved from the parent run context).
    * ``sub_workflow.active_runs`` — active child runs when the child workflow has
      identity parameters, enabling the LLM to detect whether an existing run
      should be resumed instead of starting a new one.

    The function is a no-op when ``result.sub_workflow_ref`` is not set or when
    *resolver* is ``None``.
    """
    if not result.sub_workflow_ref or resolver is None:
        return

    child_wf_def = await resolver.get_workflow(result.sub_workflow_ref)
    if child_wf_def is None:
        return

    if locale is None:
        locale = get_locale()

    sub_wf_info: dict = response.get("sub_workflow", {
        "ref": result.sub_workflow_ref,
        "params": result.sub_workflow_params,
    })

    parent_data = {**result.run.params, **result.run.state_data}
    params_schema: list[dict] = []
    has_identity = False

    for p in child_wf_def.params:
        p_info: dict = {
            "name": p.name,
            "required": p.required,
        }
        if p.label:
            p_info["label"] = p.label
        if p.description:
            p_info["description"] = p.description
        if p.default is not None:
            p_info["default"] = p.default
        mapping = result.sub_workflow_params or {}
        parent_key = mapping.get(p.name, p.name)
        if parent_key in parent_data:
            p_info["resolved_value"] = parent_data[parent_key]
        p_info["identity"] = p.identity
        if p.identity:
            has_identity = True
        params_schema.append(p_info)

    sub_wf_info["params"] = params_schema

    # Include active runs when child has identity params so the LLM can
    # detect whether an existing run should be resumed.
    if has_identity and store is not None:
        try:
            active_runs = await store.list_active(workflow_id=child_wf_def.id)
            if active_runs:
                sub_wf_info["active_runs"] = [
                    {
                        "run_id": r.id,
                        "status": r.status.value if r.status else None,
                        "current_step": r.current_step,
                        "params": r.params,
                    }
                    for r in active_runs
                ]
        except Exception as e:
            logger.debug("sub_workflow.active_runs lookup failed: %s", e)

    response["sub_workflow"] = sub_wf_info

    # Build enriched next_action with param info for WORKFLOW steps
    if params_schema:
        wf_ref = result.sub_workflow_ref
        param_lines = []
        for p in params_schema:
            parts = [f"  - `{p['name']}`"]
            if p.get("label"):
                parts.append(f"({p['label']})")
            if p.get("required"):
                parts.append("[required]")
            if p.get("identity"):
                parts.append("[identity]")
            if "resolved_value" in p:
                parts.append(f"= \"{p['resolved_value']}\"")
            elif p.get("default") is not None:
                parts.append(f"default: \"{p['default']}\"")
            if p.get("description"):
                parts.append(f"— {p['description']}")
            param_lines.append(" ".join(parts))

        active_hint = ""
        if sub_wf_info.get("active_runs"):
            runs = sub_wf_info["active_runs"]
            active_hint = locale.sub_workflow_active_runs_hint.format(count=len(runs))

        response["next_action"] = (
            locale.sub_workflow_enriched_next_action.format(
                wf_ref=wf_ref,
                param_lines="\n".join(param_lines),
                active_hint=active_hint,
                run_id=result.run.id,
                tool_name=tool_name,
            )
        )


def build_step_response(
    run: WorkflowRunState,
    wf_def: WorkflowDefinition,
    engine: WorkflowEngine,
    resolver: Optional[Callable],
    tool_name: str,
    status: str = "active",
    locale: Optional[Locale] = None,
) -> dict:
    """Build response dict for current step."""
    prompt = engine.assemble_prompt(wf_def, run, resource_resolver=resolver)
    return {
        "status": status,
        "run_id": run.id,
        "workflow_id": wf_def.id,
        "current_step": run.current_step,
        "prompt": prompt,
        "next_action": build_next_action(
            run, wf_def, engine, tool_name, locale=locale,
        ),
    }


def build_run_options(
    wf_def: WorkflowDefinition,
    active_runs: list[WorkflowRunState],
    locale: Optional[Locale] = None,
) -> dict[str, dict[str, str]]:
    """Build elicit options dict from active runs + 'new' entry."""
    if locale is None:
        locale = get_locale()

    step_names = {s.id: s.name or s.id for s in wf_def.steps}
    param_labels = {p.name: p.label or p.name for p in wf_def.params}

    options: dict[str, dict[str, str]] = {}
    for run in active_runs:
        run_params = run.params
        param_parts = []
        for p_def in wf_def.params:
            if p_def.name in run_params:
                param_parts.append(f"{param_labels[p_def.name]}: {run_params[p_def.name]}")
        label_detail = ", ".join(param_parts) if param_parts else run.id[:8]
        step_label = step_names.get(run.current_step, run.current_step) if run.current_step else ""
        step_info = f" — {step_label}" if step_label else ""
        options[run.id] = {"title": f"{label_detail}{step_info}"}
    options["__new__"] = {"title": locale.new_session}
    return options


def enrich_tool_requirements(
    resp: dict,
    wf_def: WorkflowDefinition,
    step_def: Optional[AnyStepDefinition] = None,
) -> None:
    """Enrich *resp* in-place with workflow-level and step-level tool info."""
    if wf_def.tools:
        resp["required_tools"] = [
            {
                "name": t.name,
                "server": t.server,
                "description": t.description,
                "required": t.required,
            }
            for t in wf_def.tools
        ]
    if step_def and step_def.tools:
        resp["step_tools"] = step_def.tools

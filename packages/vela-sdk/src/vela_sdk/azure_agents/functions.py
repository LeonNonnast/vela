"""Workflow tool functions for Azure AI Agents.

Creates closure-based callables compatible with ``azure.ai.agents.models.FunctionTool``.
Each function uses type annotations and ``:param`` docstrings so the Azure SDK
can auto-generate JSON schemas for the agent.
"""

import asyncio
import concurrent.futures
import json
from typing import Any, Callable, Optional

from vela_sdk.engine.workflow_engine import WorkflowEngine
from vela_sdk.fastmcp.locale import Locale, get_locale
from vela_sdk.fastmcp.protocols import SessionProvider, WorkflowResolver
from vela_sdk.fastmcp.response_builder import (
    build_response,
    build_step_response,
    run_to_dict,
    to_json,
)
from vela_sdk.schemas.resource import ResourceDefinition


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from a sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def create_workflow_functions(
    session_provider: SessionProvider,
    workflow_resolver: WorkflowResolver,
    resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]] = None,
    locale: Optional[Locale] = None,
    tool_prefix: str = "workflow",
    advance_tool_name: Optional[str] = None,
) -> dict[str, Callable[..., str]]:
    """Create workflow tool functions as closures.

    Returns a dict ``{"advance": fn, "status": fn, "list": fn}`` where each
    value is a plain callable suitable for ``FunctionTool(functions={...})``.
    The functions' ``__name__`` attributes are set to ``{tool_prefix}_advance``
    etc. so the Azure SDK registers them with the correct names.
    """
    _locale = locale if locale is not None else get_locale()
    _advance_name = advance_tool_name or f"{tool_prefix}_advance"

    # ------------------------------------------------------------------
    # workflow_advance
    # ------------------------------------------------------------------
    def workflow_advance(
        workflow_id: str = "",
        run_id: str = "",
        step_id: str = "",
        output: str = "",
        params: str = "",
        project_id: str = "",
        notes: str = "",
    ) -> str:
        """Start, resume, or advance a Vela workflow. Provide workflow_id to start or resume. Provide run_id and output to advance an active step. After calling, follow the next_action from the response.

        :param workflow_id: Workflow definition ID to start or resume.
        :param run_id: Run ID of an active workflow to advance.
        :param step_id: Current step ID for validation (optional safety check).
        :param output: Output/result from the current step. JSON string for structured captures, plain string otherwise.
        :param params: JSON string of workflow parameters (for starting a new workflow).
        :param project_id: Project ID to scope the workflow run.
        :param notes: Optional notes to attach to the current step.
        """

        async def _impl() -> str:
            # Normalize empty strings to None
            _workflow_id = workflow_id or None
            _run_id = run_id or None
            _step_id = step_id or None
            _output = output or None
            _params = params or None
            _project_id = project_id or None
            _notes = notes or None

            async with session_provider.session() as store:
                engine = WorkflowEngine(store)

                # Case 1: Advance existing run
                if _run_id:
                    run = await store.get_by_id(_run_id)
                    if not run:
                        return to_json({"error": "Run not found", "run_id": _run_id})

                    wf_def = await workflow_resolver.get_workflow(
                        run.workflow_id, run.workflow_version,
                    )
                    if not wf_def:
                        return to_json({
                            "error": "Workflow definition not found",
                            "workflow_id": run.workflow_id,
                        })

                    if _step_id:
                        if not engine._get_step(wf_def, _step_id):
                            return to_json({
                                "error": "Unknown step",
                                "step_id": _step_id,
                                "workflow_id": wf_def.id,
                                "valid_steps": [s.id for s in wf_def.steps],
                            })
                        if _step_id != run.current_step:
                            return to_json({
                                "error": "Step mismatch",
                                "expected_step": run.current_step,
                                "provided_step": _step_id,
                                "run_id": _run_id,
                            })

                    result = await engine.advance(
                        run, wf_def, step_output=_output, notes=_notes,
                        resource_resolver=resource_resolver,
                    )
                    await store.commit()

                    resp = build_response(
                        result, wf_def, engine, _advance_name, locale=_locale,
                    )
                    return to_json(resp)

                # Case 2: Start or resume by workflow_id
                if not _workflow_id:
                    return to_json({"error": "Provide workflow_id or run_id"})

                wf_def = await workflow_resolver.get_workflow(_workflow_id)
                if not wf_def:
                    return to_json({"error": "Workflow not found", "workflow_id": _workflow_id})

                parsed_params = json.loads(_params) if _params else {}

                run, is_new = await engine.start_or_resume(
                    wf_def, params=parsed_params, project_id=_project_id,
                )
                await store.commit()

                resp = build_step_response(
                    run, wf_def, engine, resource_resolver, _advance_name,
                    status="started" if is_new else "resumed",
                    locale=_locale,
                )
                return to_json(resp)

        return _run_async(_impl())

    workflow_advance.__name__ = f"{tool_prefix}_advance"
    workflow_advance.__qualname__ = f"{tool_prefix}_advance"

    # ------------------------------------------------------------------
    # workflow_status
    # ------------------------------------------------------------------
    def workflow_status(run_id: str) -> str:
        """Get the current status of a Vela workflow run by its run ID.

        :param run_id: The workflow run ID to check status for.
        """

        async def _impl() -> str:
            async with session_provider.session() as store:
                run = await store.get_by_id(run_id)
                if not run:
                    return to_json({"error": "Run not found", "run_id": run_id})
                return to_json(run_to_dict(run))

        return _run_async(_impl())

    workflow_status.__name__ = f"{tool_prefix}_status"
    workflow_status.__qualname__ = f"{tool_prefix}_status"

    # ------------------------------------------------------------------
    # workflow_list
    # ------------------------------------------------------------------
    def workflow_list(project_id: str = "") -> str:
        """List available Vela workflow definitions and active runs.

        :param project_id: Filter by project ID.
        """

        async def _impl() -> str:
            _project_id = project_id or None

            all_workflows = await workflow_resolver.list_workflows()
            definitions = [
                {
                    "id": wf.id,
                    "version": wf.version,
                    "name": wf.name,
                    "description": wf.description,
                    "tools": [
                        {"name": t.name, "server": t.server, "required": t.required}
                        for t in wf.tools
                    ] if wf.tools else [],
                }
                for wf in all_workflows.values()
            ]

            async with session_provider.session() as store:
                active_runs = await store.list_active(project_id=_project_id)
                active_dicts = [run_to_dict(r) for r in active_runs]

            return to_json({
                "definitions": definitions,
                "active_runs": active_dicts,
            })

        return _run_async(_impl())

    workflow_list.__name__ = f"{tool_prefix}_list"
    workflow_list.__qualname__ = f"{tool_prefix}_list"

    return {
        "advance": workflow_advance,
        "status": workflow_status,
        "list": workflow_list,
    }

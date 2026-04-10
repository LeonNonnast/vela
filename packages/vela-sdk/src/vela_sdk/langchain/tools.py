"""LangChain tool implementations for Vela workflows."""

import asyncio
import json
from typing import Any, Callable, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from vela_sdk.engine.types import WorkflowRunStatus
from vela_sdk.engine.workflow_engine import WorkflowEngine
from vela_sdk.fastmcp.locale import Locale, get_locale
from vela_sdk.fastmcp.protocols import SessionProvider, WorkflowResolver
from vela_sdk.fastmcp.response_builder import (
    build_next_action,
    build_response,
    build_step_response,
    run_to_dict,
    to_json,
)
from vela_sdk.langchain.schemas import (
    WorkflowAdvanceInput,
    WorkflowListInput,
    WorkflowStatusInput,
)
from vela_sdk.schemas.resource import ResourceDefinition


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from a sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # If there's already a running loop (e.g. Jupyter), create a new one in a thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class WorkflowAdvanceTool(BaseTool):
    """Start, resume, or advance a Vela workflow."""

    name: str = "workflow_advance"
    description: str = (
        "Start, resume, or advance a workflow. "
        "Provide workflow_id to start/resume. "
        "Provide run_id + output to advance an active step. "
        "After calling this tool, execute the next_action from the response immediately."
    )
    args_schema: Type[BaseModel] = WorkflowAdvanceInput

    session_provider: Any  # SessionProvider
    workflow_resolver: Any  # WorkflowResolver
    resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]] = None
    locale: Any = None  # Locale
    advance_tool_name: str = "workflow_advance"

    model_config = {"arbitrary_types_allowed": True}

    async def _arun(
        self,
        workflow_id: Optional[str] = None,
        run_id: Optional[str] = None,
        step_id: Optional[str] = None,
        output: Optional[str] = None,
        params: Optional[str] = None,
        project_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> str:
        locale: Locale = self.locale if self.locale is not None else get_locale()
        resolver = self.resource_resolver

        async with self.session_provider.session() as store:
            engine = WorkflowEngine(store)

            # Case 1: Advance existing run
            if run_id:
                run = await store.get_by_id(run_id)
                if not run:
                    return to_json({"error": "Run not found", "run_id": run_id})

                wf_def = await self.workflow_resolver.get_workflow(
                    run.workflow_id, run.workflow_version,
                )
                if not wf_def:
                    return to_json({
                        "error": "Workflow definition not found",
                        "workflow_id": run.workflow_id,
                    })

                # Validate step_id
                if step_id:
                    if not engine._get_step(wf_def, step_id):
                        return to_json({
                            "error": "Unknown step",
                            "step_id": step_id,
                            "workflow_id": wf_def.id,
                            "valid_steps": [s.id for s in wf_def.steps],
                        })
                    if step_id != run.current_step:
                        return to_json({
                            "error": "Step mismatch",
                            "expected_step": run.current_step,
                            "provided_step": step_id,
                            "run_id": run_id,
                        })

                result = await engine.advance(
                    run, wf_def, step_output=output, notes=notes,
                    resource_resolver=resolver,
                )
                await store.commit()

                resp = build_response(
                    result, wf_def, engine, self.advance_tool_name, locale=locale,
                )
                return to_json(resp)

            # Case 2: Start or resume by workflow_id
            if not workflow_id:
                return to_json({"error": "Provide workflow_id or run_id"})

            wf_def = await self.workflow_resolver.get_workflow(workflow_id)
            if not wf_def:
                return to_json({"error": "Workflow not found", "workflow_id": workflow_id})

            parsed_params = json.loads(params) if params else {}

            run, is_new = await engine.start_or_resume(
                wf_def, params=parsed_params, project_id=project_id,
            )
            await store.commit()

            resp = build_step_response(
                run, wf_def, engine, resolver, self.advance_tool_name,
                status="started" if is_new else "resumed",
                locale=locale,
            )
            return to_json(resp)

    def _run(self, **kwargs: Any) -> str:
        return _run_async(self._arun(**kwargs))


class WorkflowStatusTool(BaseTool):
    """Get the status of a Vela workflow run."""

    name: str = "workflow_status"
    description: str = "Get the status of a workflow run by run_id."
    args_schema: Type[BaseModel] = WorkflowStatusInput

    session_provider: Any  # SessionProvider

    model_config = {"arbitrary_types_allowed": True}

    async def _arun(self, run_id: str) -> str:
        async with self.session_provider.session() as store:
            run = await store.get_by_id(run_id)
            if not run:
                return to_json({"error": "Run not found", "run_id": run_id})
            return to_json(run_to_dict(run))

    def _run(self, **kwargs: Any) -> str:
        return _run_async(self._arun(**kwargs))


class WorkflowListTool(BaseTool):
    """List available Vela workflow definitions and active runs."""

    name: str = "workflow_list"
    description: str = "List available workflow definitions and active runs."
    args_schema: Type[BaseModel] = WorkflowListInput

    session_provider: Any  # SessionProvider
    workflow_resolver: Any  # WorkflowResolver

    model_config = {"arbitrary_types_allowed": True}

    async def _arun(self, project_id: Optional[str] = None) -> str:
        all_workflows = await self.workflow_resolver.list_workflows()
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

        async with self.session_provider.session() as store:
            active_runs = await store.list_active(project_id=project_id)
            active_dicts = [run_to_dict(r) for r in active_runs]

        return to_json({
            "definitions": definitions,
            "active_runs": active_dicts,
        })

    def _run(self, **kwargs: Any) -> str:
        return _run_async(self._arun(**kwargs))

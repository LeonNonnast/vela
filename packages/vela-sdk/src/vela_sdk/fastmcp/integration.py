"""VelaWorkflows — main entry point for FastMCP integration."""

import json
import os
from typing import Any, Callable, Optional

import structlog
from fastmcp import Context, FastMCP

from vela_sdk.engine.types import AdvanceResult, WorkflowRunState, WorkflowRunStatus
from vela_sdk.engine.workflow_engine import WorkflowEngine
from vela_sdk.fastmcp.auto_advance import (
    auto_advance_loop,
    elicit_step_captures,
    step_captures_complete,
)
from vela_sdk.fastmcp.elicitation import ElicitationService
from vela_sdk.fastmcp.locale import Locale, get_locale
from vela_sdk.fastmcp.protocols import (
    DefaultParamFilter,
    InMemoryWorkflowResolver,
    ParamFilter,
    ProjectResolver,
    SessionProvider,
    SimpleSessionProvider,
    WorkflowResolver,
)
from vela_sdk.fastmcp.response_builder import (
    build_next_action,
    build_response,
    build_step_response,
    enrich_sub_workflow_response,
    enrich_tool_requirements,
    run_to_dict,
    to_json,
)
from vela_sdk.fastmcp.session_elicitor import (
    elicit_missing_params,
    elicit_prompt_session,
)
from vela_sdk.loader.workflow_loader import load_workflows
from vela_sdk.schemas.resource import ResourceDefinition
from vela_sdk.schemas.workflow import StepType, WorkflowDefinition
from vela_sdk.storage.protocol import WorkflowStore

logger = structlog.get_logger()


class VelaWorkflows:
    """Main entry point for adding workflow capabilities to a FastMCP server.

    Usage::

        from fastmcp import FastMCP
        from vela_sdk import VelaWorkflows

        mcp = FastMCP("my-server")
        workflows = VelaWorkflows(mcp, workflows_dir="./workflows/")

    This registers 3 MCP tools ({prefix}_advance, {prefix}_status, {prefix}_list)
    and one prompt per workflow definition.
    """

    def __init__(
        self,
        mcp: FastMCP,
        store: Optional[WorkflowStore] = None,
        workflows_dir: Optional[str | list[str]] = None,
        resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]] = None,
        tool_prefix: str = "workflow",
        auto_advance: bool = True,
        register_prompts: bool = True,
        initial_workflows: Optional[dict[str, "WorkflowDefinition"]] = None,
        *,
        workflow_resolver: Optional[WorkflowResolver] = None,
        session_provider: Optional[SessionProvider] = None,
        param_filter: Optional[ParamFilter] = None,
        project_resolver: Optional[ProjectResolver] = None,
        tool_name_format: Optional[dict[str, str]] = None,
        locale: Optional[Locale] = None,
    ) -> None:
        self._mcp = mcp
        self._store = store
        self._resource_resolver = resource_resolver
        self._tool_prefix = tool_prefix
        self._auto_advance = auto_advance
        self._locale = locale if locale is not None else get_locale()
        self._workflows: dict[str, WorkflowDefinition] = {}

        # Extension protocols
        self._resolver: WorkflowResolver = (
            workflow_resolver
            if workflow_resolver is not None
            else InMemoryWorkflowResolver(self._workflows)
        )
        self._param_filter: ParamFilter = (
            param_filter if param_filter is not None else DefaultParamFilter()
        )
        self._project_resolver = project_resolver

        # Configurable tool names
        default_names = {
            "advance": f"{tool_prefix}_advance",
            "status": f"{tool_prefix}_status",
            "list": f"{tool_prefix}_list",
        }
        if tool_name_format:
            default_names.update(tool_name_format)
        self._tool_names: dict[str, str] = default_names

        # Load workflows from directories and/or initial dict
        if initial_workflows:
            self._workflows.update(initial_workflows)
        if workflows_dir:
            dirs = [workflows_dir] if isinstance(workflows_dir, str) else workflows_dir
            for d in dirs:
                expanded = os.path.expanduser(d)
                loaded = load_workflows(expanded)
                self._workflows.update(loaded)

        # Lazy-init store if not provided
        if self._store is None:
            self._store = self._create_default_store()

        # Session provider: use provided or default to SimpleSessionProvider
        self._session_provider: SessionProvider = (
            session_provider
            if session_provider is not None
            else SimpleSessionProvider(self._store)
        )

        # Register tools and prompts
        self._register_tools(mcp)
        if register_prompts:
            self._register_prompts(mcp)

        logger.info("vela_workflows.initialized",
                     workflows=len(self._workflows),
                     prefix=tool_prefix)

    def register(self, workflow: WorkflowDefinition) -> None:
        """Register a workflow definition programmatically."""
        key = f"{workflow.id}@{workflow.version}"
        self._workflows[key] = workflow
        # Keep InMemoryWorkflowResolver in sync (it shares the same dict,
        # but if someone replaced it we update explicitly).
        if isinstance(self._resolver, InMemoryWorkflowResolver):
            self._resolver._workflows[key] = workflow

    def _create_default_store(self) -> WorkflowStore:
        """Create a default InMemoryStore (no external deps needed)."""
        from vela_sdk.storage.memory import InMemoryStore
        return InMemoryStore()

    async def _get_workflow(
        self, workflow_id: str, version: Optional[str] = None
    ) -> Optional[WorkflowDefinition]:
        """Get workflow by ID, optionally with specific version.

        Delegates to the configured WorkflowResolver (async to support
        DB/network-backed resolvers).
        """
        return await self._resolver.get_workflow(workflow_id, version)

    def _register_tools(self, mcp: FastMCP) -> None:
        prefix = self._tool_prefix
        advance_name = self._tool_names["advance"]
        locale = self._locale

        @mcp.tool(
            name=advance_name,
            description=(
                "Start, resume, or advance a workflow. "
                "Provide workflow_id to start/resume. Provide run_id + output to advance an active step. "
                "IMPORTANT: After calling this tool, ALWAYS execute the `next_action` from the response IMMEDIATELY "
                "without asking the user for permission. The engine handles all user interaction via built-in elicitation "
                "dialogs — do NOT ask the user questions yourself. Just follow the next_action instruction."
            ),
        )
        async def workflow_advance(
            workflow_id: Optional[str] = None,
            run_id: Optional[str] = None,
            step_id: Optional[str] = None,
            output: Optional[str] = None,
            params: Optional[str] = None,
            project_id: Optional[str] = None,
            project_slug: Optional[str] = None,
            notes: Optional[str] = None,
            ctx: Context | None = None,
        ) -> str:
            async with self._session_provider.session() as store:
                engine = WorkflowEngine(store)
                resolver = self._resource_resolver

                # Resolve project_slug to project_id if resolver is available
                if not project_id and project_slug and self._project_resolver:
                    project_id = await self._project_resolver.resolve_project_id(project_slug)

                # Case 1: Advance existing run
                if run_id:
                    run = await store.get_by_id(run_id)
                    if not run:
                        return to_json({"error": "Run not found", "run_id": run_id})

                    wf_def = await self._get_workflow(run.workflow_id, run.workflow_version)
                    if not wf_def:
                        return to_json({"error": "Workflow definition not found", "workflow_id": run.workflow_id})

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

                    # Elicit missing captures for current step
                    if run.current_step and ctx:
                        run = await elicit_step_captures(ctx, engine, wf_def, run, store, locale=locale)

                    # Only advance if captures are complete OR agent provided output
                    step_def = engine._get_step(wf_def, run.current_step)
                    can_advance = (
                        output is not None
                        or not step_def
                        or not step_def.capture
                        or step_captures_complete(step_def, run)
                    )

                    if can_advance:
                        result = await engine.advance(run, wf_def, step_output=output, notes=notes, resource_resolver=resolver)
                        await store.commit()

                        if self._auto_advance and ctx:
                            result = await auto_advance_loop(ctx, engine, wf_def, result, store, resolver, locale=locale)

                        # Handle sub-workflow: auto-start child
                        if result.sub_workflow_ref:
                            child_resp = await self._start_sub_workflow(
                                result, engine, store, ctx, resolver, prefix,
                            )
                            if child_resp:
                                return child_resp

                        # Handle completed child: auto-resume parent
                        if result.completed and result.run.parent_run_id:
                            parent_resp = await self._resume_parent(
                                result.run, engine, store, ctx, resolver, prefix,
                            )
                            if parent_resp:
                                return parent_resp

                        resp = build_response(
                            result, wf_def, engine, advance_name, locale=locale,
                        )
                        await enrich_sub_workflow_response(
                            resp, result, self._resolver, store, locale=locale,
                            tool_name=advance_name,
                        )
                        step_d = engine._get_step(wf_def, result.run.current_step)
                        enrich_tool_requirements(resp, wf_def, step_d)
                        return to_json(resp)
                    else:
                        await store.commit()
                        resp = build_step_response(
                            run, wf_def, engine, resolver, advance_name,
                            status="awaiting_input",
                            locale=locale,
                        )
                        step_d = engine._get_step(wf_def, run.current_step)
                        enrich_tool_requirements(resp, wf_def, step_d)
                        return to_json(resp)

                # Case 2: Start or resume by workflow_id
                if not workflow_id:
                    return to_json({"error": "Provide workflow_id or run_id"})

                wf_def = await self._get_workflow(workflow_id)
                if not wf_def:
                    return to_json({"error": "Workflow not found", "workflow_id": workflow_id})

                parsed_params = json.loads(params) if params else {}

                # Elicit missing required params (via pluggable filter)
                missing_required = self._param_filter.filter_missing_params(wf_def, parsed_params)
                if missing_required and ctx:
                    active_runs = await store.list_active(workflow_id=wf_def.id)
                    resolved = await elicit_missing_params(
                        ctx, wf_def, missing_required, active_runs, parsed_params,
                        locale=locale,
                    )
                    if resolved is None:
                        return to_json({
                            "status": "cancelled",
                            "workflow_id": wf_def.id,
                            "message": locale.workflow_start_cancelled,
                        })
                    parsed_params.update(resolved)

                run, is_new = await engine.start_or_resume(
                    wf_def, params=parsed_params, project_id=project_id
                )

                # Elicit missing captures on first/current step
                if run.current_step and ctx:
                    run = await elicit_step_captures(ctx, engine, wf_def, run, store)

                await store.commit()

                # Auto-advance loop
                step_def = engine._get_step(wf_def, run.current_step)
                if step_def and step_captures_complete(step_def, run):
                    result = await engine.advance(run, wf_def, resource_resolver=resolver)
                    await store.commit()
                    if self._auto_advance and ctx:
                        result = await auto_advance_loop(ctx, engine, wf_def, result, store, resolver)

                    # Handle sub-workflow: auto-start child
                    if result.sub_workflow_ref:
                        child_resp = await self._start_sub_workflow(
                            result, engine, store, ctx, resolver, prefix,
                        )
                        if child_resp:
                            return child_resp

                    resp = build_response(
                        result, wf_def, engine, advance_name, locale=locale,
                    )
                    await enrich_sub_workflow_response(
                        resp, result, self._resolver, store, locale=locale,
                        tool_name=advance_name,
                    )
                    resp["status"] = "started" if is_new else "resumed_and_advanced"
                    step_d = engine._get_step(wf_def, result.run.current_step)
                    enrich_tool_requirements(resp, wf_def, step_d)
                    return to_json(resp)
                else:
                    resp = build_step_response(
                        run, wf_def, engine, resolver, advance_name,
                        status="started" if is_new else "resumed",
                        locale=locale,
                    )
                    enrich_tool_requirements(resp, wf_def, step_def)
                    return to_json(resp)

        @mcp.tool(
            name=self._tool_names["status"],
            description="Get the status of a workflow run by run_id.",
        )
        async def workflow_status(run_id: str) -> str:
            async with self._session_provider.session() as store:
                run = await store.get_by_id(run_id)
                if not run:
                    return to_json({"error": "Run not found", "run_id": run_id})
                return to_json(run_to_dict(run))

        @mcp.tool(
            name=self._tool_names["list"],
            description="List available workflow definitions and active runs.",
        )
        async def workflow_list(
            project_id: Optional[str] = None,
        ) -> str:
            all_workflows = await self._resolver.list_workflows()
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

            async with self._session_provider.session() as store:
                active_runs = await store.list_active(project_id=project_id)
                active_dicts = [run_to_dict(r) for r in active_runs]

            return to_json({
                "definitions": definitions,
                "active_runs": active_dicts,
            })

    async def _resolve_sub_workflow_params(
        self,
        parent_result: AdvanceResult,
        child_wf_def: WorkflowDefinition,
    ) -> dict:
        """Resolve params for a child workflow from parent state.

        1. Explicit params_mapping from the workflow step definition
        2. Auto-match: parent state/params keys that match child param names
        """
        parent_run = parent_result.run
        parent_data = {**parent_run.params, **parent_run.state_data}
        resolved = {}

        # Explicit mapping: {child_param: parent_key}
        mapping = parent_result.sub_workflow_params or {}
        for child_key, parent_key in mapping.items():
            if parent_key in parent_data:
                resolved[child_key] = parent_data[parent_key]

        # Auto-match: child param names that exist in parent data
        for p_def in child_wf_def.params:
            if p_def.name not in resolved and p_def.name in parent_data:
                resolved[p_def.name] = parent_data[p_def.name]

        return resolved

    async def _start_sub_workflow(
        self,
        parent_result: AdvanceResult,
        engine: WorkflowEngine,
        store: WorkflowStore,
        ctx: Any,
        resolver: Any,
        prefix: str,
    ) -> Optional[str]:
        """Auto-start a sub-workflow when a workflow step is reached.

        Returns JSON response string, or None if sub-workflow can't be started.
        """
        locale = self._locale
        child_wf_def = await self._get_workflow(parent_result.sub_workflow_ref)
        if not child_wf_def:
            logger.warning(
                "sub_workflow.not_found",
                ref=parent_result.sub_workflow_ref,
                parent_run_id=parent_result.run.id,
            )
            return None

        # Resolve params from parent state
        child_params = await self._resolve_sub_workflow_params(parent_result, child_wf_def)

        # Start child run
        child_run, _is_new = await engine.start_or_resume(
            child_wf_def,
            params=child_params,
            project_id=parent_result.run.project_id,
            parent_run_id=parent_result.run.id,
            parent_step_id=parent_result.run.current_step,
        )

        # Elicit captures on first step
        if child_run.current_step and ctx:
            child_run = await elicit_step_captures(ctx, engine, child_wf_def, child_run, store, locale=locale)

        await store.commit()

        # Auto-advance child
        child_step = engine._get_step(child_wf_def, child_run.current_step)
        if child_step and step_captures_complete(child_step, child_run):
            child_result = await engine.advance(child_run, child_wf_def, resource_resolver=resolver)
            await store.commit()
            if self._auto_advance and ctx:
                child_result = await auto_advance_loop(ctx, engine, child_wf_def, child_result, store, resolver, locale=locale)

            # If child completed immediately, resume parent
            if child_result.completed and child_result.run.parent_run_id:
                parent_resp = await self._resume_parent(
                    child_result.run, engine, store, ctx, resolver, prefix,
                )
                if parent_resp:
                    return parent_resp

            resp = build_response(
                child_result, child_wf_def, engine, self._tool_names["advance"],
                locale=locale,
            )
            await enrich_sub_workflow_response(
                resp, child_result, self._resolver, store, locale=locale,
                tool_name=self._tool_names["advance"],
            )
            resp["parent_run_id"] = parent_result.run.id
            resp["status"] = "sub_workflow_started"
            return to_json(resp)

        # Child needs input on first step
        resp = build_step_response(
            child_run, child_wf_def, engine, resolver, self._tool_names["advance"],
            status="sub_workflow_started",
            locale=locale,
        )
        resp["parent_run_id"] = parent_result.run.id
        return to_json(resp)

    async def _resume_parent(
        self,
        child_run: WorkflowRunState,
        engine: WorkflowEngine,
        store: WorkflowStore,
        ctx: Any,
        resolver: Any,
        prefix: str,
    ) -> Optional[str]:
        """Auto-resume parent workflow when a child completes.

        Returns JSON response string, or None if parent can't be resumed.
        """
        locale = self._locale
        parent_run = await store.get_by_id(child_run.parent_run_id)
        if not parent_run:
            logger.warning("sub_workflow.parent_not_found", parent_run_id=child_run.parent_run_id)
            return None

        parent_wf_def = await self._get_workflow(parent_run.workflow_id, parent_run.workflow_version)
        if not parent_wf_def:
            logger.warning("sub_workflow.parent_wf_not_found", workflow_id=parent_run.workflow_id)
            return None

        # Resume parent: advance past the workflow step
        parent_result = await engine.advance(
            parent_run, parent_wf_def,
            step_output="sub_workflow_completed",
            resource_resolver=resolver,
        )
        await store.commit()

        if self._auto_advance and ctx:
            parent_result = await auto_advance_loop(ctx, engine, parent_wf_def, parent_result, store, resolver, locale=locale)

        # Recursive: if parent also hits a sub-workflow or completes with a parent
        if parent_result.sub_workflow_ref:
            child_resp = await self._start_sub_workflow(
                parent_result, engine, store, ctx, resolver, prefix,
            )
            if child_resp:
                return child_resp

        if parent_result.completed and parent_result.run.parent_run_id:
            return await self._resume_parent(
                parent_result.run, engine, store, ctx, resolver, prefix,
            )

        resp = build_response(
            parent_result, parent_wf_def, engine, self._tool_names["advance"],
            locale=locale,
        )
        await enrich_sub_workflow_response(
            resp, parent_result, self._resolver, store, locale=locale,
            tool_name=self._tool_names["advance"],
        )
        resp["resumed_from_sub_workflow"] = child_run.workflow_id
        return to_json(resp)

    def _register_prompts(self, mcp: FastMCP) -> None:
        """Register each workflow as an MCP prompt."""
        for key, wf_def in self._workflows.items():
            prompt_name = f"{self._tool_prefix}_{wf_def.id}"
            description = wf_def.description or f"Start workflow: {wf_def.name}"
            prefix = self._tool_prefix
            locale = self._locale

            def make_prompt_handler(wf: WorkflowDefinition, pfx: str, adv_name: str, loc: Locale):
                async def handler(ctx: Context) -> str:
                    async with self._session_provider.session() as store:
                        engine = WorkflowEngine(store)
                        resolver = self._resource_resolver

                        parts = [f"# {wf.name}", ""]
                        if wf.description:
                            parts.append(wf.description)
                            parts.append("")

                        active_runs = await store.list_active(workflow_id=wf.id)

                        chosen_run = None
                        chosen_params: dict = {}
                        if active_runs or wf.params:
                            chosen_run, chosen_params = await elicit_prompt_session(
                                ctx, wf, active_runs, locale=loc
                            )

                        if chosen_run:
                            step_prompt = engine.assemble_prompt(
                                wf, chosen_run, resource_resolver=resolver
                            )
                            run_params = chosen_run.params
                            param_labels = {p.name: p.label or p.name for p in wf.params}
                            step_names = {s.id: s.name or s.id for s in wf.steps}
                            step_label = step_names.get(chosen_run.current_step, chosen_run.current_step)

                            parts.append(loc.prompt_resumed_session)
                            parts.append(loc.prompt_run_id.format(run_id=chosen_run.id))
                            parts.append(loc.prompt_current_step.format(step_label=step_label))
                            if run_params:
                                param_str = ", ".join(
                                    f"{param_labels.get(k, k)}: {v}" for k, v in run_params.items()
                                )
                                parts.append(loc.prompt_parameters.format(param_str=param_str))
                            parts.append("")
                            parts.append(step_prompt)
                            parts.append("")

                            next_action = build_next_action(
                                chosen_run, wf, engine, adv_name, locale=loc,
                            )

                            current_step_def = engine._get_step(wf, chosen_run.current_step)
                            if current_step_def and current_step_def.capture:
                                state = chosen_run.state_data
                                captured = {c.key: state[c.key] for c in current_step_def.capture if c.key in state}
                                missing = [c.key for c in current_step_def.capture if c.key not in state]
                                if captured:
                                    parts.append(loc.prompt_captured_data)
                                    for k, v in captured.items():
                                        parts.append(f"- **{k}**: {v}")
                                    parts.append("")
                                if missing:
                                    parts.append(loc.prompt_still_open.format(keys=", ".join(missing)))
                                    parts.append("")

                            parts.append(loc.prompt_next_action)
                            parts.append(next_action)
                        else:
                            if wf.params:
                                parts.append("## Parameters")
                                for p in wf.params:
                                    req = " (required)" if p.required else ""
                                    default = f" [default: {p.default}]" if p.default else ""
                                    if p.name in chosen_params:
                                        parts.append(f"- **{p.name}**{req}: `{chosen_params[p.name]}`")
                                    else:
                                        parts.append(f"- **{p.name}**{req}{default}: {p.description or ''}")
                                parts.append("")

                            parts.append("## Steps")
                            for s in wf.steps:
                                name = s.name or s.id
                                parts.append(f"1. **{name}** ({s.type})")
                            parts.append("")

                            if chosen_params:
                                params_json = json.dumps(chosen_params, ensure_ascii=False)
                                parts.append(loc.prompt_next_action)
                                parts.append(
                                    loc.prompt_call_advance_with_params.format(
                                        tool_name=adv_name, wf_id=wf.id, params_json=params_json
                                    )
                                )
                            else:
                                parts.append(loc.prompt_next_action)
                                parts.append(
                                    loc.prompt_call_advance.format(tool_name=adv_name, wf_id=wf.id)
                                )

                        parts.append("")
                        parts.append(loc.prompt_auto_mode.format(tool_name=adv_name))

                        return "\n".join(parts)

                return handler

            mcp.prompt(name=prompt_name, description=description)(
                make_prompt_handler(wf_def, prefix, self._tool_names["advance"], locale)
            )

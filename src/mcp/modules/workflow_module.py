"""Workflow Module — Thin adapter between Vela Server and vela-sdk.

Wires up Vela-specific implementations (DB sessions, module registry,
project resolution, param filtering) into the SDK's VelaWorkflows class
via the protocol-based extension points.

All workflow execution logic lives in the SDK; this module only provides
Vela's infrastructure hooks.
"""

import structlog
from fastmcp import FastMCP

from src.mcp.modules.base import VelaModuleBase
from src.shared.services.vela_param_filter import VelaParamFilter
from src.shared.services.vela_project_resolver import VelaProjectResolver
from src.shared.services.vela_session_provider import VelaSessionProvider
from src.shared.services.vela_workflow_resolver import VelaWorkflowResolver

from vela_sdk.fastmcp.integration import VelaWorkflows
from vela_sdk.fastmcp.locale import get_locale

logger = structlog.get_logger()


class WorkflowModule(VelaModuleBase):
    """Manages workflow execution via MCP tools and prompts.

    Delegates all workflow logic to the SDK's VelaWorkflows, injecting
    Vela-specific hooks for DB sessions, workflow resolution, project
    context, and parameter filtering.
    """

    def __init__(self, mcp: FastMCP, session_factory=None, module_registry=None):
        from src.shared.db.database import async_session_factory as default_factory
        session_factory = session_factory or default_factory

        # Build Vela-specific hook implementations
        resolver = VelaWorkflowResolver(
            session_factory=session_factory,
            module_registry=module_registry,
            apply_filters=True,
        )
        session_provider = VelaSessionProvider(session_factory)
        project_resolver = VelaProjectResolver(session_factory)
        param_filter = VelaParamFilter()

        # Resource resolver from ResourceModule (lazy — may not be constructed yet)
        resource_resolver = self._get_resource_resolver()

        # Delegate everything to the SDK
        # Pass filesystem workflows for eager prompt registration;
        # the resolver handles runtime lookups (including DB/registry sources).
        self._workflows = VelaWorkflows(
            mcp,
            initial_workflows=resolver._filesystem_workflows,
            workflow_resolver=resolver,
            session_provider=session_provider,
            resource_resolver=resource_resolver,
            project_resolver=project_resolver,
            param_filter=param_filter,
            tool_prefix="vela",
            tool_name_format={
                "advance": "vela_advance_workflow",
                "status": "vela_workflow_status",
                "list": "vela_list_workflows",
            },
            locale=get_locale("de"),
            auto_advance=True,
            register_prompts=True,
        )

        logger.info("workflow_module.initialized")

    @staticmethod
    def _get_resource_resolver():
        """Get resource resolver from ResourceModule (if available)."""
        from src.mcp.modules.resource_module import ResourceModule
        rm = ResourceModule.instance()
        return rm.resolve if rm else None

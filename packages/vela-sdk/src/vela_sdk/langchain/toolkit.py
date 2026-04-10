"""LangChain toolkit for Vela workflows."""

import os
from typing import Any, Callable, Optional

from langchain_core.tools import BaseTool, BaseToolkit
from pydantic import ConfigDict

from vela_sdk.fastmcp.locale import Locale, get_locale
from vela_sdk.fastmcp.protocols import (
    InMemoryWorkflowResolver,
    SessionProvider,
    SimpleSessionProvider,
    WorkflowResolver,
)
from vela_sdk.langchain.tools import (
    WorkflowAdvanceTool,
    WorkflowListTool,
    WorkflowStatusTool,
)
from vela_sdk.loader.workflow_loader import load_workflows
from vela_sdk.schemas.resource import ResourceDefinition
from vela_sdk.schemas.workflow import WorkflowDefinition
from vela_sdk.storage.protocol import WorkflowStore


class VelaToolkit(BaseToolkit):
    """LangChain toolkit that exposes Vela workflow tools.

    Usage::

        from vela_sdk.langchain import VelaToolkit

        toolkit = VelaToolkit(workflows_dir="./workflows/")
        tools = toolkit.get_tools()

        # Use with any LangChain agent
        agent = create_react_agent(llm, tools)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Configuration
    store: Optional[WorkflowStore] = None
    workflows_dir: Optional[Any] = None  # str | list[str]
    initial_workflows: Optional[dict[str, WorkflowDefinition]] = None
    resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]] = None
    tool_prefix: str = "workflow"
    tool_name_format: Optional[dict[str, str]] = None
    locale: Optional[Locale] = None
    workflow_resolver: Optional[WorkflowResolver] = None
    session_provider: Optional[SessionProvider] = None

    # Internal state
    _workflows: dict[str, WorkflowDefinition] = {}
    _resolved_session_provider: Optional[SessionProvider] = None
    _resolved_resolver: Optional[WorkflowResolver] = None
    _tool_names: dict[str, str] = {}

    def model_post_init(self, __context: Any) -> None:
        """Initialize workflows, store, and resolvers after Pydantic init."""
        self._workflows = {}

        # Load workflows
        if self.initial_workflows:
            self._workflows.update(self.initial_workflows)
        if self.workflows_dir:
            dirs = (
                [self.workflows_dir]
                if isinstance(self.workflows_dir, str)
                else self.workflows_dir
            )
            for d in dirs:
                expanded = os.path.expanduser(d)
                loaded = load_workflows(expanded)
                self._workflows.update(loaded)

        # Resolver
        self._resolved_resolver = (
            self.workflow_resolver
            if self.workflow_resolver is not None
            else InMemoryWorkflowResolver(self._workflows)
        )

        # Store + session provider
        if self.store is None:
            from vela_sdk.storage.memory import InMemoryStore
            self.store = InMemoryStore()

        self._resolved_session_provider = (
            self.session_provider
            if self.session_provider is not None
            else SimpleSessionProvider(self.store)
        )

        # Tool names
        default_names = {
            "advance": f"{self.tool_prefix}_advance",
            "status": f"{self.tool_prefix}_status",
            "list": f"{self.tool_prefix}_list",
        }
        if self.tool_name_format:
            default_names.update(self.tool_name_format)
        self._tool_names = default_names

    def register(self, workflow: WorkflowDefinition) -> None:
        """Register a workflow definition programmatically."""
        key = f"{workflow.id}@{workflow.version}"
        self._workflows[key] = workflow
        if isinstance(self._resolved_resolver, InMemoryWorkflowResolver):
            self._resolved_resolver._workflows[key] = workflow

    def get_tools(self) -> list[BaseTool]:
        """Return the 3 Vela workflow tools for LangChain agents."""
        loc = self.locale if self.locale is not None else get_locale()

        advance = WorkflowAdvanceTool(
            name=self._tool_names["advance"],
            session_provider=self._resolved_session_provider,
            workflow_resolver=self._resolved_resolver,
            resource_resolver=self.resource_resolver,
            locale=loc,
            advance_tool_name=self._tool_names["advance"],
        )
        status = WorkflowStatusTool(
            name=self._tool_names["status"],
            session_provider=self._resolved_session_provider,
        )
        list_tool = WorkflowListTool(
            name=self._tool_names["list"],
            session_provider=self._resolved_session_provider,
            workflow_resolver=self._resolved_resolver,
        )
        return [advance, status, list_tool]

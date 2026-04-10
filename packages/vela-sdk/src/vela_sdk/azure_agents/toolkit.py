"""Azure AI Agents toolset for Vela workflows."""

import os
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict

from vela_sdk.fastmcp.locale import Locale, get_locale
from vela_sdk.fastmcp.protocols import (
    InMemoryWorkflowResolver,
    SessionProvider,
    SimpleSessionProvider,
    WorkflowResolver,
)
from vela_sdk.azure_agents.functions import create_workflow_functions
from vela_sdk.loader.workflow_loader import load_workflows
from vela_sdk.schemas.resource import ResourceDefinition
from vela_sdk.schemas.workflow import WorkflowDefinition
from vela_sdk.storage.protocol import WorkflowStore


class VelaToolset(BaseModel):
    """Azure AI Agents toolset that exposes Vela workflow functions.

    Provides workflow tools as plain Python callables compatible with
    ``azure.ai.agents.models.FunctionTool``, an optional ready-made Azure
    ``ToolSet``, and a prompt advisor for ``additional_instructions``.

    Usage::

        from vela_sdk.azure_agents import VelaToolset

        toolset = VelaToolset(workflows_dir="./workflows/")

        # Plain callables for FunctionTool
        fns = toolset.get_functions()

        # Ready-made Azure ToolSet (requires azure-ai-agents)
        azure_ts = toolset.get_toolset()

        # Prompt advisor for additional_instructions
        advisor = toolset.get_prompt_advisor()
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

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def get_functions(self) -> set[Callable[..., str]]:
        """Return workflow tool functions as plain callables.

        Each function has ``__name__`` set to the tool name (e.g.
        ``workflow_advance``) and uses type annotations + docstrings that
        ``azure.ai.agents.models.FunctionTool`` can parse for auto schema
        generation.

        Usage::

            from azure.ai.agents.models import FunctionTool
            functions = toolset.get_functions()
            tool = FunctionTool(functions=functions)
        """
        fn_map = create_workflow_functions(
            session_provider=self._resolved_session_provider,
            workflow_resolver=self._resolved_resolver,
            resource_resolver=self.resource_resolver,
            locale=self.locale,
            tool_prefix=self.tool_prefix,
            advance_tool_name=self._tool_names["advance"],
        )
        return set(fn_map.values())

    def get_functions_map(self) -> dict[str, Callable[..., str]]:
        """Return workflow tool functions as a name-keyed dict.

        Keys are ``"advance"``, ``"status"``, ``"list"``.
        """
        return create_workflow_functions(
            session_provider=self._resolved_session_provider,
            workflow_resolver=self._resolved_resolver,
            resource_resolver=self.resource_resolver,
            locale=self.locale,
            tool_prefix=self.tool_prefix,
            advance_tool_name=self._tool_names["advance"],
        )

    # ------------------------------------------------------------------
    # Azure ToolSet (requires azure-ai-agents)
    # ------------------------------------------------------------------

    def get_toolset(self) -> Any:
        """Return an ``azure.ai.agents.models.ToolSet`` with the workflow functions.

        Requires ``azure-ai-agents`` to be installed.

        Usage::

            azure_toolset = toolset.get_toolset()
            agent = client.create_agent(
                model="gpt-4o",
                instructions="...",
                toolset=azure_toolset,
            )
        """
        from azure.ai.agents.models import FunctionTool, ToolSet

        ts = ToolSet()
        ts.add(FunctionTool(functions=self.get_functions()))
        return ts

    # ------------------------------------------------------------------
    # Prompt advisor
    # ------------------------------------------------------------------

    def get_prompt_advisor(self, project_id: Optional[str] = None) -> str:
        """Generate a prompt advisor text for ``additional_instructions``.

        Describes available workflows and explains how to interact with
        the workflow tools so the Azure AI agent can guide the user through
        multi-step workflows.

        Usage::

            run = client.runs.create_and_process(
                thread_id=thread.id,
                agent_id=agent.id,
                additional_instructions=toolset.get_prompt_advisor(),
            )
        """
        loc = self.locale if self.locale is not None else get_locale()
        advance_name = self._tool_names["advance"]
        status_name = self._tool_names["status"]
        list_name = self._tool_names["list"]

        lines = [
            "## Vela Workflow Advisor",
            "",
            "Du hast Zugriff auf Workflow-Tools, mit denen du den Benutzer durch "
            "strukturierte, mehrstufige Prozesse fuehren kannst.",
            "",
        ]

        # List available workflows
        if self._workflows:
            lines.append("### Verfuegbare Workflows")
            lines.append("")
            for wf in self._workflows.values():
                desc = wf.description or ""
                lines.append(f"- **{wf.name}** (`{wf.id}`): {desc}")
                if wf.params:
                    param_strs = []
                    for p in wf.params:
                        tag = " [erforderlich]" if p.required else ""
                        param_strs.append(f"`{p.name}`{tag}")
                    lines.append(f"  Parameter: {', '.join(param_strs)}")
                if wf.steps:
                    step_names = [s.name or s.id for s in wf.steps]
                    lines.append(f"  Schritte: {' -> '.join(step_names)}")
            lines.append("")

        # Interaction pattern
        lines.extend([
            "### So arbeitest du mit Workflows",
            "",
            f"1. **Workflow starten**: Rufe `{advance_name}(workflow_id=\"...\")` auf. "
            f"Uebergib benoetigte Parameter als JSON-String im `params`-Feld.",
            f"2. **Prompt lesen**: Die Tool-Antwort enthaelt ein `prompt`-Feld mit "
            f"Anweisungen fuer den aktuellen Schritt und ein `next_action`-Feld mit "
            f"der naechsten Aktion.",
            f"3. **Schritt ausfuehren**: Fuehre die Aufgabe im Prompt aus und "
            f"sammle das Ergebnis.",
            f"4. **Weiterschalten**: Rufe `{advance_name}(run_id=\"...\", output=\"...\")` "
            f"auf, um zum naechsten Schritt zu gelangen.",
            f"5. **Wiederholen**: Fahre fort, bis der Workflow abgeschlossen ist "
            f"(`completed: true`).",
            "",
            f"- Status pruefen: `{status_name}(run_id=\"...\")`",
            f"- Workflows auflisten: `{list_name}()`",
            "",
            "**Wichtig**: Folge immer der `next_action` aus der Tool-Antwort. "
            "Sie enthaelt die genaue Anweisung, was als naechstes zu tun ist.",
        ])

        return "\n".join(lines)

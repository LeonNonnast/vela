"""Admin Module — Meta-agent navigator with admin tools and prompts."""

import os
from typing import Optional

import structlog
import yaml
from fastmcp import FastMCP

from src.shared.config import VELA_AGENTS_DIR, VELA_RESOURCES_DIR, VELA_WORKFLOWS_DIR
from src.shared.db.database import async_session_factory
from src.mcp.modules.base import VelaModuleBase
from src.mcp.modules.mcp_utils import to_json
from src.shared.schemas.agent import AgentDefinition
from src.shared.schemas.resource import ResourceDefinition
from src.shared.schemas.workflow import WorkflowDefinition

logger = structlog.get_logger()

_VALIDATION_MODELS = {
    "agent": AgentDefinition,
    "workflow": WorkflowDefinition,
    "resource": ResourceDefinition,
}

_TARGET_DIRS = {
    "agent": VELA_AGENTS_DIR,
    "workflow": VELA_WORKFLOWS_DIR,
    "resource": VELA_RESOURCES_DIR,
}


class AdminModule(VelaModuleBase):
    """Central navigator module with admin tools and prompts."""

    def __init__(self, mcp: FastMCP, session_factory=None, module_registry=None):
        self._session_factory = session_factory or async_session_factory
        self._module_registry = module_registry
        self._register_tools(mcp)
        self._register_prompts(mcp)

    def _register_tools(self, mcp: FastMCP):
        @mcp.tool(
            name="vela_validate",
            description="Validate a YAML definition (agent, workflow, or resource). Returns {valid: true} or {valid: false, errors: [...]}.",
        )
        async def vela_validate(type: str, content: str) -> str:
            return self._do_validate(type, content)

        @mcp.tool(
            name="vela_save",
            description=(
                "Validate and save a YAML definition. "
                "target='filesystem' (default): saves to ~/.vela/{type}s/. "
                "target='db': saves to a DB module (requires module_name). "
                "Reloads the affected module after saving."
            ),
        )
        async def vela_save(
            type: str,
            content: str,
            filename: Optional[str] = None,
            target: str = "filesystem",
            module_name: Optional[str] = None,
        ) -> str:
            if target == "db":
                return await self._do_save_db(type, content, filename, module_name)
            return self._do_save(type, content, filename)

        @mcp.tool(
            name="vela_status",
            description="Show Vela workspace status: counts of agents, workflows, resources, active runs, projects, and memories.",
        )
        async def vela_status() -> str:
            return await self._do_status()

    def _do_validate(self, type: str, content: str) -> str:
        if type not in _VALIDATION_MODELS:
            return to_json({"valid": False, "errors": [f"Unknown type: {type}. Use: agent, workflow, resource"]})

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            return to_json({"valid": False, "errors": [f"YAML syntax error: {e}"]})

        if not data or not isinstance(data, dict):
            return to_json({"valid": False, "errors": ["Empty or invalid YAML"]})

        model = _VALIDATION_MODELS[type]
        try:
            model(**data)
            return to_json({"valid": True})
        except Exception as e:
            errors = [str(e)]
            return to_json({"valid": False, "errors": errors})

    def _do_save(self, type: str, content: str, filename: Optional[str] = None) -> str:
        # Validate first
        validation = self._do_validate(type, content)
        import json
        result = json.loads(validation)
        if not result.get("valid"):
            return validation

        data = yaml.safe_load(content)
        target_dir = _TARGET_DIRS.get(type)
        if not target_dir:
            return to_json({"saved": False, "errors": [f"Unknown type: {type}"]})

        # Auto-generate filename
        if not filename:
            def_id = data.get("id", "unnamed")
            if type == "workflow":
                version = data.get("version", "1.0.0")
                filename = f"{def_id}@{version}.yaml"
            else:
                filename = f"{def_id}.yaml"

        os.makedirs(target_dir, exist_ok=True)
        filepath = os.path.join(target_dir, filename)

        with open(filepath, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        # Reload affected module
        self._reload_module(type)

        return to_json({
            "saved": True,
            "path": filepath,
            "note": "MCP prompts for new definitions are available after server restart.",
        })

    async def _do_save_db(self, type: str, content: str, filename: Optional[str] = None, module_name: Optional[str] = None) -> str:
        """Save a definition to a DB module."""
        import hashlib

        # Validate first
        validation = self._do_validate(type, content)
        import json
        result = json.loads(validation)
        if not result.get("valid"):
            return validation

        data = yaml.safe_load(content)

        if not self._module_registry:
            from src.shared.services.module_registry_service import ModuleRegistryService
            self._module_registry = ModuleRegistryService()
        registry = self._module_registry

        # Auto-generate filename/path
        def_id = data.get("id", "unnamed")
        if not filename:
            if type == "workflow":
                version = data.get("version", "1.0.0")
                filename = f"{type}s/{def_id}@{version}.yaml"
            else:
                filename = f"{type}s/{def_id}.yaml"
        elif "/" not in filename:
            filename = f"{type}s/{filename}"

        # Find or create DB module
        if not module_name:
            module_name = "default"

        source = await registry.find_source("db", "db", module_name)
        if not source:
            await registry.register_db_module(module_name=module_name)

        sha = hashlib.sha256(content.encode()).hexdigest()[:12]
        await registry.update_cached_file(
            owner="db",
            name=module_name,
            file_type=type,
            file_path=filename,
            content=content,
            sha=sha,
            provider="db",
        )

        return to_json({
            "saved": True,
            "target": "db",
            "module": module_name,
            "path": filename,
            "sha": sha,
        })

    def _reload_module(self, type: str):
        """Reload the module dict for the given type."""
        if type == "workflow":
            from src.mcp.modules.workflow_module import WorkflowModule
            wm = WorkflowModule.instance()
            if wm:
                wm._filesystem_workflows.clear()
                wm._load_filesystem_workflows()
        elif type == "agent":
            from src.mcp.modules.agent_module import AgentModule
            am = AgentModule.instance()
            if am:
                am._filesystem_agents.clear()
                am._load_filesystem_agents()
        elif type == "resource":
            from src.mcp.modules.resource_module import ResourceModule
            rm = ResourceModule.instance()
            if rm:
                rm._filesystem_resources.clear()
                rm._load_filesystem_resources()

    async def _do_status(self) -> str:
        from src.mcp.modules.agent_module import AgentModule
        from src.mcp.modules.resource_module import ResourceModule
        from src.mcp.modules.workflow_module import WorkflowModule

        am = AgentModule.instance()
        wm = WorkflowModule.instance()
        rm = ResourceModule.instance()

        agents_count = len(am._filesystem_agents) if am else 0
        workflows_count = len(wm._filesystem_workflows) if wm else 0
        resources_count = len(rm._filesystem_resources) if rm else 0

        # DB counts
        active_runs = 0
        projects_count = 0
        memories_count = 0
        try:
            from src.shared.repositories.workflow_repository import WorkflowRepository
            from src.shared.repositories.project_repository import ProjectRepository
            from src.shared.repositories.memory_repository import MemoryRepository
            async with self._session_factory() as session:
                wf_repo = WorkflowRepository(session)
                runs = await wf_repo.list_active()
                active_runs = len(runs)

                proj_repo = ProjectRepository(session)
                projects = await proj_repo.list_all()
                projects_count = len(projects)

                mem_repo = MemoryRepository(session)
                memories = await mem_repo.search(limit=1000)
                memories_count = len(memories)
        except Exception as e:
            logger.warning("vela_status.db_error", error=str(e))

        return to_json({
            "agents": agents_count,
            "workflows": workflows_count,
            "resources": resources_count,
            "active_runs": active_runs,
            "projects": projects_count,
            "memories": memories_count,
        })

    def _register_prompts(self, mcp: FastMCP):
        @mcp.prompt(
            name="vela",
            description="Vela — Workspace Navigator. Central entry point for managing agents, workflows, resources, and projects.",
        )
        async def vela_prompt() -> str:
            from src.mcp.modules.agent_module import AgentModule
            from src.mcp.modules.workflow_module import WorkflowModule

            am = AgentModule.instance()
            wm = WorkflowModule.instance()

            parts = [
                "# Vela — Workspace Navigator",
                "",
                "Ich bin Vela, dein zentraler Einstiegspunkt für die Verwaltung deines AI-Workspaces.",
                "",
            ]

            # List agents
            if am and am._filesystem_agents:
                parts.append("## Verfügbare Agenten")
                for a in am._filesystem_agents.values():
                    parts.append(f"- **{a.name}** (`/vela_agent_{a.id}`)")
                parts.append("")

            # List workflows
            if wm and wm._filesystem_workflows:
                parts.append("## Verfügbare Workflows")
                for wf in wm._filesystem_workflows.values():
                    parts.append(f"- **{wf.name}** v{wf.version} — `vela_advance_workflow(workflow_id=\"{wf.id}\")`")
                parts.append("")

            parts.extend([
                "## Schnellstart",
                "",
                "Starte den geführten Navigator:",
                '```',
                'vela_advance_workflow(workflow_id="vela")',
                '```',
                "",
                "Oder direkt:",
                '- **Agent erstellen**: `vela_advance_workflow(workflow_id="create-agent")`',
                '- **Workflow erstellen**: `vela_advance_workflow(workflow_id="create-workflow")`',
                '- **Resource anlegen**: `vela_advance_workflow(workflow_id="create-resource")`',
                '- **Projekt einrichten**: `vela_advance_workflow(workflow_id="setup-project")`',
                '- **Team verwalten**: `vela_advance_workflow(workflow_id="team-management")`',
                '- **Status anzeigen**: `vela_status()`',
                "",
                "Für Hilfe: `/vela_help`",
            ])

            return "\n".join(parts)

        @mcp.prompt(
            name="vela_help",
            description="Vela Help — Tool reference, available schemas, and usage guide.",
        )
        async def vela_help_prompt() -> str:
            parts = [
                "# Vela Help — Tool-Referenz",
                "",
                "## MCP Tools",
                "",
                "| Tool | Beschreibung |",
                "|------|-------------|",
                "| `vela_set_project` | Projekt erstellen/aktualisieren (Upsert by Slug) |",
                "| `vela_get_project` | Projekt nach Slug abrufen |",
                "| `vela_list_projects` | Aktive Projekte auflisten |",
                "| `vela_remember` | Erinnerung speichern (decision/insight/fact/convention) |",
                "| `vela_recall` | Erinnerungen suchen (Index ohne Inhalt) |",
                "| `vela_get_memory` | Vollständigen Memory-Inhalt nach ID abrufen |",
                "| `vela_forget` | Erinnerung nach ID löschen |",
                "| `vela_advance_workflow` | Workflow starten/fortsetzen/vorantreiben |",
                "| `vela_workflow_status` | Status eines Workflow-Runs abrufen |",
                "| `vela_list_workflows` | Workflow-Definitionen und aktive Runs auflisten |",
                "| `vela_list_agents` | Verfügbare Agenten-Personas auflisten |",
                "| `vela_list_resources` | Verfügbare Ressourcen auflisten |",
                "| `vela_validate` | YAML-Definition validieren (agent/workflow/resource) |",
                "| `vela_save` | YAML validieren und nach ~/.vela speichern |",
                "| `vela_status` | Workspace-Status anzeigen (Zähler) |",
                "",
                "## Admin-Workflows",
                "",
                "- `vela_validate(type=\"agent\", content=\"...\")` — YAML prüfen",
                "- `vela_save(type=\"workflow\", content=\"...\")` — Validieren + speichern nach ~/.vela/",
                "",
                "## Speicherorte",
                "",
                "| Typ | Verzeichnis |",
                "|-----|------------|",
                "| Workflows | `~/.vela/workflows/` |",
                "| Agents | `~/.vela/agents/` |",
                "| Resources | `~/.vela/resources/` |",
                "",
                "## Schema-Referenz",
                "",
                "Verwende `vela_list_resources()` um verfügbare Schemas einzusehen.",
                "Nutze `vela_validate()` um YAML vor dem Speichern zu prüfen.",
            ]

            return "\n".join(parts)

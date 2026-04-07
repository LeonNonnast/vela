"""Context Module — Project management MCP tools."""

from typing import Optional

import structlog
from fastmcp import FastMCP

from src.mcp.modules.base import VelaModuleBase
from src.mcp.modules.mcp_utils import to_json
from src.shared.services.project_service import ProjectService

logger = structlog.get_logger()


class ContextModule(VelaModuleBase):
    """Manages project context via MCP tools."""

    def __init__(self, mcp: FastMCP, project_service: ProjectService):
        self._project_service = project_service
        self._register_tools(mcp)

    def _register_tools(self, mcp: FastMCP):
        @mcp.tool(name="vela_set_project", description="Create or update a project context. Uses upsert by slug.")
        async def vela_set_project(
            slug: str,
            name: str,
            path: Optional[str] = None,
            tech_stack: Optional[list[str]] = None,
            conventions: Optional[list[str]] = None,
        ) -> str:
            result = await self._project_service.upsert_project(
                slug=slug, name=name, path=path,
                tech_stack=tech_stack, conventions=conventions,
            )
            return to_json(result)

        @mcp.tool(name="vela_get_project", description="Get a project by its slug.")
        async def vela_get_project(slug: str) -> str:
            result = await self._project_service.get_project(slug)
            if result is None:
                return to_json({"error": "not found", "slug": slug})
            return to_json(result)

        @mcp.tool(name="vela_list_projects", description="List all active projects.")
        async def vela_list_projects() -> str:
            results = await self._project_service.list_projects()
            return to_json(results)

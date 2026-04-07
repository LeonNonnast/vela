"""Memory Module — Knowledge storage and retrieval MCP tools."""

from typing import Optional

import structlog
from fastmcp import FastMCP

from src.mcp.modules.base import VelaModuleBase
from src.mcp.modules.mcp_utils import to_json
from src.shared.services.memory_service import MemoryService

logger = structlog.get_logger()


class MemoryModule(VelaModuleBase):
    """Manages memory entries via MCP tools."""

    def __init__(self, mcp: FastMCP, memory_service: MemoryService):
        self._memory_service = memory_service
        self._register_tools(mcp)

    def _register_tools(self, mcp: FastMCP):
        @mcp.tool(
            name="vela_remember",
            description="Store a memory entry. Categories: decision, insight, fact, convention.",
        )
        async def vela_remember(
            title: str,
            content: str,
            category: str,
            tags: Optional[list[str]] = None,
            project_slug: Optional[str] = None,
        ) -> str:
            result = await self._memory_service.remember(
                title=title, content=content, category=category,
                tags=tags, project_slug=project_slug,
            )
            return to_json(result)

        @mcp.tool(
            name="vela_recall",
            description="Search memories. Returns compact index (id, title, category, tags, created_at) — NO content. Use vela_get_memory for full content.",
        )
        async def vela_recall(
            query: Optional[str] = None,
            category: Optional[str] = None,
            tags: Optional[list[str]] = None,
            project_slug: Optional[str] = None,
            limit: int = 20,
        ) -> str:
            results = await self._memory_service.recall(
                query=query, category=category, tags=tags,
                project_slug=project_slug, limit=limit,
            )
            return to_json(results)

        @mcp.tool(
            name="vela_get_memory",
            description="Get full content of a specific memory by ID.",
        )
        async def vela_get_memory(id: str) -> str:
            result = await self._memory_service.get_memory(id)
            if result is None:
                return to_json({"error": "Memory not found", "id": id})
            return to_json(result)

        @mcp.tool(
            name="vela_forget",
            description="Delete a memory entry by ID.",
        )
        async def vela_forget(id: str) -> str:
            result = await self._memory_service.forget(id)
            return to_json(result)

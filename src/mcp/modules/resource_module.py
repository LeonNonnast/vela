"""Resource Module — MCP resources and knowledge layer."""

from typing import Optional

import structlog
from fastmcp import FastMCP

from src.shared.config import VELA_RESOURCES_DIR
from src.mcp.modules.base import VelaModuleBase
from src.shared.schemas.resource import ResourceDefinition
from src.shared.services.filesystem_loader import load_from_filesystem
from src.shared.services.resource_loader import load_resources

logger = structlog.get_logger()


class ResourceModule(VelaModuleBase):
    """Manages resources as MCP resources and provides resolver for workflows."""

    def __init__(self, mcp: FastMCP, module_registry=None):
        self._module_registry = module_registry
        self._filesystem_resources: dict[str, ResourceDefinition] = {}
        self._load_filesystem_resources()
        self._register_resources(mcp)
        self._register_tools(mcp)

    def _load_filesystem_resources(self):
        """Load resource definitions from filesystem (bundled + user)."""
        self._filesystem_resources = load_from_filesystem(load_resources, "resources", VELA_RESOURCES_DIR)
        logger.info("resource_module.filesystem_loaded", count=len(self._filesystem_resources))

    async def _get_all_resources(self) -> dict[str, ResourceDefinition]:
        """Get all resources from filesystem + registry (async, includes DB/local/github modules)."""
        merged: dict[str, ResourceDefinition] = {}

        # 1. Registry modules (DB/local/github — lowest priority after bundled)
        if self._module_registry:
            try:
                registry_resources = await self._module_registry.get_resources()
                merged.update(registry_resources)
            except Exception as e:
                logger.warning("resource_module.registry_load_failed", error=str(e))

        # 2. Filesystem resources (bundled + user — highest priority, overrides registry)
        merged.update(self._filesystem_resources)

        return merged

    async def _get_filtered_resources(self) -> dict[str, ResourceDefinition]:
        """Get resources filtered by runtime module filter (env var + header)."""
        from src.shared.services.module_filter import apply_runtime_filters
        return await apply_runtime_filters(await self._get_all_resources())

    def _get_uri(self, resource: ResourceDefinition) -> str:
        """Derive URI for a resource."""
        if resource.uri_pattern:
            return resource.uri_pattern
        return f"vela://{resource.type.value}/{resource.id}"

    def _register_resources(self, mcp: FastMCP):
        """Register each resource as an MCP resource."""
        for resource_id, resource_def in self._filesystem_resources.items():
            uri = self._get_uri(resource_def)

            def make_resource_handler(resource: ResourceDefinition):
                async def handler() -> str:
                    return resource.content

                return handler

            mcp.resource(
                uri,
                name=resource_def.name,
                description=resource_def.description,
                mime_type=resource_def.mime_type,
            )(make_resource_handler(resource_def))

    def _register_tools(self, mcp: FastMCP):
        """Register resource tools."""

        @mcp.tool(
            name="vela_list_resources",
            description="List available resources (schemas, examples, conventions, etc.).",
        )
        async def vela_list_resources() -> str:
            from src.mcp.modules.mcp_utils import to_json
            all_resources = await self._get_filtered_resources()
            return to_json([
                {
                    "id": r.id,
                    "name": r.name,
                    "type": r.type.value,
                    "description": r.description,
                    "tags": r.tags,
                    "uri": self._get_uri(r),
                }
                for r in all_resources.values()
            ])

        @mcp.tool(
            name="vela_get_resource",
            description="Get full content of a resource by ID or URI. Use this to load resources referenced in workflow prompts.",
        )
        async def vela_get_resource(id: str) -> str:
            from src.mcp.modules.mcp_utils import to_json
            resource = await self.resolve_async(id)
            if not resource:
                return to_json({"error": "Resource not found", "id": id})
            return to_json({
                "id": resource.id,
                "name": resource.name,
                "type": resource.type.value,
                "content": resource.content,
            })

    def resolve(self, ref: str) -> Optional[ResourceDefinition]:
        """Resolve a resource by ID or URI (sync, filesystem only).

        Used by workflow prompt assembly to inject resource content.
        """
        # Direct ID lookup
        if ref in self._filesystem_resources:
            return self._filesystem_resources[ref]

        # URI lookup
        for resource in self._filesystem_resources.values():
            if self._get_uri(resource) == ref:
                return resource

        return None

    async def resolve_async(self, ref: str) -> Optional[ResourceDefinition]:
        """Resolve a resource by ID or URI (async, includes DB/local/github modules)."""
        all_resources = await self._get_all_resources()

        # Direct ID lookup
        if ref in all_resources:
            return all_resources[ref]

        # URI lookup
        for resource in all_resources.values():
            if self._get_uri(resource) == ref:
                return resource

        return None

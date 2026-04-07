"""Module Registry — Registers all Vela MCP modules on a FastMCP server."""

from fastmcp import FastMCP

from src.mcp.modules.base import VelaModuleBase
from src.mcp.modules.context_module import ContextModule
from src.mcp.modules.memory_module import MemoryModule
from src.mcp.modules.workflow_module import WorkflowModule
from src.mcp.modules.agent_module import AgentModule
from src.mcp.modules.resource_module import ResourceModule
from src.mcp.modules.vela_module import AdminModule
from src.mcp.modules.module_hub_module import ModuleHubModule
from src.shared.services.module_registry_service import ModuleRegistryService
from src.shared.services.project_service import ProjectService
from src.shared.services.memory_service import MemoryService


def register_all_modules(mcp: FastMCP, session_factory=None) -> None:
    """Register all Vela MCP modules on the given FastMCP server.

    Args:
        mcp: The FastMCP server instance.
        session_factory: Optional async session factory for DB access.
            Defaults to the global async_session_factory.
    """
    if session_factory is None:
        from src.shared.db.database import async_session_factory
        session_factory = async_session_factory

    # Services
    project_service = ProjectService(session_factory)
    memory_service = MemoryService(session_factory)
    module_registry = ModuleRegistryService(session_factory=session_factory)

    # Register modules
    ContextModule.construct(mcp=mcp, project_service=project_service)
    MemoryModule.construct(mcp=mcp, memory_service=memory_service)
    WorkflowModule.construct(mcp=mcp, session_factory=session_factory, module_registry=module_registry)
    AgentModule.construct(mcp=mcp, module_registry=module_registry)
    ResourceModule.construct(mcp=mcp, module_registry=module_registry)
    AdminModule.construct(mcp=mcp, session_factory=session_factory, module_registry=module_registry)
    ModuleHubModule.construct(mcp=mcp, module_registry=module_registry)

"""Module filter middleware — filters tools/prompts by VELA_MODULES env var + X-Vela-Modules header."""

from typing import Any, Sequence

import structlog
from fastmcp.server.middleware import Middleware, MiddlewareContext, CallNext

from src.shared.config import VELA_MODULES
from src.shared.services.module_filter import ModuleFilter

logger = structlog.get_logger()

# Core tools that are ALWAYS visible regardless of filter
CORE_TOOLS = {
    "vela_set_project", "vela_get_project", "vela_list_projects",
    "vela_remember", "vela_recall", "vela_get_memory", "vela_forget",
    "vela_advance_workflow", "vela_workflow_status", "vela_list_workflows",
    "vela_list_resources", "vela_get_resource", "vela_list_agents",
    "vela_clone_repo", "vela_sync_repo", "vela_remove_repo",
    "vela_list_repos", "vela_create_module", "vela_push_to_module",
    "vela_delete_from_module", "vela_validate", "vela_save", "vela_status",
}

CORE_PROMPTS = {"vela", "vela_help"}


class VelaModuleFilterMiddleware(Middleware):
    """Filter tools/prompts based on VELA_MODULES env var + X-Vela-Modules header.

    Admin filter (env var) sets the server-wide baseline.
    User filter (header) can only narrow further, never widen.
    """

    def __init__(self):
        self._admin_filter = ModuleFilter(VELA_MODULES)

    def _get_effective_filter(self) -> ModuleFilter:
        """Get the effective filter combining admin + user preferences."""
        user_patterns = ""
        try:
            from fastmcp.server.dependencies import get_http_request
            request = get_http_request()
            user_patterns = request.headers.get("x-vela-modules", "")
        except (RuntimeError, LookupError):
            pass  # stdio mode or no request context

        if not user_patterns:
            return self._admin_filter

        user_filter = ModuleFilter(user_patterns)

        if not self._admin_filter.active:
            return user_filter

        # Both active: create a combined filter that requires BOTH to match
        return _IntersectionFilter(self._admin_filter, user_filter)

    async def on_list_tools(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        tools = await call_next(context)
        mf = self._get_effective_filter()
        if not mf.active:
            return tools
        return [t for t in tools if t.name in CORE_TOOLS or mf.matches(t.name)]

    async def on_list_prompts(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        prompts = await call_next(context)
        mf = self._get_effective_filter()
        if not mf.active:
            return prompts
        return [p for p in prompts if p.name in CORE_PROMPTS or mf.matches(p.name)]


class _IntersectionFilter:
    """Filter that requires BOTH admin and user filters to match."""

    def __init__(self, admin: ModuleFilter, user: ModuleFilter):
        self._admin = admin
        self._user = user
        self.active = True

    def matches(self, name: str) -> bool:
        return self._admin.matches(name) and self._user.matches(name)

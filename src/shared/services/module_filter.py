"""Module filter — glob-based filtering for VELA_MODULES env var."""

import fnmatch
from typing import TypeVar

from src.shared.config import VELA_MODULES

T = TypeVar("T")


async def apply_runtime_filters(items: dict[str, T]) -> dict[str, T]:
    """Apply admin (env var) + user (HTTP header) module filters.

    Used by agent, resource, and workflow modules to filter definitions
    at request time.
    """
    if VELA_MODULES:
        items = ModuleFilter(VELA_MODULES).filter_dict(items)

    try:
        from fastmcp.server.dependencies import get_http_request
        request = get_http_request()
        header = request.headers.get("x-vela-modules", "")
        if header:
            items = ModuleFilter(header).filter_dict(items)
    except (RuntimeError, LookupError):
        pass  # stdio mode or no request context

    return items


class ModuleFilter:
    """Filters module names by glob patterns (fnmatch).

    Usage:
        f = ModuleFilter("migration-*,team-a-*")
        f.matches("migration-pack")  # True
        f.matches("brainstorming")   # False

        f = ModuleFilter("")  # No filter
        f.matches("anything")  # True
    """

    def __init__(self, patterns: str = ""):
        self.patterns = [p.strip() for p in patterns.split(",") if p.strip()]
        self.active = len(self.patterns) > 0

    def matches(self, name: str) -> bool:
        if not self.active:
            return True
        return any(fnmatch.fnmatch(name, p) for p in self.patterns)

    def filter_dict(self, d: dict) -> dict:
        """Filter a dict by key names. Keys may contain '@version' suffix."""
        if not self.active:
            return d
        return {k: v for k, v in d.items() if self.matches(k.split("@")[0])}

    def filter_list(self, names: list[str]) -> list[str]:
        if not self.active:
            return names
        return [n for n in names if self.matches(n)]

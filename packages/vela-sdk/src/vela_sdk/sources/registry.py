"""Global MCP-source-handler registry.

Module-level dict; lookups are O(1). Re-registering the same name raises
to surface duplicate-bootstrap bugs early. `clear_sources()` is exported
for tests only.
"""

from typing import Optional

from vela_sdk.sources.types import SourceHandler

_handlers: dict[str, SourceHandler] = {}


def register_source(name: str, handler: SourceHandler) -> None:
    """Register a handler for a source namespace (e.g. "devops").

    Raises:
        ValueError: if the name is already registered.
    """
    if name in _handlers:
        raise ValueError(f"source '{name}' already registered")
    _handlers[name] = handler


def resolve_source(name: str) -> Optional[SourceHandler]:
    """Look up a registered handler. Returns None if not registered."""
    return _handlers.get(name)


def clear_sources() -> None:
    """Test utility — wipes the registry so suites stay isolated."""
    _handlers.clear()

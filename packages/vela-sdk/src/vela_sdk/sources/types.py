"""Source registry — generic named-callback handlers for `mcp_call` steps
and the `fetch` step field.

Both schema features describe the same idea: "call a mounted MCP source
by name". Neither engine has a real MCP client, so this mirrors the
TypeScript SDK's `delegate` registry pattern instead: the embedding app
registers a handler per source namespace (e.g. "devops"), and the engine
looks it up and invokes it in-process.
"""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


def _noop_log(msg: str, meta: Any = None) -> None:
    pass


@dataclass
class SourceContext:
    """Context passed to a source handler when it is invoked."""

    signal: Optional[Any] = None  # cancellation token, if the caller has one
    log: Callable[..., None] = _noop_log


# tool, params, ctx -> result
SourceHandler = Callable[[str, dict, SourceContext], Awaitable[Any]]

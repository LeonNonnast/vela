"""Extension protocols for vela-sdk FastMCP integration.

Defines pluggable interfaces so other MCP servers can inject custom logic
for workflow resolution, session management, parameter filtering, and
project resolution.
"""

from contextlib import asynccontextmanager
from typing import AsyncContextManager, AsyncIterator, Optional, Protocol, runtime_checkable

from vela_sdk.schemas.workflow import ParamDefinition, WorkflowDefinition
from vela_sdk.storage.protocol import WorkflowStore


@runtime_checkable
class WorkflowResolver(Protocol):
    """Resolves workflow definitions. Async to support DB/network lookups."""

    async def get_workflow(
        self, workflow_id: str, version: Optional[str] = None
    ) -> Optional[WorkflowDefinition]: ...

    async def list_workflows(self) -> dict[str, WorkflowDefinition]: ...


@runtime_checkable
class SessionProvider(Protocol):
    """Provides WorkflowStore instances with proper lifecycle management (e.g. DB sessions)."""

    def session(self) -> AsyncContextManager[WorkflowStore]: ...


@runtime_checkable
class ParamFilter(Protocol):
    """Filters workflow params for elicitation."""

    def filter_missing_params(
        self, wf_def: WorkflowDefinition, provided_params: dict
    ) -> list[ParamDefinition]: ...


@runtime_checkable
class ProjectResolver(Protocol):
    """Resolves project identifiers."""

    async def resolve_project_id(
        self, project_slug: Optional[str] = None
    ) -> Optional[str]: ...


# ---------------------------------------------------------------------------
# Default implementations
# ---------------------------------------------------------------------------


class InMemoryWorkflowResolver:
    """Wraps a dict[str, WorkflowDefinition] to satisfy WorkflowResolver."""

    def __init__(self, workflows: dict[str, WorkflowDefinition]) -> None:
        self._workflows = workflows

    async def get_workflow(
        self, workflow_id: str, version: Optional[str] = None
    ) -> Optional[WorkflowDefinition]:
        if version:
            key = f"{workflow_id}@{version}"
            return self._workflows.get(key)
        matches = [
            wf for wf in self._workflows.values() if wf.id == workflow_id
        ]
        if not matches:
            return None
        matches.sort(key=lambda wf: wf.version, reverse=True)
        return matches[0]

    async def list_workflows(self) -> dict[str, WorkflowDefinition]:
        return dict(self._workflows)


class SimpleSessionProvider:
    """Wraps a single WorkflowStore, returning it as an async context manager."""

    def __init__(self, store: WorkflowStore) -> None:
        self._store = store

    def session(self) -> AsyncContextManager[WorkflowStore]:
        @asynccontextmanager
        async def _ctx() -> AsyncIterator[WorkflowStore]:
            yield self._store

        return _ctx()


class DefaultParamFilter:
    """Returns required params that are missing from provided_params."""

    def filter_missing_params(
        self, wf_def: WorkflowDefinition, provided_params: dict
    ) -> list[ParamDefinition]:
        return [
            p for p in wf_def.params
            if p.required and p.name not in provided_params
        ]

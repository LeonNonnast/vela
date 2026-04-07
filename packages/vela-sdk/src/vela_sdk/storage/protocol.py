"""Storage protocol for workflow runs."""

from typing import Optional, Protocol, runtime_checkable

from vela_sdk.engine.types import WorkflowRunState, WorkflowRunStatus


@runtime_checkable
class WorkflowStore(Protocol):
    """Protocol that storage backends must implement.

    All methods are async. Implementations handle serialization
    and persistence details internally.
    """

    async def find_by_identity(
        self,
        workflow_id: str,
        identity_params: dict[str, str],
    ) -> Optional[WorkflowRunState]:
        """Find an active/paused run matching workflow_id and identity params."""
        ...

    async def create_run(
        self,
        workflow_id: str,
        workflow_version: str,
        params: Optional[dict] = None,
        project_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        parent_step_id: Optional[str] = None,
    ) -> WorkflowRunState:
        """Create a new workflow run."""
        ...

    async def update_step(
        self,
        run_id: str,
        step_id: Optional[str],
        state_data: Optional[dict] = None,
        status: Optional[WorkflowRunStatus] = None,
    ) -> WorkflowRunState:
        """Update the current step and optionally state/status."""
        ...

    async def get_by_id(self, run_id: str) -> Optional[WorkflowRunState]:
        """Get a workflow run by ID."""
        ...

    async def list_active(
        self,
        workflow_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[WorkflowRunState]:
        """List active/paused workflow runs."""
        ...

    async def commit(self) -> None:
        """Commit pending changes."""
        ...

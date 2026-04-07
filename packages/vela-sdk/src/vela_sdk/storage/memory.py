"""In-memory workflow store for testing."""

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional

from vela_sdk.engine.types import WorkflowRunState, WorkflowRunStatus


class InMemoryStore:
    """Dict-based in-memory store for testing and prototyping.

    Implements the WorkflowStore protocol without any external dependencies.
    """

    def __init__(self) -> None:
        self._runs: dict[str, WorkflowRunState] = {}

    async def find_by_identity(
        self,
        workflow_id: str,
        identity_params: dict[str, str],
    ) -> Optional[WorkflowRunState]:
        for run in self._runs.values():
            if run.workflow_id != workflow_id:
                continue
            if run.status not in (WorkflowRunStatus.ACTIVE, WorkflowRunStatus.PAUSED):
                continue
            if all(run.params.get(k) == v for k, v in identity_params.items()):
                return run
        return None

    async def create_run(
        self,
        workflow_id: str,
        workflow_version: str,
        params: Optional[dict] = None,
        project_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        parent_step_id: Optional[str] = None,
    ) -> WorkflowRunState:
        now = datetime.now(timezone.utc)
        run = WorkflowRunState(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            params=params or {},
            project_id=project_id,
            parent_run_id=parent_run_id,
            parent_step_id=parent_step_id,
            status=WorkflowRunStatus.ACTIVE,
            state_data={},
            started_at=now,
            updated_at=now,
        )
        self._runs[run.id] = run
        return run

    async def update_step(
        self,
        run_id: str,
        step_id: Optional[str],
        state_data: Optional[dict] = None,
        status: Optional[WorkflowRunStatus] = None,
    ) -> WorkflowRunState:
        run = self._runs[run_id]
        if step_id is not None:
            run.current_step = step_id
        if state_data is not None:
            run.state_data.update(state_data)
        if status is not None:
            run.status = status
            if status in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.CANCELLED):
                run.completed_at = datetime.now(timezone.utc)
        run.updated_at = datetime.now(timezone.utc)
        return run

    async def get_by_id(self, run_id: str) -> Optional[WorkflowRunState]:
        return self._runs.get(run_id)

    async def list_active(
        self,
        workflow_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[WorkflowRunState]:
        results = []
        for run in self._runs.values():
            if run.status not in (WorkflowRunStatus.ACTIVE, WorkflowRunStatus.PAUSED):
                continue
            if workflow_id and run.workflow_id != workflow_id:
                continue
            if project_id and run.project_id != project_id:
                continue
            results.append(run)
        results.sort(key=lambda r: r.updated_at or datetime.min, reverse=True)
        return results

    async def commit(self) -> None:
        """No-op for in-memory store."""
        pass

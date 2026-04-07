"""Adapter that wraps Vela's WorkflowRepository as a vela-sdk WorkflowStore.

This allows the SDK's WorkflowEngine to work with Vela's existing
SQLAlchemy session and WorkflowRun ORM model.
"""

import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.db.models import WorkflowRun, WorkflowRunStatus as OrmStatus, utcnow
from src.shared.repositories.workflow_repository import WorkflowRepository
from vela_sdk.engine.types import WorkflowRunState, WorkflowRunStatus


class VelaWorkflowStore:
    """Adapts WorkflowRepository to the vela-sdk WorkflowStore protocol."""

    def __init__(self, repo: WorkflowRepository, session: AsyncSession):
        self._repo = repo
        self._session = session

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _orm_to_state(run: WorkflowRun) -> WorkflowRunState:
        """Convert ORM WorkflowRun to SDK WorkflowRunState."""
        status_map = {
            OrmStatus.ACTIVE: WorkflowRunStatus.ACTIVE,
            OrmStatus.PAUSED: WorkflowRunStatus.PAUSED,
            OrmStatus.COMPLETED: WorkflowRunStatus.COMPLETED,
            OrmStatus.CANCELLED: WorkflowRunStatus.CANCELLED,
        }
        return WorkflowRunState(
            id=run.id,
            workflow_id=run.workflow_id,
            workflow_version=run.workflow_version or "1.0.0",
            current_step=run.current_step,
            status=status_map.get(run.status, WorkflowRunStatus.ACTIVE),
            params=json.loads(run.params) if run.params else {},
            state_data=json.loads(run.state_data) if run.state_data else {},
            project_id=run.project_id,
            parent_run_id=run.parent_run_id,
            parent_step_id=run.parent_step_id,
            started_at=run.started_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
        )

    @staticmethod
    def _sdk_status_to_orm(status: WorkflowRunStatus) -> OrmStatus:
        """Convert SDK WorkflowRunStatus to ORM WorkflowRunStatus."""
        return OrmStatus(status.value)

    # ------------------------------------------------------------------
    # WorkflowStore protocol implementation
    # ------------------------------------------------------------------

    async def find_by_identity(
        self,
        workflow_id: str,
        identity_params: dict[str, str],
    ) -> Optional[WorkflowRunState]:
        run = await self._repo.find_by_identity(workflow_id, identity_params)
        return self._orm_to_state(run) if run else None

    async def create_run(
        self,
        workflow_id: str,
        workflow_version: str,
        params: Optional[dict] = None,
        project_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        parent_step_id: Optional[str] = None,
    ) -> WorkflowRunState:
        run = await self._repo.create_run(
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            params=params,
            project_id=project_id,
            parent_run_id=parent_run_id,
            parent_step_id=parent_step_id,
        )
        return self._orm_to_state(run)

    async def update_step(
        self,
        run_id: str,
        step_id: Optional[str],
        state_data: Optional[dict] = None,
        status: Optional[WorkflowRunStatus] = None,
    ) -> WorkflowRunState:
        run = await self._repo.get_by_id(run_id)
        if not run:
            raise ValueError(f"Run not found: {run_id}")
        orm_status = self._sdk_status_to_orm(status) if status else None
        updated = await self._repo.update_step(run, step_id, state_data=state_data, status=orm_status)
        return self._orm_to_state(updated)

    async def get_by_id(self, run_id: str) -> Optional[WorkflowRunState]:
        run = await self._repo.get_by_id(run_id)
        return self._orm_to_state(run) if run else None

    async def list_active(
        self,
        workflow_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[WorkflowRunState]:
        runs = await self._repo.list_active(workflow_id=workflow_id, project_id=project_id)
        return [self._orm_to_state(r) for r in runs]

    async def commit(self) -> None:
        await self._session.commit()

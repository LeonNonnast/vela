"""Workflow run repository for database operations."""

import json
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.db.models import WorkflowRun, WorkflowRunStatus
from src.shared.repositories.base_sqlalchemy import BaseSQLAlchemyRepository


class WorkflowRepository(BaseSQLAlchemyRepository[WorkflowRun]):
    """Repository for WorkflowRun entity operations."""

    model_class = WorkflowRun

    async def find_by_identity(
        self,
        workflow_id: str,
        identity_params: dict[str, str],
    ) -> Optional[WorkflowRun]:
        """Find an active/paused run matching workflow_id and identity params.

        Identity params are stored as part of the run's params JSON.
        """
        stmt = select(WorkflowRun).where(
            and_(
                WorkflowRun.workflow_id == workflow_id,
                WorkflowRun.status.in_([
                    WorkflowRunStatus.ACTIVE,
                    WorkflowRunStatus.PAUSED,
                ]),
            )
        ).order_by(WorkflowRun.started_at.desc())

        result = await self.session.execute(stmt)
        runs = result.scalars().all()

        # Match identity params against stored params
        for run in runs:
            if run.params:
                run_params = json.loads(run.params)
                if all(run_params.get(k) == v for k, v in identity_params.items()):
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
    ) -> WorkflowRun:
        """Create a new workflow run."""
        run = WorkflowRun(
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            params=json.dumps(params) if params else None,
            project_id=project_id,
            parent_run_id=parent_run_id,
            parent_step_id=parent_step_id,
            status=WorkflowRunStatus.ACTIVE,
        )
        return await self.create(run)

    async def update_step(
        self,
        run: WorkflowRun,
        step_id: Optional[str],
        state_data: Optional[dict] = None,
        status: Optional[WorkflowRunStatus] = None,
    ) -> WorkflowRun:
        """Update the current step and optionally state/status."""
        if step_id is not None:
            run.current_step = step_id
        if state_data is not None:
            # Merge with existing state
            existing = json.loads(run.state_data) if run.state_data else {}
            existing.update(state_data)
            run.state_data = json.dumps(existing)
        if status is not None:
            run.status = status
            if status in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.CANCELLED):
                from src.shared.db.models import utcnow
                run.completed_at = utcnow()
        await self.session.flush()
        return run

    async def list_active(
        self,
        workflow_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[WorkflowRun]:
        """List active/paused workflow runs."""
        stmt = select(WorkflowRun).where(
            WorkflowRun.status.in_([
                WorkflowRunStatus.ACTIVE,
                WorkflowRunStatus.PAUSED,
            ])
        )
        if workflow_id:
            stmt = stmt.where(WorkflowRun.workflow_id == workflow_id)
        if project_id:
            stmt = stmt.where(WorkflowRun.project_id == project_id)
        stmt = stmt.order_by(WorkflowRun.updated_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_runs(
        self,
        workflow_id: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[WorkflowRunStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkflowRun]:
        """List workflow runs with optional filters and pagination."""
        stmt = select(WorkflowRun)
        if status:
            stmt = stmt.where(WorkflowRun.status == status)
        if workflow_id:
            stmt = stmt.where(WorkflowRun.workflow_id == workflow_id)
        if project_id:
            stmt = stmt.where(WorkflowRun.project_id == project_id)
        stmt = stmt.order_by(WorkflowRun.updated_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

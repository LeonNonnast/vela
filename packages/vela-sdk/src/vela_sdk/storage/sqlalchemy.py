"""SQLAlchemy-based workflow store."""

import enum
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Enum, Index, String, Text, select, and_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from vela_sdk.engine.types import WorkflowRunState, WorkflowRunStatus


def _generate_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _WorkflowRunStatus(str, enum.Enum):
    """ORM-level status enum (mirrors WorkflowRunStatus)."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Base(DeclarativeBase):
    pass


class WorkflowRunModel(Base):
    """Standalone WorkflowRun ORM model for the SDK.

    No foreign keys to external tables — project_id is a plain string.
    """

    __tablename__ = "workflow_runs"

    id = Column(String(36), primary_key=True, default=_generate_uuid)
    workflow_id = Column(String(255), nullable=False)
    workflow_version = Column(String(50), nullable=True)
    project_id = Column(String(36), nullable=True, index=True)
    params = Column(Text, nullable=True)  # JSON
    current_step = Column(String(255), nullable=True)
    status = Column(
        Enum(_WorkflowRunStatus), default=_WorkflowRunStatus.ACTIVE, nullable=False
    )
    state_data = Column(Text, nullable=True)  # JSON
    parent_run_id = Column(String(36), nullable=True)
    parent_step_id = Column(String(255), nullable=True)
    started_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_workflow_runs_workflow_id", "workflow_id"),
        Index("ix_workflow_runs_status", "status"),
    )


def _to_state(model: WorkflowRunModel) -> WorkflowRunState:
    """Convert ORM model to WorkflowRunState dataclass."""
    status_map = {
        _WorkflowRunStatus.ACTIVE: WorkflowRunStatus.ACTIVE,
        _WorkflowRunStatus.PAUSED: WorkflowRunStatus.PAUSED,
        _WorkflowRunStatus.COMPLETED: WorkflowRunStatus.COMPLETED,
        _WorkflowRunStatus.CANCELLED: WorkflowRunStatus.CANCELLED,
    }
    return WorkflowRunState(
        id=model.id,
        workflow_id=model.workflow_id,
        workflow_version=model.workflow_version or "1.0.0",
        current_step=model.current_step,
        status=status_map[model.status],
        params=json.loads(model.params) if model.params else {},
        state_data=json.loads(model.state_data) if model.state_data else {},
        project_id=model.project_id,
        parent_run_id=model.parent_run_id,
        parent_step_id=model.parent_step_id,
        started_at=model.started_at,
        updated_at=model.updated_at,
        completed_at=model.completed_at,
    )


def _status_to_orm(status: WorkflowRunStatus) -> _WorkflowRunStatus:
    return _WorkflowRunStatus(status.value)


class SQLAlchemyStore:
    """SQLAlchemy-based workflow store.

    Can work with an externally-provided session or manage its own engine.
    """

    def __init__(
        self,
        session: Optional[AsyncSession] = None,
        session_factory: Optional[async_sessionmaker] = None,
        database_url: Optional[str] = None,
    ) -> None:
        self._session = session
        self._session_factory = session_factory
        self._owns_engine = False

        if not session and not session_factory and database_url:
            engine = create_async_engine(database_url)
            self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
            self._owns_engine = True

    async def ensure_tables(self) -> None:
        """Create tables if they don't exist. Useful for auto-setup."""
        if self._session_factory:
            engine = self._session_factory.kw.get("bind")
            if not engine and hasattr(self._session_factory, "class_"):
                pass
            # Try to get engine from factory
            async with self._session_factory() as session:
                engine = session.get_bind()
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
        elif self._session:
            engine = self._session.get_bind()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

    def _get_session(self) -> AsyncSession:
        if self._session:
            return self._session
        if self._session_factory:
            return self._session_factory()
        raise RuntimeError("No session or session_factory configured")

    async def find_by_identity(
        self,
        workflow_id: str,
        identity_params: dict[str, str],
    ) -> Optional[WorkflowRunState]:
        session = self._get_session()
        stmt = select(WorkflowRunModel).where(
            and_(
                WorkflowRunModel.workflow_id == workflow_id,
                WorkflowRunModel.status.in_([
                    _WorkflowRunStatus.ACTIVE,
                    _WorkflowRunStatus.PAUSED,
                ]),
            )
        ).order_by(WorkflowRunModel.started_at.desc())

        result = await session.execute(stmt)
        runs = result.scalars().all()

        for run in runs:
            if run.params:
                run_params = json.loads(run.params)
                if all(run_params.get(k) == v for k, v in identity_params.items()):
                    return _to_state(run)
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
        session = self._get_session()
        model = WorkflowRunModel(
            id=_generate_uuid(),
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            params=json.dumps(params) if params else None,
            project_id=project_id,
            parent_run_id=parent_run_id,
            parent_step_id=parent_step_id,
            status=_WorkflowRunStatus.ACTIVE,
            started_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(model)
        await session.flush()
        return _to_state(model)

    async def update_step(
        self,
        run_id: str,
        step_id: Optional[str],
        state_data: Optional[dict] = None,
        status: Optional[WorkflowRunStatus] = None,
    ) -> WorkflowRunState:
        session = self._get_session()
        result = await session.execute(
            select(WorkflowRunModel).where(WorkflowRunModel.id == run_id)
        )
        model = result.scalar_one()

        if step_id is not None:
            model.current_step = step_id
        if state_data is not None:
            existing = json.loads(model.state_data) if model.state_data else {}
            existing.update(state_data)
            model.state_data = json.dumps(existing)
        if status is not None:
            model.status = _status_to_orm(status)
            if status in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.CANCELLED):
                model.completed_at = _utcnow()
        model.updated_at = _utcnow()
        await session.flush()
        return _to_state(model)

    async def get_by_id(self, run_id: str) -> Optional[WorkflowRunState]:
        session = self._get_session()
        result = await session.execute(
            select(WorkflowRunModel).where(WorkflowRunModel.id == run_id)
        )
        model = result.scalar_one_or_none()
        return _to_state(model) if model else None

    async def list_active(
        self,
        workflow_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[WorkflowRunState]:
        session = self._get_session()
        stmt = select(WorkflowRunModel).where(
            WorkflowRunModel.status.in_([
                _WorkflowRunStatus.ACTIVE,
                _WorkflowRunStatus.PAUSED,
            ])
        )
        if workflow_id:
            stmt = stmt.where(WorkflowRunModel.workflow_id == workflow_id)
        if project_id:
            stmt = stmt.where(WorkflowRunModel.project_id == project_id)
        stmt = stmt.order_by(WorkflowRunModel.updated_at.desc())
        result = await session.execute(stmt)
        return [_to_state(m) for m in result.scalars().all()]

    async def commit(self) -> None:
        session = self._get_session()
        await session.commit()

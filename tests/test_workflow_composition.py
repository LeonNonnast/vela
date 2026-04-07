"""Sub-Workflow Composition Tests — Parent -> Sub -> Return."""

import json
import os
import tempfile

import pytest
import yaml
from fastmcp import Client, FastMCP
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.shared.db.base import Base
from src.shared.db.models import WorkflowRun
from vela_sdk.engine.types import WorkflowRunState, WorkflowRunStatus
from src.mcp.modules.workflow_module import WorkflowModule
from src.shared.repositories.workflow_repository import WorkflowRepository
from vela_sdk.engine.workflow_engine import WorkflowEngine
from src.shared.services.workflow_store_adapter import VelaWorkflowStore
from src.shared.schemas.workflow import (
    CaptureDefinition,
    ParamDefinition,
    StepDefinition,
    StepType,
    WorkflowDefinition,
)
from tests.conftest import reset_singleton


@pytest.fixture
async def comp_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


class TestSubWorkflowComposition:
    async def test_sub_workflow_pauses_parent(self, comp_engine):
        """When a workflow step is reached, the parent should pause."""
        session = comp_engine
        repo = WorkflowRepository(session)
        store = VelaWorkflowStore(repo, session)
        engine = WorkflowEngine(store)

        parent_def = WorkflowDefinition(
            id="parent",
            name="Parent",
            steps=[
                StepDefinition(id="s1", type=StepType.FREEFORM, prompt="First"),
                StepDefinition(
                    id="s2",
                    type=StepType.WORKFLOW,
                    prompt="Run sub-workflow",
                    workflow_ref="child-wf",
                    params_mapping={"input": "output_from_s1"},
                ),
                StepDefinition(id="s3", type=StepType.CONFIRM, prompt="Done"),
            ],
        )

        run, _ = await engine.start_or_resume(parent_def)
        await session.commit()

        # Advance past s1
        result = await engine.advance(run, parent_def, step_output="s1 done")
        await session.commit()

        # Now at s2 (workflow step) — advance should pause parent
        result = await engine.advance(result.run, parent_def, step_output="trigger sub")
        await session.commit()

        assert result.run.status == WorkflowRunStatus.PAUSED
        assert result.sub_workflow_ref == "child-wf"

    async def test_sub_workflow_creates_child_run(self, comp_engine):
        """A child run can be created with parent_run_id reference."""
        session = comp_engine
        repo = WorkflowRepository(session)

        parent = await repo.create_run(
            workflow_id="parent",
            workflow_version="1.0.0",
        )
        await session.commit()

        child = await repo.create_run(
            workflow_id="child-wf",
            workflow_version="1.0.0",
            parent_run_id=parent.id,
            parent_step_id="s2",
        )
        await session.commit()

        assert child.parent_run_id == parent.id
        assert child.parent_step_id == "s2"

    async def test_child_completion_allows_parent_resume(self, comp_engine):
        """After child completes, parent can be resumed."""
        session = comp_engine
        repo = WorkflowRepository(session)
        store = VelaWorkflowStore(repo, session)
        engine = WorkflowEngine(store)

        # Create parent and pause it
        parent_def = WorkflowDefinition(
            id="parent",
            name="Parent",
            steps=[
                StepDefinition(id="s1", type=StepType.FREEFORM, prompt="First"),
                StepDefinition(
                    id="s2",
                    type=StepType.WORKFLOW,
                    prompt="Sub",
                    workflow_ref="child",
                    next="s3",
                ),
                StepDefinition(id="s3", type=StepType.CONFIRM, prompt="Final"),
            ],
        )

        run, _ = await engine.start_or_resume(parent_def)
        await session.commit()

        # Advance to s2
        r1 = await engine.advance(run, parent_def, step_output="s1 done")
        await session.commit()

        # Advance s2 — pauses
        r2 = await engine.advance(r1.run, parent_def, step_output="go")
        await session.commit()
        assert r2.run.status == WorkflowRunStatus.PAUSED

        # Simulate child completion — resume parent via ORM repo
        orm_run = await repo.get_by_id(r2.run.id)
        from src.shared.db.models import WorkflowRunStatus as OrmStatus
        await repo.update_step(orm_run, "s3", status=OrmStatus.ACTIVE)
        await session.commit()

        resumed = await store.get_by_id(r2.run.id)
        assert resumed.status == WorkflowRunStatus.ACTIVE
        assert resumed.current_step == "s3"

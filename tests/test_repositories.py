"""Repository Tests with real in-memory SQLite — V1 models."""

import json

import pytest
from sqlalchemy import select

from src.shared.db.models import (
    Memory,
    MemoryCategory,
    Project,
    WorkflowRun,
    WorkflowRunStatus,
)


class TestProjectRepository:
    async def test_create_project(self, db_session):
        project = Project(slug="my-project", name="My Project", path="/home/user/project")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)
        assert project.id is not None
        assert project.slug == "my-project"
        assert project.name == "My Project"
        assert project.is_active is True

    async def test_get_by_slug(self, db_session):
        project = Project(slug="test-slug", name="Test")
        db_session.add(project)
        await db_session.commit()

        stmt = select(Project).where(Project.slug == "test-slug")
        result = await db_session.execute(stmt)
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.slug == "test-slug"

    async def test_slug_unique(self, db_session):
        p1 = Project(slug="unique", name="First")
        db_session.add(p1)
        await db_session.commit()

        p2 = Project(slug="unique", name="Second")
        db_session.add(p2)
        with pytest.raises(Exception):
            await db_session.commit()

    async def test_tech_stack_json(self, db_session):
        stack = json.dumps(["python", "fastmcp"])
        project = Project(slug="stack-test", name="Stack", tech_stack=stack)
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)
        assert json.loads(project.tech_stack) == ["python", "fastmcp"]


class TestMemoryRepository:
    async def test_create_memory(self, db_session):
        project = Project(slug="mem-proj", name="MemProj")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        memory = Memory(
            project_id=project.id,
            category=MemoryCategory.DECISION,
            title="Use FastMCP 3.0",
            content="We decided to use FastMCP 3.0 for the MCP server.",
            tags=json.dumps(["architecture", "mcp"]),
        )
        db_session.add(memory)
        await db_session.commit()
        await db_session.refresh(memory)

        assert memory.id is not None
        assert memory.category == MemoryCategory.DECISION
        assert memory.title == "Use FastMCP 3.0"

    async def test_memory_without_project(self, db_session):
        memory = Memory(
            category=MemoryCategory.FACT,
            title="Global fact",
            content="This is a global fact.",
        )
        db_session.add(memory)
        await db_session.commit()
        await db_session.refresh(memory)
        assert memory.project_id is None

    async def test_search_by_category(self, db_session):
        m1 = Memory(category=MemoryCategory.DECISION, title="D1", content="c1")
        m2 = Memory(category=MemoryCategory.INSIGHT, title="I1", content="c2")
        db_session.add_all([m1, m2])
        await db_session.commit()

        stmt = select(Memory).where(Memory.category == MemoryCategory.DECISION)
        result = await db_session.execute(stmt)
        found = result.scalars().all()
        assert len(found) == 1
        assert found[0].title == "D1"

    async def test_cascade_delete_with_project(self, db_session):
        project = Project(slug="cascade-test", name="Cascade")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        memory = Memory(
            project_id=project.id,
            category=MemoryCategory.CONVENTION,
            title="Convention 1",
            content="Follow PEP8",
        )
        db_session.add(memory)
        await db_session.commit()

        await db_session.delete(project)
        await db_session.commit()

        stmt = select(Memory).where(Memory.project_id == project.id)
        result = await db_session.execute(stmt)
        assert result.scalars().all() == []


class TestWorkflowRunRepository:
    async def test_create_workflow_run(self, db_session):
        run = WorkflowRun(
            workflow_id="feature-planning",
            workflow_version="1.0.0",
            current_step="step-1",
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        assert run.id is not None
        assert run.status == WorkflowRunStatus.ACTIVE
        assert run.workflow_id == "feature-planning"

    async def test_workflow_run_with_project(self, db_session):
        project = Project(slug="wf-proj", name="WF Project")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        run = WorkflowRun(
            workflow_id="test-wf",
            project_id=project.id,
            params=json.dumps({"key": "value"}),
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)
        assert run.project_id == project.id
        assert json.loads(run.params) == {"key": "value"}

    async def test_sub_workflow_run(self, db_session):
        parent = WorkflowRun(workflow_id="parent-wf", current_step="step-3")
        db_session.add(parent)
        await db_session.commit()
        await db_session.refresh(parent)

        child = WorkflowRun(
            workflow_id="child-wf",
            parent_run_id=parent.id,
            parent_step_id="step-3",
        )
        db_session.add(child)
        await db_session.commit()
        await db_session.refresh(child)

        assert child.parent_run_id == parent.id
        assert child.parent_step_id == "step-3"

    async def test_status_transitions(self, db_session):
        run = WorkflowRun(workflow_id="status-test")
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)
        assert run.status == WorkflowRunStatus.ACTIVE

        run.status = WorkflowRunStatus.PAUSED
        await db_session.commit()
        await db_session.refresh(run)
        assert run.status == WorkflowRunStatus.PAUSED

        run.status = WorkflowRunStatus.COMPLETED
        await db_session.commit()
        await db_session.refresh(run)
        assert run.status == WorkflowRunStatus.COMPLETED

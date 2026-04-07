"""Tests for storage implementations."""

import pytest

from vela_sdk.engine.types import WorkflowRunStatus
from vela_sdk.storage.memory import InMemoryStore


class TestInMemoryStore:
    @pytest.fixture
    def store(self):
        return InMemoryStore()

    async def test_create_and_get(self, store):
        run = await store.create_run("wf1", "1.0.0", params={"x": "1"})
        assert run.workflow_id == "wf1"
        assert run.params == {"x": "1"}
        assert run.status == WorkflowRunStatus.ACTIVE

        fetched = await store.get_by_id(run.id)
        assert fetched is not None
        assert fetched.id == run.id

    async def test_get_nonexistent(self, store):
        result = await store.get_by_id("nonexistent")
        assert result is None

    async def test_update_step(self, store):
        run = await store.create_run("wf1", "1.0.0")
        updated = await store.update_step(run.id, "step2", state_data={"key": "val"})
        assert updated.current_step == "step2"
        assert updated.state_data["key"] == "val"

    async def test_update_step_merges_state(self, store):
        run = await store.create_run("wf1", "1.0.0")
        await store.update_step(run.id, "s1", state_data={"a": 1})
        updated = await store.update_step(run.id, "s2", state_data={"b": 2})
        assert updated.state_data == {"a": 1, "b": 2}

    async def test_update_status(self, store):
        run = await store.create_run("wf1", "1.0.0")
        updated = await store.update_step(
            run.id, None, status=WorkflowRunStatus.COMPLETED
        )
        assert updated.status == WorkflowRunStatus.COMPLETED
        assert updated.completed_at is not None

    async def test_find_by_identity(self, store):
        await store.create_run("wf1", "1.0.0", params={"project": "alpha"})
        await store.create_run("wf1", "1.0.0", params={"project": "beta"})

        found = await store.find_by_identity("wf1", {"project": "alpha"})
        assert found is not None
        assert found.params["project"] == "alpha"

    async def test_find_by_identity_not_found(self, store):
        await store.create_run("wf1", "1.0.0", params={"project": "alpha"})
        found = await store.find_by_identity("wf1", {"project": "gamma"})
        assert found is None

    async def test_find_by_identity_ignores_completed(self, store):
        run = await store.create_run("wf1", "1.0.0", params={"project": "alpha"})
        await store.update_step(run.id, None, status=WorkflowRunStatus.COMPLETED)
        found = await store.find_by_identity("wf1", {"project": "alpha"})
        assert found is None

    async def test_list_active(self, store):
        await store.create_run("wf1", "1.0.0")
        await store.create_run("wf2", "1.0.0")
        run3 = await store.create_run("wf1", "1.0.0")
        await store.update_step(run3.id, None, status=WorkflowRunStatus.COMPLETED)

        active = await store.list_active()
        assert len(active) == 2

    async def test_list_active_filter_workflow(self, store):
        await store.create_run("wf1", "1.0.0")
        await store.create_run("wf2", "1.0.0")

        active = await store.list_active(workflow_id="wf1")
        assert len(active) == 1
        assert active[0].workflow_id == "wf1"

    async def test_list_active_filter_project(self, store):
        await store.create_run("wf1", "1.0.0", project_id="p1")
        await store.create_run("wf1", "1.0.0", project_id="p2")

        active = await store.list_active(project_id="p1")
        assert len(active) == 1
        assert active[0].project_id == "p1"

    async def test_commit_is_noop(self, store):
        await store.commit()  # Should not raise

    async def test_create_with_parent(self, store):
        parent = await store.create_run("wf1", "1.0.0")
        child = await store.create_run(
            "wf2", "1.0.0",
            parent_run_id=parent.id,
            parent_step_id="delegate_step",
        )
        assert child.parent_run_id == parent.id
        assert child.parent_step_id == "delegate_step"

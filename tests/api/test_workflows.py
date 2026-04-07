"""API Workflow & Runs endpoint tests."""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.shared.db.models import WorkflowRun, WorkflowRunStatus


def _make_run(
    id="run-1",
    workflow_id="test-wf",
    workflow_version="1.0.0",
    status=WorkflowRunStatus.ACTIVE,
    current_step="step-1",
    params=None,
    state_data=None,
):
    """Create a mock WorkflowRun."""
    run = MagicMock(spec=WorkflowRun)
    run.id = id
    run.workflow_id = workflow_id
    run.workflow_version = workflow_version
    run.project_id = None
    run.current_step = current_step
    run.status = status
    run.params = json.dumps(params) if params else None
    run.state_data = json.dumps(state_data) if state_data else None
    run.parent_run_id = None
    run.parent_step_id = None
    run.started_at = MagicMock(isoformat=lambda: "2026-03-27T10:00:00")
    run.updated_at = MagicMock(isoformat=lambda: "2026-03-27T10:05:00")
    run.completed_at = None
    return run


class TestListWorkflows:
    async def test_returns_workflow_list(self, api_client):
        async with api_client as client:
            resp = await client.get("/api/workflows")
            assert resp.status_code == 200
            data = resp.json()
            assert "workflows" in data
            assert "count" in data
            assert isinstance(data["workflows"], list)

    async def test_workflows_have_required_fields(self, api_client):
        async with api_client as client:
            resp = await client.get("/api/workflows")
            data = resp.json()
            if data["count"] > 0:
                wf = data["workflows"][0]
                assert "id" in wf
                assert "name" in wf
                assert "step_count" in wf


class TestListRuns:
    async def test_returns_empty_list(self, api_client):
        with patch("src.api.routes.workflows.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.api.routes.workflows.WorkflowRepository") as MockRepo:
                MockRepo.return_value.list_runs = AsyncMock(return_value=[])

                async with api_client as client:
                    resp = await client.get("/api/runs")
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["runs"] == []
                    assert data["count"] == 0

    async def test_returns_runs_with_data(self, api_client):
        mock_run = _make_run(state_data={"key": "val"})

        with patch("src.api.routes.workflows.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.api.routes.workflows.WorkflowRepository") as MockRepo:
                MockRepo.return_value.list_runs = AsyncMock(return_value=[mock_run])

                async with api_client as client:
                    resp = await client.get("/api/runs")
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["count"] == 1
                    run = data["runs"][0]
                    assert run["id"] == "run-1"
                    assert run["workflow_id"] == "test-wf"
                    assert run["status"] == "active"
                    assert run["current_step"] == "step-1"
                    assert run["state_data"] == {"key": "val"}

    async def test_invalid_status_returns_400(self, api_client):
        async with api_client as client:
            resp = await client.get("/api/runs?status=invalid")
            assert resp.status_code == 400
            assert "Invalid status" in resp.json()["error"]

    async def test_valid_status_filter(self, api_client):
        with patch("src.api.routes.workflows.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.api.routes.workflows.WorkflowRepository") as MockRepo:
                MockRepo.return_value.list_runs = AsyncMock(return_value=[])

                async with api_client as client:
                    resp = await client.get("/api/runs?status=completed")
                    assert resp.status_code == 200
                    MockRepo.return_value.list_runs.assert_called_once_with(
                        workflow_id=None,
                        project_id=None,
                        status=WorkflowRunStatus.COMPLETED,
                        limit=100,
                        offset=0,
                    )


class TestGetRun:
    async def test_run_not_found(self, api_client):
        with patch("src.api.routes.workflows.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.api.routes.workflows.WorkflowRepository") as MockRepo:
                MockRepo.return_value.get_by_id = AsyncMock(return_value=None)

                async with api_client as client:
                    resp = await client.get("/api/runs/nonexistent-id")
                    assert resp.status_code == 404
                    assert resp.json()["error"] == "Run not found"

    async def test_run_found(self, api_client):
        mock_run = _make_run(params={"project": "test"})

        with patch("src.api.routes.workflows.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("src.api.routes.workflows.WorkflowRepository") as MockRepo:
                MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_run)

                async with api_client as client:
                    resp = await client.get("/api/runs/run-1")
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["run"]["id"] == "run-1"
                    assert data["run"]["params"] == {"project": "test"}

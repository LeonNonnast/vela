"""Workflow Module Tests — vela_advance_workflow, vela_workflow_status, vela_list_workflows."""

import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from fastmcp import Client, FastMCP
from fastmcp.server.elicitation import AcceptedElicitation, DeclinedElicitation
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.shared.db.base import Base
from src.mcp.modules.workflow_module import WorkflowModule
from tests.conftest import reset_singleton


def _extract_text(result):
    """Extract text from a call_tool result."""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return result[0].text
    if hasattr(result, "content"):
        content = result.content
        if isinstance(content, list):
            return content[0].text
        return content
    if hasattr(result, "text"):
        return result.text
    return str(result)


def _make_workflow_yaml():
    """Create a temporary directory with a test workflow YAML."""
    tmpdir = tempfile.mkdtemp()
    wf_data = {
        "id": "test-flow",
        "version": "1.0.0",
        "name": "Test Flow",
        "description": "A test workflow",
        "params": [
            {"name": "feature", "required": True, "identity": True},
        ],
        "steps": [
            {
                "id": "step-1",
                "type": "freeform",
                "prompt": "Describe {{feature}}",
                "capture": [{"key": "description", "source": "output"}],
                "next": "step-2",
            },
            {
                "id": "step-2",
                "type": "confirm",
                "prompt": "Confirm the description.",
                "depends_on": [{"step": "step-1", "fields": ["description"]}],
            },
        ],
    }
    filepath = os.path.join(tmpdir, "test-flow@1.0.0.yaml")
    with open(filepath, "w") as f:
        yaml.dump(wf_data, f)
    return tmpdir


def _make_workflow_server(session_factory, workflows_dir):
    """Create a test server with WorkflowModule."""
    server = FastMCP("TestVela")
    reset_singleton(WorkflowModule)

    import src.mcp.modules.workflow_module as wf_mod
    import src.shared.config as config_mod
    wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
    config_mod.VELA_MODULES_DIR = "/nonexistent"

    WorkflowModule.construct(mcp=server, session_factory=session_factory)
    return server


@pytest.fixture
async def wf_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def wf_session_factory(wf_engine):
    return async_sessionmaker(wf_engine, expire_on_commit=False)


@pytest.fixture
def workflows_dir():
    return _make_workflow_yaml()


class TestWorkflowModule:
    async def test_start_workflow(self, wf_session_factory, workflows_dir):
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "auth"}),
            })
            result = json.loads(_extract_text(raw))
            assert result["status"] == "started"
            assert result["run_id"] is not None
            assert result["current_step"] == "step-1"
            assert "prompt" in result

    async def test_resume_workflow(self, wf_session_factory, workflows_dir):
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            # Start
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "auth"}),
            })
            first = json.loads(_extract_text(raw))

            # Resume with same identity
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "auth"}),
            })
            resumed = json.loads(_extract_text(raw))
            assert resumed["status"] == "resumed"
            assert resumed["run_id"] == first["run_id"]

    async def test_advance_workflow(self, wf_session_factory, workflows_dir):
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            # Start
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "auth"}),
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]

            # Advance step-1
            raw = await client.call_tool("vela_advance_workflow", {
                "run_id": run_id,
                "output": "OAuth2 implementation",
            })
            advanced = json.loads(_extract_text(raw))
            assert advanced["current_step"] == "step-2"
            assert advanced["completed"] is False

    async def test_advance_to_completion(self, wf_session_factory, workflows_dir):
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            # Start
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "auth"}),
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]

            # Advance step-1
            await client.call_tool("vela_advance_workflow", {
                "run_id": run_id,
                "output": "description",
            })

            # Advance step-2 (confirm)
            raw = await client.call_tool("vela_advance_workflow", {
                "run_id": run_id,
                "output": "confirmed",
            })
            completed = json.loads(_extract_text(raw))
            assert completed["completed"] is True
            assert completed["status"] == "completed"

    async def test_workflow_status(self, wf_session_factory, workflows_dir):
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "status-test"}),
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]

            raw = await client.call_tool("vela_workflow_status", {"run_id": run_id})
            status = json.loads(_extract_text(raw))
            assert status["workflow_id"] == "test-flow"
            assert status["status"] == "active"

    async def test_list_workflows(self, wf_session_factory, workflows_dir):
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_workflows", {})
            result = json.loads(_extract_text(raw))
            assert len(result["definitions"]) == 1
            assert result["definitions"][0]["id"] == "test-flow"

    async def test_workflow_not_found(self, wf_session_factory, workflows_dir):
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "nonexistent",
            })
            result = json.loads(_extract_text(raw))
            assert result["error"] == "Workflow not found"

    async def test_run_not_found(self, wf_session_factory, workflows_dir):
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "run_id": "nonexistent-id",
                "output": "test",
            })
            result = json.loads(_extract_text(raw))
            assert result["error"] == "Run not found"

    async def test_advance_with_step_id(self, wf_session_factory, workflows_dir):
        """Advancing with correct step_id succeeds."""
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "step-id-test"}),
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]

            raw = await client.call_tool("vela_advance_workflow", {
                "run_id": run_id,
                "step_id": "step-1",
                "output": "description text",
            })
            advanced = json.loads(_extract_text(raw))
            assert advanced["current_step"] == "step-2"
            assert advanced["completed"] is False

    async def test_advance_wrong_step_id(self, wf_session_factory, workflows_dir):
        """Advancing with wrong step_id returns step mismatch error."""
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "mismatch-test"}),
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]

            # Try to advance with wrong step_id
            raw = await client.call_tool("vela_advance_workflow", {
                "run_id": run_id,
                "step_id": "step-2",
                "output": "wrong step",
            })
            result = json.loads(_extract_text(raw))
            assert result["error"] == "Step mismatch"
            assert result["expected_step"] == "step-1"
            assert result["provided_step"] == "step-2"

    async def test_advance_unknown_step_id(self, wf_session_factory, workflows_dir):
        """Advancing with nonexistent step_id returns unknown step error."""
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "unknown-test"}),
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]

            raw = await client.call_tool("vela_advance_workflow", {
                "run_id": run_id,
                "step_id": "nonexistent-step",
                "output": "test",
            })
            result = json.loads(_extract_text(raw))
            assert result["error"] == "Unknown step"
            assert result["step_id"] == "nonexistent-step"
            assert "step-1" in result["valid_steps"]

    async def test_advance_without_step_id_still_works(self, wf_session_factory, workflows_dir):
        """Advancing without step_id is backwards-compatible."""
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "compat-test"}),
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]

            # Advance without step_id (old behavior)
            raw = await client.call_tool("vela_advance_workflow", {
                "run_id": run_id,
                "output": "description text",
            })
            advanced = json.loads(_extract_text(raw))
            assert advanced["current_step"] == "step-2"

    async def test_no_params_error(self, wf_session_factory, workflows_dir):
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {})
            result = json.loads(_extract_text(raw))
            assert "error" in result

    async def test_prompts_registered(self, wf_session_factory, workflows_dir):
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            prompts = await client.list_prompts()
            prompt_names = {p.name for p in prompts}
            assert "vela_test-flow" in prompt_names

    async def test_active_runs_in_list(self, wf_session_factory, workflows_dir):
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            # Start a workflow
            await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "list-test"}),
            })

            raw = await client.call_tool("vela_list_workflows", {})
            result = json.loads(_extract_text(raw))
            assert len(result["active_runs"]) == 1
            assert result["active_runs"][0]["workflow_id"] == "test-flow"


# ---------------------------------------------------------------------------
# Elicitation integration tests (unit-level, mock ctx.elicit)
# ---------------------------------------------------------------------------
def _make_elicit_workflow_yaml():
    """Create a workflow YAML with elicit captures."""
    tmpdir = tempfile.mkdtemp()
    wf_data = {
        "id": "elicit-flow",
        "version": "1.0.0",
        "name": "Elicit Flow",
        "description": "A workflow with elicitation",
        "steps": [
            {
                "id": "step-1",
                "type": "freeform",
                "prompt": "Describe the feature",
                "capture": [
                    {
                        "key": "priority",
                        "label": "Priority Level",
                        "input": "select",
                        "options": [
                            {"key": "high", "label": "High"},
                            {"key": "medium", "label": "Medium"},
                            {"key": "low", "label": "Low"},
                        ],
                        "elicit": "always",
                    },
                    {
                        "key": "description",
                        "source": "output",
                        "elicit": "never",
                    },
                ],
                "next": "step-2",
            },
            {
                "id": "step-2",
                "type": "confirm",
                "prompt": "Confirm.",
                "capture": [
                    {
                        "key": "scope",
                        "label": "Scope",
                        "input": "text",
                        "elicit": "if_missing",
                    },
                ],
            },
        ],
    }
    filepath = os.path.join(tmpdir, "elicit-flow@1.0.0.yaml")
    with open(filepath, "w") as f:
        yaml.dump(wf_data, f)
    return tmpdir


class TestWorkflowElicitation:
    async def test_elicit_on_start(self, wf_session_factory):
        """Starting a workflow elicits captures on the first step."""
        workflows_dir = _make_elicit_workflow_yaml()
        server = _make_workflow_server(wf_session_factory, workflows_dir)

        # Get the registered tool handler directly to pass a mock ctx
        reset_singleton(WorkflowModule)
        import src.mcp.modules.workflow_module as wf_mod
        import src.shared.config as config_mod
        wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
        config_mod.VELA_MODULES_DIR = "/nonexistent"

        module = WorkflowModule.construct(mcp=server, session_factory=wf_session_factory)
        wf_def = module._get_workflow("elicit-flow")
        assert wf_def is not None

        # Create a mock context with elicit
        mock_ctx = AsyncMock()
        mock_ctx.elicit = AsyncMock(return_value=AcceptedElicitation(data="high"))

        async with Client(server) as client:
            # We test the elicit logic by calling the internal method
            # Start a workflow first via client (no ctx)
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "elicit-flow",
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]
            assert started["status"] == "started"

        # Now test that _elicit_step_captures works correctly
        from src.shared.repositories.workflow_repository import WorkflowRepository
        from vela_sdk.engine.workflow_engine import WorkflowEngine

        async with wf_session_factory() as session:
            repo = WorkflowRepository(session)
            from src.shared.services.workflow_store_adapter import VelaWorkflowStore
            from vela_sdk.fastmcp.auto_advance import elicit_step_captures
            store = VelaWorkflowStore(repo, session)
            engine = WorkflowEngine(store)
            run_state = await store.get_by_id(run_id)
            assert run_state is not None

            await elicit_step_captures(mock_ctx, engine, wf_def, run_state, store)
            await session.commit()

            # Should have called elicit once (priority is "always", description is "never")
            assert mock_ctx.elicit.call_count == 1

            updated = await store.get_by_id(run_id)
            assert updated.state_data["priority"] == "high"

    async def test_elicit_declined_not_stored(self, wf_session_factory):
        """Declined elicitation should not store the value."""
        workflows_dir = _make_elicit_workflow_yaml()
        server = _make_workflow_server(wf_session_factory, workflows_dir)

        reset_singleton(WorkflowModule)
        import src.mcp.modules.workflow_module as wf_mod
        import src.shared.config as config_mod
        wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
        config_mod.VELA_MODULES_DIR = "/nonexistent"

        module = WorkflowModule.construct(mcp=server, session_factory=wf_session_factory)
        wf_def = module._get_workflow("elicit-flow")

        mock_ctx = AsyncMock()
        mock_ctx.elicit = AsyncMock(return_value=DeclinedElicitation())

        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "elicit-flow",
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]

        from src.shared.repositories.workflow_repository import WorkflowRepository
        from vela_sdk.engine.workflow_engine import WorkflowEngine

        async with wf_session_factory() as session:
            repo = WorkflowRepository(session)
            from src.shared.services.workflow_store_adapter import VelaWorkflowStore
            from vela_sdk.fastmcp.auto_advance import elicit_step_captures
            store = VelaWorkflowStore(repo, session)
            engine = WorkflowEngine(store)
            run_state = await store.get_by_id(run_id)

            await elicit_step_captures(mock_ctx, engine, wf_def, run_state, store)
            await session.commit()

            updated = await store.get_by_id(run_id)
            assert "priority" not in updated.state_data


# ---------------------------------------------------------------------------
# Missing params elicitation tests
# ---------------------------------------------------------------------------
class TestWorkflowMissingParamsElicitation:
    """Tests for _elicit_missing_params: resume-or-new flow when required params are missing."""

    async def test_missing_params_elicit_new_session(self, wf_session_factory, workflows_dir):
        """When required params are missing and no active runs, elicit param values."""
        server = _make_workflow_server(wf_session_factory, workflows_dir)

        reset_singleton(WorkflowModule)
        import src.mcp.modules.workflow_module as wf_mod
        import src.shared.config as config_mod
        wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
        config_mod.VELA_MODULES_DIR = "/nonexistent"

        module = WorkflowModule.construct(mcp=server, session_factory=wf_session_factory)
        wf_def = module._get_workflow("test-flow")

        mock_ctx = AsyncMock()
        # User enters "my-feature" for the missing "feature" param
        mock_ctx.elicit = AsyncMock(return_value=AcceptedElicitation(data="my-feature"))

        missing = [p for p in wf_def.params if p.required]
        result = await module._elicit_missing_params(
            mock_ctx, wf_def, missing, active_runs=[], existing_params={}
        )

        assert result is not None
        assert result["feature"] == "my-feature"
        mock_ctx.elicit.assert_called_once()

    async def test_missing_params_elicit_resume_existing(self, wf_session_factory, workflows_dir):
        """When active runs exist, user can choose to resume one."""
        server = _make_workflow_server(wf_session_factory, workflows_dir)

        # Start a workflow first to create an active run
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "existing-feature"}),
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]

        reset_singleton(WorkflowModule)
        import src.mcp.modules.workflow_module as wf_mod
        import src.shared.config as config_mod
        wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
        config_mod.VELA_MODULES_DIR = "/nonexistent"

        module = WorkflowModule.construct(mcp=server, session_factory=wf_session_factory)
        wf_def = module._get_workflow("test-flow")

        # Load active runs via store adapter
        from src.shared.repositories.workflow_repository import WorkflowRepository
        from src.shared.services.workflow_store_adapter import VelaWorkflowStore
        async with wf_session_factory() as session:
            repo = WorkflowRepository(session)
            store = VelaWorkflowStore(repo, session)
            active_runs = await store.list_active(workflow_id="test-flow")

        mock_ctx = AsyncMock()
        # User selects the existing run
        mock_ctx.elicit = AsyncMock(return_value=AcceptedElicitation(data=run_id))

        missing = [p for p in wf_def.params if p.required]
        result = await module._elicit_missing_params(
            mock_ctx, wf_def, missing, active_runs=active_runs, existing_params={}
        )

        assert result is not None
        assert result["feature"] == "existing-feature"

    async def test_missing_params_elicit_new_when_runs_exist(self, wf_session_factory, workflows_dir):
        """When active runs exist but user chooses 'new', elicit param values."""
        server = _make_workflow_server(wf_session_factory, workflows_dir)

        # Start a workflow first
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "old-feature"}),
            })

        reset_singleton(WorkflowModule)
        import src.mcp.modules.workflow_module as wf_mod
        import src.shared.config as config_mod
        wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
        config_mod.VELA_MODULES_DIR = "/nonexistent"

        module = WorkflowModule.construct(mcp=server, session_factory=wf_session_factory)
        wf_def = module._get_workflow("test-flow")

        from src.shared.repositories.workflow_repository import WorkflowRepository
        from src.shared.services.workflow_store_adapter import VelaWorkflowStore
        async with wf_session_factory() as session:
            repo = WorkflowRepository(session)
            store = VelaWorkflowStore(repo, session)
            active_runs = await store.list_active(workflow_id="test-flow")

        # First elicit: user chooses "__new__", second elicit: enters param value
        mock_ctx = AsyncMock()
        mock_ctx.elicit = AsyncMock(side_effect=[
            AcceptedElicitation(data="__new__"),
            AcceptedElicitation(data="brand-new-feature"),
        ])

        missing = [p for p in wf_def.params if p.required]
        result = await module._elicit_missing_params(
            mock_ctx, wf_def, missing, active_runs=active_runs, existing_params={}
        )

        assert result is not None
        assert result["feature"] == "brand-new-feature"
        assert mock_ctx.elicit.call_count == 2

    async def test_missing_params_cancelled(self, wf_session_factory, workflows_dir):
        """When user cancels elicitation, returns None."""
        server = _make_workflow_server(wf_session_factory, workflows_dir)

        reset_singleton(WorkflowModule)
        import src.mcp.modules.workflow_module as wf_mod
        import src.shared.config as config_mod
        wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
        config_mod.VELA_MODULES_DIR = "/nonexistent"

        module = WorkflowModule.construct(mcp=server, session_factory=wf_session_factory)
        wf_def = module._get_workflow("test-flow")

        from fastmcp.server.elicitation import CancelledElicitation

        mock_ctx = AsyncMock()
        mock_ctx.elicit = AsyncMock(return_value=CancelledElicitation())

        missing = [p for p in wf_def.params if p.required]
        result = await module._elicit_missing_params(
            mock_ctx, wf_def, missing, active_runs=[], existing_params={}
        )

        assert result is None


# ---------------------------------------------------------------------------
# Prompt session elicitation tests
# ---------------------------------------------------------------------------
class TestWorkflowPromptSession:
    """Tests for _elicit_prompt_session: resume-or-new in prompt handler."""

    async def test_prompt_session_new_no_active_runs(self, wf_session_factory, workflows_dir):
        """With no active runs, user enters new params."""
        server = _make_workflow_server(wf_session_factory, workflows_dir)

        reset_singleton(WorkflowModule)
        import src.mcp.modules.workflow_module as wf_mod
        import src.shared.config as config_mod
        wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
        config_mod.VELA_MODULES_DIR = "/nonexistent"

        module = WorkflowModule.construct(mcp=server, session_factory=wf_session_factory)
        wf_def = module._get_workflow("test-flow")

        mock_ctx = AsyncMock()
        # No active runs → no session choice, only param elicitation
        mock_ctx.elicit = AsyncMock(return_value=AcceptedElicitation(data="new-feature"))

        run, params = await module._elicit_prompt_session(mock_ctx, wf_def, [])
        assert run is None
        assert params["feature"] == "new-feature"
        mock_ctx.elicit.assert_called_once()

    async def test_prompt_session_resume_existing(self, wf_session_factory, workflows_dir):
        """User picks an existing run to resume."""
        server = _make_workflow_server(wf_session_factory, workflows_dir)

        # Create an active run
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "test-flow",
                "params": json.dumps({"feature": "resume-me"}),
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]

        reset_singleton(WorkflowModule)
        import src.mcp.modules.workflow_module as wf_mod
        import src.shared.config as config_mod
        wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
        config_mod.VELA_MODULES_DIR = "/nonexistent"

        module = WorkflowModule.construct(mcp=server, session_factory=wf_session_factory)
        wf_def = module._get_workflow("test-flow")

        from src.shared.repositories.workflow_repository import WorkflowRepository
        from src.shared.services.workflow_store_adapter import VelaWorkflowStore
        async with wf_session_factory() as session:
            repo = WorkflowRepository(session)
            store = VelaWorkflowStore(repo, session)
            active_runs = await store.list_active(workflow_id="test-flow")

        mock_ctx = AsyncMock()
        mock_ctx.elicit = AsyncMock(return_value=AcceptedElicitation(data=run_id))

        run, params = await module._elicit_prompt_session(mock_ctx, wf_def, active_runs)
        assert run is not None
        assert run.id == run_id
        assert params == {}

    async def test_prompt_session_elicit_not_supported(self, wf_session_factory, workflows_dir):
        """When client doesn't support elicitation, returns gracefully."""
        server = _make_workflow_server(wf_session_factory, workflows_dir)

        reset_singleton(WorkflowModule)
        import src.mcp.modules.workflow_module as wf_mod
        import src.shared.config as config_mod
        wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
        config_mod.VELA_MODULES_DIR = "/nonexistent"

        module = WorkflowModule.construct(mcp=server, session_factory=wf_session_factory)
        wf_def = module._get_workflow("test-flow")

        mock_ctx = AsyncMock()
        mock_ctx.elicit = AsyncMock(side_effect=Exception("Not supported"))

        run, params = await module._elicit_prompt_session(mock_ctx, wf_def, [])
        assert run is None
        assert params == {}


# ---------------------------------------------------------------------------
# Dialog step module integration tests
# ---------------------------------------------------------------------------
def _make_dialog_workflow_yaml():
    """Create a temporary directory with a dialog workflow YAML."""
    tmpdir = tempfile.mkdtemp()
    wf_data = {
        "id": "dialog-test",
        "version": "1.0.0",
        "name": "Dialog Test",
        "description": "A dialog workflow",
        "steps": [
            {
                "id": "brainstorm",
                "type": "dialog",
                "prompt": "Let's brainstorm ideas",
                "mode": "brainstorming",
                "goal": "Generate creative ideas",
                "guidelines": ["Be creative"],
            },
            {
                "id": "confirm-result",
                "type": "confirm",
                "prompt": "Review the results.",
            },
        ],
    }
    filepath = os.path.join(tmpdir, "dialog-test@1.0.0.yaml")
    with open(filepath, "w") as f:
        yaml.dump(wf_data, f)
    return tmpdir


class TestWorkflowDialogModule:
    async def test_auto_advance_stops_at_dialog(self, wf_session_factory):
        """Auto-advance loop should stop at dialog steps."""
        workflows_dir = _make_dialog_workflow_yaml()
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "dialog-test",
            })
            result = json.loads(_extract_text(raw))
            assert result["status"] == "started"
            assert result["current_step"] == "brainstorm"

    async def test_no_elicitation_on_dialog(self, wf_session_factory):
        """Dialog steps should not trigger elicitation."""
        workflows_dir = _make_dialog_workflow_yaml()
        server = _make_workflow_server(wf_session_factory, workflows_dir)

        reset_singleton(WorkflowModule)
        import src.mcp.modules.workflow_module as wf_mod
        import src.shared.config as config_mod
        wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
        config_mod.VELA_MODULES_DIR = "/nonexistent"

        module = WorkflowModule.construct(mcp=server, session_factory=wf_session_factory)
        wf_def = module._get_workflow("dialog-test")

        mock_ctx = AsyncMock()
        mock_ctx.elicit = AsyncMock(return_value=AcceptedElicitation(data="test"))

        # Start workflow
        async with Client(server) as client:
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "dialog-test",
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]

        from src.shared.repositories.workflow_repository import WorkflowRepository
        from vela_sdk.engine.workflow_engine import WorkflowEngine

        async with wf_session_factory() as session:
            repo = WorkflowRepository(session)
            from src.shared.services.workflow_store_adapter import VelaWorkflowStore
            from vela_sdk.fastmcp.auto_advance import elicit_step_captures
            store = VelaWorkflowStore(repo, session)
            engine = WorkflowEngine(store)
            run_state = await store.get_by_id(run_id)

            await elicit_step_captures(mock_ctx, engine, wf_def, run_state, store)
            # Should NOT have called elicit
            mock_ctx.elicit.assert_not_called()

    async def test_next_action_with_active_phase(self, wf_session_factory):
        """Starting a dialog auto-advances to first phase; next_action has conversation instructions."""
        workflows_dir = _make_dialog_workflow_yaml()
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            # Start workflow — auto-advance initializes first phase
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "dialog-test",
            })
            result = json.loads(_extract_text(raw))
            assert "Gespräch" in result["next_action"]
            assert "Zusammenfassung" in result["next_action"]

    async def test_next_action_without_phase(self, wf_session_factory):
        """Before dialog starts, next_action tells agent to start dialog with VELA hint."""
        workflows_dir = _make_dialog_workflow_yaml()
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        # We need to test _build_next_action directly with no phase
        from vela_sdk.engine.types import WorkflowRunState, WorkflowRunStatus
        from vela_sdk.engine.workflow_engine import WorkflowEngine
        from vela_sdk.storage.memory import InMemoryStore

        reset_singleton(WorkflowModule)
        import src.mcp.modules.workflow_module as wf_mod
        import src.shared.config as config_mod
        wf_mod.VELA_WORKFLOWS_DIR = workflows_dir
        config_mod.VELA_MODULES_DIR = "/nonexistent"

        module = WorkflowModule.construct(mcp=server, session_factory=wf_session_factory)
        wf_def = module._get_workflow("dialog-test")

        run = WorkflowRunState(
            id="test-run",
            workflow_id="dialog-test",
            workflow_version="1.0.0",
            current_step="brainstorm",
            status=WorkflowRunStatus.ACTIVE,
            state_data={},
        )
        engine = WorkflowEngine(InMemoryStore())
        action = module._build_next_action(run, wf_def, engine)
        assert "VELA liefert die erste Phase" in action

    async def test_dialog_full_lifecycle(self, wf_session_factory):
        """Full lifecycle: start (auto-inits phase 1) → 3 phases → next step → complete."""
        workflows_dir = _make_dialog_workflow_yaml()
        server = _make_workflow_server(wf_session_factory, workflows_dir)
        async with Client(server) as client:
            # Start — auto-advance initializes first phase (diverge)
            raw = await client.call_tool("vela_advance_workflow", {
                "workflow_id": "dialog-test",
            })
            started = json.loads(_extract_text(raw))
            run_id = started["run_id"]
            assert "Divergieren" in started.get("prompt", "")

            # Phase 1 → 2 (converge)
            raw = await client.call_tool("vela_advance_workflow", {
                "run_id": run_id,
                "output": "Lots of ideas",
            })
            phase2 = json.loads(_extract_text(raw))
            assert "Konvergieren" in phase2.get("prompt", "")

            # Phase 2 → 3 (synthesize)
            raw = await client.call_tool("vela_advance_workflow", {
                "run_id": run_id,
                "output": "Filtered ideas",
            })
            phase3 = json.loads(_extract_text(raw))
            assert "Synthese" in phase3.get("prompt", "")

            # Phase 3 → confirm step
            raw = await client.call_tool("vela_advance_workflow", {
                "run_id": run_id,
                "output": "Final synthesis",
            })
            confirm = json.loads(_extract_text(raw))
            assert confirm["current_step"] == "confirm-result"
            assert confirm["completed"] is False

            # Complete
            raw = await client.call_tool("vela_advance_workflow", {
                "run_id": run_id,
                "output": "confirmed",
            })
            completed = json.loads(_extract_text(raw))
            assert completed["completed"] is True

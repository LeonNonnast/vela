"""Tests for LangChain integration."""

import json

import pytest

# Guard: skip if langchain-core not installed
langchain_core = pytest.importorskip("langchain_core")

from vela_sdk.langchain import VelaToolkit
from vela_sdk.schemas.workflow import WorkflowDefinition
from vela_sdk.storage.memory import InMemoryStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_WORKFLOW = {
    "id": "onboarding",
    "version": "1.0.0",
    "name": "User Onboarding",
    "description": "Onboard a new user.",
    "params": [
        {"name": "user_name", "label": "User Name", "required": True},
    ],
    "steps": [
        {
            "id": "welcome",
            "type": "freeform",
            "name": "Welcome",
            "prompt": "Welcome {{params.user_name}}! Describe your goals.",
            "capture": [{"key": "goals", "source": "output"}],
        },
        {
            "id": "confirm",
            "type": "confirm",
            "name": "Confirm",
            "prompt": "Ready to proceed?",
            "capture": [{"key": "confirmed", "source": "output"}],
        },
    ],
}

MINIMAL_WORKFLOW = {
    "id": "minimal",
    "version": "1.0.0",
    "name": "Minimal",
    "description": "A single-step workflow.",
    "params": [],
    "steps": [
        {
            "id": "step1",
            "type": "freeform",
            "name": "Only Step",
            "prompt": "Do something.",
            "capture": [{"key": "result", "source": "output"}],
        },
    ],
}


def make_toolkit(*workflow_dicts: dict) -> VelaToolkit:
    """Create a toolkit from raw workflow dicts."""
    workflows = {}
    for d in workflow_dicts:
        wf = WorkflowDefinition.model_validate(d)
        key = f"{wf.id}@{wf.version}"
        workflows[key] = wf
    return VelaToolkit(initial_workflows=workflows)


# ---------------------------------------------------------------------------
# Toolkit creation
# ---------------------------------------------------------------------------


class TestVelaToolkit:
    def test_get_tools_returns_3(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW)
        tools = toolkit.get_tools()
        assert len(tools) == 3

    def test_tool_names(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW)
        names = [t.name for t in toolkit.get_tools()]
        assert "workflow_advance" in names
        assert "workflow_status" in names
        assert "workflow_list" in names

    def test_custom_prefix(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW)
        toolkit.tool_prefix = "vela"
        # Need to re-init to pick up prefix change — use constructor instead
        workflows = {}
        wf = WorkflowDefinition.model_validate(SIMPLE_WORKFLOW)
        workflows[f"{wf.id}@{wf.version}"] = wf
        toolkit = VelaToolkit(initial_workflows=workflows, tool_prefix="vela")
        names = [t.name for t in toolkit.get_tools()]
        assert "vela_advance" in names
        assert "vela_status" in names
        assert "vela_list" in names

    def test_tools_have_descriptions(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW)
        for tool in toolkit.get_tools():
            assert tool.description

    def test_register_workflow(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW)
        wf = WorkflowDefinition.model_validate(MINIMAL_WORKFLOW)
        toolkit.register(wf)
        # Should now have 2 workflows
        tools = toolkit.get_tools()
        list_tool = next(t for t in tools if t.name == "workflow_list")
        result = json.loads(list_tool.invoke({}))
        assert len(result["definitions"]) == 2


# ---------------------------------------------------------------------------
# Advance tool
# ---------------------------------------------------------------------------


class TestAdvanceTool:
    async def test_start_workflow(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW)
        tools = toolkit.get_tools()
        advance = next(t for t in tools if t.name == "workflow_advance")

        result = json.loads(await advance.ainvoke({
            "workflow_id": "onboarding",
            "params": json.dumps({"user_name": "Alice"}),
        }))

        assert result["run_id"]
        assert result["workflow_id"] == "onboarding"
        assert result["current_step"] == "welcome"
        assert result["status"] == "started"

    async def test_advance_with_output(self):
        toolkit = make_toolkit(MINIMAL_WORKFLOW)
        tools = toolkit.get_tools()
        advance = next(t for t in tools if t.name == "workflow_advance")

        # Start
        start = json.loads(await advance.ainvoke({
            "workflow_id": "minimal",
        }))
        assert start["current_step"] == "step1"

        # Complete
        complete = json.loads(await advance.ainvoke({
            "run_id": start["run_id"],
            "output": "Done!",
        }))
        assert complete["completed"] is True

    async def test_error_on_missing_args(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW)
        tools = toolkit.get_tools()
        advance = next(t for t in tools if t.name == "workflow_advance")

        result = json.loads(await advance.ainvoke({}))
        assert "error" in result

    async def test_error_on_unknown_run(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW)
        tools = toolkit.get_tools()
        advance = next(t for t in tools if t.name == "workflow_advance")

        result = json.loads(await advance.ainvoke({
            "run_id": "nonexistent",
        }))
        assert "error" in result


# ---------------------------------------------------------------------------
# Status tool
# ---------------------------------------------------------------------------


class TestStatusTool:
    async def test_status_of_active_run(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW)
        tools = toolkit.get_tools()
        advance = next(t for t in tools if t.name == "workflow_advance")
        status = next(t for t in tools if t.name == "workflow_status")

        # Start a workflow
        start = json.loads(await advance.ainvoke({
            "workflow_id": "onboarding",
            "params": json.dumps({"user_name": "Bob"}),
        }))

        # Check status
        result = json.loads(await status.ainvoke({
            "run_id": start["run_id"],
        }))
        assert result["run_id"] == start["run_id"]
        assert result["workflow_id"] == "onboarding"
        assert result["current_step"] == "welcome"

    async def test_error_on_unknown_run(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW)
        tools = toolkit.get_tools()
        status = next(t for t in tools if t.name == "workflow_status")

        result = json.loads(await status.ainvoke({
            "run_id": "nonexistent",
        }))
        assert "error" in result


# ---------------------------------------------------------------------------
# List tool
# ---------------------------------------------------------------------------


class TestListTool:
    async def test_list_workflows(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW, MINIMAL_WORKFLOW)
        tools = toolkit.get_tools()
        list_tool = next(t for t in tools if t.name == "workflow_list")

        result = json.loads(await list_tool.ainvoke({}))
        assert len(result["definitions"]) == 2
        ids = [d["id"] for d in result["definitions"]]
        assert "onboarding" in ids
        assert "minimal" in ids

    async def test_list_includes_active_runs(self):
        toolkit = make_toolkit(SIMPLE_WORKFLOW)
        tools = toolkit.get_tools()
        advance = next(t for t in tools if t.name == "workflow_advance")
        list_tool = next(t for t in tools if t.name == "workflow_list")

        # Start a workflow
        await advance.ainvoke({
            "workflow_id": "onboarding",
            "params": json.dumps({"user_name": "Test"}),
        })

        result = json.loads(await list_tool.ainvoke({}))
        assert len(result["active_runs"]) >= 1

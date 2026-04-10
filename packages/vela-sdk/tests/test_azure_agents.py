"""Tests for Azure AI Agents integration."""

import json

import pytest

from vela_sdk.azure_agents import VelaToolset
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


def make_toolset(*workflow_dicts: dict) -> VelaToolset:
    """Create a toolset from raw workflow dicts."""
    workflows = {}
    for d in workflow_dicts:
        wf = WorkflowDefinition.model_validate(d)
        key = f"{wf.id}@{wf.version}"
        workflows[key] = wf
    return VelaToolset(initial_workflows=workflows)


# ---------------------------------------------------------------------------
# Toolset creation
# ---------------------------------------------------------------------------


class TestVelaToolset:
    def test_get_functions_returns_3(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        functions = toolset.get_functions()
        assert len(functions) == 3

    def test_function_names(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        names = {fn.__name__ for fn in toolset.get_functions()}
        assert "workflow_advance" in names
        assert "workflow_status" in names
        assert "workflow_list" in names

    def test_custom_prefix(self):
        workflows = {}
        wf = WorkflowDefinition.model_validate(SIMPLE_WORKFLOW)
        workflows[f"{wf.id}@{wf.version}"] = wf
        toolset = VelaToolset(initial_workflows=workflows, tool_prefix="vela")
        names = {fn.__name__ for fn in toolset.get_functions()}
        assert "vela_advance" in names
        assert "vela_status" in names
        assert "vela_list" in names

    def test_functions_have_docstrings(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        for fn in toolset.get_functions():
            assert fn.__doc__

    def test_functions_map_keys(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        fn_map = toolset.get_functions_map()
        assert set(fn_map.keys()) == {"advance", "status", "list"}

    def test_register_workflow(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        wf = WorkflowDefinition.model_validate(MINIMAL_WORKFLOW)
        toolset.register(wf)

        fn_map = toolset.get_functions_map()
        result = json.loads(fn_map["list"]())
        assert len(result["definitions"]) == 2


# ---------------------------------------------------------------------------
# Advance function
# ---------------------------------------------------------------------------


class TestAdvanceFunction:
    def test_start_workflow(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        fn_map = toolset.get_functions_map()
        advance = fn_map["advance"]

        result = json.loads(advance(
            workflow_id="onboarding",
            params=json.dumps({"user_name": "Alice"}),
        ))

        assert result["run_id"]
        assert result["workflow_id"] == "onboarding"
        assert result["current_step"] == "welcome"
        assert result["status"] == "started"

    def test_advance_with_output(self):
        toolset = make_toolset(MINIMAL_WORKFLOW)
        fn_map = toolset.get_functions_map()
        advance = fn_map["advance"]

        # Start
        start = json.loads(advance(workflow_id="minimal"))
        assert start["current_step"] == "step1"

        # Complete
        complete = json.loads(advance(
            run_id=start["run_id"],
            output="Done!",
        ))
        assert complete["completed"] is True

    def test_error_on_missing_args(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        fn_map = toolset.get_functions_map()
        advance = fn_map["advance"]

        result = json.loads(advance())
        assert "error" in result

    def test_error_on_unknown_run(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        fn_map = toolset.get_functions_map()
        advance = fn_map["advance"]

        result = json.loads(advance(run_id="nonexistent"))
        assert "error" in result

    def test_step_mismatch_error(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        fn_map = toolset.get_functions_map()
        advance = fn_map["advance"]

        start = json.loads(advance(
            workflow_id="onboarding",
            params=json.dumps({"user_name": "Test"}),
        ))

        result = json.loads(advance(
            run_id=start["run_id"],
            step_id="confirm",  # Wrong step — should be "welcome"
        ))
        assert "error" in result
        assert result["error"] == "Step mismatch"


# ---------------------------------------------------------------------------
# Status function
# ---------------------------------------------------------------------------


class TestStatusFunction:
    def test_status_of_active_run(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        fn_map = toolset.get_functions_map()

        start = json.loads(fn_map["advance"](
            workflow_id="onboarding",
            params=json.dumps({"user_name": "Bob"}),
        ))

        result = json.loads(fn_map["status"](run_id=start["run_id"]))
        assert result["run_id"] == start["run_id"]
        assert result["workflow_id"] == "onboarding"
        assert result["current_step"] == "welcome"

    def test_error_on_unknown_run(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        fn_map = toolset.get_functions_map()

        result = json.loads(fn_map["status"](run_id="nonexistent"))
        assert "error" in result


# ---------------------------------------------------------------------------
# List function
# ---------------------------------------------------------------------------


class TestListFunction:
    def test_list_workflows(self):
        toolset = make_toolset(SIMPLE_WORKFLOW, MINIMAL_WORKFLOW)
        fn_map = toolset.get_functions_map()

        result = json.loads(fn_map["list"]())
        assert len(result["definitions"]) == 2
        ids = [d["id"] for d in result["definitions"]]
        assert "onboarding" in ids
        assert "minimal" in ids

    def test_list_includes_active_runs(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        fn_map = toolset.get_functions_map()

        fn_map["advance"](
            workflow_id="onboarding",
            params=json.dumps({"user_name": "Test"}),
        )

        result = json.loads(fn_map["list"]())
        assert len(result["active_runs"]) >= 1


# ---------------------------------------------------------------------------
# Prompt advisor
# ---------------------------------------------------------------------------


class TestPromptAdvisor:
    def test_prompt_advisor_contains_workflow_info(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        advisor = toolset.get_prompt_advisor()

        assert "Vela Workflow Advisor" in advisor
        assert "User Onboarding" in advisor
        assert "onboarding" in advisor
        assert "workflow_advance" in advisor

    def test_prompt_advisor_contains_steps(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        advisor = toolset.get_prompt_advisor()

        assert "Welcome" in advisor
        assert "Confirm" in advisor

    def test_prompt_advisor_contains_params(self):
        toolset = make_toolset(SIMPLE_WORKFLOW)
        advisor = toolset.get_prompt_advisor()

        assert "user_name" in advisor
        assert "erforderlich" in advisor

    def test_prompt_advisor_custom_prefix(self):
        workflows = {}
        wf = WorkflowDefinition.model_validate(SIMPLE_WORKFLOW)
        workflows[f"{wf.id}@{wf.version}"] = wf
        toolset = VelaToolset(initial_workflows=workflows, tool_prefix="vela")

        advisor = toolset.get_prompt_advisor()
        assert "vela_advance" in advisor
        assert "vela_status" in advisor
        assert "vela_list" in advisor

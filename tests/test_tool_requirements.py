"""Tests for ToolRequirement — schema parsing, prompt builder, and response enrichment."""

import json

import pytest
import yaml

from src.shared.schemas.workflow import (
    StepDefinition,
    StepType,
    ToolRequirement,
    WorkflowDefinition,
)
from vela_sdk.engine.prompt_builder import PromptBuilder
from vela_sdk.engine.types import WorkflowRunState, WorkflowRunStatus
from vela_sdk.fastmcp.response_builder import enrich_tool_requirements


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------


class TestToolRequirementSchema:
    def test_minimal(self):
        t = ToolRequirement(name="create_issue")
        assert t.name == "create_issue"
        assert t.server is None
        assert t.description is None
        assert t.required is True

    def test_full(self):
        t = ToolRequirement(
            name="create_issue",
            server="github",
            description="Create GitHub issues",
            required=False,
        )
        assert t.name == "create_issue"
        assert t.server == "github"
        assert t.description == "Create GitHub issues"
        assert t.required is False

    def test_workflow_with_tools(self):
        wf = WorkflowDefinition(
            id="test",
            name="Test",
            tools=[
                ToolRequirement(name="create_issue", server="github"),
                ToolRequirement(name="search_code", server="github", required=False),
            ],
            steps=[
                StepDefinition(id="s1", type=StepType.FREEFORM, prompt="Hi"),
            ],
        )
        assert len(wf.tools) == 2
        assert wf.tools[0].name == "create_issue"
        assert wf.tools[1].required is False

    def test_workflow_without_tools(self):
        wf = WorkflowDefinition(
            id="test",
            name="Test",
            steps=[
                StepDefinition(id="s1", type=StepType.FREEFORM, prompt="Hi"),
            ],
        )
        assert wf.tools == []

    def test_yaml_parsing(self, tmp_path):
        yaml_content = {
            "id": "review",
            "name": "Code Review",
            "tools": [
                {"name": "create_issue", "server": "github"},
                {"name": "search_code", "server": "github", "required": False},
            ],
            "steps": [
                {"id": "s1", "type": "execute", "prompt": "Review code"},
            ],
        }
        wf = WorkflowDefinition(**yaml_content)
        assert len(wf.tools) == 2
        assert wf.tools[0].server == "github"
        assert wf.tools[1].required is False


# ---------------------------------------------------------------------------
# PromptBuilder Tests
# ---------------------------------------------------------------------------


class TestPromptBuilderTools:
    def _make_run(self, wf: WorkflowDefinition) -> WorkflowRunState:
        return WorkflowRunState(
            id="run-1",
            workflow_id=wf.id,
            workflow_version=wf.version,
            current_step=wf.steps[0].id,
            status=WorkflowRunStatus.ACTIVE,
            params={},
            state_data={},
        )

    def test_workflow_tools_in_prompt(self):
        wf = WorkflowDefinition(
            id="test",
            name="Test",
            tools=[
                ToolRequirement(name="create_issue", server="github", description="Create issues"),
                ToolRequirement(name="search_code", server="github", required=False),
            ],
            steps=[
                StepDefinition(id="s1", type=StepType.EXECUTE, prompt="Do stuff"),
            ],
        )
        run = self._make_run(wf)
        builder = PromptBuilder()
        prompt = builder.assemble_prompt(wf, run, wf.steps[0])

        assert "### Benötigte externe Tools" in prompt
        assert "**create_issue** (github)" in prompt
        assert "[erforderlich]" in prompt
        assert "**search_code** (github)" in prompt
        assert "[optional]" in prompt

    def test_step_tools_in_prompt(self):
        wf = WorkflowDefinition(
            id="test",
            name="Test",
            steps=[
                StepDefinition(
                    id="s1",
                    type=StepType.EXECUTE,
                    prompt="Do stuff",
                    tools=["create_issue", "search_code"],
                ),
            ],
        )
        run = self._make_run(wf)
        builder = PromptBuilder()
        prompt = builder.assemble_prompt(wf, run, wf.steps[0])

        assert "### Tools für diesen Step" in prompt
        assert "`create_issue`" in prompt
        assert "`search_code`" in prompt

    def test_no_tools_no_section(self):
        wf = WorkflowDefinition(
            id="test",
            name="Test",
            steps=[
                StepDefinition(id="s1", type=StepType.FREEFORM, prompt="Hi"),
            ],
        )
        run = self._make_run(wf)
        builder = PromptBuilder()
        prompt = builder.assemble_prompt(wf, run, wf.steps[0])

        assert "### Benötigte externe Tools" not in prompt
        assert "### Tools für diesen Step" not in prompt


# ---------------------------------------------------------------------------
# Response Enrichment Tests
# ---------------------------------------------------------------------------


class TestEnrichToolRequirements:
    def test_workflow_tools_added(self):
        wf = WorkflowDefinition(
            id="test",
            name="Test",
            tools=[
                ToolRequirement(name="create_issue", server="github", description="Issues", required=True),
            ],
            steps=[
                StepDefinition(id="s1", type=StepType.FREEFORM, prompt="Hi"),
            ],
        )
        resp: dict = {}
        enrich_tool_requirements(resp, wf)
        assert "required_tools" in resp
        assert len(resp["required_tools"]) == 1
        assert resp["required_tools"][0]["name"] == "create_issue"
        assert resp["required_tools"][0]["server"] == "github"

    def test_step_tools_added(self):
        wf = WorkflowDefinition(
            id="test",
            name="Test",
            steps=[
                StepDefinition(id="s1", type=StepType.EXECUTE, prompt="Do", tools=["foo", "bar"]),
            ],
        )
        resp: dict = {}
        enrich_tool_requirements(resp, wf, wf.steps[0])
        assert "step_tools" in resp
        assert resp["step_tools"] == ["foo", "bar"]

    def test_no_tools_no_keys(self):
        wf = WorkflowDefinition(
            id="test",
            name="Test",
            steps=[
                StepDefinition(id="s1", type=StepType.FREEFORM, prompt="Hi"),
            ],
        )
        resp: dict = {}
        enrich_tool_requirements(resp, wf, wf.steps[0])
        assert "required_tools" not in resp
        assert "step_tools" not in resp

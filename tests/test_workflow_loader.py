"""Workflow Loader Tests — YAML parsing, semver, validation."""

import os
import tempfile

import pytest
import yaml

from src.shared.schemas.workflow import WorkflowDefinition, StepType
from src.shared.schemas.agent import AgentDefinition
from src.shared.services.workflow_loader import (
    load_agent_file,
    load_agents,
    load_workflow_file,
    load_workflows,
    parse_workflow_filename,
)


class TestParseWorkflowFilename:
    def test_with_version(self):
        wf_id, version = parse_workflow_filename("feature-planning@1.0.0.yaml")
        assert wf_id == "feature-planning"
        assert version == "1.0.0"

    def test_with_version_yml(self):
        wf_id, version = parse_workflow_filename("my-workflow@2.1.3.yml")
        assert wf_id == "my-workflow"
        assert version == "2.1.3"

    def test_without_version(self):
        wf_id, version = parse_workflow_filename("simple.yaml")
        assert wf_id == "simple"
        assert version == "1.0.0"

    def test_complex_name(self):
        wf_id, version = parse_workflow_filename("my-complex-workflow@0.1.0.yaml")
        assert wf_id == "my-complex-workflow"
        assert version == "0.1.0"


class TestLoadWorkflowFile:
    def test_load_valid_workflow(self, tmp_path):
        wf_data = {
            "id": "test-wf",
            "name": "Test Workflow",
            "description": "A test",
            "steps": [
                {"id": "step-1", "type": "freeform", "prompt": "Hello"},
            ],
        }
        filepath = tmp_path / "test-wf@1.0.0.yaml"
        filepath.write_text(yaml.dump(wf_data))

        result = load_workflow_file(str(filepath))
        assert result is not None
        assert result.id == "test-wf"
        assert result.name == "Test Workflow"
        assert len(result.steps) == 1
        assert result.steps[0].type == StepType.FREEFORM

    def test_load_derives_id_from_filename(self, tmp_path):
        wf_data = {
            "name": "No ID",
            "steps": [{"id": "s1", "type": "confirm", "prompt": "ok?"}],
        }
        filepath = tmp_path / "derived-id@2.0.0.yaml"
        filepath.write_text(yaml.dump(wf_data))

        result = load_workflow_file(str(filepath))
        assert result is not None
        assert result.id == "derived-id"
        assert result.version == "2.0.0"

    def test_load_empty_file(self, tmp_path):
        filepath = tmp_path / "empty.yaml"
        filepath.write_text("")

        result = load_workflow_file(str(filepath))
        assert result is None

    def test_load_invalid_yaml(self, tmp_path):
        filepath = tmp_path / "bad.yaml"
        filepath.write_text("{{invalid yaml")

        result = load_workflow_file(str(filepath))
        assert result is None

    def test_load_with_params(self, tmp_path):
        wf_data = {
            "id": "param-wf",
            "name": "Params",
            "params": [
                {"name": "feature_name", "required": True, "identity": True},
                {"name": "scope", "default": "mvp"},
            ],
            "steps": [{"id": "s1", "type": "freeform", "prompt": "go"}],
        }
        filepath = tmp_path / "param-wf@1.0.0.yaml"
        filepath.write_text(yaml.dump(wf_data))

        result = load_workflow_file(str(filepath))
        assert len(result.params) == 2
        assert result.params[0].identity is True
        assert result.params[1].default == "mvp"

    def test_load_with_choice_step(self, tmp_path):
        wf_data = {
            "id": "choice-wf",
            "name": "Choice",
            "steps": [{
                "id": "pick",
                "type": "choice",
                "prompt": "Pick one",
                "options": [
                    {"key": "a", "label": "A", "next": "step-a"},
                    {"key": "b", "label": "B"},
                ],
            }],
        }
        filepath = tmp_path / "choice-wf.yaml"
        filepath.write_text(yaml.dump(wf_data))

        result = load_workflow_file(str(filepath))
        assert result.steps[0].type == StepType.CHOICE
        assert len(result.steps[0].options) == 2
        assert result.steps[0].options[0].next == "step-a"


class TestLoadWorkflows:
    def test_load_directory(self, tmp_path):
        for name, wf_id in [("a@1.0.0.yaml", "a"), ("b@2.0.0.yaml", "b")]:
            (tmp_path / name).write_text(yaml.dump({
                "id": wf_id,
                "name": f"WF {wf_id}",
                "steps": [{"id": "s1", "type": "freeform", "prompt": "x"}],
            }))

        result = load_workflows(str(tmp_path))
        assert len(result) == 2
        assert "a@1.0.0" in result
        assert "b@2.0.0" in result

    def test_load_nonexistent_directory(self):
        result = load_workflows("/nonexistent/path")
        assert result == {}

    def test_skips_non_yaml(self, tmp_path):
        (tmp_path / "readme.md").write_text("# Not a workflow")
        (tmp_path / "wf@1.0.0.yaml").write_text(yaml.dump({
            "id": "wf",
            "name": "WF",
            "steps": [{"id": "s1", "type": "freeform", "prompt": "x"}],
        }))

        result = load_workflows(str(tmp_path))
        assert len(result) == 1


class TestLoadAgents:
    def test_load_agent_file(self, tmp_path):
        agent_data = {
            "id": "test-agent",
            "name": "Test Agent",
            "persona": "You are helpful.",
            "greeting": "Hello!",
            "workflows": ["wf-1"],
            "tools": ["tool-1"],
        }
        filepath = tmp_path / "test-agent.yaml"
        filepath.write_text(yaml.dump(agent_data))

        result = load_agent_file(str(filepath))
        assert result is not None
        assert result.id == "test-agent"
        assert result.name == "Test Agent"
        assert "wf-1" in result.workflows

    def test_load_agents_directory(self, tmp_path):
        for name in ["agent-a.yaml", "agent-b.yaml"]:
            (tmp_path / name).write_text(yaml.dump({
                "name": name.replace(".yaml", ""),
                "persona": "test",
            }))

        result = load_agents(str(tmp_path))
        assert len(result) == 2

    def test_load_empty_agent_file(self, tmp_path):
        filepath = tmp_path / "empty.yaml"
        filepath.write_text("")
        result = load_agent_file(str(filepath))
        assert result is None


class TestExampleFiles:
    def test_example_workflow_loads(self):
        """Verify the example workflow YAML loads correctly."""
        filepath = os.path.join(
            os.path.dirname(__file__),
            "..",
            "examples",
            "workflows",
            "feature-planning@1.0.0.yaml",
        )
        if not os.path.exists(filepath):
            pytest.skip("Example workflow not found")
        result = load_workflow_file(filepath)
        assert result is not None
        assert result.id == "feature-planning"
        assert result.version == "1.0.0"
        assert len(result.steps) >= 4

    def test_example_agent_loads(self):
        """Verify the example agent YAML loads correctly."""
        filepath = os.path.join(
            os.path.dirname(__file__),
            "..",
            "examples",
            "agents",
            "kfz-sachbearbeiter.yaml",
        )
        if not os.path.exists(filepath):
            pytest.skip("Example agent not found")
        result = load_agent_file(filepath)
        assert result is not None
        assert result.id == "kfz-sachbearbeiter"

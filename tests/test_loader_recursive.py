"""Tests for recursive loading and 3-source loading hierarchy."""

import os
import tempfile

import yaml

from src.shared.services.workflow_loader import load_agents, load_workflows


class TestRecursiveLoading:
    """Test os.walk-based recursive loading."""

    def test_load_workflows_from_subdirectory(self):
        """Workflows in subdirectories should be found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "sub")
            os.makedirs(subdir)

            wf_data = {
                "id": "sub-wf",
                "name": "Sub Workflow",
                "steps": [{"id": "s1", "type": "freeform", "prompt": "go"}],
            }
            with open(os.path.join(subdir, "sub-wf@1.0.0.yaml"), "w") as f:
                yaml.dump(wf_data, f)

            result = load_workflows(tmpdir)
            assert "sub-wf@1.0.0" in result
            assert result["sub-wf@1.0.0"].name == "Sub Workflow"

    def test_load_agents_from_subdirectory(self):
        """Agents in subdirectories should be found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "deep", "nested")
            os.makedirs(subdir)

            agent_data = {"id": "nested-agent", "name": "Nested Agent"}
            with open(os.path.join(subdir, "nested-agent.yaml"), "w") as f:
                yaml.dump(agent_data, f)

            result = load_agents(tmpdir)
            assert "nested-agent" in result

    def test_load_workflows_mixed_flat_and_nested(self):
        """Both flat and nested YAML files should be loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Flat file
            wf1 = {"id": "flat-wf", "name": "Flat", "steps": [{"id": "s1", "type": "freeform", "prompt": "go"}]}
            with open(os.path.join(tmpdir, "flat-wf@1.0.0.yaml"), "w") as f:
                yaml.dump(wf1, f)

            # Nested file
            subdir = os.path.join(tmpdir, "module-a")
            os.makedirs(subdir)
            wf2 = {"id": "nested-wf", "name": "Nested", "steps": [{"id": "s1", "type": "freeform", "prompt": "go"}]}
            with open(os.path.join(subdir, "nested-wf@1.0.0.yaml"), "w") as f:
                yaml.dump(wf2, f)

            result = load_workflows(tmpdir)
            assert "flat-wf@1.0.0" in result
            assert "nested-wf@1.0.0" in result

    def test_load_workflows_nonexistent_dir(self):
        """Non-existent directory should return empty dict."""
        result = load_workflows("/nonexistent/path")
        assert result == {}

    def test_load_agents_nonexistent_dir(self):
        """Non-existent directory should return empty dict."""
        result = load_agents("/nonexistent/path")
        assert result == {}


class TestThreeSourceLoading:
    """Test that user definitions override bundled ones."""

    def test_user_overrides_bundled_workflow(self):
        """When same workflow ID exists in two dirs, later call overwrites."""
        with tempfile.TemporaryDirectory() as dir1, tempfile.TemporaryDirectory() as dir2:
            # Bundled version
            wf1 = {"id": "shared", "name": "Bundled Version", "steps": [{"id": "s1", "type": "freeform", "prompt": "go"}]}
            with open(os.path.join(dir1, "shared@1.0.0.yaml"), "w") as f:
                yaml.dump(wf1, f)

            # User version
            wf2 = {"id": "shared", "name": "User Version", "steps": [{"id": "s1", "type": "freeform", "prompt": "go"}]}
            with open(os.path.join(dir2, "shared@1.0.0.yaml"), "w") as f:
                yaml.dump(wf2, f)

            # Simulate 3-source loading: bundled first, user second
            workflows = {}
            workflows.update(load_workflows(dir1))
            workflows.update(load_workflows(dir2))

            assert workflows["shared@1.0.0"].name == "User Version"

    def test_user_overrides_bundled_agent(self):
        """When same agent ID exists in two dirs, later call overwrites."""
        with tempfile.TemporaryDirectory() as dir1, tempfile.TemporaryDirectory() as dir2:
            a1 = {"id": "shared-agent", "name": "Bundled"}
            with open(os.path.join(dir1, "shared-agent.yaml"), "w") as f:
                yaml.dump(a1, f)

            a2 = {"id": "shared-agent", "name": "User"}
            with open(os.path.join(dir2, "shared-agent.yaml"), "w") as f:
                yaml.dump(a2, f)

            agents = {}
            agents.update(load_agents(dir1))
            agents.update(load_agents(dir2))

            assert agents["shared-agent"].name == "User"

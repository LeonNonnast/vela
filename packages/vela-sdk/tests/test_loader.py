"""Tests for workflow loader."""

import os
import tempfile

import pytest
import yaml

from vela_sdk.loader.workflow_loader import (
    load_workflow_file,
    load_workflows,
    parse_workflow_filename,
)


class TestParseWorkflowFilename:
    def test_versioned_filename(self):
        wf_id, version = parse_workflow_filename("feature-planning@1.0.0.yaml")
        assert wf_id == "feature-planning"
        assert version == "1.0.0"

    def test_simple_filename(self):
        wf_id, version = parse_workflow_filename("simple-workflow.yaml")
        assert wf_id == "simple-workflow"
        assert version == "1.0.0"

    def test_yml_extension(self):
        wf_id, version = parse_workflow_filename("test@2.1.0.yml")
        assert wf_id == "test"
        assert version == "2.1.0"


class TestLoadWorkflowFile:
    def test_load_valid_file(self, tmp_path):
        data = {
            "id": "test-wf",
            "name": "Test Workflow",
            "version": "1.0.0",
            "steps": [
                {"id": "s1", "type": "freeform", "prompt": "Hello"},
            ],
        }
        filepath = tmp_path / "test-wf@1.0.0.yaml"
        filepath.write_text(yaml.dump(data))

        wf = load_workflow_file(str(filepath))
        assert wf is not None
        assert wf.id == "test-wf"
        assert wf.name == "Test Workflow"
        assert len(wf.steps) == 1

    def test_load_file_derives_id(self, tmp_path):
        data = {
            "name": "Auto ID",
            "steps": [],
        }
        filepath = tmp_path / "my-workflow@2.0.0.yaml"
        filepath.write_text(yaml.dump(data))

        wf = load_workflow_file(str(filepath))
        assert wf is not None
        assert wf.id == "my-workflow"
        assert wf.version == "2.0.0"

    def test_load_empty_file(self, tmp_path):
        filepath = tmp_path / "empty.yaml"
        filepath.write_text("")

        wf = load_workflow_file(str(filepath))
        assert wf is None

    def test_load_invalid_yaml(self, tmp_path):
        filepath = tmp_path / "bad.yaml"
        filepath.write_text("name: 123\nsteps: not_a_list\n  bad indent")

        wf = load_workflow_file(str(filepath))
        assert wf is None


class TestLoadWorkflows:
    def test_load_directory(self, tmp_path):
        for i in range(3):
            data = {
                "id": f"wf-{i}",
                "name": f"Workflow {i}",
                "steps": [],
            }
            filepath = tmp_path / f"wf-{i}.yaml"
            filepath.write_text(yaml.dump(data))

        workflows = load_workflows(str(tmp_path))
        assert len(workflows) == 3

    def test_load_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        data = {"id": "nested", "name": "Nested", "steps": []}
        (sub / "nested.yaml").write_text(yaml.dump(data))

        workflows = load_workflows(str(tmp_path))
        assert "nested@1.0.0" in workflows

    def test_load_nonexistent_dir(self):
        workflows = load_workflows("/nonexistent/path")
        assert workflows == {}

    def test_skips_non_yaml(self, tmp_path):
        (tmp_path / "readme.md").write_text("# Hello")
        (tmp_path / "wf.yaml").write_text(yaml.dump({
            "id": "wf", "name": "WF", "steps": []
        }))

        workflows = load_workflows(str(tmp_path))
        assert len(workflows) == 1

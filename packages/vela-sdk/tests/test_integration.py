"""Tests for VelaWorkflows FastMCP integration."""

import pytest
import yaml

from vela_sdk.schemas.workflow import (
    StepDefinition,
    StepType,
    WorkflowDefinition,
)
from vela_sdk.storage.memory import InMemoryStore

# Guard: skip if fastmcp not installed
fastmcp = pytest.importorskip("fastmcp")
from fastmcp import FastMCP

from vela_sdk.fastmcp.integration import VelaWorkflows


class TestVelaWorkflowsInit:
    async def test_registers_tools(self, tmp_path):
        data = {
            "id": "test",
            "name": "Test",
            "steps": [{"id": "s1", "type": "freeform", "prompt": "Hi"}],
        }
        (tmp_path / "test.yaml").write_text(yaml.dump(data))

        mcp = FastMCP("test-server")
        store = InMemoryStore()
        wf = VelaWorkflows(
            mcp,
            store=store,
            workflows_dir=str(tmp_path),
        )

        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "workflow_advance" in tool_names
        assert "workflow_status" in tool_names
        assert "workflow_list" in tool_names

    async def test_custom_prefix(self, tmp_path):
        data = {
            "id": "test",
            "name": "Test",
            "steps": [{"id": "s1", "type": "freeform", "prompt": "Hi"}],
        }
        (tmp_path / "test.yaml").write_text(yaml.dump(data))

        mcp = FastMCP("test-server")
        store = InMemoryStore()
        wf = VelaWorkflows(
            mcp,
            store=store,
            workflows_dir=str(tmp_path),
            tool_prefix="wf",
        )

        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert "wf_advance" in tool_names
        assert "wf_status" in tool_names
        assert "wf_list" in tool_names

    async def test_registers_prompts(self, tmp_path):
        data = {
            "id": "my-flow",
            "name": "My Flow",
            "description": "A test flow",
            "steps": [{"id": "s1", "type": "freeform", "prompt": "Hi"}],
        }
        (tmp_path / "my-flow.yaml").write_text(yaml.dump(data))

        mcp = FastMCP("test-server")
        store = InMemoryStore()
        wf = VelaWorkflows(
            mcp,
            store=store,
            workflows_dir=str(tmp_path),
        )

        prompts = await mcp.list_prompts()
        prompt_names = [p.name for p in prompts]
        assert "workflow_my-flow" in prompt_names

    async def test_no_prompts(self, tmp_path):
        data = {
            "id": "test",
            "name": "Test",
            "steps": [{"id": "s1", "type": "freeform", "prompt": "Hi"}],
        }
        (tmp_path / "test.yaml").write_text(yaml.dump(data))

        mcp = FastMCP("test-server")
        store = InMemoryStore()
        wf = VelaWorkflows(
            mcp,
            store=store,
            workflows_dir=str(tmp_path),
            register_prompts=False,
        )

        prompts = await mcp.list_prompts()
        assert len(prompts) == 0

    def test_register_programmatic(self):
        mcp = FastMCP("test-server")
        store = InMemoryStore()
        wf = VelaWorkflows(mcp, store=store)

        wf.register(WorkflowDefinition(
            id="prog-wf",
            name="Programmatic WF",
            steps=[StepDefinition(id="s1", type=StepType.FREEFORM, prompt="Hi")],
        ))

        assert "prog-wf@1.0.0" in wf._workflows

    def test_default_store(self):
        """When no store is provided, InMemoryStore is used."""
        mcp = FastMCP("test-server")
        wf = VelaWorkflows(mcp)
        assert wf._store is not None

    def test_multiple_dirs(self, tmp_path):
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        (dir1 / "wf1.yaml").write_text(yaml.dump({
            "id": "wf1", "name": "WF1", "steps": []
        }))
        (dir2 / "wf2.yaml").write_text(yaml.dump({
            "id": "wf2", "name": "WF2", "steps": []
        }))

        mcp = FastMCP("test-server")
        store = InMemoryStore()
        wf = VelaWorkflows(
            mcp,
            store=store,
            workflows_dir=[str(dir1), str(dir2)],
        )

        assert len(wf._workflows) == 2

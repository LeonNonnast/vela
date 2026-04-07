"""Agent Module Tests — agent prompts, listing, persona loading."""

import json
import os
import tempfile

import pytest
import yaml
from fastmcp import Client, FastMCP

from src.mcp.modules.agent_module import AgentModule
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


def _make_agents_dir():
    """Create a temporary directory with test agent YAMLs."""
    tmpdir = tempfile.mkdtemp()
    agent_data = {
        "id": "test-agent",
        "name": "Test Agent",
        "persona": "You are a helpful test assistant.",
        "greeting": "Hello! I'm your test agent.",
        "workflows": ["test-workflow"],
        "tools": ["vela_remember", "vela_recall"],
    }
    filepath = os.path.join(tmpdir, "test-agent.yaml")
    with open(filepath, "w") as f:
        yaml.dump(agent_data, f)

    # Second agent
    agent_data2 = {
        "id": "minimal-agent",
        "name": "Minimal Agent",
        "persona": "Minimal persona.",
    }
    filepath2 = os.path.join(tmpdir, "minimal-agent.yaml")
    with open(filepath2, "w") as f:
        yaml.dump(agent_data2, f)

    return tmpdir


def _make_agent_server(agents_dir):
    """Create a test server with AgentModule."""
    server = FastMCP("TestVela")
    reset_singleton(AgentModule)

    import src.mcp.modules.agent_module as agent_mod
    import src.shared.config as config_mod
    agent_mod.VELA_AGENTS_DIR = agents_dir
    config_mod.VELA_MODULES_DIR = "/nonexistent"
    AgentModule.construct(mcp=server)
    return server


@pytest.fixture
def agents_dir():
    return _make_agents_dir()


class TestAgentModule:
    async def test_list_agents(self, agents_dir):
        server = _make_agent_server(agents_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_agents", {})
            result = json.loads(_extract_text(raw))
            assert len(result) == 2
            ids = {a["id"] for a in result}
            assert ids == {"test-agent", "minimal-agent"}

    async def test_agent_has_workflows(self, agents_dir):
        server = _make_agent_server(agents_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_agents", {})
            result = json.loads(_extract_text(raw))
            test_agent = next(a for a in result if a["id"] == "test-agent")
            assert "test-workflow" in test_agent["workflows"]

    async def test_agent_has_tools(self, agents_dir):
        server = _make_agent_server(agents_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_agents", {})
            result = json.loads(_extract_text(raw))
            test_agent = next(a for a in result if a["id"] == "test-agent")
            assert "vela_remember" in test_agent["tools"]

    async def test_prompts_registered(self, agents_dir):
        server = _make_agent_server(agents_dir)
        async with Client(server) as client:
            prompts = await client.list_prompts()
            prompt_names = {p.name for p in prompts}
            assert "vela_agent_test-agent" in prompt_names
            assert "vela_agent_minimal-agent" in prompt_names

    async def test_prompt_persona_is_assistant_role(self, agents_dir):
        server = _make_agent_server(agents_dir)
        async with Client(server) as client:
            result = await client.get_prompt("vela_agent_test-agent")
            # First message is assistant role (persona + capabilities)
            assert result.messages[0].role == "assistant"
            text = result.messages[0].content.text if hasattr(result.messages[0].content, 'text') else str(result.messages[0].content)
            assert "Test Agent" in text
            assert "helpful test assistant" in text

    async def test_prompt_greeting_is_user_role(self, agents_dir):
        server = _make_agent_server(agents_dir)
        async with Client(server) as client:
            result = await client.get_prompt("vela_agent_test-agent")
            # Second message is user role (greeting instruction)
            assert len(result.messages) == 2
            assert result.messages[1].role == "user"
            text = result.messages[1].content.text if hasattr(result.messages[1].content, 'text') else str(result.messages[1].content)
            assert "Hello!" in text

    async def test_prompt_contains_workflow_menu(self, agents_dir):
        server = _make_agent_server(agents_dir)
        async with Client(server) as client:
            result = await client.get_prompt("vela_agent_test-agent")
            text = result.messages[0].content.text if hasattr(result.messages[0].content, 'text') else str(result.messages[0].content)
            assert "test-workflow" in text

    async def test_no_agents_empty_dir(self):
        tmpdir = tempfile.mkdtemp()
        server = _make_agent_server(tmpdir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_agents", {})
            result = json.loads(_extract_text(raw))
            assert result == []

    async def test_minimal_agent_prompt(self, agents_dir):
        server = _make_agent_server(agents_dir)
        async with Client(server) as client:
            result = await client.get_prompt("vela_agent_minimal-agent")
            # Minimal agent has no greeting → only 1 message (assistant)
            assert len(result.messages) == 1
            assert result.messages[0].role == "assistant"
            text = result.messages[0].content.text if hasattr(result.messages[0].content, 'text') else str(result.messages[0].content)
            assert "Minimal Agent" in text
            assert "Minimal persona" in text

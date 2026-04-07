"""Standalone SDK integration tests for refactored vela-sdk.

Tests that the SDK works independently with custom protocols,
locales, tool names, and initial_workflows — no DB or external services.
"""

import json
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import pytest

from vela_sdk.schemas.workflow import (
    ParamDefinition,
    StepDefinition,
    StepType,
    WorkflowDefinition,
)
from vela_sdk.storage.memory import InMemoryStore
from vela_sdk.storage.protocol import WorkflowStore

# Guard: skip if fastmcp not installed
fastmcp = pytest.importorskip("fastmcp")
from fastmcp import Client, FastMCP

from vela_sdk.fastmcp.integration import VelaWorkflows
from vela_sdk.fastmcp.locale import Locale, get_locale
from vela_sdk.fastmcp.protocols import (
    ParamFilter,
    SessionProvider,
    WorkflowResolver,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_workflow(wf_id: str = "simple", name: str = "Simple WF") -> WorkflowDefinition:
    return WorkflowDefinition(
        id=wf_id,
        version="1.0.0",
        name=name,
        description="A simple test workflow",
        steps=[
            StepDefinition(id="s1", type=StepType.FREEFORM, prompt="Enter input"),
            StepDefinition(id="s2", type=StepType.CONFIRM, prompt="Confirm: {{state.input}}"),
        ],
    )


def _param_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="param-wf",
        version="1.0.0",
        name="Param WF",
        params=[
            ParamDefinition(name="project", required=True, identity=True),
            ParamDefinition(name="env", required=False, default="staging"),
            ParamDefinition(name="hidden", required=False, application=True),
        ],
        steps=[
            StepDefinition(id="s1", type=StepType.FREEFORM, prompt="Go"),
        ],
    )


async def _call_tool(client: Client, name: str, args: dict | None = None) -> dict:
    """Call a tool via Client and parse the JSON result."""
    result = await client.call_tool(name, args or {})
    text = result.content[0].text
    return json.loads(text)


# ---------------------------------------------------------------------------
# Mock protocol implementations
# ---------------------------------------------------------------------------

class MockWorkflowResolver:
    """WorkflowResolver backed by an in-memory dict."""

    def __init__(self, workflows: dict[str, WorkflowDefinition]) -> None:
        self._workflows = workflows

    async def get_workflow(
        self, workflow_id: str, version: Optional[str] = None
    ) -> Optional[WorkflowDefinition]:
        if version:
            return self._workflows.get(f"{workflow_id}@{version}")
        matches = [wf for wf in self._workflows.values() if wf.id == workflow_id]
        return matches[0] if matches else None

    async def list_workflows(self) -> dict[str, WorkflowDefinition]:
        return dict(self._workflows)


class MockSessionProvider:
    """SessionProvider that tracks open/close calls."""

    def __init__(self, store: WorkflowStore) -> None:
        self._store = store
        self.open_count = 0
        self.close_count = 0

    def session(self):
        provider = self

        @asynccontextmanager
        async def _ctx() -> AsyncIterator[WorkflowStore]:
            provider.open_count += 1
            try:
                yield provider._store
            finally:
                provider.close_count += 1

        return _ctx()


class ApplicationParamFilter:
    """ParamFilter that excludes params with application=True."""

    def filter_missing_params(
        self, wf_def: WorkflowDefinition, provided_params: dict
    ) -> list[ParamDefinition]:
        return [
            p for p in wf_def.params
            if p.required and not p.application and p.name not in provided_params
        ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStandaloneDefaults:
    """VelaWorkflows with just mcp + workflows_dir, no custom protocols."""

    async def test_registers_default_tools(self, tmp_path):
        import yaml
        wf = _simple_workflow()
        (tmp_path / "simple.yaml").write_text(yaml.dump(wf.model_dump()))

        mcp = FastMCP("test")
        VelaWorkflows(mcp, workflows_dir=str(tmp_path))

        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert "workflow_advance" in names
        assert "workflow_status" in names
        assert "workflow_list" in names

    async def test_advance_start_workflow(self, tmp_path):
        """Start a workflow via workflow_advance and get a response."""
        import yaml
        wf = _simple_workflow()
        (tmp_path / "simple.yaml").write_text(yaml.dump(wf.model_dump()))

        mcp = FastMCP("test")
        store = InMemoryStore()
        VelaWorkflows(mcp, store=store, workflows_dir=str(tmp_path))

        async with Client(mcp) as client:
            result = await _call_tool(client, "workflow_advance", {"workflow_id": "simple"})
            assert "run_id" in result
            assert "current_step" in result

    async def test_list_shows_workflows(self, tmp_path):
        import yaml
        wf = _simple_workflow()
        (tmp_path / "simple.yaml").write_text(yaml.dump(wf.model_dump()))

        mcp = FastMCP("test")
        store = InMemoryStore()
        VelaWorkflows(mcp, store=store, workflows_dir=str(tmp_path))

        async with Client(mcp) as client:
            result = await _call_tool(client, "workflow_list")
            assert len(result["definitions"]) == 1
            assert result["definitions"][0]["id"] == "simple"


class TestCustomToolNames:
    """VelaWorkflows with tool_name_format overrides."""

    async def test_custom_names_registered(self):
        mcp = FastMCP("test")
        store = InMemoryStore()
        VelaWorkflows(
            mcp,
            store=store,
            tool_name_format={
                "advance": "my_advance",
                "status": "my_status",
                "list": "my_list",
            },
        )

        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert "my_advance" in names
        assert "my_status" in names
        assert "my_list" in names
        # Default names should NOT be registered
        assert "workflow_advance" not in names

    async def test_partial_override(self):
        """Override only advance, keep defaults for status and list."""
        mcp = FastMCP("test")
        store = InMemoryStore()
        VelaWorkflows(
            mcp,
            store=store,
            tool_name_format={"advance": "do_next"},
        )

        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert "do_next" in names
        assert "workflow_status" in names
        assert "workflow_list" in names

    async def test_custom_tool_names_callable(self):
        """Custom-named tools actually work when called."""
        wf = _simple_workflow()
        mcp = FastMCP("test")
        store = InMemoryStore()
        vw = VelaWorkflows(
            mcp,
            store=store,
            tool_name_format={
                "advance": "my_advance",
                "list": "my_list",
            },
        )
        vw.register(wf)

        async with Client(mcp) as client:
            result = await _call_tool(client, "my_list")
            assert len(result["definitions"]) == 1

            result = await _call_tool(client, "my_advance", {"workflow_id": "simple"})
            assert "run_id" in result


class TestCustomWorkflowResolver:
    """VelaWorkflows with a mock WorkflowResolver."""

    async def test_list_uses_resolver(self):
        wf = _simple_workflow()
        resolver = MockWorkflowResolver({f"{wf.id}@{wf.version}": wf})

        mcp = FastMCP("test")
        store = InMemoryStore()
        VelaWorkflows(mcp, store=store, workflow_resolver=resolver)

        async with Client(mcp) as client:
            result = await _call_tool(client, "workflow_list")
            assert len(result["definitions"]) == 1
            assert result["definitions"][0]["id"] == "simple"

    async def test_advance_uses_resolver(self):
        wf = _simple_workflow()
        resolver = MockWorkflowResolver({f"{wf.id}@{wf.version}": wf})

        mcp = FastMCP("test")
        store = InMemoryStore()
        VelaWorkflows(mcp, store=store, workflow_resolver=resolver)

        async with Client(mcp) as client:
            result = await _call_tool(client, "workflow_advance", {"workflow_id": "simple"})
            assert "run_id" in result
            assert "current_step" in result

    async def test_resolver_unknown_workflow(self):
        resolver = MockWorkflowResolver({})

        mcp = FastMCP("test")
        store = InMemoryStore()
        VelaWorkflows(mcp, store=store, workflow_resolver=resolver)

        async with Client(mcp) as client:
            result = await _call_tool(client, "workflow_advance", {"workflow_id": "nope"})
            assert "error" in result
            assert result["workflow_id"] == "nope"


class TestCustomSessionProvider:
    """VelaWorkflows with a mock SessionProvider that tracks lifecycle."""

    async def test_session_open_close_on_list(self):
        wf = _simple_workflow()
        store = InMemoryStore()
        session_provider = MockSessionProvider(store)

        mcp = FastMCP("test")
        vw = VelaWorkflows(
            mcp,
            store=store,
            session_provider=session_provider,
        )
        vw.register(wf)

        async with Client(mcp) as client:
            await _call_tool(client, "workflow_list")

        assert session_provider.open_count >= 1
        assert session_provider.close_count >= 1
        assert session_provider.open_count == session_provider.close_count

    async def test_session_open_close_on_advance(self):
        wf = _simple_workflow()
        store = InMemoryStore()
        session_provider = MockSessionProvider(store)

        mcp = FastMCP("test")
        vw = VelaWorkflows(
            mcp,
            store=store,
            session_provider=session_provider,
        )
        vw.register(wf)

        async with Client(mcp) as client:
            await _call_tool(client, "workflow_advance", {"workflow_id": "simple"})

        assert session_provider.open_count >= 1
        assert session_provider.open_count == session_provider.close_count

    async def test_session_open_close_on_status(self):
        wf = _simple_workflow()
        store = InMemoryStore()
        session_provider = MockSessionProvider(store)

        mcp = FastMCP("test")
        vw = VelaWorkflows(
            mcp,
            store=store,
            session_provider=session_provider,
        )
        vw.register(wf)

        async with Client(mcp) as client:
            result = await _call_tool(client, "workflow_status", {"run_id": "nonexistent"})
            assert "error" in result

        assert session_provider.open_count >= 1
        assert session_provider.open_count == session_provider.close_count


class TestCustomParamFilter:
    """VelaWorkflows with a custom ParamFilter."""

    async def test_application_params_excluded(self):
        """ApplicationParamFilter excludes application=True params from missing list."""
        wf = _param_workflow()
        pf = ApplicationParamFilter()

        mcp = FastMCP("test")
        store = InMemoryStore()
        vw = VelaWorkflows(mcp, store=store, param_filter=pf)
        vw.register(wf)

        # Verify the filter correctly excludes application params
        missing = pf.filter_missing_params(wf, {})
        names = [p.name for p in missing]
        assert "project" in names       # required, not application
        assert "hidden" not in names     # application=True, excluded
        assert "env" not in names        # not required

    async def test_filter_with_provided_params(self):
        wf = _param_workflow()
        pf = ApplicationParamFilter()

        missing = pf.filter_missing_params(wf, {"project": "myproj"})
        assert len(missing) == 0  # project is provided, hidden is excluded

    async def test_filter_is_wired_into_sdk(self):
        """Verify the custom filter is actually stored on the VelaWorkflows instance."""
        pf = ApplicationParamFilter()
        mcp = FastMCP("test")
        store = InMemoryStore()
        vw = VelaWorkflows(mcp, store=store, param_filter=pf)
        assert vw._param_filter is pf


class TestLocaleEnglish:
    """Default locale (English) produces English response strings."""

    async def test_default_locale_is_english(self):
        mcp = FastMCP("test")
        store = InMemoryStore()
        vw = VelaWorkflows(mcp, store=store)

        assert vw._locale.workflow_completed == "Workflow completed. No further action needed."
        assert vw._locale.new_session == "Start new session"

    async def test_explicit_en_locale(self):
        locale = get_locale("en")
        mcp = FastMCP("test")
        store = InMemoryStore()
        vw = VelaWorkflows(mcp, store=store, locale=locale)

        assert vw._locale.workflow_start_cancelled == "Workflow start cancelled."
        assert "Resumed Session" in vw._locale.prompt_resumed_session

    async def test_advance_response_in_english(self):
        wf = _simple_workflow()
        locale = get_locale("en")

        mcp = FastMCP("test")
        store = InMemoryStore()
        vw = VelaWorkflows(mcp, store=store, locale=locale)
        vw.register(wf)

        async with Client(mcp) as client:
            result = await _call_tool(client, "workflow_advance", {"workflow_id": "simple"})
            next_action = result.get("next_action", "")
            # Should not contain German words
            assert "Rufe" not in next_action
            assert "sofort" not in next_action


class TestLocaleGerman:
    """German locale produces German response strings."""

    async def test_german_locale_strings(self):
        locale = get_locale("de")
        mcp = FastMCP("test")
        store = InMemoryStore()
        vw = VelaWorkflows(mcp, store=store, locale=locale)

        assert vw._locale.workflow_completed == "Workflow abgeschlossen. Keine weitere Aktion nötig."
        assert vw._locale.new_session == "Neue Session starten"
        assert vw._locale.workflow_start_cancelled == "Workflow start abgebrochen."

    async def test_advance_response_in_german(self):
        wf = _simple_workflow()
        locale = get_locale("de")

        mcp = FastMCP("test")
        store = InMemoryStore()
        vw = VelaWorkflows(mcp, store=store, locale=locale)
        vw.register(wf)

        async with Client(mcp) as client:
            result = await _call_tool(client, "workflow_advance", {"workflow_id": "simple"})
            next_action = result.get("next_action", "")
            # Should not contain English-specific text
            assert "Execute the task" not in next_action
            assert "Show the user" not in next_action


class TestInitialWorkflows:
    """VelaWorkflows with initial_workflows for eager prompt registration."""

    async def test_initial_workflows_registered(self):
        wf = _simple_workflow()
        initial = {f"{wf.id}@{wf.version}": wf}

        mcp = FastMCP("test")
        store = InMemoryStore()
        vw = VelaWorkflows(mcp, store=store, initial_workflows=initial)

        assert f"{wf.id}@{wf.version}" in vw._workflows

    async def test_prompts_from_initial_workflows(self):
        wf = _simple_workflow()
        initial = {f"{wf.id}@{wf.version}": wf}

        mcp = FastMCP("test")
        store = InMemoryStore()
        VelaWorkflows(
            mcp, store=store, initial_workflows=initial, register_prompts=True,
        )

        prompts = await mcp.list_prompts()
        prompt_names = [p.name for p in prompts]
        assert f"workflow_{wf.id}" in prompt_names

    async def test_initial_workflows_usable_via_advance(self):
        wf = _simple_workflow()
        initial = {f"{wf.id}@{wf.version}": wf}

        mcp = FastMCP("test")
        store = InMemoryStore()
        VelaWorkflows(mcp, store=store, initial_workflows=initial)

        async with Client(mcp) as client:
            result = await _call_tool(client, "workflow_advance", {"workflow_id": "simple"})
            assert "run_id" in result
            assert "current_step" in result

    async def test_initial_workflows_listed(self):
        wf = _simple_workflow()
        initial = {f"{wf.id}@{wf.version}": wf}

        mcp = FastMCP("test")
        store = InMemoryStore()
        VelaWorkflows(mcp, store=store, initial_workflows=initial)

        async with Client(mcp) as client:
            result = await _call_tool(client, "workflow_list")
            assert len(result["definitions"]) == 1
            assert result["definitions"][0]["id"] == "simple"

    async def test_no_prompts_when_disabled(self):
        wf = _simple_workflow()
        initial = {f"{wf.id}@{wf.version}": wf}

        mcp = FastMCP("test")
        store = InMemoryStore()
        VelaWorkflows(
            mcp, store=store, initial_workflows=initial, register_prompts=False,
        )

        prompts = await mcp.list_prompts()
        assert len(prompts) == 0

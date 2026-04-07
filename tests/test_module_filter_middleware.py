"""Tests for VelaModuleFilterMiddleware — per-request module filtering."""

from dataclasses import dataclass
from typing import Any, Sequence
from unittest.mock import patch, MagicMock

import pytest

from src.mcp.middleware.module_filter_middleware import (
    CORE_PROMPTS,
    CORE_TOOLS,
    VelaModuleFilterMiddleware,
    _IntersectionFilter,
)
from src.shared.services.module_filter import ModuleFilter


# --- Fake Tool / Prompt objects ---

@dataclass
class FakeTool:
    name: str


@dataclass
class FakePrompt:
    name: str


# --- Helpers ---

def _make_tools(*names: str) -> list[FakeTool]:
    return [FakeTool(name=n) for n in names]


def _make_prompts(*names: str) -> list[FakePrompt]:
    return [FakePrompt(name=n) for n in names]


async def _call_next_tools(tools):
    """Factory: returns a call_next that yields the given tools."""
    async def call_next(_ctx):
        return tools
    return call_next


async def _call_next_prompts(prompts):
    """Factory: returns a call_next that yields the given prompts."""
    async def call_next(_ctx):
        return prompts
    return call_next


# --- IntersectionFilter ---

class TestIntersectionFilter:
    def test_both_must_match(self):
        admin = ModuleFilter("migration-*,team-*")
        user = ModuleFilter("migration-*")
        f = _IntersectionFilter(admin, user)
        assert f.active is True
        assert f.matches("migration-pack") is True
        assert f.matches("team-ops") is False  # user doesn't allow team-*
        assert f.matches("other") is False

    def test_active_always_true(self):
        f = _IntersectionFilter(ModuleFilter("a"), ModuleFilter("b"))
        assert f.active is True


# --- Middleware: no filter ---

class TestMiddlewareNoFilter:
    """When VELA_MODULES is empty and no header, all tools/prompts pass."""

    @pytest.mark.asyncio
    async def test_all_tools_returned(self):
        with patch("src.mcp.middleware.module_filter_middleware.VELA_MODULES", ""):
            mw = VelaModuleFilterMiddleware()

        tools = _make_tools("vela_set_project", "vela_migration-pack", "custom_tool")

        async def call_next(_ctx):
            return tools

        result = await mw.on_list_tools(None, call_next)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_all_prompts_returned(self):
        with patch("src.mcp.middleware.module_filter_middleware.VELA_MODULES", ""):
            mw = VelaModuleFilterMiddleware()

        prompts = _make_prompts("vela", "vela_help", "vela_migration-pack")

        async def call_next(_ctx):
            return prompts

        result = await mw.on_list_prompts(None, call_next)
        assert len(result) == 3


# --- Middleware: admin filter only ---

class TestMiddlewareAdminFilter:
    """When VELA_MODULES is set, non-core tools/prompts are filtered."""

    @pytest.mark.asyncio
    async def test_core_tools_always_pass(self):
        with patch("src.mcp.middleware.module_filter_middleware.VELA_MODULES", "migration-*"):
            mw = VelaModuleFilterMiddleware()

        # Patch out HTTP request (simulate stdio)
        with patch(
            "src.mcp.middleware.module_filter_middleware.VelaModuleFilterMiddleware._get_effective_filter",
            return_value=mw._admin_filter,
        ):
            core_tools = _make_tools(*list(CORE_TOOLS)[:5])
            non_matching = _make_tools("brainstorming-tool")
            matching = _make_tools("migration-pack-tool")
            all_tools = core_tools + non_matching + matching

            async def call_next(_ctx):
                return all_tools

            result = await mw.on_list_tools(None, call_next)
            result_names = {t.name for t in result}

            # Core tools always pass
            for t in core_tools:
                assert t.name in result_names

            # matching passes
            assert "migration-pack-tool" in result_names

            # non-matching filtered
            assert "brainstorming-tool" not in result_names

    @pytest.mark.asyncio
    async def test_core_prompts_always_pass(self):
        with patch("src.mcp.middleware.module_filter_middleware.VELA_MODULES", "migration-*"):
            mw = VelaModuleFilterMiddleware()

        with patch(
            "src.mcp.middleware.module_filter_middleware.VelaModuleFilterMiddleware._get_effective_filter",
            return_value=mw._admin_filter,
        ):
            prompts = _make_prompts("vela", "vela_help", "brainstorming-prompt", "migration-setup-prompt")

            async def call_next(_ctx):
                return prompts

            result = await mw.on_list_prompts(None, call_next)
            result_names = {p.name for p in result}

            assert "vela" in result_names           # core prompt
            assert "vela_help" in result_names       # core prompt
            assert "migration-setup-prompt" in result_names  # matches migration-*
            assert "brainstorming-prompt" not in result_names  # doesn't match


# --- Middleware: user header only ---

class TestMiddlewareUserHeader:
    """When only X-Vela-Modules header is set (no admin filter)."""

    @pytest.mark.asyncio
    async def test_user_header_filters(self):
        with patch("src.mcp.middleware.module_filter_middleware.VELA_MODULES", ""):
            mw = VelaModuleFilterMiddleware()

        # Simulate HTTP request with header
        mock_request = MagicMock()
        mock_request.headers = {"x-vela-modules": "team-*"}

        with patch(
            "src.mcp.middleware.module_filter_middleware.get_http_request",
            return_value=mock_request,
            create=True,
        ):
            # Manually patch the import inside the method
            import src.mcp.middleware.module_filter_middleware as mod
            original_get = mw._get_effective_filter

            def patched_get():
                user_filter = ModuleFilter("team-*")
                return user_filter

            mw._get_effective_filter = patched_get

            tools = _make_tools("vela_set_project", "team-ops-deploy", "migration-pack-run")

            async def call_next(_ctx):
                return tools

            result = await mw.on_list_tools(None, call_next)
            result_names = {t.name for t in result}

            assert "vela_set_project" in result_names  # core tool
            assert "team-ops-deploy" in result_names   # matches user filter
            assert "migration-pack-run" not in result_names  # doesn't match

            mw._get_effective_filter = original_get


# --- Middleware: both admin + user (intersection) ---

class TestMiddlewareBothFilters:
    """When both admin and user filters are active, intersection is used."""

    @pytest.mark.asyncio
    async def test_intersection_narrows(self):
        admin = ModuleFilter("migration-*,team-*")
        user = ModuleFilter("migration-*")
        intersection = _IntersectionFilter(admin, user)

        with patch("src.mcp.middleware.module_filter_middleware.VELA_MODULES", "migration-*,team-*"):
            mw = VelaModuleFilterMiddleware()

        mw._get_effective_filter = lambda: intersection

        tools = _make_tools(
            "vela_set_project",       # core
            "migration-pack-run",     # matches both
            "team-ops-deploy",        # matches admin only
            "brainstorming-start",    # matches neither
        )

        async def call_next(_ctx):
            return tools

        result = await mw.on_list_tools(None, call_next)
        result_names = {t.name for t in result}

        assert "vela_set_project" in result_names
        assert "migration-pack-run" in result_names
        assert "team-ops-deploy" not in result_names
        assert "brainstorming-start" not in result_names


# --- _get_effective_filter logic ---

class TestGetEffectiveFilter:
    """Test the filter resolution logic."""

    def test_no_admin_no_header_returns_inactive(self):
        with patch("src.mcp.middleware.module_filter_middleware.VELA_MODULES", ""):
            mw = VelaModuleFilterMiddleware()
        # No HTTP context -> should return admin filter (inactive)
        f = mw._get_effective_filter()
        assert f.active is False

    def test_admin_only_returns_admin(self):
        with patch("src.mcp.middleware.module_filter_middleware.VELA_MODULES", "migration-*"):
            mw = VelaModuleFilterMiddleware()
        # No HTTP context -> returns admin filter
        f = mw._get_effective_filter()
        assert f.active is True
        assert f.matches("migration-pack") is True
        assert f.matches("brainstorming") is False


# --- Core tools set is comprehensive ---

class TestCoreToolsSet:
    """Verify the CORE_TOOLS set contains expected entries."""

    def test_core_tools_not_empty(self):
        assert len(CORE_TOOLS) > 0

    def test_expected_core_tools(self):
        expected = {
            "vela_set_project", "vela_advance_workflow",
            "vela_remember", "vela_status",
        }
        assert expected.issubset(CORE_TOOLS)

    def test_core_prompts(self):
        assert "vela" in CORE_PROMPTS
        assert "vela_help" in CORE_PROMPTS

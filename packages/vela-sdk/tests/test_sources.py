"""Registry tests — register / resolve / duplicate-raises / clear."""

import pytest

from vela_sdk.sources.registry import clear_sources, register_source, resolve_source


async def noop_handler(tool, params, ctx):
    return None


@pytest.fixture(autouse=True)
def _clear():
    clear_sources()
    yield
    clear_sources()


def test_registers_and_resolves_a_handler():
    register_source("devops", noop_handler)
    assert resolve_source("devops") is noop_handler


def test_returns_none_for_unregistered_names():
    assert resolve_source("missing") is None


def test_raises_when_registering_the_same_name_twice():
    register_source("devops", noop_handler)
    with pytest.raises(ValueError, match="already registered"):
        register_source("devops", noop_handler)


def test_clear_sources_wipes_the_registry():
    register_source("devops", noop_handler)
    clear_sources()
    assert resolve_source("devops") is None


def test_supports_multiple_distinct_sources_side_by_side():
    async def a(tool, params, ctx):
        return "a"

    async def b(tool, params, ctx):
        return "b"

    register_source("a", a)
    register_source("b", b)
    assert resolve_source("a") is a
    assert resolve_source("b") is b

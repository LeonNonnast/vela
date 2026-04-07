"""Resource Module Tests — resource registration, listing, resolution."""

import json
import os
import tempfile

import pytest
import yaml
from fastmcp import Client, FastMCP

from src.mcp.modules.resource_module import ResourceModule
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


def _make_resources_dir():
    """Create a temporary directory with test resource YAMLs."""
    tmpdir = tempfile.mkdtemp()

    # Short resource (inline candidate)
    short_data = {
        "id": "short-res",
        "name": "Short Resource",
        "type": "convention",
        "description": "A short convention",
        "content": "Use snake_case for all functions.",
        "tags": ["python", "style"],
    }
    with open(os.path.join(tmpdir, "short-res.yaml"), "w") as f:
        yaml.dump(short_data, f)

    # Long resource (on-demand candidate)
    long_data = {
        "id": "long-res",
        "name": "Long Resource",
        "type": "example",
        "description": "A long example",
        "content": "x" * 600,
        "tags": ["example"],
    }
    with open(os.path.join(tmpdir, "long-res.yaml"), "w") as f:
        yaml.dump(long_data, f)

    # Resource with custom URI
    custom_uri_data = {
        "id": "custom-uri",
        "name": "Custom URI Resource",
        "type": "reference",
        "description": "Has a custom URI",
        "content": "custom content",
        "uri_pattern": "vela://custom/my-resource",
    }
    with open(os.path.join(tmpdir, "custom-uri.yaml"), "w") as f:
        yaml.dump(custom_uri_data, f)

    return tmpdir


def _make_resource_server(resources_dir):
    """Create a test server with ResourceModule."""
    server = FastMCP("TestVela")
    reset_singleton(ResourceModule)

    import src.mcp.modules.resource_module as res_mod
    import src.shared.config as config_mod
    res_mod.VELA_RESOURCES_DIR = resources_dir
    config_mod.VELA_MODULES_DIR = "/nonexistent"

    ResourceModule.construct(mcp=server)
    return server


@pytest.fixture
def resources_dir():
    return _make_resources_dir()


class TestResourceModule:
    async def test_list_resources(self, resources_dir):
        server = _make_resource_server(resources_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_resources", {})
            result = json.loads(_extract_text(raw))
            assert len(result) == 3
            ids = {r["id"] for r in result}
            assert ids == {"short-res", "long-res", "custom-uri"}

    async def test_resource_has_type(self, resources_dir):
        server = _make_resource_server(resources_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_resources", {})
            result = json.loads(_extract_text(raw))
            short = next(r for r in result if r["id"] == "short-res")
            assert short["type"] == "convention"

    async def test_resource_has_tags(self, resources_dir):
        server = _make_resource_server(resources_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_resources", {})
            result = json.loads(_extract_text(raw))
            short = next(r for r in result if r["id"] == "short-res")
            assert "python" in short["tags"]

    async def test_resource_has_uri(self, resources_dir):
        server = _make_resource_server(resources_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_resources", {})
            result = json.loads(_extract_text(raw))
            short = next(r for r in result if r["id"] == "short-res")
            assert short["uri"] == "vela://convention/short-res"

    async def test_custom_uri(self, resources_dir):
        server = _make_resource_server(resources_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_resources", {})
            result = json.loads(_extract_text(raw))
            custom = next(r for r in result if r["id"] == "custom-uri")
            assert custom["uri"] == "vela://custom/my-resource"

    async def test_resources_registered(self, resources_dir):
        server = _make_resource_server(resources_dir)
        async with Client(server) as client:
            resources = await client.list_resources()
            uris = {str(r.uri) for r in resources}
            assert "vela://convention/short-res" in uris
            assert "vela://example/long-res" in uris
            assert "vela://custom/my-resource" in uris

    async def test_read_resource(self, resources_dir):
        server = _make_resource_server(resources_dir)
        async with Client(server) as client:
            result = await client.read_resource("vela://convention/short-res")
            # Result is a list of resource contents
            content = result[0].text if hasattr(result[0], 'text') else str(result[0])
            assert "snake_case" in content

    async def test_no_resources_empty_dir(self):
        tmpdir = tempfile.mkdtemp()
        server = _make_resource_server(tmpdir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_list_resources", {})
            result = json.loads(_extract_text(raw))
            assert result == []


class TestGetResource:
    async def test_get_resource_by_id(self, resources_dir):
        server = _make_resource_server(resources_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_get_resource", {"id": "short-res"})
            result = json.loads(_extract_text(raw))
            assert result["id"] == "short-res"
            assert result["name"] == "Short Resource"
            assert result["type"] == "convention"
            assert "snake_case" in result["content"]

    async def test_get_resource_by_uri(self, resources_dir):
        server = _make_resource_server(resources_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_get_resource", {"id": "vela://custom/my-resource"})
            result = json.loads(_extract_text(raw))
            assert result["id"] == "custom-uri"
            assert result["content"] == "custom content"

    async def test_get_resource_not_found(self, resources_dir):
        server = _make_resource_server(resources_dir)
        async with Client(server) as client:
            raw = await client.call_tool("vela_get_resource", {"id": "nonexistent"})
            result = json.loads(_extract_text(raw))
            assert result["error"] == "Resource not found"
            assert result["id"] == "nonexistent"


class TestResourceResolver:
    def test_resolve_by_id(self, resources_dir):
        reset_singleton(ResourceModule)
        import src.mcp.modules.resource_module as res_mod
        res_mod.VELA_RESOURCES_DIR = resources_dir
        
        server = FastMCP("TestVela")
        module = ResourceModule.construct(mcp=server)

        result = module.resolve("short-res")
        assert result is not None
        assert result.id == "short-res"

    def test_resolve_by_uri(self, resources_dir):
        reset_singleton(ResourceModule)
        import src.mcp.modules.resource_module as res_mod
        res_mod.VELA_RESOURCES_DIR = resources_dir
        
        server = FastMCP("TestVela")
        module = ResourceModule.construct(mcp=server)

        result = module.resolve("vela://custom/my-resource")
        assert result is not None
        assert result.id == "custom-uri"

    def test_resolve_not_found(self, resources_dir):
        reset_singleton(ResourceModule)
        import src.mcp.modules.resource_module as res_mod
        res_mod.VELA_RESOURCES_DIR = resources_dir
        
        server = FastMCP("TestVela")
        module = ResourceModule.construct(mcp=server)

        result = module.resolve("nonexistent")
        assert result is None

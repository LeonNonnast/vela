"""Tests for LocalModuleProvider — DB-backed with local path info."""

from contextlib import asynccontextmanager

import pytest

from src.shared.db.models import CachedModuleFile, ModuleSource
from src.shared.services.local_module_provider import LocalModuleProvider


def _make_session_factory(db_session):
    @asynccontextmanager
    async def _factory():
        yield db_session
    return _factory


class TestLocalModuleProvider:
    async def test_register_module_returns_local_paths(self, db_session):
        factory = _make_session_factory(db_session)
        provider = LocalModuleProvider(factory, "/home/user/.vela/modules")

        result = await provider.register_module("my-module", "A test module")

        assert result["name"] == "my-module"
        assert result["provider"] == "local"
        assert result["description"] == "A test module"
        assert result["local_path"] == "/home/user/.vela/modules/my-module"
        assert result["local_paths"]["base"] == "/home/user/.vela/modules/my-module"
        assert result["local_paths"]["workflows"] == "/home/user/.vela/modules/my-module/workflows"
        assert result["local_paths"]["agents"] == "/home/user/.vela/modules/my-module/agents"
        assert result["local_paths"]["resources"] == "/home/user/.vela/modules/my-module/resources"
        assert "instruction" in result
        assert result["id"] is not None

    async def test_register_module_creates_db_entry(self, db_session):
        factory = _make_session_factory(db_session)
        provider = LocalModuleProvider(factory, "/tmp/modules")

        result = await provider.register_module("test-mod")

        from sqlalchemy import select
        res = await db_session.execute(
            select(ModuleSource).where(
                ModuleSource.provider == "local",
                ModuleSource.name == "test-mod",
            )
        )
        source = res.scalar_one_or_none()
        assert source is not None
        assert source.owner == "local"

    async def test_list_modules_filters_local(self, db_session):
        factory = _make_session_factory(db_session)
        provider = LocalModuleProvider(factory, "/tmp/modules")

        # Create a local module
        await provider.register_module("local-mod")

        # Create a non-local module directly in DB
        github_source = ModuleSource(
            provider="github", owner="acme", name="gh-mod", branch="main",
        )
        db_session.add(github_source)
        await db_session.commit()

        modules = await provider.list_modules()
        assert len(modules) == 1
        assert modules[0]["name"] == "local-mod"
        assert "local_path" in modules[0]

    async def test_write_file_saves_to_db_and_returns_local_path(self, db_session):
        factory = _make_session_factory(db_session)
        provider = LocalModuleProvider(factory, "/home/user/.vela/modules")

        reg = await provider.register_module("my-mod")
        source_id = reg["id"]

        result = await provider.write_file(
            source_id=source_id,
            file_type="workflow",
            file_path="workflows/plan@1.0.0.yaml",
            content="id: plan\nname: Plan\nsteps: []\n",
            module_name="my-mod",
        )

        assert result["saved_to_db"] is True
        assert result["sha"] is not None
        assert result["local_path"] == "/home/user/.vela/modules/my-mod/workflows/plan@1.0.0.yaml"
        assert "instruction" in result

        # Verify DB
        files = await provider.get_module_files(source_id, module_name="my-mod")
        assert len(files) == 1
        assert files[0]["file_path"] == "workflows/plan@1.0.0.yaml"
        assert files[0]["local_path"] == "/home/user/.vela/modules/my-mod/workflows/plan@1.0.0.yaml"

    async def test_write_file_without_module_name_no_local_path(self, db_session):
        factory = _make_session_factory(db_session)
        provider = LocalModuleProvider(factory, "/tmp/modules")

        reg = await provider.register_module("mod")
        source_id = reg["id"]

        result = await provider.write_file(
            source_id=source_id,
            file_type="agent",
            file_path="agents/helper.yaml",
            content="id: helper\nname: Helper\n",
        )

        assert result["saved_to_db"] is True
        assert "local_path" not in result

    async def test_delete_file_from_db_returns_instruction(self, db_session):
        factory = _make_session_factory(db_session)
        provider = LocalModuleProvider(factory, "/home/user/.vela/modules")

        reg = await provider.register_module("my-mod")
        source_id = reg["id"]

        await provider.write_file(
            source_id=source_id, file_type="workflow",
            file_path="workflows/old.yaml", content="old content",
        )

        result = await provider.delete_file(source_id, "workflows/old.yaml", module_name="my-mod")

        assert result["deleted_from_db"] is True
        assert result["local_path"] == "/home/user/.vela/modules/my-mod/workflows/old.yaml"
        assert "instruction" in result

        # Verify file is gone
        files = await provider.get_module_files(source_id)
        assert len(files) == 0

    async def test_delete_nonexistent_file(self, db_session):
        factory = _make_session_factory(db_session)
        provider = LocalModuleProvider(factory, "/tmp/modules")

        reg = await provider.register_module("mod")
        source_id = reg["id"]

        result = await provider.delete_file(source_id, "nonexistent.yaml")
        assert result["deleted_from_db"] is False

    async def test_remove_module_from_db(self, db_session):
        factory = _make_session_factory(db_session)
        provider = LocalModuleProvider(factory, "/home/user/.vela/modules")

        reg = await provider.register_module("doomed")
        source_id = reg["id"]

        result = await provider.remove_module(source_id, module_name="doomed")
        assert result["deleted_from_db"] is True
        assert result["local_path"] == "/home/user/.vela/modules/doomed"
        assert "instruction" in result

    async def test_get_module_files_empty(self, db_session):
        factory = _make_session_factory(db_session)
        provider = LocalModuleProvider(factory, "/tmp/modules")

        reg = await provider.register_module("empty-mod")
        files = await provider.get_module_files(reg["id"])
        assert files == []

    async def test_register_module_idempotent(self, db_session):
        """Registering the same module twice should upsert, not duplicate."""
        factory = _make_session_factory(db_session)
        provider = LocalModuleProvider(factory, "/tmp/modules")

        r1 = await provider.register_module("my-mod", "first")
        r2 = await provider.register_module("my-mod", "updated")

        assert r1["id"] == r2["id"]
        assert r2["description"] == "updated"

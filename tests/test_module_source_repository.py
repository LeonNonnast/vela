"""Tests for ModuleSourceRepository and CachedModuleFileRepository."""

import pytest
from sqlalchemy import select

from src.shared.db.models import CachedModuleFile, ModuleSource
from src.shared.repositories.module_source_repository import (
    CachedModuleFileRepository,
    ModuleSourceRepository,
)


async def _create_source(
    db_session, owner: str = "acme", name: str = "modules"
) -> ModuleSource:
    """Helper: create and return a persisted ModuleSource."""
    source = ModuleSource(
        provider="github",
        owner=owner,
        name=name,
        branch="main",
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


class TestModuleSourceRepository:
    async def test_create_module_source(self, db_session):
        repo = ModuleSourceRepository(db_session)

        source = ModuleSource(
            provider="github",
            owner="acme",
            name="vela-modules",
            branch="main",
        )
        created = await repo.create(source)
        await db_session.commit()

        assert created.id is not None
        assert created.provider == "github"
        assert created.owner == "acme"
        assert created.name == "vela-modules"
        assert created.is_active is True

        # Retrieve by id
        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    async def test_get_by_repo(self, db_session):
        source = await _create_source(db_session, "owner1", "repo1")

        repo = ModuleSourceRepository(db_session)
        found = await repo.get_by_repo("github", "owner1", "repo1")
        assert found is not None
        assert found.id == source.id

        # Not found for different owner
        missing = await repo.get_by_repo("github", "other", "repo1")
        assert missing is None

    async def test_list_active(self, db_session):
        s1 = await _create_source(db_session, "active", "one")
        s2 = await _create_source(db_session, "inactive", "two")

        # Deactivate s2
        s2.is_active = False
        await db_session.commit()

        repo = ModuleSourceRepository(db_session)
        active = await repo.list_active()
        assert len(active) == 1
        assert active[0].id == s1.id

    async def test_get_with_files(self, db_session):
        source = await _create_source(db_session)

        # Add a cached file
        cached = CachedModuleFile(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/test@1.0.0.yaml",
            content="id: test\nname: Test",
            sha="abc123",
        )
        db_session.add(cached)
        await db_session.commit()

        repo = ModuleSourceRepository(db_session)
        loaded = await repo.get_with_files(source.id)
        assert loaded is not None
        assert len(loaded.cached_files) == 1
        assert loaded.cached_files[0].file_path == "workflows/test@1.0.0.yaml"

    async def test_unique_constraint(self, db_session):
        await _create_source(db_session, "dup-owner", "dup-repo")

        # Second source with same provider+owner+name should fail
        dup = ModuleSource(
            provider="github",
            owner="dup-owner",
            name="dup-repo",
            branch="main",
        )
        db_session.add(dup)
        with pytest.raises(Exception):
            await db_session.commit()


class TestCachedModuleFileRepository:
    async def test_upsert_file_insert(self, db_session):
        source = await _create_source(db_session)

        file_repo = CachedModuleFileRepository(db_session)
        f = await file_repo.upsert_file(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/plan@1.0.0.yaml",
            content="id: plan\nname: Plan",
            sha="sha1",
        )
        await db_session.commit()

        assert f.id is not None
        assert f.content == "id: plan\nname: Plan"
        assert f.sha == "sha1"

    async def test_upsert_file_update(self, db_session):
        source = await _create_source(db_session)

        file_repo = CachedModuleFileRepository(db_session)

        # Insert
        f1 = await file_repo.upsert_file(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/plan@1.0.0.yaml",
            content="old content",
            sha="sha-old",
        )
        await db_session.commit()
        original_id = f1.id

        # Update same path
        f2 = await file_repo.upsert_file(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/plan@1.0.0.yaml",
            content="new content",
            sha="sha-new",
        )
        await db_session.commit()

        assert f2.id == original_id
        assert f2.content == "new content"
        assert f2.sha == "sha-new"

    async def test_delete_by_source(self, db_session):
        source = await _create_source(db_session)

        file_repo = CachedModuleFileRepository(db_session)
        await file_repo.upsert_file(
            source_id=source.id,
            file_type="workflow",
            file_path="workflows/a.yaml",
            content="content-a",
            sha=None,
        )
        await file_repo.upsert_file(
            source_id=source.id,
            file_type="agent",
            file_path="agents/b.yaml",
            content="content-b",
            sha=None,
        )
        await db_session.commit()

        count = await file_repo.delete_by_source(source.id)
        await db_session.commit()
        assert count == 2

        # Verify empty
        remaining = await file_repo.list_by_source(source.id)
        assert len(remaining) == 0

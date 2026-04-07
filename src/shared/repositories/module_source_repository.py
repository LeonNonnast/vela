"""Module source repository for database operations."""

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.shared.db.models import CachedModuleFile, ModuleSource
from src.shared.repositories.base_sqlalchemy import BaseSQLAlchemyRepository


class ModuleSourceRepository(BaseSQLAlchemyRepository[ModuleSource]):
    """Repository for ModuleSource entity operations."""

    model_class = ModuleSource

    async def get_by_repo(
        self, provider: str, owner: str, name: str
    ) -> Optional[ModuleSource]:
        """Get a module source by provider + owner + name."""
        result = await self.session.execute(
            select(ModuleSource).where(
                ModuleSource.provider == provider,
                ModuleSource.owner == owner,
                ModuleSource.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[ModuleSource]:
        """Return all active module sources."""
        result = await self.session.execute(
            select(ModuleSource).where(ModuleSource.is_active == True).options(selectinload(ModuleSource.cached_files))
        )
        return list(result.scalars().all())

    async def list_active(self) -> list[ModuleSource]:
        """List all active module sources (for background refresh)."""
        result = await self.session.execute(
            select(ModuleSource).where(ModuleSource.is_active == True)
        )
        return list(result.scalars().all())

    async def get_with_files(self, source_id: str) -> Optional[ModuleSource]:
        """Get module source with eager-loaded cached files."""
        result = await self.session.execute(
            select(ModuleSource)
            .where(ModuleSource.id == source_id)
            .options(selectinload(ModuleSource.cached_files))
        )
        return result.scalar_one_or_none()

    async def list_all_with_files(self) -> list[ModuleSource]:
        """List all module sources with eager-loaded cached files."""
        result = await self.session.execute(
            select(ModuleSource)
            .options(selectinload(ModuleSource.cached_files))
            .order_by(ModuleSource.created_at.desc())
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        provider: str = "github",
        owner: str = "",
        name: str = "",
        branch: str = "main",
        manifest: Optional[dict] = None,
    ) -> ModuleSource:
        """Insert or update a ModuleSource by (provider, owner, name)."""
        existing = await self.get_by_repo(provider, owner, name)
        if existing:
            existing.branch = branch
            if manifest is not None:
                existing.manifest = json.dumps(manifest)
            await self.session.flush()
            return existing
        source = ModuleSource(
            provider=provider,
            owner=owner,
            name=name,
            branch=branch,
            manifest=json.dumps(manifest) if manifest else None,
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def get_cached_files(self, source_id: str) -> list[CachedModuleFile]:
        """Get all cached files for a source."""
        result = await self.session.execute(
            select(CachedModuleFile)
            .where(CachedModuleFile.source_id == source_id)
            .order_by(CachedModuleFile.file_path)
        )
        return list(result.scalars().all())

    async def upsert_cached_file(
        self, source_id: str, file_type: str, file_path: str, content: str, sha: str,
    ) -> CachedModuleFile:
        """Insert or update a CachedModuleFile."""
        result = await self.session.execute(
            select(CachedModuleFile).where(
                CachedModuleFile.source_id == source_id,
                CachedModuleFile.file_path == file_path,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.content = content
            existing.sha = sha
            existing.file_type = file_type
            await self.session.flush()
            return existing
        entity = CachedModuleFile(
            source_id=source_id,
            file_type=file_type,
            file_path=file_path,
            content=content,
            sha=sha,
        )
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete_cached_file(self, source_id: str, file_path: str) -> bool:
        """Delete a single CachedModuleFile by source_id + file_path."""
        result = await self.session.execute(
            select(CachedModuleFile).where(
                CachedModuleFile.source_id == source_id,
                CachedModuleFile.file_path == file_path,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            await self.session.delete(existing)
            await self.session.flush()
            return True
        return False

    async def delete_source(self, source_id: str) -> bool:
        """Delete a ModuleSource by id (cascade deletes cached files)."""
        source = await self.get_by_id(source_id)
        if source:
            await self.session.delete(source)
            await self.session.flush()
            return True
        return False


class CachedModuleFileRepository(BaseSQLAlchemyRepository[CachedModuleFile]):
    """Repository for CachedModuleFile entity operations."""

    model_class = CachedModuleFile

    async def get_by_source_and_type(
        self, source_id: str, file_type: str
    ) -> list[CachedModuleFile]:
        """Get all cached files for a source filtered by type."""
        result = await self.session.execute(
            select(CachedModuleFile).where(
                CachedModuleFile.source_id == source_id,
                CachedModuleFile.file_type == file_type,
            )
        )
        return list(result.scalars().all())

    async def upsert_file(
        self, source_id: str, file_type: str, file_path: str, content: str, sha: Optional[str]
    ) -> CachedModuleFile:
        """Insert or update a cached file."""
        result = await self.session.execute(
            select(CachedModuleFile).where(
                CachedModuleFile.source_id == source_id,
                CachedModuleFile.file_path == file_path,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.content = content
            existing.sha = sha
            existing.file_type = file_type
            await self.session.flush()
            return existing
        else:
            entity = CachedModuleFile(
                source_id=source_id,
                file_type=file_type,
                file_path=file_path,
                content=content,
                sha=sha,
            )
            self.session.add(entity)
            await self.session.flush()
            return entity

    async def delete_by_source(self, source_id: str) -> int:
        """Delete all cached files for a source. Returns count deleted."""
        result = await self.session.execute(
            select(CachedModuleFile).where(CachedModuleFile.source_id == source_id)
        )
        files = list(result.scalars().all())
        for f in files:
            await self.session.delete(f)
        await self.session.flush()
        return len(files)

    async def list_by_source(self, source_id: str) -> list[CachedModuleFile]:
        """List all cached files for a source."""
        result = await self.session.execute(
            select(CachedModuleFile)
            .where(CachedModuleFile.source_id == source_id)
            .order_by(CachedModuleFile.file_path)
        )
        return list(result.scalars().all())

"""Database module provider — stores modules directly in the database."""

import hashlib

import structlog

from src.shared.repositories.module_source_repository import ModuleSourceRepository

logger = structlog.get_logger()


class DbModuleProvider:
    """Reads/writes modules directly in the database using ModuleSource + CachedModuleFile."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def list_modules(self) -> list[dict]:
        """List all DB modules."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            sources = await repo.list_all_with_files()
            return [
                {
                    "source_id": s.id,
                    "name": s.name,
                    "provider": s.provider,
                    "owner": s.owner,
                    "description": (s.manifest or {}).get("description", "") if isinstance(s.manifest, dict) else "",
                }
                for s in sources
                if s.provider == "db"
            ]

    async def register_module(self, name: str, description: str = "") -> dict:
        """Create a new DB module (ModuleSource with provider='db')."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            source = await repo.upsert(
                provider="db",
                owner="db",
                name=name,
                branch="main",
                manifest={"name": name, "description": description, "version": "1.0.0"},
            )
            await session.commit()
            return {"id": source.id, "name": name, "provider": "db", "description": description}

    async def get_module_files(self, source_id: str) -> list[dict]:
        """List all CachedModuleFile entries for a module."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            files = await repo.get_cached_files(source_id)
            return [
                {
                    "file_type": f.file_type,
                    "file_path": f.file_path,
                    "content": f.content,
                    "sha": f.sha,
                }
                for f in files
            ]

    async def write_file(self, source_id: str, file_type: str, file_path: str, content: str) -> dict:
        """Upsert YAML content as a CachedModuleFile."""
        sha = hashlib.sha256(content.encode()).hexdigest()[:12]
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            await repo.upsert_cached_file(
                source_id=source_id,
                file_type=file_type,
                file_path=file_path,
                content=content,
                sha=sha,
            )
            await session.commit()
        return {"file_path": file_path, "sha": sha, "size": len(content)}

    async def delete_file(self, source_id: str, file_path: str) -> bool:
        """Delete a CachedModuleFile entry."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            deleted = await repo.delete_cached_file(source_id, file_path)
            await session.commit()
            return deleted

    async def remove_module(self, source_id: str) -> bool:
        """Delete ModuleSource + cascade CachedModuleFiles."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            deleted = await repo.delete_source(source_id)
            await session.commit()
            return deleted

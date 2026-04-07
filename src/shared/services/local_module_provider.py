"""Local module provider — DB-backed storage with local path information for AI assistants.

All data is stored in the database (ModuleSource + CachedModuleFile).
The provider additionally computes local filesystem paths that the AI
assistant should use to place files on the user's machine.
"""

import hashlib
from pathlib import Path
from typing import Optional

import structlog

from src.shared.repositories.module_source_repository import ModuleSourceRepository

logger = structlog.get_logger()


class LocalModuleProvider:
    """DB-backed module storage with local path information for AI assistants.

    All data is stored in the database (ModuleSource + CachedModuleFile).
    The provider additionally computes local filesystem paths that the AI
    assistant should use to place files on the user's machine.
    """

    def __init__(self, session_factory, base_dir: str):
        self._session_factory = session_factory
        self.base_dir = Path(base_dir)

    def _local_path(self, module_name: str, file_path: str = "") -> str:
        """Compute the local filesystem path for a module or file."""
        path = self.base_dir / module_name
        if file_path:
            path = path / file_path
        return str(path)

    async def list_modules(self) -> list[dict]:
        """List all local-provider modules from DB."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            sources = await repo.list_all_with_files()
            return [
                {
                    "name": s.name,
                    "provider": s.provider,
                    "description": (s.manifest or {}).get("description", "") if isinstance(s.manifest, dict) else "",
                    "local_path": self._local_path(s.name),
                }
                for s in sources
                if s.provider == "local"
            ]

    async def register_module(self, name: str, description: str = "") -> dict:
        """Create a new local module in DB, return with local path info."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            source = await repo.upsert(
                provider="local",
                owner="local",
                name=name,
                branch="main",
                manifest={"name": name, "description": description, "version": "1.0.0"},
            )
            await session.commit()
            return {
                "id": source.id,
                "name": name,
                "provider": "local",
                "description": description,
                "local_path": self._local_path(name),
                "local_paths": {
                    "base": self._local_path(name),
                    "workflows": self._local_path(name, "workflows"),
                    "agents": self._local_path(name, "agents"),
                    "resources": self._local_path(name, "resources"),
                },
                "instruction": "Please create this directory structure on the local filesystem.",
            }

    async def get_module_files(self, source_id: str, module_name: str = "") -> list[dict]:
        """List all cached files for a module from DB, with local paths."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            files = await repo.get_cached_files(source_id)
            return [
                {
                    "file_type": f.file_type,
                    "file_path": f.file_path,
                    "content": f.content,
                    "sha": f.sha,
                    "local_path": self._local_path(module_name, f.file_path) if module_name else "",
                }
                for f in files
            ]

    async def write_file(self, source_id: str, file_type: str, file_path: str, content: str, module_name: str = "") -> dict:
        """Save content to DB and return local path for AI to write."""
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
        result = {
            "file_path": file_path,
            "sha": sha,
            "size": len(content),
            "saved_to_db": True,
        }
        if module_name:
            result["local_path"] = self._local_path(module_name, file_path)
            result["instruction"] = f"Please also save this file locally at: {result['local_path']}"
        return result

    async def delete_file(self, source_id: str, file_path: str, module_name: str = "") -> dict:
        """Delete from DB, return local path for AI to also delete."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            deleted = await repo.delete_cached_file(source_id, file_path)
            await session.commit()
        result = {"deleted_from_db": deleted, "file_path": file_path}
        if module_name:
            result["local_path"] = self._local_path(module_name, file_path)
            result["instruction"] = f"Please also delete the local file at: {result['local_path']}"
        return result

    async def remove_module(self, source_id: str, module_name: str = "") -> dict:
        """Remove module from DB, return local path for AI to also remove."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            deleted = await repo.delete_source(source_id)
            await session.commit()
        result = {"deleted_from_db": deleted}
        if module_name:
            result["local_path"] = self._local_path(module_name)
            result["instruction"] = f"Please also remove the local directory at: {result['local_path']}"
        return result

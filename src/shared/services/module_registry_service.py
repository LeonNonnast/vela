"""Module Registry Service — fetch, cache, load modules from registered repos."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
import yaml
from sqlalchemy import select

from src.shared.config import VELA_LOCAL_MODULES_DIR
from src.shared.db.database import async_session_factory
from src.shared.db.models import CachedModuleFile, ModuleSource
from src.shared.repositories.module_source_repository import (
    CachedModuleFileRepository,
    ModuleSourceRepository,
)
from src.shared.schemas.agent import AgentDefinition
from src.shared.schemas.resource import ResourceDefinition
from src.shared.schemas.workflow import WorkflowDefinition
from src.shared.services.db_module_provider import DbModuleProvider
from src.shared.services.github_api_service import GitHubApiService
from src.shared.services.local_module_provider import LocalModuleProvider
from src.shared.services.workflow_loader import parse_workflow_filename

logger = structlog.get_logger()


@dataclass
class UserModules:
    """In-memory cache of parsed modules (global)."""
    workflows: dict[str, WorkflowDefinition] = field(default_factory=dict)
    agents: dict[str, AgentDefinition] = field(default_factory=dict)
    resources: dict[str, ResourceDefinition] = field(default_factory=dict)


# Sentinel key for global module cache
_GLOBAL_CACHE_KEY = "__global__"


class ModuleRegistryService:
    """Manages registered modules: fetch, cache, load, refresh."""

    def __init__(
        self,
        session_factory=None,
        github: GitHubApiService | None = None,
        local: LocalModuleProvider | None = None,
        db_provider: DbModuleProvider | None = None,
    ):
        sf = session_factory or async_session_factory
        self.github = github or GitHubApiService()
        self.local = local or LocalModuleProvider(sf, VELA_LOCAL_MODULES_DIR)
        self.db_provider = db_provider or DbModuleProvider(sf)
        self._session_factory = sf
        self._modules_cache: Optional[UserModules] = None

    async def register_repo(
        self,
        token: str = "",
        owner: str = "",
        name: str = "",
        branch: str = "main",
    ) -> dict:
        """Register a repo: fetch YAMLs via API, cache in DB, load in memory."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            file_repo = CachedModuleFileRepository(session)

            # Check if already registered
            existing = await repo.get_by_repo("github", owner, name)
            if existing:
                # Re-sync instead
                return await self._sync_source(existing, token, session, repo, file_repo)

            # Fetch manifest (optional)
            manifest = await self.github.get_manifest(token, owner, name, branch)

            # Fetch all module files
            files = await self.github.fetch_module_files(token, owner, name, branch)

            # Create ModuleSource
            source = ModuleSource(
                provider="github",
                owner=owner,
                name=name,
                branch=branch,
                manifest=json.dumps(manifest) if manifest else None,
                last_fetched_at=datetime.now(timezone.utc),
            )
            await repo.create(source)

            # Cache files
            stats = {"workflows": 0, "agents": 0, "resources": 0}
            for f in files:
                await file_repo.upsert_file(
                    source_id=source.id,
                    file_type=f.file_type,
                    file_path=f.file_path,
                    content=f.content,
                    sha=f.sha,
                )
                key = f"{f.file_type}s"
                if key in stats:
                    stats[key] += 1

            await session.commit()

            # Load into memory
            await self._load_source_modules(source.id)

            logger.info(
                "registry.repo_registered",
                owner=owner, name=name, stats=stats,
            )

            return {
                "registered": True,
                "source_id": source.id,
                "repo": f"{owner}/{name}",
                "branch": branch,
                "stats": stats,
            }

    async def unregister_repo(
        self, owner: str = "", name: str = ""
    ) -> dict:
        """Unregister a repo: remove from DB + memory."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            source = await repo.get_by_repo("github", owner, name)
            if not source:
                return {"error": "Repo not found", "repo": f"{owner}/{name}"}

            source_id = source.id
            await repo.delete(source)
            await session.commit()

        # Clean memory
        self._invalidate_cache()

        logger.info("registry.repo_unregistered", owner=owner, name=name)
        return {"unregistered": True, "repo": f"{owner}/{name}", "source_id": source_id}

    async def sync_repo(
        self, token: str, owner: str, name: str
    ) -> dict:
        """Re-fetch a repo and update cache."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            file_repo = CachedModuleFileRepository(session)
            source = await repo.get_by_repo("github", owner, name)
            if not source:
                return {"error": "Repo not found", "repo": f"{owner}/{name}"}

            return await self._sync_source(source, token, session, repo, file_repo)

    async def register_local_module(
        self,
        module_name: str,
        description: str = "",
    ) -> dict:
        """Register a local module in DB with local path info for AI assistants."""
        result = await self.local.register_module(module_name, description)

        self._invalidate_cache()

        logger.info(
            "registry.local_module_registered",
            module_name=module_name,
        )

        return {
            "registered": True,
            "source_id": result["id"],
            "provider": "local",
            "module": module_name,
            "local_path": result["local_path"],
            "local_paths": result["local_paths"],
            "instruction": result["instruction"],
        }

    async def register_db_module(
        self,
        module_name: str,
        description: str = "",
    ) -> dict:
        """Register a DB module (ModuleSource with provider='db')."""
        result = await self.db_provider.register_module(module_name, description)

        self._invalidate_cache()

        logger.info("registry.db_module_registered", module_name=module_name)

        return {
            "registered": True,
            "source_id": result["id"],
            "provider": "db",
            "module": module_name,
        }

    async def sync_local_module(
        self,
        module_name: str,
    ) -> dict:
        """Sync a local module — reload from DB cache into memory."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)

            source = await repo.get_by_repo("local", "local", module_name)
            if not source:
                return {"error": "Local module not found", "module": module_name}

            source_id = source.id

        self._invalidate_cache()
        await self._load_source_modules(source_id)

        logger.info("registry.local_module_synced", module_name=module_name)

        return {
            "synced": True,
            "source_id": source_id,
            "provider": "local",
            "module": module_name,
        }

    async def unregister_module(
        self, provider: str, owner: str, name: str,
    ) -> dict:
        """Unregister a module of any provider type."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            source = await repo.get_by_repo(provider, owner, name)
            if not source:
                return {"error": "Module not found", "module": name, "provider": provider}

            source_id = source.id
            await repo.delete(source)
            await session.commit()

        self._invalidate_cache()

        logger.info("registry.module_unregistered", name=name, provider=provider)
        return {"unregistered": True, "module": name, "provider": provider, "source_id": source_id}

    async def get_source_by_id(self, source_id: str) -> Optional[ModuleSource]:
        """Look up a ModuleSource by id."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            return await repo.get_with_files(source_id)

    async def find_source(
        self, provider: str, owner: str, name: str,
    ) -> Optional[ModuleSource]:
        """Find a ModuleSource by provider + owner + name."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            return await repo.get_by_repo(provider, owner, name)

    async def _sync_source(
        self,
        source: ModuleSource,
        token: str,
        session,
        repo: ModuleSourceRepository,
        file_repo: CachedModuleFileRepository,
    ) -> dict:
        """Internal: re-fetch and update a source."""
        # Fetch fresh files
        files = await self.github.fetch_module_files(
            token, source.owner, source.name, source.branch
        )

        # Update manifest
        manifest = await self.github.get_manifest(
            token, source.owner, source.name, source.branch
        )
        source.manifest = json.dumps(manifest) if manifest else None
        source.last_fetched_at = datetime.now(timezone.utc)

        # Delete old cached files and insert new ones
        await file_repo.delete_by_source(source.id)

        stats = {"workflows": 0, "agents": 0, "resources": 0}
        for f in files:
            await file_repo.upsert_file(
                source_id=source.id,
                file_type=f.file_type,
                file_path=f.file_path,
                content=f.content,
                sha=f.sha,
            )
            key = f"{f.file_type}s"
            if key in stats:
                stats[key] += 1

        await session.commit()

        # Reload memory
        self._invalidate_cache()
        await self._load_source_modules(source.id)

        logger.info(
            "registry.repo_synced",
            owner=source.owner, name=source.name, stats=stats,
        )

        return {
            "synced": True,
            "source_id": source.id,
            "repo": f"{source.owner}/{source.name}",
            "stats": stats,
        }

    async def load_modules(self) -> UserModules:
        """Load all modules from DB cache into memory."""
        if self._modules_cache is not None:
            return self._modules_cache

        modules = UserModules()

        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            sources = await repo.list_all_with_files()

            for source in sources:
                if not source.is_active:
                    continue
                for cached_file in source.cached_files:
                    self._parse_and_add(cached_file, modules)

        self._modules_cache = modules
        logger.info(
            "registry.modules_loaded",
            workflows=len(modules.workflows),
            agents=len(modules.agents),
            resources=len(modules.resources),
        )
        return modules

    async def get_workflows(self) -> dict[str, WorkflowDefinition]:
        modules = await self.load_modules()
        return modules.workflows

    async def get_agents(self) -> dict[str, AgentDefinition]:
        modules = await self.load_modules()
        return modules.agents

    async def get_resources(self) -> dict[str, ResourceDefinition]:
        modules = await self.load_modules()
        return modules.resources

    async def list_repos(self) -> list[dict]:
        """List registered repos with file stats. Always includes built-in modules first."""
        from src.shared.config import VELA_MODULES_DIR

        builtin_entries = []
        modules_dir = Path(VELA_MODULES_DIR).resolve()
        if modules_dir.is_dir():
            for module_dir in sorted(modules_dir.iterdir()):
                if not module_dir.is_dir():
                    continue
                stats = {
                    "workflows": len(list((module_dir / "workflows").glob("*.yaml"))) if (module_dir / "workflows").is_dir() else 0,
                    "agents":    len(list((module_dir / "agents").glob("*.yaml")))    if (module_dir / "agents").is_dir()    else 0,
                    "resources": len(list((module_dir / "resources").glob("*.yaml"))) if (module_dir / "resources").is_dir() else 0,
                }
                builtin_entries.append({
                    "source_id": f"builtin:{module_dir.name}",
                    "provider": "builtin",
                    "owner": "vela",
                    "name": module_dir.name,
                    "repo": f"vela/{module_dir.name}",
                    "branch": None,
                    "is_active": True,
                    "last_fetched_at": None,
                    "stats": stats,
                    "created_at": None,
                })

        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            sources = await repo.list_all_with_files()
            return builtin_entries + [self._source_to_dict(s) for s in sources]

    async def refresh_all_sources(self, token_resolver=None):
        """Background task: refresh all active sources."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            sources = await repo.list_active()
            for source in sources:
                try:
                    # Note: in production, token should come from stored OAuth tokens
                    # For now, this is a placeholder for background refresh
                    logger.info(
                        "registry.refresh_skipped",
                        source_id=source.id,
                        reason="no_token_resolver",
                    )
                except Exception as e:
                    logger.error(
                        "registry.refresh_failed",
                        source_id=source.id, error=str(e),
                    )

    async def _load_source_modules(self, source_id: str):
        """Load modules from a single source into the global memory cache."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            source = await repo.get_with_files(source_id)
            if not source:
                return

            if self._modules_cache is None:
                self._modules_cache = UserModules()

            for cached_file in source.cached_files:
                self._parse_and_add(cached_file, self._modules_cache)

    def _parse_and_add(self, cached_file: CachedModuleFile, modules: UserModules):
        """Parse a cached YAML file and add to the appropriate module dict."""
        try:
            data = yaml.safe_load(cached_file.content)
            if not data or not isinstance(data, dict):
                return

            filename = Path(cached_file.file_path).name

            if cached_file.file_type == "workflow":
                file_id, file_version = parse_workflow_filename(filename)
                if "id" not in data:
                    data["id"] = file_id
                if "version" not in data:
                    data["version"] = file_version
                wf = WorkflowDefinition(**data)
                key = f"{wf.id}@{wf.version}"
                modules.workflows[key] = wf

            elif cached_file.file_type == "agent":
                if "id" not in data:
                    data["id"] = Path(filename).stem
                agent = AgentDefinition(**data)
                modules.agents[agent.id] = agent

            elif cached_file.file_type == "resource":
                if "id" not in data:
                    data["id"] = Path(filename).stem
                resource = ResourceDefinition(**data)
                modules.resources[resource.id] = resource

        except Exception as e:
            logger.error(
                "registry.parse_error",
                file_path=cached_file.file_path,
                file_type=cached_file.file_type,
                error=str(e),
            )

    @staticmethod
    def _source_to_dict(source: ModuleSource) -> dict:
        """Convert a ModuleSource to a response dict with file stats."""
        stats = {"workflows": 0, "agents": 0, "resources": 0}
        for f in source.cached_files:
            key = f"{f.file_type}s"
            if key in stats:
                stats[key] += 1

        return {
            "source_id": source.id,
            "provider": source.provider,
            "owner": source.owner,
            "name": source.name,
            "repo": f"{source.owner}/{source.name}",
            "branch": source.branch,
            "is_active": source.is_active,
            "last_fetched_at": str(source.last_fetched_at) if source.last_fetched_at else None,
            "stats": stats,
            "created_at": str(source.created_at),
        }

    async def update_cached_file(
        self, owner: str, name: str,
        file_type: str, file_path: str, content: str, sha: str,
        provider: str = "github",
    ) -> None:
        """Upsert a single file in the cache and invalidate memory."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)
            file_repo = CachedModuleFileRepository(session)

            source = await repo.get_by_repo(provider, owner, name)
            if not source:
                logger.warning(
                    "registry.update_cached_file_no_source",
                    owner=owner, name=name, provider=provider,
                )
                return

            await file_repo.upsert_file(
                source_id=source.id,
                file_type=file_type,
                file_path=file_path,
                content=content,
                sha=sha,
            )
            await session.commit()

        self._invalidate_cache()

    async def delete_cached_file(
        self, owner: str, name: str, file_path: str,
        provider: str = "github",
    ) -> None:
        """Delete a single file from cache and invalidate memory."""
        async with self._session_factory() as session:
            repo = ModuleSourceRepository(session)

            source = await repo.get_by_repo(provider, owner, name)
            if not source:
                return

            result = await session.execute(
                select(CachedModuleFile).where(
                    CachedModuleFile.source_id == source.id,
                    CachedModuleFile.file_path == file_path,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                await session.delete(existing)
                await session.commit()

        self._invalidate_cache()

    def _invalidate_cache(self):
        """Clear the global in-memory module cache (forces reload on next access)."""
        self._modules_cache = None

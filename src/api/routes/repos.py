"""Module repository management endpoints."""

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.shared.services.module_registry_service import ModuleRegistryService

logger = structlog.get_logger()

router = APIRouter(tags=["repos"])

_registry: ModuleRegistryService | None = None


def _get_registry() -> ModuleRegistryService:
    """Lazy-create a single ModuleRegistryService for the API layer."""
    global _registry
    if _registry is None:
        _registry = ModuleRegistryService()
    return _registry


@router.get("/repos")
async def api_list_repos() -> JSONResponse:
    """List connected modules (all providers)."""
    try:
        registry = _get_registry()
        repos = await registry.list_repos()
        return JSONResponse({"repos": repos, "count": len(repos)})
    except Exception as e:
        logger.error("api.repos.error", error=str(e))
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/repos/install")
async def api_install_repo(request: Request) -> JSONResponse:
    """Connect a module. Supports provider='github' (default), 'local', or 'db'."""
    try:
        body = await request.json()
        provider = body.get("provider", "github")
        name = body.get("name")
        if not name:
            return JSONResponse({"error": "name required"}, status_code=400)

        registry = _get_registry()

        if provider == "local":
            result = await registry.register_local_module(
                module_name=name,
                description=body.get("description", ""),
            )
            return JSONResponse(result)

        if provider == "db":
            result = await registry.register_db_module(
                module_name=name,
                description=body.get("description", ""),
            )
            return JSONResponse(result)

        # GitHub flow
        owner = body.get("owner")
        branch = body.get("branch", "main")
        if not owner:
            return JSONResponse({"error": "owner required for GitHub provider"}, status_code=400)

        github_token = body.get("github_token", "")

        result = await registry.register_repo(
            token=github_token,
            owner=owner, name=name, branch=branch,
        )
        return JSONResponse(result)
    except Exception as e:
        logger.error("api.install.error", error=str(e))
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/repos/remove")
async def api_remove_repo(request: Request) -> JSONResponse:
    """Disconnect a module. Supports all providers."""
    try:
        body = await request.json()
        provider = body.get("provider", "github")
        name = body.get("name")
        if not name:
            return JSONResponse({"error": "name required"}, status_code=400)

        registry = _get_registry()

        if provider in ("local", "db"):
            owner = provider  # local/db modules use provider as owner
            result = await registry.unregister_module(
                provider=provider,
                owner=owner,
                name=name,
            )
            return JSONResponse(result)

        # GitHub flow
        owner = body.get("owner")
        if not owner:
            return JSONResponse({"error": "owner required for GitHub provider"}, status_code=400)

        result = await registry.unregister_repo(
            owner=owner, name=name,
        )
        return JSONResponse(result)
    except Exception as e:
        logger.error("api.remove.error", error=str(e))
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/repos/sync")
async def api_sync_repo(request: Request) -> JSONResponse:
    """Sync a connected module. Supports all providers."""
    try:
        body = await request.json()
        provider = body.get("provider", "github")
        name = body.get("name")
        if not name:
            return JSONResponse({"error": "name required"}, status_code=400)

        registry = _get_registry()

        if provider == "local":
            result = await registry.sync_local_module(
                module_name=name,
            )
            return JSONResponse(result)

        if provider == "db":
            # DB modules are always in sync
            registry._invalidate_cache()
            return JSONResponse({"synced": True, "provider": "db", "module": name})

        # GitHub flow
        owner = body.get("owner")
        if not owner:
            return JSONResponse({"error": "owner required for GitHub provider"}, status_code=400)

        github_token = body.get("github_token", "")

        result = await registry.sync_repo(
            token=github_token,
            owner=owner, name=name,
        )
        return JSONResponse(result)
    except Exception as e:
        logger.error("api.sync.error", error=str(e))
        return JSONResponse({"error": str(e)}, status_code=500)

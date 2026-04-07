"""Module Hub — MCP tools for managing module repos (GitHub, local, DB)."""

import os
import re
from typing import Optional

import structlog
import yaml
from fastmcp import Context, FastMCP
from fastmcp.prompts.prompt import Message

from src.mcp.modules.base import VelaModuleBase
from src.mcp.modules.mcp_utils import to_json
from src.shared.schemas.agent import AgentDefinition
from src.shared.schemas.workflow import WorkflowDefinition
from src.shared.services.github_api_service import GitHubApiService
from src.shared.services.module_registry_service import ModuleRegistryService

logger = structlog.get_logger()

# Pattern: "owner/name" or full GitHub URL
_REPO_URL_PATTERN = re.compile(
    r"(?:https?://github\.com/)?([^/]+)/([^/?#]+?)(?:\.git)?/?$"
)


def parse_repo_string(repo: str) -> tuple[str, str]:
    """Parse 'owner/name' or GitHub URL into (owner, name)."""
    match = _REPO_URL_PATTERN.match(repo.strip())
    if match:
        return match.group(1), match.group(2)
    parts = repo.strip().split("/")
    if len(parts) == 2:
        return parts[0], parts[1]
    raise ValueError(f"Invalid repo format: {repo!r}. Use 'owner/name' or a GitHub URL.")


def _get_github_token() -> Optional[str]:
    """Get GitHub token from environment variable. Returns None if unavailable."""
    return os.getenv("GITHUB_TOKEN") or None


def _require_github_token() -> str:
    """Get GitHub token or raise ValueError."""
    token = _get_github_token()
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable not set. Required for GitHub operations.")
    return token


class ModuleHubModule(VelaModuleBase):
    """Manages module hub via MCP tools — connect/sync/disconnect GitHub repos."""

    def __init__(self, mcp: FastMCP, module_registry: ModuleRegistryService | None = None):
        self._mcp = mcp
        self._registry = module_registry or ModuleRegistryService()
        self._github = GitHubApiService()
        self._register_tools(mcp)

    def _register_tools(self, mcp: FastMCP):
        @mcp.tool(
            name="vela_clone_repo",
            description=(
                "Connect a Vela module. "
                "source='github': use owner/name or GitHub URL (requires GITHUB_TOKEN env var). "
                "source='local': create/connect a local filesystem module. "
                "source='db': create/connect a database-stored module."
            ),
        )
        async def vela_clone_repo(
            repo: str,
            branch: str = "main",
            source: str = "github",
            ctx: Context = None,
        ) -> str:
            if source == "local":
                result = await self._registry.register_local_module(
                    module_name=repo.strip(),
                    description="",
                )
                await self._register_prompts()
                return to_json(result)

            if source == "db":
                result = await self._registry.register_db_module(
                    module_name=repo.strip(),
                    description="",
                )
                await self._register_prompts()
                return to_json(result)

            # GitHub flow
            try:
                token = _require_github_token()
            except ValueError as e:
                return to_json({"error": str(e)})

            try:
                owner, name = parse_repo_string(repo)
            except ValueError as e:
                return to_json({"error": str(e)})

            result = await self._registry.register_repo(
                token=token,
                owner=owner,
                name=name,
                branch=branch,
            )

            # Dynamically register prompts for new workflows/agents
            await self._register_prompts()

            return to_json(result)

        @mcp.tool(
            name="vela_sync_repo",
            description=(
                "Sync a connected module — re-fetches latest content "
                "and updates cached workflows/agents/resources. "
                "Works with GitHub, local, and DB modules."
            ),
        )
        async def vela_sync_repo(
            repo: str,
            ctx: Context = None,
        ) -> str:
            # Determine provider by looking up the source
            source_info = await self._find_source_by_name(repo)
            if source_info and source_info.provider == "local":
                result = await self._registry.sync_local_module(
                    module_name=source_info.name,
                )
                await self._register_prompts()
                return to_json(result)

            if source_info and source_info.provider == "db":
                # DB modules don't need sync — they're already in the DB
                self._registry._invalidate_cache()
                await self._register_prompts()
                return to_json({"synced": True, "provider": "db", "module": source_info.name})

            # GitHub flow
            try:
                token = _require_github_token()
            except ValueError as e:
                return to_json({"error": str(e)})

            try:
                owner, name = parse_repo_string(repo)
            except ValueError as e:
                return to_json({"error": str(e)})

            result = await self._registry.sync_repo(
                token=token,
                owner=owner,
                name=name,
            )

            # Re-register prompts after sync
            await self._register_prompts()

            return to_json(result)

        @mcp.tool(
            name="vela_remove_repo",
            description=(
                "Disconnect a module — removes all its workflows, "
                "agents, and resources from your workspace. "
                "Works with GitHub, local, and DB modules."
            ),
        )
        async def vela_remove_repo(
            repo: str,
            ctx: Context = None,
        ) -> str:
            # Determine provider by looking up the source
            source_info = await self._find_source_by_name(repo)
            if source_info and source_info.provider in ("local", "db"):
                result = await self._registry.unregister_module(
                    provider=source_info.provider,
                    owner=source_info.owner,
                    name=source_info.name,
                )
                return to_json(result)

            # GitHub flow
            try:
                owner, name = parse_repo_string(repo)
            except ValueError as e:
                return to_json({"error": str(e)})

            result = await self._registry.unregister_repo(
                owner=owner,
                name=name,
            )
            return to_json(result)

        @mcp.tool(
            name="vela_list_repos",
            description="List all your connected modules (GitHub, local, DB) with contents and sync status.",
        )
        async def vela_list_repos(
            ctx: Context = None,
        ) -> str:
            repos = await self._registry.list_repos()
            return to_json({"repos": repos, "count": len(repos)})

        @mcp.tool(
            name="vela_create_module",
            description=(
                "Create a new Vela module. "
                "source='github': creates a GitHub repository (requires GITHUB_TOKEN env var). "
                "source='local': creates a local filesystem module. "
                "source='db': creates a database-stored module."
            ),
        )
        async def vela_create_module(
            name: str,
            description: str = "",
            private: bool = True,
            source: str = "local",
            ctx: Context = None,
        ) -> str:
            return await self._create_module_impl(name, description, private, source, ctx)

        @mcp.tool(
            name="vela_push_to_module",
            description=(
                "Push a workflow, agent, or resource YAML file to a module. "
                "Automatically determines the file path from the YAML content. "
                "Works with GitHub, local, and DB modules."
            ),
        )
        async def vela_push_to_module(
            repo: str,
            file_type: str,
            content: str,
            filename: str | None = None,
            message: str | None = None,
            ctx: Context = None,
        ) -> str:
            return await self._push_to_module_impl(repo, file_type, content, filename, message, ctx)

        @mcp.tool(
            name="vela_delete_from_module",
            description=(
                "Delete a file from a module. "
                "Works with GitHub, local, and DB modules."
            ),
        )
        async def vela_delete_from_module(
            repo: str,
            file_path: str,
            ctx: Context = None,
        ) -> str:
            return await self._delete_from_module_impl(repo, file_path, ctx)

    async def _find_source_by_name(self, repo: str):
        """Try to find a ModuleSource by name, checking local/db providers first."""
        repo_name = repo.strip()

        # Check local
        source = await self._registry.find_source("local", "local", repo_name)
        if source:
            return source
        # Check db
        source = await self._registry.find_source("db", "db", repo_name)
        if source:
            return source
        # Check github by trying to parse as owner/name
        try:
            owner, name = parse_repo_string(repo)
            source = await self._registry.find_source("github", owner, name)
            if source:
                return source
        except ValueError:
            pass
        return None

    async def _create_module_impl(
        self, name: str, description: str, private: bool, source: str, ctx: Context,
    ) -> str:
        if source == "local":
            result = await self._registry.register_local_module(
                module_name=name,
                description=description,
            )
            await self._register_prompts()
            response = {
                "created": True,
                "module": name,
                "provider": "local",
                "source_id": result.get("source_id", ""),
                "local_path": result.get("local_path", ""),
                "local_paths": result.get("local_paths", {}),
                "instruction": result.get("instruction", ""),
            }
            return to_json(response)

        if source == "db":
            result = await self._registry.register_db_module(
                module_name=name,
                description=description,
            )
            await self._register_prompts()
            return to_json({
                "created": True,
                "module": name,
                "provider": "db",
                "source_id": result.get("source_id", ""),
            })

        # GitHub flow
        try:
            token = _require_github_token()
        except ValueError as e:
            return to_json({"error": str(e)})

        # Create GitHub repo
        repo_result = await self._github.create_repo(token, name, description, private)
        if "error" in repo_result:
            return to_json(repo_result)

        owner = repo_result["owner"]
        repo_name = repo_result["name"]

        # Push vela.yaml manifest
        manifest_content = yaml.dump(
            {"name": name, "description": description, "version": "1.0.0"},
            default_flow_style=False,
        )
        file_result = await self._github.create_or_update_file(
            token, owner, repo_name, "vela.yaml",
            manifest_content, "Initialize Vela module",
        )
        if "error" in file_result:
            return to_json({"error": f"Repo created but manifest push failed: {file_result['error']}"})

        # Register in DB + cache
        reg_result = await self._registry.register_repo(
            token=token,
            owner=owner,
            name=repo_name,
        )

        # Register prompts
        await self._register_prompts()

        return to_json({
            "created": True,
            "repo": f"{owner}/{repo_name}",
            "html_url": repo_result.get("html_url", ""),
            "source_id": reg_result.get("source_id", ""),
        })

    async def _push_to_module_impl(
        self, repo: str, file_type: str, content: str,
        filename: str | None, message: str | None, ctx: Context,
    ) -> str:
        if file_type not in ("workflow", "agent", "resource"):
            return to_json({"error": f"Invalid file_type: {file_type!r}. Must be workflow, agent, or resource."})

        # Parse YAML to extract id and version
        try:
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return to_json({"error": "Content must be valid YAML mapping"})
        except yaml.YAMLError as e:
            return to_json({"error": f"Invalid YAML: {e}"})

        file_id = data.get("id")
        if not file_id:
            return to_json({"error": "YAML must contain an 'id' field"})

        # Determine file path
        if filename:
            path = filename
        elif file_type == "workflow":
            version = data.get("version", "1.0.0")
            path = f"workflows/{file_id}@{version}.yaml"
        elif file_type == "agent":
            path = f"agents/{file_id}.yaml"
        else:
            path = f"resources/{file_id}.yaml"

        # Determine provider
        source_info = await self._find_source_by_name(repo)

        if source_info and source_info.provider == "local":
            # Write to DB, get local path info for AI assistant
            result = await self._registry.local.write_file(
                source_id=source_info.id,
                file_type=file_type,
                file_path=path,
                content=content,
                module_name=source_info.name,
            )
            self._registry._invalidate_cache()
            await self._register_prompts()
            response = {
                "pushed": True,
                "module": source_info.name,
                "provider": "local",
                "path": path,
                "sha": result["sha"],
                "action": "created",
            }
            if "local_path" in result:
                response["local_path"] = result["local_path"]
                response["instruction"] = result["instruction"]
            return to_json(response)

        if source_info and source_info.provider == "db":
            # Write directly to DB
            import hashlib
            sha = hashlib.sha256(content.encode()).hexdigest()[:12]
            await self._registry.update_cached_file(
                owner="db",
                name=source_info.name,
                file_type=file_type,
                file_path=path,
                content=content,
                sha=sha,
                provider="db",
            )
            await self._register_prompts()
            return to_json({
                "pushed": True,
                "module": source_info.name,
                "provider": "db",
                "path": path,
                "sha": sha,
                "action": "created",
            })

        # GitHub flow
        try:
            token = _require_github_token()
        except ValueError as e:
            return to_json({"error": str(e)})

        try:
            owner, name = parse_repo_string(repo)
        except ValueError as e:
            return to_json({"error": str(e)})

        # Check if file exists (to get sha for update)
        existing = await self._github.get_file_content(token, owner, name, path)
        sha = existing[1] if existing else None
        action = "updated" if sha else "created"

        commit_msg = message or f"{'Update' if sha else 'Add'} {file_type} {file_id}"

        # Push file
        result = await self._github.create_or_update_file(
            token, owner, name, path, content, commit_msg, sha,
        )
        if "error" in result:
            return to_json(result)

        # Update cache
        await self._registry.update_cached_file(
            owner=owner,
            name=name,
            file_type=file_type,
            file_path=path,
            content=content,
            sha=result["sha"],
        )

        # Re-register prompts
        await self._register_prompts()

        return to_json({
            "pushed": True,
            "repo": f"{owner}/{name}",
            "path": path,
            "sha": result["sha"],
            "action": action,
        })

    async def _delete_from_module_impl(
        self, repo: str, file_path: str, ctx: Context,
    ) -> str:
        # Determine provider
        source_info = await self._find_source_by_name(repo)

        if source_info and source_info.provider == "local":
            # Delete from DB, get local path info for AI assistant
            result = await self._registry.local.delete_file(
                source_id=source_info.id,
                file_path=file_path,
                module_name=source_info.name,
            )
            if not result["deleted_from_db"]:
                return to_json({"error": f"File not found: {file_path}"})
            self._registry._invalidate_cache()
            await self._register_prompts()
            response = {
                "deleted": True,
                "module": source_info.name,
                "provider": "local",
                "path": file_path,
            }
            if "local_path" in result:
                response["local_path"] = result["local_path"]
                response["instruction"] = result["instruction"]
            return to_json(response)

        if source_info and source_info.provider == "db":
            # Delete from DB
            await self._registry.delete_cached_file(
                owner="db",
                name=source_info.name,
                file_path=file_path,
                provider="db",
            )
            await self._register_prompts()
            return to_json({
                "deleted": True,
                "module": source_info.name,
                "provider": "db",
                "path": file_path,
            })

        # GitHub flow
        try:
            token = _require_github_token()
        except ValueError as e:
            return to_json({"error": str(e)})

        try:
            owner, name = parse_repo_string(repo)
        except ValueError as e:
            return to_json({"error": str(e)})

        # Get current sha
        existing = await self._github.get_file_content(token, owner, name, file_path)
        if not existing:
            return to_json({"error": f"File not found: {file_path}"})

        _, sha = existing

        # Delete from GitHub
        result = await self._github.delete_file(
            token, owner, name, file_path, sha, f"Delete {file_path}",
        )
        if "error" in result:
            return to_json(result)

        # Delete from cache
        await self._registry.delete_cached_file(
            owner=owner,
            name=name,
            file_path=file_path,
        )

        # Re-register prompts
        await self._register_prompts()

        return to_json({
            "deleted": True,
            "repo": f"{owner}/{name}",
            "path": file_path,
        })

    async def _register_prompts(self):
        """Register MCP prompts for workflows and agents dynamically."""
        modules = await self._registry.load_modules()
        mcp = self._mcp

        # Register workflow prompts
        for wf_key, wf_def in modules.workflows.items():
            prompt_name = f"vela_{wf_def.id}"

            def make_workflow_handler(wf: WorkflowDefinition):
                async def handler(ctx: Context) -> str:
                    parts = [f"# {wf.name}", ""]
                    if wf.description:
                        parts.append(wf.description)
                        parts.append("")

                    parts.append("## Steps")
                    for s in wf.steps:
                        name = s.name or s.id
                        parts.append(f"1. **{name}** ({s.type})")
                    parts.append("")

                    parts.append("## Next Action")
                    parts.append(
                        f'Call `vela_advance_workflow` with '
                        f'`workflow_id="{wf.id}"` to start this workflow.'
                    )
                    return "\n".join(parts)
                return handler

            mcp.prompt(
                name=prompt_name,
                description=f"{wf_def.name} — {wf_def.description}",
            )(make_workflow_handler(wf_def))

        # Register agent prompts
        for agent_id, agent_def in modules.agents.items():
            prompt_name = f"vela_agent_{agent_def.id}"

            def make_agent_handler(agent: AgentDefinition):
                async def handler() -> list[Message]:
                    parts = [f"# Agent: {agent.name}", ""]
                    if agent.persona:
                        parts.append("## Persona")
                        parts.append(agent.persona)
                        parts.append("")
                    if agent.workflows:
                        parts.append("## Available Workflows")
                        for wf_id in agent.workflows:
                            parts.append(f'- `vela_advance_workflow` with workflow_id="{wf_id}"')
                        parts.append("")
                    if agent.tools:
                        parts.append("## Available Tools")
                        for tool in agent.tools:
                            parts.append(f"- `{tool}`")
                        parts.append("")

                    messages = [Message(role="assistant", content="\n".join(parts))]
                    if agent.greeting:
                        messages.append(Message(role="user", content=agent.greeting))
                    return messages
                return handler

            mcp.prompt(
                name=prompt_name,
                description=f"Activate agent: {agent_def.name}",
            )(make_agent_handler(agent_def))

        logger.info(
            "module_hub.prompts_registered",
            workflows=len(modules.workflows),
            agents=len(modules.agents),
        )

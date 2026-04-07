"""Agent Module — Persona-based MCP prompts with workflow menus."""

from typing import Optional

import structlog
from fastmcp import FastMCP
from fastmcp.prompts.prompt import Message

from src.shared.config import VELA_AGENTS_DIR
from src.mcp.modules.base import VelaModuleBase
from src.shared.schemas.agent import AgentDefinition
from src.shared.services.filesystem_loader import load_from_filesystem
from src.shared.services.workflow_loader import load_agents

logger = structlog.get_logger()


class AgentModule(VelaModuleBase):
    """Manages agent personas as MCP prompts."""

    def __init__(self, mcp: FastMCP, module_registry=None):
        self._module_registry = module_registry
        self._filesystem_agents: dict[str, AgentDefinition] = {}
        self._load_filesystem_agents()
        self._register_prompts(mcp)
        self._register_tools(mcp)

    def _load_filesystem_agents(self):
        """Load agent definitions from filesystem (bundled + user)."""
        self._filesystem_agents = load_from_filesystem(load_agents, "agents", VELA_AGENTS_DIR)
        logger.info("agent_module.filesystem_loaded", count=len(self._filesystem_agents))

    async def _get_all_agents(self) -> dict[str, AgentDefinition]:
        """Get all agents from filesystem + registry (async, includes DB/local/github modules)."""
        merged: dict[str, AgentDefinition] = {}

        # 1. Registry modules (DB/local/github — lowest priority after bundled)
        if self._module_registry:
            try:
                registry_agents = await self._module_registry.get_agents()
                merged.update(registry_agents)
            except Exception as e:
                logger.warning("agent_module.registry_load_failed", error=str(e))

        # 2. Filesystem agents (bundled + user — highest priority, overrides registry)
        merged.update(self._filesystem_agents)

        return merged

    async def _get_filtered_agents(self) -> dict[str, AgentDefinition]:
        """Get agents filtered by runtime module filter (env var + header)."""
        from src.shared.services.module_filter import apply_runtime_filters
        return await apply_runtime_filters(await self._get_all_agents())

    def _register_prompts(self, mcp: FastMCP):
        """Register each agent as an MCP prompt."""
        for agent_id, agent_def in self._filesystem_agents.items():
            prompt_name = f"vela_agent_{agent_def.id}"
            description = f"Activate agent: {agent_def.name}"

            def make_prompt_handler(agent: AgentDefinition):
                async def handler() -> list[Message]:
                    parts = []

                    # Persona
                    parts.append(f"# Agent: {agent.name}")
                    parts.append("")
                    if agent.persona:
                        parts.append("## Persona")
                        parts.append(agent.persona)
                        parts.append("")

                    # Workflow menu
                    if agent.workflows:
                        parts.append("## Available Workflows")
                        for wf_id in agent.workflows:
                            parts.append(f"- `vela_advance_workflow` with workflow_id=\"{wf_id}\"")
                        parts.append("")

                    # Tools
                    if agent.tools:
                        parts.append("## Available Tools")
                        for tool in agent.tools:
                            parts.append(f"- `{tool}`")
                        parts.append("")

                    messages: list[Message] = []

                    # Persona + capabilities as assistant message
                    messages.append(Message(
                        role="assistant",
                        content="\n".join(parts),
                    ))

                    # Greeting as user message (instruction to respond)
                    if agent.greeting:
                        messages.append(Message(
                            role="user",
                            content=agent.greeting,
                        ))

                    return messages

                return handler

            mcp.prompt(name=prompt_name, description=description)(
                make_prompt_handler(agent_def)
            )

    def _register_tools(self, mcp: FastMCP):
        """Register agent listing tool."""

        @mcp.tool(
            name="vela_list_agents",
            description="List available agent personas.",
        )
        async def vela_list_agents() -> str:
            from src.mcp.modules.mcp_utils import to_json
            filtered = await self._get_filtered_agents()
            return to_json([
                {
                    "id": a.id,
                    "name": a.name,
                    "workflows": a.workflows,
                    "tools": a.tools,
                }
                for a in filtered.values()
            ])

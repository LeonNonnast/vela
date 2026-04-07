"""Workflow and agent YAML loader with semver parsing.

Workflow loading re-exports from vela_sdk.
Agent loading remains here (not part of the SDK).
"""

import os
from pathlib import Path
from typing import Optional

import structlog
import yaml

# Re-export workflow loader from SDK
from vela_sdk.loader.workflow_loader import (
    VERSION_PATTERN,
    load_workflow_file,
    load_workflows,
    parse_workflow_filename,
)

from src.shared.schemas.agent import AgentDefinition

logger = structlog.get_logger()


def load_agent_file(filepath: str) -> Optional[AgentDefinition]:
    """Load a single agent definition from a YAML file."""
    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            logger.warning("agent_loader.empty_file", path=filepath)
            return None

        if "id" not in data:
            data["id"] = Path(filepath).stem

        return AgentDefinition(**data)
    except Exception as e:
        logger.error("agent_loader.parse_error", path=filepath, error=str(e))
        return None


def load_agents(directory: str) -> dict[str, AgentDefinition]:
    """Load all agent definitions from a directory (recursive).

    Returns dict keyed by agent id.
    """
    agents: dict[str, AgentDefinition] = {}

    if not os.path.isdir(directory):
        logger.info("agent_loader.dir_not_found", directory=directory)
        return agents

    for root, _dirs, files in os.walk(directory):
        for filename in sorted(files):
            if not filename.endswith((".yaml", ".yml")):
                continue

            filepath = os.path.join(root, filename)
            agent = load_agent_file(filepath)
            if agent:
                agents[agent.id] = agent
                logger.info("agent_loader.loaded", id=agent.id, name=agent.name)

    return agents

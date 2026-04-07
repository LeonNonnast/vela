"""Connector configuration loader for external MCP servers."""

import os
from pathlib import Path
from typing import Any, Optional

import structlog
import yaml
from pydantic import BaseModel, Field

logger = structlog.get_logger()

CONNECTORS_PATH = os.path.expanduser("~/.vela/connectors.yaml")


class ConnectorConfig(BaseModel):
    """Configuration for an external MCP server connection."""
    id: str
    name: str
    transport: str = "stdio"
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None  # For HTTP transport


def load_connectors(path: Optional[str] = None) -> dict[str, ConnectorConfig]:
    """Load connector configurations from YAML file.

    Returns dict keyed by connector id.
    """
    filepath = path or CONNECTORS_PATH
    connectors: dict[str, ConnectorConfig] = {}

    if not os.path.isfile(filepath):
        logger.info("connectors.file_not_found", path=filepath)
        return connectors

    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)

        if not data or "connectors" not in data:
            return connectors

        for entry in data["connectors"]:
            # Resolve environment variable references in env
            resolved_env = {}
            for k, v in entry.get("env", {}).items():
                if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                    env_name = v[2:-1]
                    resolved_env[k] = os.getenv(env_name, "")
                else:
                    resolved_env[k] = v
            entry["env"] = resolved_env

            config = ConnectorConfig(**entry)
            connectors[config.id] = config
            logger.info("connectors.loaded", id=config.id, name=config.name)

    except Exception as e:
        logger.error("connectors.load_error", path=filepath, error=str(e))

    return connectors

"""Resource definition YAML loader."""

import os
from pathlib import Path
from typing import Optional

import structlog
import yaml

from src.shared.schemas.resource import ResourceDefinition

logger = structlog.get_logger()


def load_resource_file(filepath: str) -> Optional[ResourceDefinition]:
    """Load a single resource definition from a YAML file."""
    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            logger.warning("resource_loader.empty_file", path=filepath)
            return None

        if "id" not in data:
            data["id"] = Path(filepath).stem

        return ResourceDefinition(**data)
    except Exception as e:
        logger.error("resource_loader.parse_error", path=filepath, error=str(e))
        return None


def load_resources(directory: str) -> dict[str, ResourceDefinition]:
    """Load all resource definitions from a directory.

    Returns dict keyed by resource id.
    """
    resources: dict[str, ResourceDefinition] = {}

    if not os.path.isdir(directory):
        logger.info("resource_loader.dir_not_found", directory=directory)
        return resources

    for filename in sorted(os.listdir(directory)):
        if not filename.endswith((".yaml", ".yml")):
            continue

        filepath = os.path.join(directory, filename)
        resource = load_resource_file(filepath)
        if resource:
            resources[resource.id] = resource
            logger.info("resource_loader.loaded", id=resource.id, name=resource.name)

    return resources

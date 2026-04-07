"""Workflow YAML loader with semver parsing."""

import os
import re
from pathlib import Path
from typing import Optional

import structlog
import yaml

from vela_sdk.schemas.workflow import WorkflowDefinition

logger = structlog.get_logger()

# Pattern: filename@version.yaml (e.g., feature-planning@1.0.0.yaml)
VERSION_PATTERN = re.compile(r"^(.+?)@(\d+\.\d+\.\d+)\.ya?ml$")


def parse_workflow_filename(filename: str) -> tuple[str, str]:
    """Parse workflow filename into (id, version).

    Supports:
    - feature-planning@1.0.0.yaml -> ("feature-planning", "1.0.0")
    - simple-workflow.yaml -> ("simple-workflow", "1.0.0")
    """
    match = VERSION_PATTERN.match(filename)
    if match:
        return match.group(1), match.group(2)
    # No version in filename — default to 1.0.0
    stem = Path(filename).stem
    return stem, "1.0.0"


def load_workflow_file(filepath: str) -> Optional[WorkflowDefinition]:
    """Load a single workflow definition from a YAML file."""
    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            logger.warning("workflow_loader.empty_file", path=filepath)
            return None

        filename = os.path.basename(filepath)
        file_id, file_version = parse_workflow_filename(filename)

        # Use file-derived id/version as defaults
        if "id" not in data:
            data["id"] = file_id
        if "version" not in data:
            data["version"] = file_version

        return WorkflowDefinition(**data)
    except Exception as e:
        logger.error("workflow_loader.parse_error", path=filepath, error=str(e))
        return None


def load_workflows(directory: str) -> dict[str, WorkflowDefinition]:
    """Load all workflow definitions from a directory (recursive).

    Returns dict keyed by "{id}@{version}".
    """
    workflows: dict[str, WorkflowDefinition] = {}

    if not os.path.isdir(directory):
        logger.info("workflow_loader.dir_not_found", directory=directory)
        return workflows

    for root, _dirs, files in os.walk(directory):
        for filename in sorted(files):
            if not filename.endswith((".yaml", ".yml")):
                continue

            filepath = os.path.join(root, filename)
            wf = load_workflow_file(filepath)
            if wf:
                key = f"{wf.id}@{wf.version}"
                workflows[key] = wf
                logger.info("workflow_loader.loaded", key=key, name=wf.name)

    return workflows

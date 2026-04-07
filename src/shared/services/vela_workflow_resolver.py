"""VelaWorkflowResolver — WorkflowResolver backed by filesystem + module registry.

Replicates the loading logic from WorkflowModule (filesystem + registry merge)
but packaged as a standalone class that satisfies the vela-sdk WorkflowResolver
protocol.  This lets VelaWorkflows (SDK) resolve workflows from all Vela sources
without coupling to the WorkflowModule itself.
"""

from typing import Optional

import structlog

from vela_sdk.schemas.workflow import WorkflowDefinition

from src.shared.config import VELA_WORKFLOWS_DIR
from src.shared.services.filesystem_loader import load_from_filesystem
from vela_sdk.loader.workflow_loader import load_workflows

logger = structlog.get_logger()


class VelaWorkflowResolver:
    """Resolves workflows from filesystem + module registry (+ optional runtime filters).

    Satisfies ``vela_sdk.fastmcp.protocols.WorkflowResolver``.

    Priority (lowest to highest):
      1. Registry modules (DB / local / github)
      2. Filesystem workflows (bundled modules + user directory)
    """

    def __init__(
        self,
        session_factory=None,
        module_registry=None,
        *,
        workflows_dir: Optional[str] = None,
        apply_filters: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self._module_registry = module_registry
        self._apply_filters = apply_filters

        # Eagerly load filesystem workflows (same as WorkflowModule.__init__)
        self._filesystem_workflows: dict[str, WorkflowDefinition] = load_from_filesystem(
            load_workflows,
            "workflows",
            workflows_dir or VELA_WORKFLOWS_DIR,
        )
        logger.info(
            "vela_workflow_resolver.filesystem_loaded",
            count=len(self._filesystem_workflows),
        )

    # ------------------------------------------------------------------
    # WorkflowResolver protocol
    # ------------------------------------------------------------------

    async def get_workflow(
        self, workflow_id: str, version: Optional[str] = None
    ) -> Optional[WorkflowDefinition]:
        """Get workflow by ID from all sources (filesystem + registry)."""
        all_workflows = await self._get_all_workflows()
        if version:
            key = f"{workflow_id}@{version}"
            return all_workflows.get(key)
        matches = [
            (k, wf) for k, wf in all_workflows.items()
            if wf.id == workflow_id
        ]
        if not matches:
            return None
        matches.sort(key=lambda x: x[1].version, reverse=True)
        return matches[0][1]

    async def list_workflows(self) -> dict[str, WorkflowDefinition]:
        """Return all merged workflows, optionally filtered by runtime filters."""
        workflows = await self._get_all_workflows()
        if self._apply_filters:
            from src.shared.services.module_filter import apply_runtime_filters
            workflows = await apply_runtime_filters(workflows)
        return workflows

    # ------------------------------------------------------------------
    # Internal helpers (mirrors WorkflowModule._get_all_workflows)
    # ------------------------------------------------------------------

    async def _get_all_workflows(self) -> dict[str, WorkflowDefinition]:
        """Merge workflows from registry (lowest prio) + filesystem (highest prio)."""
        merged: dict[str, WorkflowDefinition] = {}

        # 1. Registry modules (DB / local / github)
        if self._module_registry:
            try:
                registry_workflows = await self._module_registry.get_workflows()
                merged.update(registry_workflows)
            except Exception as e:
                logger.warning("vela_workflow_resolver.registry_load_failed", error=str(e))

        # 2. Filesystem workflows (bundled + user — highest priority)
        merged.update(self._filesystem_workflows)

        return merged

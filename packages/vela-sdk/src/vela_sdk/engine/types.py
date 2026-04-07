"""Core types for the workflow engine."""

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


class WorkflowRunStatus(str, enum.Enum):
    """Workflow run lifecycle status."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowRunState:
    """Framework-agnostic representation of a workflow run.

    The engine works with this dataclass instead of ORM objects.
    Storage implementations convert between their native format and this type.
    """
    id: str
    workflow_id: str
    workflow_version: str
    current_step: Optional[str] = None
    status: WorkflowRunStatus = WorkflowRunStatus.ACTIVE
    params: dict[str, Any] = field(default_factory=dict)
    state_data: dict[str, Any] = field(default_factory=dict)
    project_id: Optional[str] = None
    parent_run_id: Optional[str] = None
    parent_step_id: Optional[str] = None
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class AdvanceResult:
    """Result of advancing a workflow."""
    run: WorkflowRunState
    prompt: Optional[str] = None
    completed: bool = False
    sub_workflow_ref: Optional[str] = None
    sub_workflow_params: Optional[dict] = None


@dataclass
class ErrorAction:
    """Result of error handling."""
    action: str  # retry | fallback | abort
    fallback_step: Optional[str] = None
    message: Optional[str] = None

"""Pydantic input schemas for LangChain workflow tools."""

from typing import Optional

from pydantic import BaseModel, Field


class WorkflowAdvanceInput(BaseModel):
    """Input schema for the workflow advance tool."""

    workflow_id: Optional[str] = Field(
        None,
        description="Workflow definition ID to start/resume. Required if run_id is not provided.",
    )
    run_id: Optional[str] = Field(
        None,
        description="Run ID of an active workflow to advance. Required if workflow_id is not provided.",
    )
    step_id: Optional[str] = Field(
        None,
        description="Current step ID for validation (optional safety check).",
    )
    output: Optional[str] = Field(
        None,
        description="Output/result from the current step. JSON string for structured captures, plain string otherwise.",
    )
    params: Optional[str] = Field(
        None,
        description="JSON string of workflow parameters (for starting a new workflow).",
    )
    project_id: Optional[str] = Field(
        None,
        description="Project ID to scope the workflow run.",
    )
    notes: Optional[str] = Field(
        None,
        description="Optional notes to attach to the current step.",
    )


class WorkflowStatusInput(BaseModel):
    """Input schema for the workflow status tool."""

    run_id: str = Field(
        ...,
        description="The workflow run ID to check status for.",
    )


class WorkflowListInput(BaseModel):
    """Input schema for the workflow list tool."""

    project_id: Optional[str] = Field(
        None,
        description="Filter by project ID.",
    )

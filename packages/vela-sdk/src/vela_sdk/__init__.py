"""Vela SDK — Workflow engine for FastMCP servers.

Usage::

    from fastmcp import FastMCP
    from vela_sdk import VelaWorkflows

    mcp = FastMCP("my-server")
    workflows = VelaWorkflows(mcp, workflows_dir="./workflows/")
"""

from vela_sdk.engine.types import AdvanceResult, WorkflowRunState, WorkflowRunStatus
from vela_sdk.engine.workflow_engine import WorkflowEngine
from vela_sdk.fastmcp.locale import Locale, get_locale
from vela_sdk.schemas.workflow import (
    AnyStepDefinition,
    BaseStepDefinition,
    CaptureDefinition,
    ChoiceStep,
    ConfirmStep,
    DialogStep,
    ExecuteStep,
    FreeformStep,
    McpCallStep,
    StepDefinition,
    StepType,
    WorkflowDefinition,
    WorkflowStep,
)
from vela_sdk.storage.protocol import WorkflowStore

# FastMCP integration (lazy import to avoid hard dep)
try:
    from vela_sdk.fastmcp.integration import VelaWorkflows
except ImportError:
    VelaWorkflows = None  # type: ignore[assignment,misc]

# LangChain integration (lazy import to avoid hard dep)
try:
    from vela_sdk.langchain import VelaToolkit
except ImportError:
    VelaToolkit = None  # type: ignore[assignment,misc]

# Azure AI Agents integration (lazy import to avoid hard dep)
try:
    from vela_sdk.azure_agents import VelaToolset
except ImportError:
    VelaToolset = None  # type: ignore[assignment,misc]

__all__ = [
    "AdvanceResult",
    "AnyStepDefinition",
    "BaseStepDefinition",
    "CaptureDefinition",
    "ChoiceStep",
    "ConfirmStep",
    "DialogStep",
    "ExecuteStep",
    "FreeformStep",
    "Locale",
    "McpCallStep",
    "StepDefinition",
    "StepType",
    "VelaToolkit",
    "VelaToolset",
    "VelaWorkflows",
    "WorkflowDefinition",
    "WorkflowEngine",
    "WorkflowRunState",
    "WorkflowRunStatus",
    "WorkflowStep",
    "WorkflowStore",
    "get_locale",
]

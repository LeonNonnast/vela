"""Pydantic models for workflow definitions.

Schema version: 0.3.0 — type-safe discriminated unions for step types
"""

from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Discriminator, Field, Tag, TypeAdapter

from vela_sdk.schemas.resource import ResourceReference


class StepType(str, Enum):
    """Supported step types."""
    CHOICE = "choice"
    FREEFORM = "freeform"
    EXECUTE = "execute"
    CONFIRM = "confirm"
    WORKFLOW = "workflow"
    MCP_CALL = "mcp_call"
    DIALOG = "dialog"


class DialogPhaseDefinition(BaseModel):
    """A single phase within a dialog step."""
    id: str
    name: Optional[str] = None
    guideline: str


class ChoiceOption(BaseModel):
    """A selectable option within a choice step."""
    key: str
    label: str
    description: Optional[str] = None
    next: Optional[str] = None


class CaptureOption(BaseModel):
    """A selectable option for select/multi-select elicitation."""
    key: str
    label: str


class CaptureDefinition(BaseModel):
    """Defines what data a step captures AND how to collect/validate it.

    Flow: prompt -> user interaction -> workflow_advance(step_output)
          -> capture validation -> ctx.elicit() for missing/structured -> save

    The `input` field controls the elicitation UI type used during
    the tool call when the engine validates and collects data via ctx.elicit().
    """
    key: str
    label: Optional[str] = None
    type: str = "string"  # string | boolean | date | number
    required: bool = False
    source: str = "output"  # output | param

    # Elicitation strategy
    input: Optional[str] = None  # text | number | boolean | select | multi-select | confirm
    options: list[CaptureOption] = Field(default_factory=list)
    suggest: bool = False
    placeholder: Optional[str] = None
    default: Optional[Any] = None
    elicit: str = "if_missing"  # always | if_missing | never


class DependsOnDefinition(BaseModel):
    """Declares which data from a previous step this step needs."""
    step: str
    fields: list[str]


class FetchDefinition(BaseModel):
    """Defines server-side data retrieval before step execution.

    The server acts as MCP client, calls mounted servers, and injects
    results into the step prompt via {{fetch.key}}.
    """
    key: str  # state key to store result
    source: str  # mounted MCP server namespace (e.g. "devops")
    action: str  # tool name on the mounted server
    params: dict[str, Any] = Field(default_factory=dict)


class OnErrorDefinition(BaseModel):
    """Error handling strategy for a step."""
    retry: int = 0
    fallback: Optional[str] = None  # step ID to jump to
    abort: bool = False
    message: Optional[str] = None


class BaseStepDefinition(BaseModel):
    """Shared fields across all step types."""
    id: str
    name: Optional[str] = None
    prompt: str = ""

    # Context dependencies (Principle of Least Context)
    depends_on: list[DependsOnDefinition] = Field(default_factory=list)
    fetch: list[FetchDefinition] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)

    # Structured output
    capture: list[CaptureDefinition] = Field(default_factory=list)

    # Navigation
    next: Optional[str] = None
    notes: bool = True

    # Error handling
    on_error: Optional[OnErrorDefinition] = None

    # Resources
    resources: list[ResourceReference] = Field(default_factory=list)


class FreeformStep(BaseStepDefinition):
    """A freeform text input step."""
    type: Literal["freeform"] = "freeform"


class ChoiceStep(BaseStepDefinition):
    """A step with selectable options."""
    type: Literal["choice"] = "choice"
    options: list[ChoiceOption] = Field(default_factory=list)


class ConfirmStep(BaseStepDefinition):
    """A yes/no confirmation step."""
    type: Literal["confirm"] = "confirm"


class ExecuteStep(BaseStepDefinition):
    """A step where the agent performs a task."""
    type: Literal["execute"] = "execute"
    instructions: Optional[str] = None
    delegate: Optional[str] = None  # "subagent"


class DialogStep(BaseStepDefinition):
    """A multi-phase conversation step."""
    type: Literal["dialog"] = "dialog"
    mode: Optional[str] = None  # brainstorming | requirements | planning | review | freeform
    goal: Optional[str] = None
    guidelines: list[str] = Field(default_factory=list)
    phases: list[DialogPhaseDefinition] = Field(default_factory=list)


class WorkflowStep(BaseStepDefinition):
    """A step that delegates to a sub-workflow."""
    type: Literal["workflow"] = "workflow"
    workflow_ref: Optional[str] = None
    params_mapping: dict[str, str] = Field(default_factory=dict)


class McpCallStep(BaseStepDefinition):
    """A step that makes a server-side MCP tool call."""
    type: Literal["mcp_call"] = "mcp_call"
    mcp_tool: Optional[str] = None
    mcp_source: Optional[str] = None
    mcp_params: dict[str, Any] = Field(default_factory=dict)


AnyStepDefinition = Annotated[
    Union[
        Annotated[FreeformStep, Tag("freeform")],
        Annotated[ChoiceStep, Tag("choice")],
        Annotated[ConfirmStep, Tag("confirm")],
        Annotated[ExecuteStep, Tag("execute")],
        Annotated[DialogStep, Tag("dialog")],
        Annotated[WorkflowStep, Tag("workflow")],
        Annotated[McpCallStep, Tag("mcp_call")],
    ],
    Discriminator("type"),
]

_step_adapter: TypeAdapter[AnyStepDefinition] = TypeAdapter(AnyStepDefinition)


def StepDefinition(**kwargs: Any) -> AnyStepDefinition:
    """Create a type-safe step definition.

    Accepts the same kwargs as the old monolithic StepDefinition.
    Dispatches to the correct subclass based on the ``type`` field.

    Example::

        step = StepDefinition(id="s1", type="freeform", prompt="Hello")
        assert isinstance(step, FreeformStep)

    Also accepts ``StepType`` enum values::

        step = StepDefinition(id="s1", type=StepType.CHOICE, options=[...])
        assert isinstance(step, ChoiceStep)
    """
    # Normalise StepType enum → plain string for the discriminator
    if "type" in kwargs and isinstance(kwargs["type"], StepType):
        kwargs["type"] = kwargs["type"].value
    return _step_adapter.validate_python(kwargs)


class ToolRequirement(BaseModel):
    """An external MCP tool required by this workflow."""
    name: str
    server: Optional[str] = None
    description: Optional[str] = None
    required: bool = True


class ParamDefinition(BaseModel):
    """Workflow parameter definition."""
    name: str
    label: Optional[str] = None
    description: Optional[str] = None
    required: bool = False
    default: Optional[Any] = None
    identity: bool = False
    application: bool = False
    resolve: bool = False


class ContextAutoDefinition(BaseModel):
    """Auto-context configuration."""
    auto: list[str] = Field(default_factory=list)


class LifecycleDefinition(BaseModel):
    """Workflow lifecycle configuration."""
    auto_archive_after: Optional[str] = None  # e.g. "30d"
    auto_cancel_after: Optional[str] = None  # e.g. "90d"
    allow_pause: bool = True


class WorkflowDefinition(BaseModel):
    """Complete workflow definition loaded from YAML."""
    id: str
    version: str = "1.0.0"
    name: str
    description: str = ""
    params: list[ParamDefinition] = Field(default_factory=list)
    context: Optional[ContextAutoDefinition] = None
    lifecycle: Optional[LifecycleDefinition] = None
    tools: list[ToolRequirement] = Field(default_factory=list)
    resources: list[ResourceReference] = Field(default_factory=list)
    steps: list[AnyStepDefinition] = Field(default_factory=list)

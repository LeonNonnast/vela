"""Shared test fixtures for vela-sdk tests."""

import pytest

from vela_sdk.engine.workflow_engine import WorkflowEngine
from vela_sdk.schemas.workflow import (
    CaptureDefinition,
    ChoiceOption,
    DependsOnDefinition,
    ParamDefinition,
    StepDefinition,
    StepType,
    WorkflowDefinition,
)
from vela_sdk.storage.memory import InMemoryStore


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def engine(store):
    return WorkflowEngine(store)


@pytest.fixture
def simple_workflow():
    """A minimal 2-step workflow for basic tests."""
    return WorkflowDefinition(
        id="test-wf",
        version="1.0.0",
        name="Test Workflow",
        steps=[
            StepDefinition(
                id="step1",
                name="First Step",
                type=StepType.FREEFORM,
                prompt="Enter something",
                capture=[
                    CaptureDefinition(key="input1", elicit="never"),
                ],
            ),
            StepDefinition(
                id="step2",
                name="Second Step",
                type=StepType.CONFIRM,
                prompt="Confirm: {{state.input1}}",
            ),
        ],
    )


@pytest.fixture
def choice_workflow():
    """A workflow with a choice step that branches."""
    return WorkflowDefinition(
        id="choice-wf",
        version="1.0.0",
        name="Choice Workflow",
        steps=[
            StepDefinition(
                id="choose",
                name="Choose Path",
                type=StepType.CHOICE,
                prompt="Pick one",
                options=[
                    ChoiceOption(key="a", label="Option A", next="path_a"),
                    ChoiceOption(key="b", label="Option B", next="path_b"),
                ],
            ),
            StepDefinition(
                id="path_a",
                name="Path A",
                type=StepType.EXECUTE,
                prompt="Do A",
            ),
            StepDefinition(
                id="path_b",
                name="Path B",
                type=StepType.EXECUTE,
                prompt="Do B",
            ),
        ],
    )


@pytest.fixture
def parameterized_workflow():
    """A workflow with identity params for resume behavior."""
    return WorkflowDefinition(
        id="param-wf",
        version="1.0.0",
        name="Parameterized Workflow",
        params=[
            ParamDefinition(name="project", required=True, identity=True),
            ParamDefinition(name="mode", default="standard"),
        ],
        steps=[
            StepDefinition(
                id="step1",
                name="Step 1",
                type=StepType.FREEFORM,
                prompt="Working on {{params.project}} in {{params.mode}} mode",
            ),
        ],
    )


@pytest.fixture
def depends_on_workflow():
    """A workflow where step2 depends on step1 captures."""
    return WorkflowDefinition(
        id="depends-wf",
        version="1.0.0",
        name="DependsOn Workflow",
        steps=[
            StepDefinition(
                id="step1",
                name="Gather",
                type=StepType.FREEFORM,
                prompt="Provide input",
                capture=[
                    CaptureDefinition(key="gathered", elicit="never"),
                ],
            ),
            StepDefinition(
                id="step2",
                name="Use",
                type=StepType.EXECUTE,
                prompt="Use: {{state.gathered}}",
                depends_on=[
                    DependsOnDefinition(step="step1", fields=["gathered"]),
                ],
            ),
        ],
    )

"""Workflow Engine Tests -- state machine, routing, templates."""

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.shared.db.base import Base
from vela_sdk.engine.types import WorkflowRunState, WorkflowRunStatus
from src.shared.repositories.workflow_repository import WorkflowRepository
from src.shared.schemas.workflow import (
    ChoiceOption,
    CaptureDefinition,
    DependsOnDefinition,
    DialogPhaseDefinition,
    LifecycleDefinition,
    OnErrorDefinition,
    ParamDefinition,
    StepDefinition,
    StepType,
    WorkflowDefinition,
)
from vela_sdk.engine.workflow_engine import DIALOG_MODES, WorkflowEngine
from vela_sdk.engine.types import AdvanceResult, ErrorAction
from src.shared.services.workflow_store_adapter import VelaWorkflowStore


def _make_simple_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="test-wf",
        version="1.0.0",
        name="Test Workflow",
        steps=[
            StepDefinition(id="step-1", type=StepType.FREEFORM, prompt="First step"),
            StepDefinition(id="step-2", type=StepType.FREEFORM, prompt="Second step"),
            StepDefinition(id="step-3", type=StepType.CONFIRM, prompt="Confirm?"),
        ],
    )


def _make_choice_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="choice-wf",
        version="1.0.0",
        name="Choice Workflow",
        steps=[
            StepDefinition(
                id="pick",
                type=StepType.CHOICE,
                prompt="Pick one",
                options=[
                    ChoiceOption(key="a", label="Option A", next="step-a"),
                    ChoiceOption(key="b", label="Option B", next="step-b"),
                ],
            ),
            StepDefinition(id="step-a", type=StepType.FREEFORM, prompt="You chose A"),
            StepDefinition(id="step-b", type=StepType.FREEFORM, prompt="You chose B"),
        ],
    )


def _make_capture_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="capture-wf",
        version="1.0.0",
        name="Capture Workflow",
        steps=[
            StepDefinition(
                id="gather",
                type=StepType.FREEFORM,
                prompt="Tell me about {{feature_name}}",
                capture=[CaptureDefinition(key="requirements", source="output")],
                next="review",
            ),
            StepDefinition(
                id="review",
                type=StepType.CONFIRM,
                prompt="Requirements: {{state.requirements}}",
                depends_on=[
                    DependsOnDefinition(step="gather", fields=["requirements"]),
                ],
            ),
        ],
        params=[
            ParamDefinition(name="feature_name", required=True, identity=True),
        ],
    )


@pytest_asyncio.fixture
async def wf_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        repo = WorkflowRepository(session)
        store = VelaWorkflowStore(repo, session)
        wf_eng = WorkflowEngine(store)
        yield wf_eng, session
    await engine.dispose()


class TestWorkflowEngineStartOrResume:
    async def test_start_new_run(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_simple_workflow()

        run, is_new = await engine.start_or_resume(wf_def)
        await session.commit()

        assert is_new is True
        assert run.workflow_id == "test-wf"
        assert run.current_step == "step-1"
        assert run.status == WorkflowRunStatus.ACTIVE

    async def test_resume_by_identity(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_capture_workflow()

        run1, is_new1 = await engine.start_or_resume(
            wf_def, params={"feature_name": "auth"}
        )
        await session.commit()
        assert is_new1 is True

        run2, is_new2 = await engine.start_or_resume(
            wf_def, params={"feature_name": "auth"}
        )
        assert is_new2 is False
        assert run2.id == run1.id

    async def test_different_identity_creates_new(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_capture_workflow()

        run1, _ = await engine.start_or_resume(
            wf_def, params={"feature_name": "auth"}
        )
        await session.commit()

        run2, is_new = await engine.start_or_resume(
            wf_def, params={"feature_name": "billing"}
        )
        await session.commit()

        assert is_new is True
        assert run2.id != run1.id

    async def test_default_params(self, wf_engine):
        engine, session = wf_engine
        wf_def = WorkflowDefinition(
            id="default-wf",
            name="Defaults",
            params=[ParamDefinition(name="scope", default="mvp")],
            steps=[StepDefinition(id="s1", type=StepType.FREEFORM, prompt="go")],
        )

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        assert run.params["scope"] == "mvp"


class TestWorkflowEngineAdvance:
    async def test_advance_sequential(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_simple_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        result = await engine.advance(run, wf_def, step_output="step 1 done")
        await session.commit()

        assert result.completed is False
        assert result.run.current_step == "step-2"
        assert result.prompt is not None

    async def test_advance_to_completion(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_simple_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        r1 = await engine.advance(run, wf_def, step_output="s1")
        await session.commit()
        r2 = await engine.advance(r1.run, wf_def, step_output="s2")
        await session.commit()
        result = await engine.advance(r2.run, wf_def, step_output="confirmed")
        await session.commit()

        assert result.completed is True
        assert result.run.status == WorkflowRunStatus.COMPLETED

    async def test_advance_choice_routing(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_choice_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        result = await engine.advance(run, wf_def, step_output="b")
        await session.commit()

        assert result.run.current_step == "step-b"

    async def test_advance_captures_output(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_capture_workflow()

        run, _ = await engine.start_or_resume(
            wf_def, params={"feature_name": "auth"}
        )
        await session.commit()

        result = await engine.advance(
            run, wf_def, step_output="Need OAuth2 and API keys"
        )
        await session.commit()

        assert result.run.state_data["requirements"] == "Need OAuth2 and API keys"

    async def test_advance_completed_run_noop(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_simple_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        # Mark as completed via store
        run = WorkflowRunState(
            id=run.id, workflow_id=run.workflow_id,
            workflow_version=run.workflow_version,
            status=WorkflowRunStatus.COMPLETED,
            current_step=run.current_step,
            params=run.params, state_data=run.state_data,
        )

        result = await engine.advance(run, wf_def, step_output="x")
        assert result.completed is True


class TestWorkflowEnginePrompt:
    async def test_assemble_prompt_basic(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_simple_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        step = wf_def.steps[0]
        prompt = engine.assemble_prompt(wf_def, run, step)
        assert "Test Workflow" in prompt
        assert "step-1" in prompt
        assert "First step" in prompt

    async def test_assemble_prompt_with_depends_on(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_capture_workflow()

        run, _ = await engine.start_or_resume(
            wf_def, params={"feature_name": "auth"}
        )
        await session.commit()

        # Advance to set requirements in state
        result = await engine.advance(run, wf_def, step_output="Need OAuth2")
        await session.commit()

        step = wf_def.steps[1]  # review step
        prompt = engine.assemble_prompt(wf_def, result.run, step)
        assert "requirements" in prompt
        assert "Need OAuth2" in prompt

    async def test_resolve_templates(self, wf_engine):
        engine, _ = wf_engine
        result = engine.resolve_templates(
            "Feature: {{feature_name}}, Scope: {{state.scope}}",
            {"feature_name": "auth", "state": {"scope": "mvp"}},
        )
        assert result == "Feature: auth, Scope: mvp"

    async def test_resolve_templates_missing(self, wf_engine):
        engine, _ = wf_engine
        result = engine.resolve_templates("{{missing}}", {})
        assert result == "{{missing}}"


class TestWorkflowEngineValidation:
    async def test_validate_depends_on_met(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_capture_workflow()

        run, _ = await engine.start_or_resume(
            wf_def, params={"feature_name": "x"}
        )
        await session.commit()

        result = await engine.advance(run, wf_def, step_output="requirements data")
        await session.commit()

        step = wf_def.steps[1]
        valid, missing = engine.validate_depends_on(result.run, step)
        assert valid is True
        assert missing == []

    async def test_validate_depends_on_missing(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_capture_workflow()

        run, _ = await engine.start_or_resume(
            wf_def, params={"feature_name": "x"}
        )
        await session.commit()

        step = wf_def.steps[1]
        valid, missing = engine.validate_depends_on(run, step)
        assert valid is False
        assert "requirements" in missing

    async def test_handle_on_error_abort(self, wf_engine):
        engine, _ = wf_engine
        run = WorkflowRunState(id="r", workflow_id="test", workflow_version="1.0.0")
        step = StepDefinition(id="s1", type=StepType.EXECUTE, prompt="x")
        action = engine.handle_on_error(run, step, "boom")
        assert action.action == "abort"

    async def test_handle_on_error_retry(self, wf_engine):
        engine, _ = wf_engine
        run = WorkflowRunState(id="r", workflow_id="test", workflow_version="1.0.0")
        step = StepDefinition(
            id="s1", type=StepType.EXECUTE, prompt="x",
            on_error=OnErrorDefinition(retry=3),
        )
        action = engine.handle_on_error(run, step, "boom")
        assert action.action == "retry"

    async def test_handle_on_error_fallback(self, wf_engine):
        engine, _ = wf_engine
        run = WorkflowRunState(id="r", workflow_id="test", workflow_version="1.0.0")
        step = StepDefinition(
            id="s1", type=StepType.EXECUTE, prompt="x",
            on_error=OnErrorDefinition(fallback="recovery"),
        )
        action = engine.handle_on_error(run, step, "boom")
        assert action.action == "fallback"
        assert action.fallback_step == "recovery"


class TestWorkflowLifecycle:
    async def test_check_lifecycle_no_config(self, wf_engine):
        engine, _ = wf_engine
        run = WorkflowRunState(id="r", workflow_id="test", workflow_version="1.0.0")
        result = engine.check_lifecycle(run, None)
        assert result is None

    async def test_check_lifecycle_auto_cancel(self, wf_engine):
        engine, _ = wf_engine
        from datetime import datetime, timezone, timedelta

        run = WorkflowRunState(
            id="r", workflow_id="test", workflow_version="1.0.0",
            status=WorkflowRunStatus.ACTIVE,
            updated_at=datetime.now(timezone.utc) - timedelta(hours=50),
        )

        lifecycle = LifecycleDefinition(auto_cancel_after="48h")
        result = engine.check_lifecycle(run, lifecycle)
        assert result == WorkflowRunStatus.CANCELLED

    async def test_check_lifecycle_not_expired(self, wf_engine):
        engine, _ = wf_engine
        from datetime import datetime, timezone

        run = WorkflowRunState(
            id="r", workflow_id="test", workflow_version="1.0.0",
            status=WorkflowRunStatus.ACTIVE,
            updated_at=datetime.now(timezone.utc),
        )

        lifecycle = LifecycleDefinition(auto_cancel_after="48h")
        result = engine.check_lifecycle(run, lifecycle)
        assert result is None


class TestParseStepOutput:
    def test_json_dict_extracts_per_key(self):
        caps = [
            CaptureDefinition(key="name", source="output"),
            CaptureDefinition(key="scope", source="output"),
        ]
        output = '{"name": "Auth", "scope": "mvp"}'
        result = WorkflowEngine._parse_step_output(output, caps)
        assert result == {"name": "Auth", "scope": "mvp"}

    def test_json_dict_missing_key_falls_back_to_whole_output(self):
        caps = [
            CaptureDefinition(key="name", source="output"),
            CaptureDefinition(key="missing", source="output"),
        ]
        output = '{"name": "Auth"}'
        result = WorkflowEngine._parse_step_output(output, caps)
        assert result["name"] == "Auth"
        assert result["missing"] == output

    def test_plain_string_single_capture(self):
        caps = [CaptureDefinition(key="desc", source="output")]
        result = WorkflowEngine._parse_step_output("hello world", caps)
        assert result == {"desc": "hello world"}

    def test_plain_string_multi_capture(self):
        caps = [
            CaptureDefinition(key="a", source="output"),
            CaptureDefinition(key="b", source="output"),
        ]
        result = WorkflowEngine._parse_step_output("hello", caps)
        assert result == {"a": "hello", "b": "hello"}

    def test_none_output(self):
        caps = [CaptureDefinition(key="x", source="output")]
        result = WorkflowEngine._parse_step_output(None, caps)
        assert result == {}

    def test_empty_captures(self):
        result = WorkflowEngine._parse_step_output("hello", [])
        assert result == {}


# ---------------------------------------------------------------------------
# Dialog step tests
# ---------------------------------------------------------------------------
def _make_dialog_workflow(mode: str = "brainstorming") -> WorkflowDefinition:
    return WorkflowDefinition(
        id="dialog-wf",
        version="1.0.0",
        name="Dialog Workflow",
        steps=[
            StepDefinition(
                id="dialog-step",
                type=StepType.DIALOG,
                prompt="Let's brainstorm",
                mode=mode,
                goal="Generate ideas",
                guidelines=["Be creative", "No judgment"],
            ),
            StepDefinition(id="final", type=StepType.CONFIRM, prompt="Done?"),
        ],
    )


def _make_dialog_workflow_with_phases() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="dialog-phases-wf",
        version="1.0.0",
        name="Dialog Phases Workflow",
        steps=[
            StepDefinition(
                id="dialog-step",
                type=StepType.DIALOG,
                prompt="Custom dialog",
                phases=[
                    DialogPhaseDefinition(id="p1", name="Phase 1", guideline="Do first thing"),
                    DialogPhaseDefinition(id="p2", name="Phase 2", guideline="Do second thing"),
                ],
                goal="Custom goal",
            ),
            StepDefinition(id="final", type=StepType.CONFIRM, prompt="Done?"),
        ],
    )


def _make_dialog_workflow_with_captures() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="dialog-cap-wf",
        version="1.0.0",
        name="Dialog Captures Workflow",
        steps=[
            StepDefinition(
                id="dialog-step",
                type=StepType.DIALOG,
                prompt="Dialog with captures",
                mode="review",
                goal="Review something",
                capture=[CaptureDefinition(key="result", source="output")],
            ),
            StepDefinition(
                id="final",
                type=StepType.CONFIRM,
                prompt="Result: {{state.result}}",
                depends_on=[DependsOnDefinition(step="dialog-step", fields=["result"])],
            ),
        ],
    )


def _make_freeform_dialog_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="freeform-dialog-wf",
        version="1.0.0",
        name="Freeform Dialog",
        steps=[
            StepDefinition(
                id="dialog-step",
                type=StepType.DIALOG,
                prompt="Free dialog",
                mode="freeform",
                goal="Open-ended discussion",
            ),
            StepDefinition(id="final", type=StepType.CONFIRM, prompt="Done?"),
        ],
    )


class TestDialogModeResolution:
    def test_mode_resolves_to_phases(self):
        step = StepDefinition(id="d", type=StepType.DIALOG, mode="brainstorming")
        phases = WorkflowEngine._get_dialog_phases(step)
        assert len(phases) == 3
        assert phases[0].id == "diverge"
        assert phases[1].id == "converge"
        assert phases[2].id == "synthesize"

    def test_explicit_phases_override_mode(self):
        custom_phases = [
            DialogPhaseDefinition(id="x", guideline="Custom"),
        ]
        step = StepDefinition(
            id="d", type=StepType.DIALOG, mode="brainstorming",
            phases=custom_phases,
        )
        phases = WorkflowEngine._get_dialog_phases(step)
        assert len(phases) == 1
        assert phases[0].id == "x"

    def test_freeform_mode_no_phases(self):
        step = StepDefinition(id="d", type=StepType.DIALOG, mode="freeform")
        phases = WorkflowEngine._get_dialog_phases(step)
        assert phases == []

    def test_all_modes_exist(self):
        for mode in ("brainstorming", "requirements", "planning", "review", "freeform"):
            assert mode in DIALOG_MODES

    def test_requirements_mode_has_4_phases(self):
        step = StepDefinition(id="d", type=StepType.DIALOG, mode="requirements")
        phases = WorkflowEngine._get_dialog_phases(step)
        assert len(phases) == 4

    def test_unknown_mode_no_phases(self):
        step = StepDefinition(id="d", type=StepType.DIALOG, mode="nonexistent")
        phases = WorkflowEngine._get_dialog_phases(step)
        assert phases == []


class TestDialogAdvance:
    async def test_first_advance_initializes_phase(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_dialog_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        result = await engine.advance(run, wf_def)
        await session.commit()

        assert result.completed is False
        assert result.run.current_step == "dialog-step"
        assert result.prompt is not None
        assert "Divergieren" in result.prompt
        assert "Phase:" in result.prompt

        assert result.run.state_data["_dialog_phase"] == "diverge"

    async def test_phase_advancement_stays_on_step(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_dialog_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        # Init first phase
        r1 = await engine.advance(run, wf_def)
        await session.commit()

        # Advance with phase output
        result = await engine.advance(r1.run, wf_def, step_output="Ideas collected")
        await session.commit()

        assert result.completed is False
        assert result.run.current_step == "dialog-step"
        assert "Konvergieren" in result.prompt

        assert result.run.state_data["_dialog_phase"] == "converge"
        assert result.run.state_data["_dialog_phases_output"]["diverge"] == "Ideas collected"

    async def test_all_phases_complete_moves_to_next_step(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_dialog_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        # Phase 1: init
        r = await engine.advance(run, wf_def)
        await session.commit()

        # Phase 1 -> 2
        r = await engine.advance(r.run, wf_def, step_output="Diverge output")
        await session.commit()

        # Phase 2 -> 3
        r = await engine.advance(r.run, wf_def, step_output="Converge output")
        await session.commit()

        # Phase 3 -> done -> next step
        result = await engine.advance(r.run, wf_def, step_output="Synthesis output")
        await session.commit()

        assert result.completed is False
        assert result.run.current_step == "final"
        assert "Done?" in result.prompt

    async def test_explicit_phases_override_mode(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_dialog_workflow_with_phases()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        # Init
        r = await engine.advance(run, wf_def)
        await session.commit()
        assert "Phase 1" in r.prompt

        # Phase 1 -> 2
        r = await engine.advance(r.run, wf_def, step_output="P1 done")
        await session.commit()
        assert "Phase 2" in r.prompt

        # Phase 2 -> next step
        r = await engine.advance(r.run, wf_def, step_output="P2 done")
        await session.commit()
        assert r.run.current_step == "final"

    async def test_freeform_mode_skips_phases(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_freeform_dialog_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        # Freeform has no phases — single advance with output moves to next step
        result = await engine.advance(run, wf_def, step_output="Discussion result")
        await session.commit()

        assert result.run.current_step == "final"

    async def test_resume_mid_phase(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_dialog_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        # Init phase
        r = await engine.advance(run, wf_def)
        await session.commit()

        # Advance to phase 2
        r = await engine.advance(r.run, wf_def, step_output="Phase 1 output")
        await session.commit()

        assert r.run.state_data["_dialog_phase"] == "converge"

        # Simulate resume — advance again
        result = await engine.advance(r.run, wf_def, step_output="Phase 2 output")
        await session.commit()

        assert result.run.current_step == "dialog-step"
        assert result.run.state_data["_dialog_phase"] == "synthesize"

    async def test_empty_phase_output(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_dialog_workflow_with_phases()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        # Init
        r = await engine.advance(run, wf_def)
        await session.commit()

        # Advance with empty output
        result = await engine.advance(r.run, wf_def, step_output="")
        await session.commit()

        # Should still advance to phase 2
        assert result.run.current_step == "dialog-step"
        assert result.run.state_data["_dialog_phase"] == "p2"

    async def test_captures_after_all_phases(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_dialog_workflow_with_captures()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        # review mode: understand -> evaluate -> decide (3 phases)
        r = await engine.advance(run, wf_def)
        await session.commit()
        r = await engine.advance(r.run, wf_def, step_output="Understood")
        await session.commit()
        r = await engine.advance(r.run, wf_def, step_output="Evaluated")
        await session.commit()
        result = await engine.advance(r.run, wf_def, step_output="Decision made")
        await session.commit()

        assert result.run.current_step == "final"
        state = result.run.state_data
        # Merged output should be stored in "result" capture
        assert "result" in state
        assert "Understood" in state["result"]
        assert "Evaluated" in state["result"]
        assert "Decision made" in state["result"]

    async def test_prompt_shows_previous_outputs(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_dialog_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        # Init
        r = await engine.advance(run, wf_def)
        await session.commit()

        # Advance with output
        result = await engine.advance(r.run, wf_def, step_output="First phase ideas")
        await session.commit()

        assert "Bisherige Ergebnisse" in result.prompt
        assert "First phase ideas" in result.prompt

    async def test_dialog_prompt_contains_goal_and_guidelines(self, wf_engine):
        engine, session = wf_engine
        wf_def = _make_dialog_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        result = await engine.advance(run, wf_def)
        await session.commit()

        assert "Generate ideas" in result.prompt
        assert "Be creative" in result.prompt
        assert "No judgment" in result.prompt

    async def test_dialog_prompt_contains_instructions(self, wf_engine):
        """Dialog prompt should contain the instruction block."""
        engine, session = wf_engine
        wf_def = _make_dialog_workflow()

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        result = await engine.advance(run, wf_def)
        await session.commit()

        assert "Anweisungen" in result.prompt
        assert "Gespräch" in result.prompt
        assert "Zusammenfassung" in result.prompt
        assert "workflow_advance" in result.prompt

    async def test_dialog_prompt_with_resources(self, wf_engine):
        """Dialog prompt should include resources when resolver is provided."""
        engine, session = wf_engine
        from src.shared.schemas.resource import ResourceDefinition, ResourceType
        from src.shared.schemas.workflow import ResourceReference

        wf_def = WorkflowDefinition(
            id="dialog-res-wf",
            version="1.0.0",
            name="Dialog Resources",
            steps=[
                StepDefinition(
                    id="dialog-step",
                    type=StepType.DIALOG,
                    prompt="Dialog with resources",
                    mode="brainstorming",
                    goal="Test resources",
                    resources=[ResourceReference(ref="test-res")],
                ),
                StepDefinition(id="final", type=StepType.CONFIRM, prompt="Done?"),
            ],
        )

        short_resource = ResourceDefinition(
            id="test-res",
            name="Test Guidelines",
            type=ResourceType.CONVENTION,
            content="Short content",
        )

        def resolver(ref: str):
            if ref == "test-res":
                return short_resource
            return None

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        result = await engine.advance(run, wf_def, resource_resolver=resolver)
        await session.commit()

        assert "Test Guidelines" in result.prompt
        assert "Short content" in result.prompt

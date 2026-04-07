"""Tests for the WorkflowEngine."""

import pytest

from vela_sdk.engine.types import WorkflowRunStatus
from vela_sdk.engine.workflow_engine import WorkflowEngine, _parse_duration_hours
from vela_sdk.schemas.workflow import (
    CaptureDefinition,
    DialogPhaseDefinition,
    LifecycleDefinition,
    OnErrorDefinition,
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


class TestStartOrResume:
    async def test_start_new_run(self, engine, simple_workflow):
        run, is_new = await engine.start_or_resume(simple_workflow)
        assert is_new is True
        assert run.workflow_id == "test-wf"
        assert run.current_step == "step1"
        assert run.status == WorkflowRunStatus.ACTIVE

    async def test_resume_by_identity(self, engine, parameterized_workflow):
        run1, _ = await engine.start_or_resume(
            parameterized_workflow, params={"project": "alpha"}
        )
        run2, is_new = await engine.start_or_resume(
            parameterized_workflow, params={"project": "alpha"}
        )
        assert is_new is False
        assert run2.id == run1.id

    async def test_new_run_different_identity(self, engine, parameterized_workflow):
        run1, _ = await engine.start_or_resume(
            parameterized_workflow, params={"project": "alpha"}
        )
        run2, is_new = await engine.start_or_resume(
            parameterized_workflow, params={"project": "beta"}
        )
        assert is_new is True
        assert run2.id != run1.id

    async def test_default_params(self, engine, parameterized_workflow):
        run, _ = await engine.start_or_resume(
            parameterized_workflow, params={"project": "test"}
        )
        assert run.params["mode"] == "standard"


class TestAdvance:
    async def test_advance_to_next_step(self, engine, simple_workflow):
        run, _ = await engine.start_or_resume(simple_workflow)
        result = await engine.advance(run, simple_workflow, step_output="hello")
        assert result.run.current_step == "step2"
        assert result.prompt is not None
        assert "hello" in result.prompt  # Template resolved

    async def test_advance_to_completion(self, engine, simple_workflow):
        run, _ = await engine.start_or_resume(simple_workflow)
        result = await engine.advance(run, simple_workflow, step_output="hello")
        result = await engine.advance(result.run, simple_workflow, step_output="confirmed")
        assert result.completed is True
        assert result.run.status == WorkflowRunStatus.COMPLETED

    async def test_advance_completed_run_is_noop(self, engine, simple_workflow):
        run, _ = await engine.start_or_resume(simple_workflow)
        result = await engine.advance(run, simple_workflow, step_output="a")
        result = await engine.advance(result.run, simple_workflow, step_output="b")
        assert result.completed is True
        # Advancing again should be a no-op
        result2 = await engine.advance(result.run, simple_workflow, step_output="c")
        assert result2.completed is True

    async def test_choice_branching(self, engine, choice_workflow):
        run, _ = await engine.start_or_resume(choice_workflow)
        result = await engine.advance(run, choice_workflow, step_output="a")
        assert result.run.current_step == "path_a"

    async def test_choice_branching_b(self, engine, choice_workflow):
        run, _ = await engine.start_or_resume(choice_workflow)
        result = await engine.advance(run, choice_workflow, step_output="b")
        assert result.run.current_step == "path_b"

    async def test_capture_from_json_output(self, engine, simple_workflow):
        run, _ = await engine.start_or_resume(simple_workflow)
        result = await engine.advance(
            run, simple_workflow,
            step_output='{"input1": "from json"}'
        )
        assert result.run.state_data.get("input1") == "from json"

    async def test_capture_from_plain_output(self, engine, simple_workflow):
        run, _ = await engine.start_or_resume(simple_workflow)
        result = await engine.advance(
            run, simple_workflow,
            step_output="plain text"
        )
        assert result.run.state_data.get("input1") == "plain text"

    async def test_sub_workflow(self, engine, store):
        wf = WorkflowDefinition(
            id="parent",
            version="1.0.0",
            name="Parent",
            steps=[
                StepDefinition(
                    id="delegate",
                    type=StepType.WORKFLOW,
                    workflow_ref="child@1.0.0",
                    params_mapping={"x": "y"},
                ),
            ],
        )
        run, _ = await engine.start_or_resume(wf)
        result = await engine.advance(run, wf)
        assert result.sub_workflow_ref == "child@1.0.0"
        assert result.run.status == WorkflowRunStatus.PAUSED


class TestDialog:
    async def test_dialog_phase_advancement(self, engine, store):
        wf = WorkflowDefinition(
            id="dialog-wf",
            version="1.0.0",
            name="Dialog WF",
            steps=[
                StepDefinition(
                    id="discuss",
                    name="Discussion",
                    type=StepType.DIALOG,
                    mode="review",
                    prompt="Review this item",
                ),
            ],
        )
        run, _ = await engine.start_or_resume(wf)

        # First advance: init to first phase
        r = await engine.advance(run, wf)
        assert "Verstehen" in r.prompt
        assert r.run.state_data.get("_dialog_phase") == "understand"

        # Second advance: move to next phase
        r = await engine.advance(r.run, wf, step_output="understood")
        assert "Bewerten" in r.prompt
        assert r.run.state_data.get("_dialog_phase") == "evaluate"

        # Third advance: move to last phase
        r = await engine.advance(r.run, wf, step_output="evaluated")
        assert "Entscheiden" in r.prompt

        # Fourth advance: complete
        r = await engine.advance(r.run, wf, step_output="decided")
        assert r.completed is True

    async def test_dialog_freeform_mode(self, engine, store):
        wf = WorkflowDefinition(
            id="free-dialog",
            version="1.0.0",
            name="Free Dialog",
            steps=[
                StepDefinition(
                    id="talk",
                    type=StepType.DIALOG,
                    mode="freeform",
                    capture=[CaptureDefinition(key="result", elicit="never")],
                ),
            ],
        )
        run, _ = await engine.start_or_resume(wf)
        r = await engine.advance(run, wf, step_output="output")
        assert r.completed is True
        assert r.run.state_data.get("_dialog_result") == "output"


class TestTemplateResolution:
    async def test_resolve_params(self, engine, parameterized_workflow):
        run, _ = await engine.start_or_resume(
            parameterized_workflow, params={"project": "vela"}
        )
        prompt = engine.assemble_prompt(parameterized_workflow, run)
        assert "vela" in prompt
        assert "standard" in prompt

    def test_resolve_nested(self, engine):
        ctx = {"params": {"name": "test"}, "state": {"x": "42"}, "steps": {}}
        result = engine.resolve_templates("Hello {{params.name}}, x={{state.x}}", ctx)
        assert result == "Hello test, x=42"

    def test_unresolved_kept(self, engine):
        ctx = {"params": {}, "state": {}, "steps": {}}
        result = engine.resolve_templates("{{missing.key}}", ctx)
        assert result == "{{missing.key}}"


class TestDependsOn:
    async def test_valid_depends_on(self, engine, depends_on_workflow):
        run, _ = await engine.start_or_resume(depends_on_workflow)
        result = await engine.advance(run, depends_on_workflow, step_output="data")
        # step2 depends on gathered from step1
        step2 = engine._get_step(depends_on_workflow, "step2")
        is_valid, missing = engine.validate_depends_on(result.run, step2)
        assert is_valid is True

    async def test_missing_depends_on(self, engine, depends_on_workflow):
        run, _ = await engine.start_or_resume(depends_on_workflow)
        step2 = engine._get_step(depends_on_workflow, "step2")
        is_valid, missing = engine.validate_depends_on(run, step2)
        assert is_valid is False
        assert "gathered" in missing


class TestErrorHandling:
    def test_no_error_config(self, engine, store):
        e = WorkflowEngine(store)
        step = StepDefinition(id="s", type=StepType.EXECUTE)
        from vela_sdk.engine.types import WorkflowRunState
        run = WorkflowRunState(id="r", workflow_id="w", workflow_version="1")
        action = e.handle_on_error(run, step, "boom")
        assert action.action == "abort"

    def test_retry_config(self, engine, store):
        e = WorkflowEngine(store)
        step = StepDefinition(
            id="s", type=StepType.EXECUTE,
            on_error=OnErrorDefinition(retry=3, message="try again"),
        )
        from vela_sdk.engine.types import WorkflowRunState
        run = WorkflowRunState(id="r", workflow_id="w", workflow_version="1")
        action = e.handle_on_error(run, step, "boom")
        assert action.action == "retry"
        assert action.message == "try again"

    def test_fallback_config(self, engine, store):
        e = WorkflowEngine(store)
        step = StepDefinition(
            id="s", type=StepType.EXECUTE,
            on_error=OnErrorDefinition(fallback="recover"),
        )
        from vela_sdk.engine.types import WorkflowRunState
        run = WorkflowRunState(id="r", workflow_id="w", workflow_version="1")
        action = e.handle_on_error(run, step, "boom")
        assert action.action == "fallback"
        assert action.fallback_step == "recover"


class TestLifecycle:
    def test_auto_cancel(self, engine):
        from datetime import datetime, timedelta, timezone
        lifecycle = LifecycleDefinition(auto_cancel_after="1h")
        from vela_sdk.engine.types import WorkflowRunState
        run = WorkflowRunState(
            id="r", workflow_id="w", workflow_version="1",
            status=WorkflowRunStatus.ACTIVE,
            updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        result = engine.check_lifecycle(run, lifecycle)
        assert result == WorkflowRunStatus.CANCELLED

    def test_no_cancel_if_recent(self, engine):
        from datetime import datetime, timezone
        lifecycle = LifecycleDefinition(auto_cancel_after="1h")
        from vela_sdk.engine.types import WorkflowRunState
        run = WorkflowRunState(
            id="r", workflow_id="w", workflow_version="1",
            status=WorkflowRunStatus.ACTIVE,
            updated_at=datetime.now(timezone.utc),
        )
        result = engine.check_lifecycle(run, lifecycle)
        assert result is None


class TestAssemblePrompt:
    async def test_progress_indicator(self, engine, simple_workflow):
        run, _ = await engine.start_or_resume(simple_workflow)
        prompt = engine.assemble_prompt(simple_workflow, run)
        assert "→ First Step" in prompt
        assert "Second Step" in prompt

    async def test_cta_freeform(self, engine, simple_workflow):
        run, _ = await engine.start_or_resume(simple_workflow)
        prompt = engine.assemble_prompt(simple_workflow, run)
        assert "Bitte Eingabe machen" in prompt

    async def test_cta_confirm(self, engine, simple_workflow):
        run, _ = await engine.start_or_resume(simple_workflow)
        result = await engine.advance(run, simple_workflow, step_output="x")
        prompt = engine.assemble_prompt(simple_workflow, result.run)
        assert "bestaetigen oder ablehnen" in prompt


class TestParseStepOutput:
    def test_json_dict(self):
        caps = [CaptureDefinition(key="a"), CaptureDefinition(key="b")]
        result = WorkflowEngine._parse_step_output('{"a": 1, "b": 2}', caps)
        assert result == {"a": 1, "b": 2}

    def test_plain_string_single_capture(self):
        caps = [CaptureDefinition(key="x")]
        result = WorkflowEngine._parse_step_output("hello", caps)
        assert result == {"x": "hello"}

    def test_none_output(self):
        caps = [CaptureDefinition(key="x")]
        result = WorkflowEngine._parse_step_output(None, caps)
        assert result == {}


class TestParseDuration:
    def test_hours(self):
        assert _parse_duration_hours("48h") == 48.0

    def test_days(self):
        assert _parse_duration_hours("30d") == 720.0

    def test_invalid(self):
        assert _parse_duration_hours("abc") is None

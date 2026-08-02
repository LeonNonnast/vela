"""End-to-end mcp_call / fetch / pause_run / resolved.x / project.x tests.

Mirrors the TypeScript SDK's mcp-call-step.test.ts / fetch.test.ts /
pause.test.ts / prompt-builder.test.ts.
"""

import pytest

from vela_sdk.engine.types import WorkflowRunStatus
from vela_sdk.engine.workflow_engine import WorkflowEngine
from vela_sdk.schemas.workflow import (
    CaptureDefinition,
    LifecycleDefinition,
    OnErrorDefinition,
    ParamDefinition,
    StepDefinition,
    StepType,
    WorkflowDefinition,
)
from vela_sdk.sources.registry import clear_sources, register_source
from vela_sdk.storage.memory import InMemoryStore


@pytest.fixture(autouse=True)
def _clear():
    clear_sources()
    yield
    clear_sources()


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def engine(store):
    return WorkflowEngine(store)


def mcp_call_workflow(mcp_source, mcp_tool="do-thing", on_error=None, extra_steps=None, capture_key="result"):
    steps = [
        StepDefinition(
            id="call-it",
            type=StepType.MCP_CALL,
            mcp_source=mcp_source,
            mcp_tool=mcp_tool,
            mcp_params={"who": "{{params.who}}"},
            capture=[CaptureDefinition(key=capture_key, elicit="never")],
            on_error=on_error,
        ),
        *(extra_steps or []),
    ]
    return WorkflowDefinition(id="wf-mcp-call-test", name="Mcp Call Test", steps=steps)


def fallback_step(step_id):
    return StepDefinition(id=step_id, type=StepType.FREEFORM, prompt=f"Recovering via {step_id}")


class TestMcpCallStep:
    async def test_invokes_handler_and_captures_result(self, engine):
        calls = []

        async def handler(tool, params, ctx):
            calls.append((tool, params))
            return {"result": "ok", "echo": params}

        register_source("devops", handler)
        # Capture "echo" rather than "result" — the handler's own JSON
        # result already has a top-level "result" key, so capturing under
        # that same name would just extract the inner string, not the dict.
        wf = mcp_call_workflow("devops", capture_key="echo")

        run, _ = await engine.start_or_resume(wf, params={"who": "world"})
        result = await engine.advance(run, wf)

        assert calls == [("do-thing", {"who": "world"})]
        assert result.completed is True
        assert result.run.state_data["echo"] == {"who": "world"}

    async def test_aborts_when_no_handler_registered(self, engine):
        wf = mcp_call_workflow("nonexistent")
        run, _ = await engine.start_or_resume(wf)
        result = await engine.advance(run, wf)

        assert result.run.status == WorkflowRunStatus.CANCELLED
        assert "No handler registered for source" in result.error

    async def test_retries_then_succeeds(self, engine):
        attempts = 0

        async def handler(tool, params, ctx):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("transient failure")
            return {"result": "ok"}

        register_source("flaky", handler)
        wf = mcp_call_workflow("flaky", on_error=OnErrorDefinition(retry=2))

        run, _ = await engine.start_or_resume(wf)
        out = await engine.advance(run, wf)

        assert attempts == 3
        assert out.error is None
        assert out.run.state_data["result"] == "ok"

    async def test_falls_back_when_handler_keeps_failing(self, engine):
        async def handler(tool, params, ctx):
            raise RuntimeError("boom")

        register_source("always-fails", handler)
        wf = mcp_call_workflow(
            "always-fails",
            on_error=OnErrorDefinition(fallback="recover", message="source unavailable"),
            extra_steps=[fallback_step("recover")],
        )

        run, _ = await engine.start_or_resume(wf)
        out = await engine.advance(run, wf)

        assert out.completed is False
        assert out.error == "source unavailable"
        assert out.run.current_step == "recover"
        assert out.run.state_data["_error"] == "source unavailable"
        assert out.run.status != WorkflowRunStatus.CANCELLED

    async def test_aborts_with_no_fallback_configured(self, engine):
        async def handler(tool, params, ctx):
            raise RuntimeError("fatal")

        register_source("fatal-handler", handler)
        wf = mcp_call_workflow("fatal-handler")

        run, _ = await engine.start_or_resume(wf)
        out = await engine.advance(run, wf)

        assert out.completed is True
        assert out.error == "fatal"
        assert out.run.status == WorkflowRunStatus.CANCELLED

    async def test_fails_through_on_error_when_source_tool_missing(self, engine):
        wf = mcp_call_workflow(
            "", "",
            on_error=OnErrorDefinition(fallback="recover"),
            extra_steps=[fallback_step("recover")],
        )
        run, _ = await engine.start_or_resume(wf)
        out = await engine.advance(run, wf)

        assert out.run.current_step == "recover"
        assert "missing mcp_source/mcp_tool" in out.error


def freeform_step(step_id, prompt, fetch=None, on_error=None, next_step=None):
    return StepDefinition(
        id=step_id, type=StepType.FREEFORM, prompt=prompt,
        fetch=fetch or [], on_error=on_error, next=next_step,
    )


class TestFetchStepField:
    async def test_populates_fetch_for_first_step(self, engine):
        async def handler(tool, params, ctx):
            assert tool == "get-status"
            assert params == {}
            return "green"

        register_source("devops", handler)
        wf = WorkflowDefinition(
            id="wf-fetch-test", name="Fetch Test",
            steps=[freeform_step("s1", "Status is {{fetch.status}}.", fetch=[
                {"key": "status", "source": "devops", "action": "get-status", "params": {}},
            ])],
        )

        run, _ = await engine.start_or_resume(wf)
        assert run.state_data["_fetch"] == {"status": "green"}
        assert "Status is green." in engine.assemble_prompt(wf, run)

    async def test_populates_fetch_when_landing_on_later_step(self, engine):
        async def handler(tool, params, ctx):
            return "42"

        register_source("devops", handler)
        wf = WorkflowDefinition(
            id="wf-fetch-test", name="Fetch Test",
            steps=[
                freeform_step("s1", "Step 1", next_step="s2"),
                freeform_step("s2", "Count is {{fetch.count}}.", fetch=[
                    {"key": "count", "source": "devops", "action": "get-count", "params": {}},
                ]),
            ],
        )

        run, _ = await engine.start_or_resume(wf)
        out = await engine.advance(run, wf, step_output="ok")

        assert out.run.current_step == "s2"
        assert out.run.state_data["_fetch"] == {"count": "42"}
        assert "Count is 42." in out.prompt

    async def test_resolves_fetch_params_via_templates(self, engine):
        calls = []

        async def handler(tool, params, ctx):
            calls.append(params)
            return "ok"

        register_source("devops", handler)
        wf = WorkflowDefinition(
            id="wf-fetch-test", name="Fetch Test",
            params=[ParamDefinition(name="who")],
            steps=[freeform_step("s1", "{{fetch.result}}", fetch=[
                {"key": "result", "source": "devops", "action": "lookup", "params": {"who": "{{params.who}}"}},
            ])],
        )

        await engine.start_or_resume(wf, params={"who": "alice"})
        assert calls == [{"who": "alice"}]

    async def test_no_behavior_change_when_step_declares_no_fetch(self, engine):
        wf = WorkflowDefinition(id="wf-fetch-test", name="Fetch Test", steps=[freeform_step("s1", "hello")])
        run, _ = await engine.start_or_resume(wf)
        assert "_fetch" not in run.state_data

    async def test_falls_back_when_fetch_handler_keeps_failing(self, engine):
        async def handler(tool, params, ctx):
            raise RuntimeError("boom")

        register_source("always-fails", handler)
        wf = WorkflowDefinition(
            id="wf-fetch-test", name="Fetch Test",
            steps=[
                freeform_step(
                    "s1", "Data: {{fetch.x}}",
                    fetch=[{"key": "x", "source": "always-fails", "action": "get", "params": {}}],
                    on_error=OnErrorDefinition(fallback="recover", message="fetch unavailable"),
                ),
                freeform_step("recover", "Recovering"),
            ],
        )

        run, _ = await engine.start_or_resume(wf)
        assert run.current_step == "recover"
        assert run.state_data["_error"] == "fetch unavailable"

    async def test_retries_failing_fetch_then_succeeds(self, engine):
        attempts = 0

        async def handler(tool, params, ctx):
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise RuntimeError("transient")
            return "recovered"

        register_source("flaky", handler)
        wf = WorkflowDefinition(
            id="wf-fetch-test", name="Fetch Test",
            steps=[freeform_step(
                "s1", "{{fetch.x}}",
                fetch=[{"key": "x", "source": "flaky", "action": "get", "params": {}}],
                on_error=OnErrorDefinition(retry=1),
            )],
        )

        run, _ = await engine.start_or_resume(wf)
        assert attempts == 2
        assert run.state_data["_fetch"] == {"x": "recovered"}

    async def test_clears_stale_fetch_when_next_step_declares_none(self, engine):
        async def handler(tool, params, ctx):
            return "value"

        register_source("devops", handler)
        wf = WorkflowDefinition(
            id="wf-fetch-test", name="Fetch Test",
            steps=[
                freeform_step("s1", "{{fetch.x}}", fetch=[
                    {"key": "x", "source": "devops", "action": "get", "params": {}},
                ], next_step="s2"),
                freeform_step("s2", "no fetch here"),
            ],
        )

        run, _ = await engine.start_or_resume(wf)
        assert run.state_data["_fetch"] == {"x": "value"}

        out = await engine.advance(run, wf, step_output="ok")
        assert out.run.current_step == "s2"
        assert out.run.state_data["_fetch"] == {}


class TestPauseRun:
    def _workflow(self, allow_pause=None):
        lifecycle = None if allow_pause is None else LifecycleDefinition(allow_pause=allow_pause)
        return WorkflowDefinition(
            id="wf-pause-test", name="Pause Test", lifecycle=lifecycle,
            steps=[
                StepDefinition(id="s1", type=StepType.FREEFORM, prompt="Step 1", next="s2"),
                StepDefinition(id="s2", type=StepType.FREEFORM, prompt="Step 2"),
            ],
        )

    async def test_pauses_active_run_by_default(self, engine):
        wf = self._workflow()
        run, _ = await engine.start_or_resume(wf)
        paused = await engine.pause_run(run, wf)
        assert paused.status == WorkflowRunStatus.PAUSED

    async def test_raises_when_allow_pause_false(self, engine):
        wf = self._workflow(allow_pause=False)
        run, _ = await engine.start_or_resume(wf)
        with pytest.raises(ValueError, match="allow_pause"):
            await engine.pause_run(run, wf)

    async def test_raises_when_not_active(self, engine):
        wf = self._workflow()
        run, _ = await engine.start_or_resume(wf)
        paused = await engine.pause_run(run, wf)
        with pytest.raises(ValueError, match="not 'active'"):
            await engine.pause_run(paused, wf)

    async def test_resumes_via_advance(self, engine):
        wf = self._workflow()
        run, _ = await engine.start_or_resume(wf)
        paused = await engine.pause_run(run, wf)

        result = await engine.advance(paused, wf, step_output="ok")
        assert result.completed is False
        assert result.run.current_step == "s2"


class TestTemplateContext:
    async def test_resolved_x_exposes_resolve_flagged_params(self, engine):
        wf = WorkflowDefinition(
            id="wf-resolved-test", name="Resolved Test",
            params=[
                ParamDefinition(name="tenant", resolve=True),
                ParamDefinition(name="who"),
            ],
            steps=[StepDefinition(id="s1", type=StepType.FREEFORM, prompt="{{resolved.tenant}} / {{params.who}}")],
        )

        run, _ = await engine.start_or_resume(wf, params={"who": "alice"}, resolved_params={"tenant": "acme"})
        assert run.params["tenant"] == "acme"
        prompt = engine.assemble_prompt(wf, run)
        assert "acme / alice" in prompt

    async def test_project_x_populated_via_resolver(self, engine):
        wf = WorkflowDefinition(
            id="wf-project-test", name="Project Test",
            steps=[StepDefinition(id="s1", type=StepType.FREEFORM, prompt="Project: {{project.name}}")],
        )

        run, _ = await engine.start_or_resume(wf, project_id="proj-1")
        prompt = engine.assemble_prompt(
            wf, run, project_data_resolver=lambda pid: {"name": "Acme Corp"} if pid == "proj-1" else None,
        )
        assert "Project: Acme Corp" in prompt

    async def test_project_x_empty_without_resolver(self, engine):
        wf = WorkflowDefinition(
            id="wf-project-test", name="Project Test",
            steps=[StepDefinition(id="s1", type=StepType.FREEFORM, prompt="[{{project.name}}]")],
        )
        run, _ = await engine.start_or_resume(wf, project_id="proj-1")
        prompt = engine.assemble_prompt(wf, run)
        assert "[{{project.name}}]" in prompt

"""Resource-Workflow Integration Tests — prompt assembly with resources."""

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.shared.db.base import Base
from src.shared.db.models import WorkflowRun, WorkflowRunStatus
from src.shared.repositories.workflow_repository import WorkflowRepository
from src.shared.schemas.resource import ResourceDefinition, ResourceReference, ResourceType
from src.shared.schemas.workflow import (
    StepDefinition,
    StepType,
    WorkflowDefinition,
)
from vela_sdk.engine.workflow_engine import WorkflowEngine
from src.shared.services.workflow_store_adapter import VelaWorkflowStore


# --- Factories ---

def _make_resource(
    id: str,
    name: str,
    type: ResourceType = ResourceType.CONVENTION,
    content: str = "short content",
    description: str = "",
    uri_pattern: str | None = None,
) -> ResourceDefinition:
    return ResourceDefinition(
        id=id, name=name, type=type, content=content,
        description=description, uri_pattern=uri_pattern,
    )


def _make_resolver(resources: dict[str, ResourceDefinition]):
    """Create a resolver function from a dict of resources."""
    def resolver(ref: str):
        if ref in resources:
            return resources[ref]
        for r in resources.values():
            uri = r.uri_pattern or f"vela://{r.type.value}/{r.id}"
            if uri == ref:
                return r
        return None
    return resolver


def _make_workflow_with_resources(
    wf_resources: list[ResourceReference] | None = None,
    step_resources: list[ResourceReference] | None = None,
) -> WorkflowDefinition:
    return WorkflowDefinition(
        id="res-wf",
        version="1.0.0",
        name="Resource Workflow",
        resources=wf_resources or [],
        steps=[
            StepDefinition(
                id="step-1",
                type=StepType.FREEFORM,
                prompt="Do the thing.",
                resources=step_resources or [],
            ),
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


class TestAssemblePromptWithResources:
    async def test_inline_short_resource(self, wf_engine):
        """Short resources (< 500 chars) should be inlined in the prompt."""
        engine, session = wf_engine
        resources = {
            "py-conv": _make_resource("py-conv", "Python Conventions", content="Use snake_case."),
        }
        wf_def = _make_workflow_with_resources(
            wf_resources=[ResourceReference(ref="py-conv")],
        )

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        prompt = engine.assemble_prompt(
            wf_def, run, resource_resolver=_make_resolver(resources)
        )
        assert "### Python Conventions" in prompt
        assert "Use snake_case." in prompt

    async def test_reference_long_resource(self, wf_engine):
        """Long resources (>= 500 chars) should be listed as URI references."""
        engine, session = wf_engine
        resources = {
            "long-ex": _make_resource(
                "long-ex", "Long Example",
                type=ResourceType.EXAMPLE,
                content="x" * 600,
                description="A long example",
            ),
        }
        wf_def = _make_workflow_with_resources(
            wf_resources=[ResourceReference(ref="long-ex")],
        )

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        prompt = engine.assemble_prompt(
            wf_def, run, resource_resolver=_make_resolver(resources)
        )
        assert "### Available Resources" in prompt
        assert "vela://example/long-ex" in prompt
        assert "A long example" in prompt
        assert "read_resource(" in prompt
        assert "vela_get_resource" in prompt
        # Content should NOT be inlined
        assert "x" * 600 not in prompt

    async def test_explicit_inline_true(self, wf_engine):
        """Explicit inline=True should inline even long content."""
        engine, session = wf_engine
        long_content = "y" * 600
        resources = {
            "forced-inline": _make_resource(
                "forced-inline", "Forced Inline", content=long_content,
            ),
        }
        wf_def = _make_workflow_with_resources(
            wf_resources=[ResourceReference(ref="forced-inline", inline=True)],
        )

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        prompt = engine.assemble_prompt(
            wf_def, run, resource_resolver=_make_resolver(resources)
        )
        assert "### Forced Inline" in prompt
        assert long_content in prompt

    async def test_explicit_inline_false(self, wf_engine):
        """Explicit inline=False should reference even short content."""
        engine, session = wf_engine
        resources = {
            "forced-ref": _make_resource(
                "forced-ref", "Forced Reference",
                type=ResourceType.REFERENCE,
                content="short",
                description="Short but forced reference",
            ),
        }
        wf_def = _make_workflow_with_resources(
            wf_resources=[ResourceReference(ref="forced-ref", inline=False)],
        )

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        prompt = engine.assemble_prompt(
            wf_def, run, resource_resolver=_make_resolver(resources)
        )
        assert "### Available Resources" in prompt
        assert "vela://reference/forced-ref" in prompt
        # Content should NOT be inlined
        assert "### Forced Reference" not in prompt

    async def test_step_level_resources(self, wf_engine):
        """Step-level resources are included in prompt."""
        engine, session = wf_engine
        resources = {
            "step-res": _make_resource("step-res", "Step Resource", content="Step content."),
        }
        wf_def = _make_workflow_with_resources(
            step_resources=[ResourceReference(ref="step-res")],
        )

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        prompt = engine.assemble_prompt(
            wf_def, run, resource_resolver=_make_resolver(resources)
        )
        assert "### Step Resource" in prompt
        assert "Step content." in prompt

    async def test_workflow_and_step_merge(self, wf_engine):
        """Workflow-level and step-level resources are merged."""
        engine, session = wf_engine
        resources = {
            "wf-res": _make_resource("wf-res", "Workflow Resource", content="WF content."),
            "step-res": _make_resource("step-res", "Step Resource", content="Step content."),
        }
        wf_def = _make_workflow_with_resources(
            wf_resources=[ResourceReference(ref="wf-res")],
            step_resources=[ResourceReference(ref="step-res")],
        )

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        prompt = engine.assemble_prompt(
            wf_def, run, resource_resolver=_make_resolver(resources)
        )
        assert "### Workflow Resource" in prompt
        assert "### Step Resource" in prompt

    async def test_step_overrides_workflow_same_ref(self, wf_engine):
        """Step-level resource overrides workflow-level for same ref."""
        engine, session = wf_engine
        resources = {
            "shared-res": _make_resource(
                "shared-res", "Shared Resource", content="x" * 600,
            ),
        }
        wf_def = _make_workflow_with_resources(
            # Workflow says no inline preference (auto → reference since > 500)
            wf_resources=[ResourceReference(ref="shared-res")],
            # Step says force inline
            step_resources=[ResourceReference(ref="shared-res", inline=True)],
        )

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        prompt = engine.assemble_prompt(
            wf_def, run, resource_resolver=_make_resolver(resources)
        )
        # Step override wins — content should be inlined
        assert "### Shared Resource" in prompt
        assert "x" * 600 in prompt

    async def test_unresolved_resource_skipped(self, wf_engine):
        """Unresolvable resource references are silently skipped."""
        engine, session = wf_engine
        wf_def = _make_workflow_with_resources(
            wf_resources=[ResourceReference(ref="nonexistent")],
        )

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        prompt = engine.assemble_prompt(
            wf_def, run, resource_resolver=_make_resolver({})
        )
        # Should still have the step prompt
        assert "Do the thing." in prompt
        # Should NOT have resource sections
        assert "### Available Resources" not in prompt

    async def test_no_resolver_no_resources(self, wf_engine):
        """Without a resolver, resources are not included."""
        engine, session = wf_engine
        wf_def = _make_workflow_with_resources(
            wf_resources=[ResourceReference(ref="some-res")],
        )

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        prompt = engine.assemble_prompt(wf_def, run)
        assert "Do the thing." in prompt
        assert "### Available Resources" not in prompt

    async def test_custom_uri_in_reference(self, wf_engine):
        """Custom URI pattern is used in reference listing."""
        engine, session = wf_engine
        resources = {
            "custom": _make_resource(
                "custom", "Custom",
                type=ResourceType.SCHEMA,
                content="x" * 600,
                description="Custom schema",
                uri_pattern="vela://schemas/my-custom",
            ),
        }
        wf_def = _make_workflow_with_resources(
            wf_resources=[ResourceReference(ref="custom")],
        )

        run, _ = await engine.start_or_resume(wf_def)
        await session.commit()

        prompt = engine.assemble_prompt(
            wf_def, run, resource_resolver=_make_resolver(resources)
        )
        assert "vela://schemas/my-custom" in prompt

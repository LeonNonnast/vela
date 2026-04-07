"""Dialog step handling for multi-phase conversations."""

from typing import Any, Callable, Optional

from vela_sdk.engine.dialog_modes import DialogModeRegistry
from vela_sdk.engine.prompt_builder import PromptBuilder
from vela_sdk.engine.types import AdvanceResult, WorkflowRunState, WorkflowRunStatus
from vela_sdk.schemas.resource import ResourceDefinition
from vela_sdk.schemas.workflow import (
    AnyStepDefinition,
    CaptureDefinition,
    DialogPhaseDefinition,
    WorkflowDefinition,
)
from vela_sdk.storage.protocol import WorkflowStore


def _get_dialog_modes() -> dict[str, list[DialogPhaseDefinition]]:
    """Return all registered dialog modes (backward-compatible accessor)."""
    return DialogModeRegistry.all_modes()


# Backward-compatible module-level reference.
# Code that reads ``DIALOG_MODES["brainstorming"]`` will continue to work
# because ``DialogModeRegistry.all_modes()`` returns a plain dict.
# Code that *writes* to ``DIALOG_MODES`` should use ``DialogModeRegistry.register()`` instead.
DIALOG_MODES = _get_dialog_modes()


class DialogHandler:
    """Handles dialog step advancement through phases.

    Manages multi-phase dialog conversations, tracking phase state
    and assembling phase-specific prompts.
    """

    def __init__(self, store: WorkflowStore, prompt_builder: PromptBuilder):
        self.store = store
        self.prompt_builder = prompt_builder

    @staticmethod
    def get_dialog_phases(step: AnyStepDefinition) -> list[DialogPhaseDefinition]:
        """Return dialog phases: explicit phases override mode lookup."""
        if step.phases:
            return step.phases
        if step.mode:
            phases = DialogModeRegistry.get(step.mode)
            if phases is not None:
                return phases
        return []

    async def advance_dialog(
        self,
        run: WorkflowRunState,
        workflow_def: WorkflowDefinition,
        step: AnyStepDefinition,
        step_output: Optional[str],
        notes: Optional[str],
        resolve_next_fn: Callable,
        get_step_fn: Callable,
        parse_step_output_fn: Callable,
        resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]] = None,
    ) -> AdvanceResult:
        """Handle dialog step advancement through phases."""
        state = run.state_data
        phases = self.get_dialog_phases(step)

        current_phase_id = state.get("_dialog_phase")
        phases_output: dict[str, str] = state.get("_dialog_phases_output", {})

        if not phases:
            # Freeform mode or no phases: behave like single-phase
            state_updates: dict[str, Any] = {}
            if step_output:
                state_updates["_dialog_result"] = step_output
                if step.capture:
                    output_captures = [c for c in step.capture if c.source == "output"]
                    state_updates.update(parse_step_output_fn(step_output, output_captures))

            if notes:
                state_updates["_notes"] = notes

            # Clean up dialog state
            state_updates.pop("_dialog_phase", None)
            state_updates.pop("_dialog_phases_output", None)

            next_step_id = resolve_next_fn(step, step_output, workflow_def)
            if next_step_id:
                run = await self.store.update_step(run.id, next_step_id, state_data=state_updates)
                next_step = get_step_fn(workflow_def, next_step_id)
                if next_step:
                    prompt = self.prompt_builder.assemble_prompt(workflow_def, run, next_step, resource_resolver=resource_resolver)
                    return AdvanceResult(run=run, prompt=prompt)

            run = await self.store.update_step(
                run.id, run.current_step, state_data=state_updates,
                status=WorkflowRunStatus.COMPLETED,
            )
            return AdvanceResult(run=run, completed=True)

        if current_phase_id is None:
            # First call: initialize to first phase
            first_phase = phases[0]
            state["_dialog_phase"] = first_phase.id
            state["_dialog_phases_output"] = {}
            run = await self.store.update_step(run.id, run.current_step, state_data=state)
            prompt = self._assemble_dialog_prompt(
                workflow_def, run, step, first_phase, phases, {},
                resource_resolver=resource_resolver,
            )
            return AdvanceResult(run=run, prompt=prompt)

        # Store current phase output
        if step_output:
            phases_output[current_phase_id] = step_output

        # Find current phase index
        phase_ids = [p.id for p in phases]
        try:
            current_idx = phase_ids.index(current_phase_id)
        except ValueError:
            current_idx = len(phase_ids) - 1

        if current_idx + 1 < len(phases):
            # More phases remain — advance to next phase
            next_phase = phases[current_idx + 1]
            state["_dialog_phase"] = next_phase.id
            state["_dialog_phases_output"] = phases_output
            run = await self.store.update_step(run.id, run.current_step, state_data=state)
            prompt = self._assemble_dialog_prompt(
                workflow_def, run, step, next_phase, phases, phases_output,
                resource_resolver=resource_resolver,
            )
            return AdvanceResult(run=run, prompt=prompt)

        # All phases complete — merge outputs, process captures, move to next step
        merged_output = "\n\n".join(
            f"### {p.name or p.id}\n{phases_output.get(p.id, '')}"
            for p in phases
        )

        state_updates = {}
        if step.capture:
            output_captures = [c for c in step.capture if c.source == "output"]
            if output_captures:
                state_updates.update(parse_step_output_fn(merged_output, output_captures))

        state_updates["_dialog_result"] = merged_output
        if notes:
            state_updates["_notes"] = notes

        # Clean up dialog tracking keys
        for cleanup_key in ("_dialog_phase", "_dialog_phases_output"):
            if cleanup_key in state:
                del state[cleanup_key]
            state_updates.pop(cleanup_key, None)

        next_step_id = resolve_next_fn(step, step_output, workflow_def)
        if next_step_id:
            run = await self.store.update_step(run.id, next_step_id, state_data=state_updates)
            next_step = get_step_fn(workflow_def, next_step_id)
            if next_step:
                prompt = self.prompt_builder.assemble_prompt(workflow_def, run, next_step, resource_resolver=resource_resolver)
                return AdvanceResult(run=run, prompt=prompt)

        run = await self.store.update_step(
            run.id, run.current_step, state_data=state_updates,
            status=WorkflowRunStatus.COMPLETED,
        )
        return AdvanceResult(run=run, completed=True)

    def _assemble_dialog_prompt(
        self,
        workflow_def: WorkflowDefinition,
        run: WorkflowRunState,
        step: AnyStepDefinition,
        phase: DialogPhaseDefinition,
        all_phases: list[DialogPhaseDefinition],
        phases_output: dict[str, str],
        resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]] = None,
    ) -> str:
        """Assemble prompt for a dialog phase."""
        phase_idx = next((i for i, p in enumerate(all_phases) if p.id == phase.id), 0)
        total = len(all_phases)

        parts: list[str] = []

        step_name = step.name or step.id
        phase_name = phase.name or phase.id
        parts.append(f"## {workflow_def.name} — {step_name}")
        parts.append(f"### Phase: {phase_name} ({phase_idx + 1}/{total})")
        parts.append("")

        if step.goal:
            parts.append(f"**Ziel:** {step.goal}")
            parts.append("")

        if step.guidelines:
            parts.append("**Guidelines:**")
            for gl in step.guidelines:
                parts.append(f"- {gl}")
            parts.append("")

        parts.append(f"**Phase-Anweisung:** {phase.guideline}")
        parts.append("")

        # Dialog instructions
        parts.append("### Anweisungen")
        parts.append("- Führe ein **Gespräch** mit dem User gemäß der Phase-Anweisung oben.")
        parts.append("- Stelle Rückfragen, mache Vorschläge, iteriere — bis das Phasenziel erreicht ist.")
        parts.append("- Wenn die Phase abgeschlossen ist, fasse das Ergebnis **stichpunktartig** zusammen.")
        parts.append(f"- Rufe dann `workflow_advance(run_id=\"{run.id}\", output=\"<Zusammenfassung>\")` auf.")
        parts.append("- Gib die Zusammenfassung als `output` mit — sie wird für spätere Phasen gespeichert.")
        parts.append("")

        # Resources
        if resource_resolver:
            resource_parts = self.prompt_builder.assemble_resources(
                workflow_def, step, resource_resolver
            )
            if resource_parts:
                parts.extend(resource_parts)
                parts.append("")

        # Step prompt (with template resolution)
        if step.prompt:
            context = self.prompt_builder.build_template_context(workflow_def, run)
            prompt = self.prompt_builder.resolve_templates(step.prompt, context)
            parts.append(prompt)
            parts.append("")

        # Previous phase results
        if phases_output:
            parts.append("### Bisherige Ergebnisse")
            for p in all_phases:
                if p.id in phases_output:
                    p_name = p.name or p.id
                    parts.append(f"- **{p_name}:** {phases_output[p.id]}")
            parts.append("")

        return "\n".join(parts)

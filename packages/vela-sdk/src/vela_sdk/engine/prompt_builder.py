"""Prompt assembly and template resolution for workflow steps."""

import re
from typing import Any, Callable, Optional

from vela_sdk.engine.types import WorkflowRunState
from vela_sdk.schemas.resource import ResourceDefinition
from vela_sdk.schemas.workflow import (
    AnyStepDefinition,
    StepType,
    WorkflowDefinition,
)


class PromptBuilder:
    """Assembles prompts for workflow steps.

    Pure logic — no store dependency. Handles template resolution,
    progress indicators, resource assembly, and CTAs.
    """

    @staticmethod
    def build_template_context(
        workflow_def: WorkflowDefinition,
        run: WorkflowRunState,
    ) -> dict[str, Any]:
        """Build nested context dict for template resolution.

        Supports: {{params.X}}, {{steps.step_id.capture_key}}, {{state.key}}
        """
        state = run.state_data
        params = run.params

        # Build steps context: map step_id -> {capture_key: value}
        steps_context: dict[str, dict[str, Any]] = {}
        for step_def in workflow_def.steps:
            step_data = {}
            for cap in step_def.capture:
                if cap.key in state:
                    step_data[cap.key] = state[cap.key]
            if step_data:
                steps_context[step_def.id] = step_data

        return {
            "params": params,
            "steps": steps_context,
            "state": state,
        }

    @staticmethod
    def resolve_templates(text: str, context: dict) -> str:
        """Resolve {{variable}} templates in text."""
        def replacer(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            # Support dotted access: state.key
            key_parts = key.split(".")
            value: Any = context
            for part in key_parts:
                if isinstance(value, dict):
                    value = value.get(part, f"{{{{{key}}}}}")
                else:
                    return f"{{{{{key}}}}}"
            return str(value)

        return re.sub(r"\{\{(.+?)\}\}", replacer, text)

    @staticmethod
    def assemble_resources(
        workflow_def: WorkflowDefinition,
        step: AnyStepDefinition,
        resource_resolver: Callable[[str], Optional[ResourceDefinition]],
    ) -> list[str]:
        """Assemble resource sections for the prompt.

        Merges workflow-level and step-level resources (step wins on same ref).
        Resources < 500 chars are inlined; others are listed as URI references.
        """
        from vela_sdk.schemas.resource import ResourceReference
        # Merge: workflow-level first, step-level overrides
        merged: dict[str, ResourceReference] = {}
        for ref in workflow_def.resources:
            merged[ref.ref] = ref
        for ref in step.resources:
            merged[ref.ref] = ref

        if not merged:
            return []

        inline_parts: list[str] = []
        reference_parts: list[str] = []

        for ref_key, res_ref in merged.items():
            resource = resource_resolver(res_ref.ref)
            if not resource:
                continue

            # Determine inline vs reference
            should_inline = res_ref.inline
            if should_inline is None:
                should_inline = len(resource.content) < 500

            if should_inline:
                inline_parts.append(f"### {resource.name}")
                inline_parts.append(resource.content)
                inline_parts.append("")
            else:
                uri = resource.uri_pattern or f"vela://{resource.type.value}/{resource.id}"
                desc = f" — {resource.description}" if resource.description else ""
                reference_parts.append(f"- `{uri}`{desc}")

        parts: list[str] = []
        if inline_parts:
            parts.extend(inline_parts)
        if reference_parts:
            parts.append("### Available Resources")
            parts.extend(reference_parts)
            parts.append("*Lade mit `read_resource(\"URI\")` oder `vela_get_resource(id=\"...\")`.* ")

        return parts

    def assemble_prompt(
        self,
        workflow_def: WorkflowDefinition,
        run: WorkflowRunState,
        step: AnyStepDefinition,
        resource_resolver: Optional[Callable[[str], Optional[ResourceDefinition]]] = None,
    ) -> str:
        """Assemble the prompt for a step.

        Includes progress overview, depends_on context, resources, step prompt,
        capture info, and CTA.
        """
        state = run.state_data
        context = self.build_template_context(workflow_def, run)

        parts: list[str] = []

        # Header with step name
        step_name = step.name or step.id
        parts.append(f"## {workflow_def.name} — {step_name}")
        parts.append("")

        # Progress overview
        parts.append("### Fortschritt")
        for s in workflow_def.steps:
            s_name = s.name or s.id
            if s.id == step.id:
                parts.append(f"- **→ {s_name}** ← aktuell")
            elif any(cap.key in state for cap in s.capture):
                parts.append(f"- ~~{s_name}~~ ✓")
            else:
                parts.append(f"- {s_name}")
        parts.append("")

        # depends_on context: extract all field keys from DependsOnDefinition list
        if step.depends_on:
            parts.append("### Kontext aus vorherigen Steps:")
            for dep in step.depends_on:
                for field in dep.fields:
                    value = state.get(field, "(nicht erfasst)")
                    parts.append(f"- **{field}**: {value}")
            parts.append("")

        # Resources: merge workflow-level + step-level (step wins on same ref)
        if resource_resolver:
            resource_parts = self.assemble_resources(
                workflow_def, step, resource_resolver
            )
            if resource_parts:
                parts.extend(resource_parts)
                parts.append("")

        # Workflow-level tool requirements
        if workflow_def.tools:
            parts.append("### Benötigte externe Tools")
            for t in workflow_def.tools:
                server_hint = f" ({t.server})" if t.server else ""
                desc_hint = f" — {t.description}" if t.description else ""
                req_hint = "[erforderlich]" if t.required else "[optional]"
                parts.append(f"- **{t.name}**{server_hint}{desc_hint} {req_hint}")
            parts.append("")

        # Step-level tool hints
        if step.tools:
            tool_list = ", ".join(f"`{t}`" for t in step.tools)
            parts.append(f"### Tools für diesen Step")
            parts.append(f"Nutze folgende Tools: {tool_list}")
            parts.append("")

        # Step prompt with template resolution
        prompt = self.resolve_templates(step.prompt, context)
        parts.append(prompt)

        # Choice options
        if step.type == StepType.CHOICE and step.options:
            parts.append("")
            parts.append("### Optionen:")
            for i, opt in enumerate(step.options, 1):
                desc = f" — {opt.description}" if opt.description else ""
                parts.append(f"{i}. **{opt.label}**{desc}")

        # Capture info
        if step.capture:
            parts.append("")
            keys = [c.key for c in step.capture]
            parts.append(f"*Dieser Step erfasst: {', '.join(keys)}*")

        # CTA
        parts.append("")
        if step.type == StepType.CONFIRM:
            parts.append("**Bitte bestaetigen oder ablehnen.**")
        elif step.type == StepType.CHOICE:
            parts.append("**Bitte eine Option wählen.**")
        elif step.type == StepType.FREEFORM:
            parts.append("**Bitte Eingabe machen.**")
        elif step.type == StepType.EXECUTE:
            parts.append("**Ausführen, dann Abschluss bestaetigen.**")
        elif step.type == StepType.DIALOG:
            if state.get("_dialog_phase"):
                parts.append("**Dialog fortsetzen — aktuelle Phase bearbeiten.**")
            else:
                parts.append("**Dialog starten — advance aufrufen.**")

        return "\n".join(parts)

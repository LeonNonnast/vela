"""Vela-specific ParamFilter implementation.

Filters out application-level params (e.g. project_id) that are resolved
server-side rather than elicited from the user.
"""

from vela_sdk.schemas.workflow import ParamDefinition, WorkflowDefinition


class VelaParamFilter:
    """Filters out application params and returns missing required params."""

    def filter_missing_params(
        self, wf_def: WorkflowDefinition, provided_params: dict
    ) -> list[ParamDefinition]:
        return [
            p for p in wf_def.params
            if p.required and p.name not in provided_params and not p.application
        ]

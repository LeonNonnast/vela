"""Elicitation Service — maps CaptureDefinition to FastMCP ctx.elicit() calls."""

from typing import Any

from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)
from pydantic import BaseModel, Field, create_model

from vela_sdk.schemas.workflow import CaptureDefinition


def _titled_scalar(title: str, python_type: type) -> type:
    """Create a Pydantic model with a titled 'value' field.

    This ensures the MCP elicitation schema includes a human-readable title
    for the input field instead of the generic "value" label.
    """
    return create_model(
        "ElicitResponse",
        value=(python_type, Field(title=title)),
    )


class ElicitationService:
    """Stateless service for building and processing elicitation requests."""

    @staticmethod
    def needs_elicitation(
        captures: list[CaptureDefinition], state_data: dict
    ) -> list[CaptureDefinition]:
        """Filter captures that need elicitation.

        - elicit="always" -> always
        - elicit="if_missing" -> only if key not in state_data
        - elicit="never" -> never
        """
        result: list[CaptureDefinition] = []
        for cap in captures:
            if cap.elicit == "always":
                result.append(cap)
            elif cap.elicit == "if_missing" and cap.key not in state_data:
                result.append(cap)
            # elicit="never" -> skip
        return result

    @staticmethod
    def build_response_type(
        capture: CaptureDefinition,
    ) -> type | list[str] | dict[str, dict[str, str]] | list[list[str]] | None:
        """Map capture.input to FastMCP elicit response_type."""
        input_type = capture.input
        title = capture.label or capture.key

        if input_type == "confirm":
            return _titled_scalar(title, bool)
        elif input_type == "text":
            return _titled_scalar(title, str)
        elif input_type == "number":
            return _titled_scalar(title, int)
        elif input_type == "boolean":
            return _titled_scalar(title, bool)
        elif input_type == "select":
            if capture.options:
                has_labels = any(o.label != o.key for o in capture.options)
                if has_labels:
                    return {
                        o.key: {"title": o.label} for o in capture.options
                    }
                return [o.key for o in capture.options]
            return _titled_scalar(title, str)
        elif input_type == "multi-select":
            if capture.options:
                has_labels = any(o.label != o.key for o in capture.options)
                if has_labels:
                    return [
                        {o.key: {"title": o.label} for o in capture.options}
                    ]
                return [[o.key for o in capture.options]]
            return _titled_scalar(title, str)
        elif input_type is None:
            return _titled_scalar(title, str)
        else:
            return _titled_scalar(title, str)

    @staticmethod
    def build_message(capture: CaptureDefinition) -> str:
        """Build the elicit message from capture definition."""
        label = capture.label or capture.key

        parts = [label]

        if capture.placeholder:
            parts.append(f"(e.g. {capture.placeholder})")

        if capture.default is not None:
            parts.append(f"[default: {capture.default}]")

        return " ".join(parts)

    @staticmethod
    def process_result(
        capture: CaptureDefinition, result: Any
    ) -> tuple[str, Any] | None:
        """Process an ElicitationResult.

        - AcceptedElicitation -> (capture.key, result.data)
        - DeclinedElicitation/CancelledElicitation -> None
        """
        if isinstance(result, AcceptedElicitation):
            data = result.data
            # Extract value from Pydantic model (used for titled scalar fields)
            if isinstance(data, BaseModel) and hasattr(data, "value"):
                data = data.value
            return (capture.key, data)
        if isinstance(result, (DeclinedElicitation, CancelledElicitation)):
            return None
        return None

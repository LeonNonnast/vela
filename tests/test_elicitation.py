"""ElicitationService Tests — needs_elicitation, build_response_type, build_message, process_result."""

import pytest
from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)
from pydantic import BaseModel

from src.shared.schemas.workflow import CaptureDefinition, CaptureOption
from vela_sdk.fastmcp.elicitation import ElicitationService


# ---------------------------------------------------------------------------
# needs_elicitation
# ---------------------------------------------------------------------------
class TestNeedsElicitation:
    def test_always_returns_capture(self):
        caps = [CaptureDefinition(key="name", elicit="always")]
        result = ElicitationService.needs_elicitation(caps, {"name": "existing"})
        assert len(result) == 1
        assert result[0].key == "name"

    def test_if_missing_returns_when_absent(self):
        caps = [CaptureDefinition(key="name", elicit="if_missing")]
        result = ElicitationService.needs_elicitation(caps, {})
        assert len(result) == 1

    def test_if_missing_skips_when_present(self):
        caps = [CaptureDefinition(key="name", elicit="if_missing")]
        result = ElicitationService.needs_elicitation(caps, {"name": "val"})
        assert len(result) == 0

    def test_never_always_skipped(self):
        caps = [CaptureDefinition(key="name", elicit="never")]
        result = ElicitationService.needs_elicitation(caps, {})
        assert len(result) == 0

    def test_mixed_strategies(self):
        caps = [
            CaptureDefinition(key="a", elicit="always"),
            CaptureDefinition(key="b", elicit="if_missing"),
            CaptureDefinition(key="c", elicit="never"),
            CaptureDefinition(key="d", elicit="if_missing"),
        ]
        state = {"b": "exists"}
        result = ElicitationService.needs_elicitation(caps, state)
        keys = [c.key for c in result]
        assert keys == ["a", "d"]

    def test_empty_captures(self):
        result = ElicitationService.needs_elicitation([], {})
        assert result == []

    def test_if_missing_default_strategy(self):
        """Default elicit value is 'if_missing'."""
        caps = [CaptureDefinition(key="x")]
        result = ElicitationService.needs_elicitation(caps, {})
        assert len(result) == 1


# ---------------------------------------------------------------------------
# build_response_type
# ---------------------------------------------------------------------------
class TestBuildResponseType:
    def test_confirm_returns_titled_bool_model(self):
        cap = CaptureDefinition(key="ok", label="Confirm?", input="confirm")
        result = ElicitationService.build_response_type(cap)
        assert issubclass(result, BaseModel)
        schema = result.model_json_schema()
        assert schema["properties"]["value"]["type"] == "boolean"
        assert schema["properties"]["value"]["title"] == "Confirm?"

    def test_text_returns_titled_model(self):
        cap = CaptureDefinition(key="name", label="Your Name", input="text")
        result = ElicitationService.build_response_type(cap)
        assert issubclass(result, BaseModel)
        schema = result.model_json_schema()
        assert schema["properties"]["value"]["type"] == "string"
        assert schema["properties"]["value"]["title"] == "Your Name"

    def test_number_returns_titled_model(self):
        cap = CaptureDefinition(key="count", label="Count", input="number")
        result = ElicitationService.build_response_type(cap)
        assert issubclass(result, BaseModel)
        schema = result.model_json_schema()
        assert schema["properties"]["value"]["type"] == "integer"
        assert schema["properties"]["value"]["title"] == "Count"

    def test_boolean_returns_titled_model(self):
        cap = CaptureDefinition(key="flag", label="Enable?", input="boolean")
        result = ElicitationService.build_response_type(cap)
        assert issubclass(result, BaseModel)
        schema = result.model_json_schema()
        assert schema["properties"]["value"]["type"] == "boolean"
        assert schema["properties"]["value"]["title"] == "Enable?"

    def test_select_without_labels(self):
        cap = CaptureDefinition(
            key="choice",
            input="select",
            options=[
                CaptureOption(key="a", label="a"),
                CaptureOption(key="b", label="b"),
            ],
        )
        result = ElicitationService.build_response_type(cap)
        assert result == ["a", "b"]

    def test_select_with_labels(self):
        cap = CaptureDefinition(
            key="choice",
            input="select",
            options=[
                CaptureOption(key="a", label="Option A"),
                CaptureOption(key="b", label="Option B"),
            ],
        )
        result = ElicitationService.build_response_type(cap)
        assert result == {"a": {"title": "Option A"}, "b": {"title": "Option B"}}

    def test_select_no_options_falls_back_to_titled_model(self):
        cap = CaptureDefinition(key="choice", input="select")
        result = ElicitationService.build_response_type(cap)
        assert issubclass(result, BaseModel)

    def test_multi_select_without_labels(self):
        cap = CaptureDefinition(
            key="tags",
            input="multi-select",
            options=[
                CaptureOption(key="x", label="x"),
                CaptureOption(key="y", label="y"),
            ],
        )
        result = ElicitationService.build_response_type(cap)
        assert result == [["x", "y"]]

    def test_multi_select_with_labels(self):
        cap = CaptureDefinition(
            key="tags",
            input="multi-select",
            options=[
                CaptureOption(key="x", label="Tag X"),
                CaptureOption(key="y", label="Tag Y"),
            ],
        )
        result = ElicitationService.build_response_type(cap)
        assert result == [{"x": {"title": "Tag X"}, "y": {"title": "Tag Y"}}]

    def test_none_input_returns_titled_model(self):
        cap = CaptureDefinition(key="data")
        result = ElicitationService.build_response_type(cap)
        assert issubclass(result, BaseModel)

    def test_unknown_input_returns_titled_model(self):
        cap = CaptureDefinition(key="data", input="fancy-widget")
        result = ElicitationService.build_response_type(cap)
        assert issubclass(result, BaseModel)


# ---------------------------------------------------------------------------
# build_message
# ---------------------------------------------------------------------------
class TestBuildMessage:
    def test_label_used_when_present(self):
        cap = CaptureDefinition(key="name", label="Your Name")
        assert ElicitationService.build_message(cap) == "Your Name"

    def test_key_used_when_no_label(self):
        cap = CaptureDefinition(key="name")
        assert ElicitationService.build_message(cap) == "name"

    def test_placeholder_appended(self):
        cap = CaptureDefinition(key="email", placeholder="user@example.com")
        msg = ElicitationService.build_message(cap)
        assert "email" in msg
        assert "(e.g. user@example.com)" in msg

    def test_default_appended(self):
        cap = CaptureDefinition(key="scope", default="mvp")
        msg = ElicitationService.build_message(cap)
        assert "[default: mvp]" in msg

    def test_label_placeholder_and_default(self):
        cap = CaptureDefinition(
            key="scope", label="Project Scope", placeholder="mvp/full", default="mvp"
        )
        msg = ElicitationService.build_message(cap)
        assert msg == "Project Scope (e.g. mvp/full) [default: mvp]"


# ---------------------------------------------------------------------------
# process_result
# ---------------------------------------------------------------------------
class TestProcessResult:
    def test_accepted_returns_key_value(self):
        cap = CaptureDefinition(key="name")
        result = AcceptedElicitation(data="Alice")
        processed = ElicitationService.process_result(cap, result)
        assert processed == ("name", "Alice")

    def test_accepted_extracts_value_from_model(self):
        """Process result should extract .value from Pydantic model responses."""
        cap = CaptureDefinition(key="name")

        class FakeModel(BaseModel):
            value: str

        result = AcceptedElicitation(data=FakeModel(value="Alice"))
        processed = ElicitationService.process_result(cap, result)
        assert processed == ("name", "Alice")

    def test_accepted_with_dict_data(self):
        cap = CaptureDefinition(key="config")
        result = AcceptedElicitation(data={"a": 1})
        processed = ElicitationService.process_result(cap, result)
        assert processed == ("config", {"a": 1})

    def test_declined_returns_none(self):
        cap = CaptureDefinition(key="name")
        result = DeclinedElicitation()
        assert ElicitationService.process_result(cap, result) is None

    def test_cancelled_returns_none(self):
        cap = CaptureDefinition(key="name")
        result = CancelledElicitation()
        assert ElicitationService.process_result(cap, result) is None

    def test_unknown_result_returns_none(self):
        cap = CaptureDefinition(key="name")
        assert ElicitationService.process_result(cap, "garbage") is None

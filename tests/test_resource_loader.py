"""Resource Loader Tests — YAML parsing, validation."""

import os

import pytest
import yaml

from src.shared.schemas.resource import ResourceDefinition, ResourceType
from src.shared.services.resource_loader import load_resource_file, load_resources


class TestLoadResourceFile:
    def test_load_valid_resource(self, tmp_path):
        data = {
            "id": "test-res",
            "name": "Test Resource",
            "type": "convention",
            "content": "Use snake_case.",
        }
        filepath = tmp_path / "test-res.yaml"
        filepath.write_text(yaml.dump(data))

        result = load_resource_file(str(filepath))
        assert result is not None
        assert result.id == "test-res"
        assert result.name == "Test Resource"
        assert result.type == ResourceType.CONVENTION
        assert result.content == "Use snake_case."

    def test_load_derives_id_from_filename(self, tmp_path):
        data = {
            "name": "No ID",
            "type": "example",
            "content": "example content",
        }
        filepath = tmp_path / "derived-id.yaml"
        filepath.write_text(yaml.dump(data))

        result = load_resource_file(str(filepath))
        assert result is not None
        assert result.id == "derived-id"

    def test_load_empty_file(self, tmp_path):
        filepath = tmp_path / "empty.yaml"
        filepath.write_text("")
        result = load_resource_file(str(filepath))
        assert result is None

    def test_load_invalid_yaml(self, tmp_path):
        filepath = tmp_path / "bad.yaml"
        filepath.write_text("{{invalid yaml")
        result = load_resource_file(str(filepath))
        assert result is None

    def test_load_with_all_fields(self, tmp_path):
        data = {
            "id": "full-res",
            "name": "Full Resource",
            "type": "schema",
            "description": "A full resource",
            "content": "schema content here",
            "mime_type": "application/yaml",
            "tags": ["schema", "test"],
            "uri_pattern": "vela://custom/full-res",
        }
        filepath = tmp_path / "full-res.yaml"
        filepath.write_text(yaml.dump(data))

        result = load_resource_file(str(filepath))
        assert result is not None
        assert result.mime_type == "application/yaml"
        assert result.tags == ["schema", "test"]
        assert result.uri_pattern == "vela://custom/full-res"

    def test_load_invalid_type(self, tmp_path):
        data = {
            "id": "bad-type",
            "name": "Bad Type",
            "type": "nonexistent",
            "content": "x",
        }
        filepath = tmp_path / "bad-type.yaml"
        filepath.write_text(yaml.dump(data))

        result = load_resource_file(str(filepath))
        assert result is None


class TestLoadResources:
    def test_load_directory(self, tmp_path):
        for name, res_id, res_type in [
            ("a.yaml", "a", "convention"),
            ("b.yaml", "b", "example"),
        ]:
            (tmp_path / name).write_text(yaml.dump({
                "id": res_id,
                "name": f"Res {res_id}",
                "type": res_type,
                "content": f"content for {res_id}",
            }))

        result = load_resources(str(tmp_path))
        assert len(result) == 2
        assert "a" in result
        assert "b" in result

    def test_load_nonexistent_directory(self):
        result = load_resources("/nonexistent/path")
        assert result == {}

    def test_skips_non_yaml(self, tmp_path):
        (tmp_path / "readme.md").write_text("# Not a resource")
        (tmp_path / "res.yaml").write_text(yaml.dump({
            "id": "res",
            "name": "Res",
            "type": "reference",
            "content": "x",
        }))

        result = load_resources(str(tmp_path))
        assert len(result) == 1


class TestExampleResources:
    def test_example_resources_load(self):
        """Verify bundled example resources load correctly."""
        examples_dir = os.path.join(
            os.path.dirname(__file__), "..", "examples", "resources"
        )
        if not os.path.isdir(examples_dir):
            pytest.skip("Example resources directory not found")

        result = load_resources(examples_dir)
        assert len(result) >= 2
        assert "test-guidelines" in result
        assert "elicitation-cheatsheet" in result

    def test_python_conventions_is_short(self):
        """Python conventions resource should be < 500 chars (inline candidate)."""
        examples_dir = os.path.join(
            os.path.dirname(__file__), "..", "examples", "resources"
        )
        result = load_resources(examples_dir)
        if "python-conventions" not in result:
            pytest.skip("python-conventions not found")
        assert len(result["python-conventions"].content) < 500

    def test_repository_pattern_is_long(self):
        """Repository pattern resource should be >= 500 chars (on-demand)."""
        examples_dir = os.path.join(
            os.path.dirname(__file__), "..", "examples", "resources"
        )
        result = load_resources(examples_dir)
        if "repository-pattern" not in result:
            pytest.skip("repository-pattern not found")
        assert len(result["repository-pattern"].content) >= 500

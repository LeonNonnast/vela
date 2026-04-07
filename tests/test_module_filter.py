"""Tests for ModuleFilter — glob-based filtering for VELA_MODULES."""

import pytest

from src.shared.services.module_filter import ModuleFilter


class TestModuleFilterEmpty:
    """Empty filter matches everything."""

    def test_empty_string_matches_all(self):
        f = ModuleFilter("")
        assert f.matches("anything") is True
        assert f.matches("migration-pack") is True

    def test_no_arg_matches_all(self):
        f = ModuleFilter()
        assert f.matches("anything") is True

    def test_active_is_false(self):
        f = ModuleFilter("")
        assert f.active is False

    def test_filter_dict_returns_all(self):
        f = ModuleFilter("")
        d = {"a": 1, "b": 2}
        assert f.filter_dict(d) == d

    def test_filter_list_returns_all(self):
        f = ModuleFilter("")
        names = ["a", "b", "c"]
        assert f.filter_list(names) == names


class TestModuleFilterSinglePattern:
    """Single glob pattern."""

    def test_wildcard_matches(self):
        f = ModuleFilter("migration-*")
        assert f.matches("migration-pack") is True
        assert f.matches("migration-v2") is True

    def test_wildcard_no_match(self):
        f = ModuleFilter("migration-*")
        assert f.matches("brainstorming") is False
        assert f.matches("team-a-ops") is False

    def test_active_is_true(self):
        f = ModuleFilter("migration-*")
        assert f.active is True


class TestModuleFilterMultiplePatterns:
    """Comma-separated patterns."""

    def test_multiple_patterns(self):
        f = ModuleFilter("migration-*,team-*")
        assert f.matches("migration-pack") is True
        assert f.matches("team-a-ops") is True
        assert f.matches("brainstorming") is False

    def test_whitespace_in_patterns(self):
        f = ModuleFilter("migration-* , team-* ")
        assert f.matches("migration-pack") is True
        assert f.matches("team-a-ops") is True

    def test_empty_segments_ignored(self):
        f = ModuleFilter("migration-*,,team-*,")
        assert len(f.patterns) == 2


class TestModuleFilterExactMatch:
    """Exact name (no glob chars) matches only that name."""

    def test_exact_match(self):
        f = ModuleFilter("brainstorming")
        assert f.matches("brainstorming") is True
        assert f.matches("brainstorming-v2") is False
        assert f.matches("other") is False


class TestModuleFilterDict:
    """filter_dict with @version keys."""

    def test_filter_dict_with_version_suffix(self):
        f = ModuleFilter("migration-*")
        d = {
            "migration-pack@1.0.0": "a",
            "migration-pack@2.0.0": "b",
            "brainstorming@1.0.0": "c",
        }
        result = f.filter_dict(d)
        assert "migration-pack@1.0.0" in result
        assert "migration-pack@2.0.0" in result
        assert "brainstorming@1.0.0" not in result

    def test_filter_dict_without_version(self):
        f = ModuleFilter("team-*")
        d = {"team-ops": 1, "team-dev": 2, "other": 3}
        result = f.filter_dict(d)
        assert result == {"team-ops": 1, "team-dev": 2}


class TestModuleFilterList:
    """filter_list."""

    def test_filter_list(self):
        f = ModuleFilter("migration-*,shared-*")
        names = ["migration-pack", "shared-utils", "brainstorming", "other"]
        result = f.filter_list(names)
        assert result == ["migration-pack", "shared-utils"]

    def test_filter_list_empty_result(self):
        f = ModuleFilter("nonexistent-*")
        names = ["migration-pack", "brainstorming"]
        result = f.filter_list(names)
        assert result == []

"""Tests for ModuleHubModule — parse_repo_string and tool registration."""

import pytest

from src.mcp.modules.module_hub_module import parse_repo_string


class TestParseRepoString:
    def test_parse_repo_string_owner_name(self):
        """Standard 'owner/name' format."""
        owner, name = parse_repo_string("acme/vela-modules")
        assert owner == "acme"
        assert name == "vela-modules"

    def test_parse_repo_string_url(self):
        """Full GitHub URL."""
        owner, name = parse_repo_string("https://github.com/acme/vela-modules")
        assert owner == "acme"
        assert name == "vela-modules"

    def test_parse_repo_string_url_with_git(self):
        """GitHub URL ending in .git."""
        owner, name = parse_repo_string("https://github.com/acme/vela-modules.git")
        assert owner == "acme"
        assert name == "vela-modules"

    def test_parse_repo_string_url_trailing_slash(self):
        """GitHub URL with trailing slash."""
        owner, name = parse_repo_string("https://github.com/acme/vela-modules/")
        assert owner == "acme"
        assert name == "vela-modules"

    def test_parse_repo_string_with_whitespace(self):
        """Input with leading/trailing whitespace."""
        owner, name = parse_repo_string("  acme/vela-modules  ")
        assert owner == "acme"
        assert name == "vela-modules"

    def test_parse_repo_string_invalid_single_segment(self):
        """Single segment should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid repo format"):
            parse_repo_string("just-a-name")

    def test_parse_repo_string_invalid_empty(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid repo format"):
            parse_repo_string("")

    def test_parse_repo_string_invalid_too_many_segments(self):
        """Three slash-separated segments (not a URL) should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid repo format"):
            parse_repo_string("a/b/c")

    def test_parse_repo_string_http_url(self):
        """HTTP (non-HTTPS) URL."""
        owner, name = parse_repo_string("http://github.com/acme/modules")
        assert owner == "acme"
        assert name == "modules"

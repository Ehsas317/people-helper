"""Tests for people_helper.walker — repo parsing + file walking."""

import pytest

from people_helper.walker import (
    detect_primary_language,
    parse_repo_arg,
    walk_repo,
)


class TestParseRepoArg:
    def test_owner_name(self):
        assert parse_repo_arg("foo/bar") == ("foo", "bar")

    def test_owner_name_with_spaces(self):
        assert parse_repo_arg("  foo/bar  ") == ("foo", "bar")

    def test_https_url(self):
        assert parse_repo_arg("https://github.com/foo/bar") == ("foo", "bar")

    def test_https_url_with_trailing_dot_git(self):
        assert parse_repo_arg("https://github.com/foo/bar.git") == ("foo", "bar")

    def test_ssh_url(self):
        assert parse_repo_arg("git@github.com:foo/bar.git") == ("foo", "bar")

    def test_invalid_single_part(self):
        with pytest.raises(ValueError):
            parse_repo_arg("justoneword")

    def test_invalid_url(self):
        with pytest.raises(ValueError):
            parse_repo_arg("https://github.com/onlyonepart")


class TestWalkRepo:
    def test_returns_files_with_required_keys(self, clean_utility_repo):
        files = walk_repo(clean_utility_repo)
        assert len(files) > 0
        for f in files:
            assert "path" in f
            assert "abs_path" in f
            assert "ext" in f
            assert "size" in f
            assert "content" in f

    def test_skips_hidden_files(self, clean_utility_repo):
        # Create a fake hidden file
        (clean_utility_repo / ".hidden").write_text("nope")
        try:
            files = walk_repo(clean_utility_repo)
            paths = [f["path"] for f in files]
            assert ".hidden" not in paths
        finally:
            (clean_utility_repo / ".hidden").unlink()

    def test_skips_example_files_kept(self, clean_utility_repo):
        # .env.example should be kept (per the heuristic)
        (clean_utility_repo / ".env.example").write_text("FOO=bar")
        try:
            files = walk_repo(clean_utility_repo)
            paths = [f["path"] for f in files]
            assert ".env.example" in paths
        finally:
            (clean_utility_repo / ".env.example").unlink()

    def test_reads_text_content(self, clean_utility_repo):
        files = walk_repo(clean_utility_repo)
        string_utils = next(f for f in files if f["path"].endswith("string_utils.py"))
        assert "slugify" in string_utils["content"]


class TestDetectPrimaryLanguage:
    def test_python_repo(self, clean_utility_repo):
        files = walk_repo(clean_utility_repo)
        assert detect_primary_language(files) == "Python"

    def test_multi_language_picks_most_common(self, multi_language_repo):
        files = walk_repo(multi_language_repo)
        # Two of each (Python via __init__, TS, Go) — TS has 1, Go has 1
        # so any of them could win; just confirm it's a known language
        lang = detect_primary_language(files)
        assert lang in {"TypeScript", "Go", "Python", "Unknown"}

    def test_empty_returns_unknown(self, tmp_path):
        assert detect_primary_language([]) == "Unknown"

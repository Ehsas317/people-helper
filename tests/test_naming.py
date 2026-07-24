"""Tests for people_helper.naming — name + tag generation."""

from people_helper.models import Candidate
from people_helper.naming import suggest_name, suggest_tags


def _cand(path: str, docstring: str = "", language: str = "Python") -> Candidate:
    return Candidate(
        path=path, language=language, loc=50,
        has_tests=False, has_docstring=bool(docstring),
        internal_imports=0, external_imports=0,
        filename_score=0.0,
        docstring_snippet=docstring,
    )


class TestSuggestName:
    def test_simple_utility(self):
        c = _cand("src/string_utils.py")
        assert suggest_name(c) == "string-utils"

    def test_generic_name_uses_parent(self):
        c = _cand("src/auth/utils.py")
        name = suggest_name(c)
        assert "auth" in name

    def test_strips_invalid_chars(self):
        c = _cand("src/foo_bar.baz.py")
        name = suggest_name(c)
        assert all(ch.isalnum() or ch == "-" for ch in name)
        assert "foo-bar-baz" in name

    def test_never_empty(self):
        c = _cand("x.py")
        assert suggest_name(c)
        assert len(suggest_name(c)) > 0


class TestSuggestTags:
    def test_includes_language_tag(self):
        c = _cand("src/foo.py", language="Python")
        tags = suggest_tags(c)
        assert "python" in tags

    def test_includes_language_tag_ts(self):
        c = _cand("src/foo.ts", language="TypeScript")
        tags = suggest_tags(c)
        assert "typescript" in tags

    def test_utility_pattern_adds_utility_tag(self):
        c = _cand("src/string_utils.py")
        tags = suggest_tags(c)
        assert "utility" in tags

    def test_validator_adds_validation_tag(self):
        c = _cand("src/email_validator.py")
        tags = suggest_tags(c)
        assert "validation" in tags

    def test_capped_at_8(self):
        c = _cand(
            "src/util.py",
            docstring="parse convert validate sanitize cache retry log auth jwt limit",
        )
        tags = suggest_tags(c)
        assert len(tags) <= 8

    def test_always_includes_open_source(self):
        c = _cand("src/foo.py")
        tags = suggest_tags(c)
        assert "open-source" in tags
        assert "library" in tags

    def test_filters_noise_words_from_docstring(self):
        c = _cand(
            "src/foo.py",
            docstring="the module for the function and class with import from file",
        )
        tags = suggest_tags(c)
        # Noise words should not be tags
        for noise in ["the", "module", "for", "function", "class", "and", "with", "import", "from", "file"]:
            assert noise not in tags

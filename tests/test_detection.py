"""Tests for people_helper.detection — candidate detection heuristics."""

from people_helper.detection import (
    build_import_graph,
    compute_fan_in,
    compute_filename_score,
    count_imports,
    count_loc,
    cyclomatic_complexity_python,
    detect_candidates,
    detect_docstring,
    find_cycles_scc,
    has_test_for,
    is_framework_route,
)
from people_helper.walker import detect_primary_language, walk_repo


class TestCountLoc:
    def test_simple(self):
        assert count_loc("x = 1\ny = 2\n") == 2

    def test_skips_blank_lines(self):
        assert count_loc("\n\nx = 1\n\n") == 1

    def test_skips_comment_only(self):
        assert count_loc("# comment\nx = 1\n") == 1

    def test_empty(self):
        assert count_loc("") == 0

    def test_only_comments(self):
        assert count_loc("# a\n# b\n") == 0


class TestDetectDocstring:
    def test_python_module_docstring(self):
        content = '"""Module docstring."""\n\nx = 1\n'
        has, snippet = detect_docstring(content, ".py")
        assert has is True
        assert "Module docstring" in snippet

    def test_python_no_docstring(self):
        content = "x = 1\n"
        has, _ = detect_docstring(content, ".py")
        assert has is False

    def test_jsdoc(self):
        content = "/**\n * JSDoc.\n */\nexport function f() {}\n"
        has, snippet = detect_docstring(content, ".ts")
        assert has is True
        assert "JSDoc" in snippet

    def test_go_package_comment(self):
        content = "// Package foo does foo.\n// Second line.\npackage foo\n"
        has, snippet = detect_docstring(content, ".go")
        assert has is True
        assert "Package foo" in snippet

    def test_rust_module_doc(self):
        content = "//! Module doc.\n//! Second line.\npub fn x() {}\n"
        has, snippet = detect_docstring(content, ".rs")
        assert has is True


class TestCountImports:
    def test_python_internal_relative(self):
        content = "from . import sibling\n"
        project_files = {"src/sibling.py"}
        internal, external = count_imports(content, ".py", project_files)
        assert internal == 1
        assert external == 0

    def test_python_external(self):
        content = "import httpx\nimport json\n"
        project_files = set()
        internal, external = count_imports(content, ".py", project_files)
        assert internal == 0
        assert external == 2

    def test_js_internal_relative(self):
        content = "import { foo } from './foo';\n"
        project_files = set()
        internal, external = count_imports(content, ".ts", project_files)
        assert internal == 1
        assert external == 0

    def test_js_external(self):
        content = "import React from 'react';\n"
        project_files = set()
        internal, external = count_imports(content, ".tsx", project_files)
        assert internal == 0
        assert external == 1


class TestFilenameScore:
    def test_utility_pattern_positive(self):
        assert compute_filename_score("src/string_utils.py") > 0

    def test_framework_entry_negative(self):
        assert compute_filename_score("src/pages/index.tsx") < 0

    def test_test_file_negative(self):
        assert compute_filename_score("src/foo.test.ts") < 0

    def test_neutral(self):
        assert compute_filename_score("src/foo.py") == 0


class TestIsFrameworkRoute:
    def test_nextjs_pages_dir(self):
        assert is_framework_route("src/pages/index.tsx") is True

    def test_nextjs_app_dir(self):
        assert is_framework_route("src/app/page.tsx") is True

    def test_normal_utility(self):
        assert is_framework_route("src/utils/format.ts") is False


class TestHasTestFor:
    def test_python_test_sibling(self):
        files = {"src/foo.py", "tests/test_foo.py"}
        assert has_test_for("src/foo.py", files) is True

    def test_python_test_no_match(self):
        files = {"src/foo.py", "src/bar.py"}
        assert has_test_for("src/foo.py", files) is False

    def test_js_test_sibling(self):
        files = {"src/foo.ts", "src/foo.test.ts"}
        assert has_test_for("src/foo.ts", files) is True


class TestCyclomaticComplexity:
    def test_flat_function(self):
        src = "def f(x):\n    return x + 1\n"
        assert cyclomatic_complexity_python(src) == 1

    def test_if_else(self):
        src = "def f(x):\n    if x > 0:\n        return 1\n    else:\n        return 2\n"
        assert cyclomatic_complexity_python(src) == 2

    def test_many_branches(self):
        src = (
            "def f(x):\n"
            "    if x == 1:\n        return 1\n"
            "    elif x == 2:\n        return 2\n"
            "    elif x == 3:\n        return 3\n"
            "    elif x == 4:\n        return 4\n"
            "    return 0\n"
        )
        assert cyclomatic_complexity_python(src) == 5

    def test_syntax_error_returns_zero(self):
        # Should not raise
        assert cyclomatic_complexity_python("def f(:\n") == 0

    def test_god_function_high_complexity(self, god_function_repo):
        files = walk_repo(god_function_repo)
        god_file = next(f for f in files if f["path"].endswith("god_function.py"))
        cc = cyclomatic_complexity_python(god_file["content"])
        assert cc >= 20, f"expected cc>=20, got {cc}"


class TestImportGraph:
    def test_clean_repo_no_cycles(self, clean_utility_repo):
        files = walk_repo(clean_utility_repo)
        graph = build_import_graph(files)
        cycles = find_cycles_scc(graph)
        assert cycles == []

    def test_cycle_detection(self, import_cycle_repo):
        files = walk_repo(import_cycle_repo)
        graph = build_import_graph(files)
        cycles = find_cycles_scc(graph)
        assert len(cycles) >= 1, f"expected at least 1 cycle, got {cycles}"

    def test_fan_in_zero_for_orphan(self, orphan_leaf_repo):
        files = walk_repo(orphan_leaf_repo)
        graph = build_import_graph(files)
        fan_in = compute_fan_in(graph)
        # orphan.py should have fan_in == 0
        orphan_path = next(
            p for p in fan_in
            if p.endswith("orphan.py")
        )
        assert fan_in[orphan_path] == 0, f"expected 0, got {fan_in[orphan_path]}"

    def test_fan_in_high_for_database_stub(self, coupled_core_repo):
        files = walk_repo(coupled_core_repo)
        graph = build_import_graph(files)
        fan_in = compute_fan_in(graph)
        # database.py is imported by config_loader.py — fan_in >= 1
        db_path = next(
            p for p in fan_in
            if p.endswith("database.py")
        )
        assert fan_in[db_path] >= 1


class TestDetectCandidatesIntegration:
    def test_clean_utility_flagged_as_extractable(self, clean_utility_repo):
        files = walk_repo(clean_utility_repo)
        lang = detect_primary_language(files)
        candidates = detect_candidates(files, lang)
        active = [c for c in candidates if not c.skipped]
        paths = [c.path for c in active]
        assert any("string_utils" in p for p in paths), \
            f"string_utils should be flagged, got: {paths}"

    def test_coupled_core_skipped(self, coupled_core_repo):
        files = walk_repo(coupled_core_repo)
        lang = detect_primary_language(files)
        candidates = detect_candidates(files, lang)
        skipped = [c for c in candidates if c.skipped]
        # config_loader should be skipped (3 internal imports)
        config_loader_skipped = any(
            "config_loader" in c.path for c in skipped
        )
        assert config_loader_skipped, \
            f"config_loader should be skipped, got skipped={[c.path for c in skipped]}"

    def test_orphan_flagged_with_orphan_hint(self, orphan_leaf_repo):
        files = walk_repo(orphan_leaf_repo)
        lang = detect_primary_language(files)
        candidates = detect_candidates(files, lang)
        active = [c for c in candidates if not c.skipped]
        orphan = next(
            (c for c in active if "orphan" in c.path),
            None,
        )
        assert orphan is not None, "orphan.py should be flagged as extractable"
        # Should have an orphan-related reason
        reasons_joined = " ".join(orphan.why_extractable).lower()
        assert "orphan" in reasons_joined or "fan-in" in reasons_joined or "self-contained" in reasons_joined, \
            f"expected orphan/fan-in reason, got: {orphan.why_extractable}"

    def test_god_function_low_score_or_skipped(self, god_function_repo):
        files = walk_repo(god_function_repo)
        lang = detect_primary_language(files)
        candidates = detect_candidates(files, lang)
        # god_function should either be skipped or have a low code_quality score
        god = next(
            (c for c in candidates if "god_function" in c.path),
            None,
        )
        assert god is not None
        # If active, it should have a complexity penalty
        if not god.skipped:
            assert god.code_quality <= 5.0, \
                f"god_function should be penalized, got code_quality={god.code_quality}"

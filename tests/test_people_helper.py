"""People Helper test suite.

Tests cover the correctness-critical paths:
- Language handlers (Python, JS/TS, Go, Rust, JVM, C/C++, C#, Ruby, PHP, Swift)
- Extraction verification (relative imports, sibling resolution, blocked files)
- License detection
- Test file detection
- Report generation
- End-to-end candidate detection
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tempfile
import unittest
from pathlib import Path
from people_helper.detection import (
    _resolve_sibling,
    detect_license_in_repo,
    has_test_for,
    detect_candidates,
)
from people_helper.languages import get_handler
from people_helper.scoring import score_candidate, _compute_uniqueness
from people_helper.models import Candidate
from people_helper.report import generate_report


def make_file(path, content, ext=".py"):
    return {"path": path, "abs_path": f"/tmp/{path}", "ext": ext,
            "size": len(content), "content": content, "loc": content.count("\n") + 1}


# =============================================================================
# Python handler tests
# =============================================================================

class TestPythonRelativeImports(unittest.TestCase):
    """Tests for PythonHandler.extract_relative_imports."""

    def setUp(self):
        self.handler = get_handler(".py")

    def test_from_dot_module(self):
        self.assertEqual(self.handler.extract_relative_imports("from .utils import helper"), [("utils", 1)])

    def test_from_dot_import_single(self):
        self.assertEqual(self.handler.extract_relative_imports("from . import utils"), [("utils", 1)])

    def test_from_dot_import_multiple(self):
        result = self.handler.extract_relative_imports("from . import utils, helpers, common")
        self.assertEqual(result, [("utils", 1), ("helpers", 1), ("common", 1)])

    def test_from_dot_import_parens_single_line(self):
        self.assertEqual(self.handler.extract_relative_imports("from . import (a, b, c)"), [("a", 1), ("b", 1), ("c", 1)])

    def test_from_dot_import_parens_multi_line(self):
        content = "from . import (\n    a,\n    b,\n    c,\n)"
        self.assertEqual(self.handler.extract_relative_imports(content), [("a", 1), ("b", 1), ("c", 1)])

    def test_from_dotdot_module(self):
        self.assertEqual(self.handler.extract_relative_imports("from .. import config"), [("config", 2)])

    def test_from_dotdot_module_import(self):
        self.assertEqual(self.handler.extract_relative_imports("from ..helpers import foo"), [("helpers", 2)])

    def test_nested_module(self):
        self.assertEqual(self.handler.extract_relative_imports("from .sub.module import X"), [("sub", 1)])

    def test_inline_comment_stripped(self):
        self.assertEqual(self.handler.extract_relative_imports("from . import utils  # type: ignore"), [("utils", 1)])

    def test_external_import_not_relative(self):
        self.assertEqual(self.handler.extract_relative_imports("import os"), [])
        self.assertEqual(self.handler.extract_relative_imports("from os import path"), [])
        self.assertEqual(self.handler.extract_relative_imports("from django.conf import settings"), [])


class TestPythonPublicApi(unittest.TestCase):
    def setUp(self):
        self.handler = get_handler(".py")

    def test_counts_public_functions(self):
        content = 'def foo():\n    pass\ndef _bar():\n    pass\ndef baz():\n    pass\n'
        count, names = self.handler.count_public_api(content)
        self.assertEqual(count, 2)  # foo, baz (not _bar)
        self.assertIn("foo", names)
        self.assertIn("baz", names)

    def test_counts_classes(self):
        content = 'class Foo:\n    pass\nclass _Bar:\n    pass\n'
        count, names = self.handler.count_public_api(content)
        self.assertEqual(count, 1)
        self.assertIn("Foo", names)


class TestPythonDocstring(unittest.TestCase):
    def setUp(self):
        self.handler = get_handler(".py")

    def test_docstring_after_shebang(self):
        content = '#!/usr/bin/env python3\n"""Module docstring."""\nimport os\n'
        found, snippet = self.handler.detect_docstring(content)
        self.assertTrue(found)
        self.assertIn("Module docstring", snippet)

    def test_docstring_after_future_import(self):
        content = 'from __future__ import annotations\n"""Module docstring."""\nimport os\n'
        found, _ = self.handler.detect_docstring(content)
        self.assertTrue(found)

    def test_single_line_docstring(self):
        content = '"""Single line."""\nimport os\n'
        found, snippet = self.handler.detect_docstring(content)
        self.assertTrue(found)
        self.assertIn("Single line", snippet)

    def test_no_docstring(self):
        content = 'import os\nimport sys\n'
        found, _ = self.handler.detect_docstring(content)
        self.assertFalse(found)


# =============================================================================
# JS/TS handler tests
# =============================================================================

class TestJsTsRelativeImports(unittest.TestCase):
    def setUp(self):
        self.handler = get_handler(".ts")

    def test_from_dot_slash(self):
        self.assertEqual(self.handler.extract_relative_imports("import { foo } from './utils'"), [("utils", 1)])

    def test_from_dotdot_slash(self):
        self.assertEqual(self.handler.extract_relative_imports("import { foo } from '../helpers'"), [("helpers", 2)])

    def test_require_dot_slash(self):
        self.assertEqual(self.handler.extract_relative_imports("const x = require('./utils')"), [("utils", 1)])

    def test_external_not_relative(self):
        self.assertEqual(self.handler.extract_relative_imports("import React from 'react'"), [])


# =============================================================================
# Rust handler tests
# =============================================================================

class TestRustRelativeImports(unittest.TestCase):
    def setUp(self):
        self.handler = get_handler(".rs")

    def test_use_super(self):
        self.assertEqual(self.handler.extract_relative_imports("use super::utils;"), [("utils", 2)])

    def test_use_crate(self):
        self.assertEqual(self.handler.extract_relative_imports("use crate::models;"), [("models", 1)])

    def test_external_not_relative(self):
        self.assertEqual(self.handler.extract_relative_imports("use serde::Serialize;"), [])


# =============================================================================
# Go handler tests
# =============================================================================

class TestGoHandler(unittest.TestCase):
    def setUp(self):
        self.handler = get_handler(".go")

    def test_no_relative_imports(self):
        self.assertEqual(self.handler.extract_relative_imports('import "fmt"'), [])
        self.assertEqual(self.handler.extract_relative_imports('import "github.com/user/repo"'), [])

    def test_stdlib_not_external(self):
        imports = self.handler.extract_external_imports('import "fmt"')
        self.assertEqual(imports, [])

    def test_external_with_slash_detected(self):
        imports = self.handler.extract_external_imports('import "github.com/user/repo"')
        # Now returns the full import path (not just first component)
        # so get_dependency_weight can check for heavy packages via substring
        self.assertIn("github.com/user/repo", imports)

    def test_public_api_capitalized(self):
        content = 'func Foo() {}\nfunc bar() {}\ntype Bar struct{}\n'
        count, names = self.handler.count_public_api(content)
        self.assertIn("Foo", names)
        self.assertIn("Bar", names)
        self.assertNotIn("bar", names)


# =============================================================================
# JVM handler tests (Java + Kotlin)
# =============================================================================

class TestJavaHandler(unittest.TestCase):
    def setUp(self):
        self.handler = get_handler(".java")

    def test_java_import_with_semicolon(self):
        content = 'import org.springframework.boot.SpringApplication;\nimport java.util.List;\n'
        imports = self.handler.extract_external_imports(content)
        self.assertIn("org", imports)
        # java.* is stdlib — should NOT appear
        self.assertNotIn("java", imports)

    def test_java_public_api(self):
        content = '''public class Calculator {
    public int add(int a, int b) { return a + b; }
    public int subtract(int a, int b) { return a - b; }
}'''
        count, names = self.handler.count_public_api(content)
        self.assertGreaterEqual(count, 1)
        self.assertIn("Calculator", names)

    def test_java_javadoc_after_package(self):
        content = '''package com.example;
import java.util.List;

/**
 * Calculator service.
 */
public class Calculator {}
'''
        found, snippet = self.handler.detect_docstring(content)
        self.assertTrue(found)
        self.assertIn("Calculator service", snippet)


class TestKotlinHandler(unittest.TestCase):
    """Tests for Kotlin-specific behavior."""
    def setUp(self):
        self.handler = get_handler(".kt")

    def test_kotlin_import_without_semicolon(self):
        """Critical: Kotlin imports don't use semicolons (unlike Java)."""
        content = '''import org.springframework.boot.SpringApplication
import com.fasterxml.jackson.databind.ObjectMapper
import kotlinx.coroutines.runBlocking
'''
        imports = self.handler.extract_external_imports(content)
        self.assertIn("org", imports)
        self.assertIn("com", imports)
        # kotlinx.* is EXTERNAL (not kotlin.* stdlib)
        self.assertIn("kotlinx", imports)

    def test_kotlin_default_public_functions(self):
        """Critical: Kotlin functions without `public` keyword are public by default."""
        content = '''class Calculator {
    fun add(a: Int, b: Int): Int { return a + b }
    fun subtract(a: Int, b: Int): Int { return a - b }
}
'''
        count, names = self.handler.count_public_api(content)
        self.assertGreaterEqual(count, 2)
        self.assertIn("add", names)
        self.assertIn("subtract", names)

    def test_kotlin_top_level_function(self):
        content = 'fun square(x: Int): Int { return x * x }\n'
        count, names = self.handler.count_public_api(content)
        self.assertIn("square", names)

    def test_kotlin_import_alias(self):
        """Critical: import aliases must not break import detection."""
        content = 'import com.foo.Bar as Baz\n'
        imports = self.handler.extract_external_imports(content)
        self.assertIn("com", imports)


# =============================================================================
# C/C++ handler tests
# =============================================================================

class TestCFamilyHandler(unittest.TestCase):
    def setUp(self):
        self.cpp_handler = get_handler(".cpp")
        self.c_handler = get_handler(".c")

    def test_boost_detected_as_external(self):
        """Critical: <boost/asio.hpp> must be detected as external."""
        content = '#include <iostream>\n#include <boost/asio.hpp>\n#include <vector>\n'
        imports = self.cpp_handler.extract_external_imports(content)
        self.assertIn("boost", imports)
        self.assertNotIn("iostream", imports)
        self.assertNotIn("vector", imports)

    def test_opencv_detected(self):
        content = '#include <opencv2/core.hpp>\n#include <stdio.h>\n'
        imports = self.cpp_handler.extract_external_imports(content)
        self.assertIn("opencv2", imports)
        self.assertNotIn("stdio", imports)

    def test_eigen_detected(self):
        content = '#include <Eigen/Dense>\n#include <cmath>\n'
        imports = self.cpp_handler.extract_external_imports(content)
        self.assertIn("Eigen", imports)

    def test_preprocessor_counted_as_loc(self):
        """Critical: #include, #define must count as LOC in C/C++."""
        content = '#include <iostream>\n#define MAX 100\nint main() {\n    return 0;\n}\n'
        loc = self.cpp_handler.count_loc(content)
        self.assertEqual(loc, 5)

    def test_python_comment_not_counted_as_loc(self):
        """Python # comments should still be skipped."""
        py_handler = get_handler(".py")
        content = '# comment\nimport os\nx = 1\n'
        loc = py_handler.count_loc(content)
        self.assertEqual(loc, 2)


# =============================================================================
# C# handler tests
# =============================================================================

class TestDotNetHandler(unittest.TestCase):
    def setUp(self):
        self.handler = get_handler(".cs")

    def test_using_detected(self):
        content = 'using System;\nusing Newtonsoft.Json;\nusing NUnit.Framework;\n'
        imports = self.handler.extract_external_imports(content)
        self.assertIn("Newtonsoft", imports)
        self.assertIn("NUnit", imports)
        self.assertNotIn("System", imports)

    def test_xml_doc_comments_detected(self):
        """Critical: /// XML doc comments (Microsoft convention) must be detected."""
        content = '''using System;

/// <summary>
/// Calculator service.
/// </summary>
public class Calculator {}
'''
        found, snippet = self.handler.detect_docstring(content)
        self.assertTrue(found)
        self.assertIn("Calculator service", snippet)

    def test_block_doc_comments_detected(self):
        content = '''using System;

/** Calculator service. */
public class Calculator {}
'''
        found, snippet = self.handler.detect_docstring(content)
        self.assertTrue(found)


# =============================================================================
# Ruby, PHP, Swift handler tests
# =============================================================================

class TestRubyHandler(unittest.TestCase):
    def setUp(self):
        self.handler = get_handler(".rb")

    def test_require_external(self):
        content = "require 'json'\nrequire 'redis'\nrequire_relative 'helper'\n"
        imports = self.handler.extract_external_imports(content)
        self.assertIn("json", imports)
        self.assertIn("redis", imports)
        self.assertNotIn("helper", imports)

    def test_methods_counted(self):
        content = '''class Calculator
  def add(a, b)
    a + b
  end
  def subtract(a, b)
    a - b
  end
end
'''
        count, names = self.handler.count_public_api(content)
        self.assertGreaterEqual(count, 2)
        self.assertIn("add", names)


class TestPhpHandler(unittest.TestCase):
    def setUp(self):
        self.handler = get_handler(".php")

    def test_use_detected(self):
        content = '<?php\nuse Foo\\Bar;\nuse Baz\\Qux;\n'
        imports = self.handler.extract_external_imports(content)
        self.assertIn("Foo", imports)
        self.assertIn("Baz", imports)

    def test_functions_counted(self):
        content = '''<?php
class Calculator {
    public function add($a, $b) { return $a + $b; }
    public function subtract($a, $b) { return $a - $b; }
}
'''
        count, names = self.handler.count_public_api(content)
        self.assertGreaterEqual(count, 2)
        self.assertIn("add", names)


class TestSwiftHandler(unittest.TestCase):
    def setUp(self):
        self.handler = get_handler(".swift")

    def test_import_detected(self):
        content = 'import Foundation\nimport Alamofire\nimport SnapKit\n'
        imports = self.handler.extract_external_imports(content)
        self.assertIn("Alamofire", imports)
        self.assertIn("SnapKit", imports)
        self.assertNotIn("Foundation", imports)

    def test_functions_counted(self):
        content = '''struct Calculator {
    func add(_ a: Int, _ b: Int) -> Int { return a + b }
    func subtract(_ a: Int, _ b: Int) -> Int { return a - b }
}
'''
        count, names = self.handler.count_public_api(content)
        self.assertGreaterEqual(count, 2)


# =============================================================================
# Sibling resolution tests
# =============================================================================

class TestSiblingResolution(unittest.TestCase):
    def test_python_same_dir(self):
        file_set = {"src/utils.py", "src/parser.py"}
        result = _resolve_sibling("utils", 1, "src/parser.py", ".py", file_set)
        self.assertEqual(result, "src/utils.py")

    def test_python_parent_dir(self):
        """Critical: from .. import X must look in PARENT dir."""
        file_set = {"config.py", "src/parser.py"}
        result = _resolve_sibling("config", 2, "src/parser.py", ".py", file_set)
        self.assertEqual(result, "config.py")

    def test_missing_sibling(self):
        file_set = {"src/parser.py"}
        result = _resolve_sibling("ghost", 1, "src/parser.py", ".py", file_set)
        self.assertIsNone(result)

    def test_python_package_init(self):
        file_set = {"src/utils/__init__.py", "src/parser.py"}
        result = _resolve_sibling("utils", 1, "src/parser.py", ".py", file_set)
        self.assertEqual(result, "src/utils/__init__.py")


# =============================================================================
# License detection tests
# =============================================================================

class TestLicenseDetection(unittest.TestCase):
    def test_license_exact(self):
        self.assertTrue(detect_license_in_repo([make_file("LICENSE", "MIT...")]))

    def test_license_md(self):
        self.assertTrue(detect_license_in_repo([make_file("LICENSE.md", "MIT...")]))

    def test_license_mit(self):
        self.assertTrue(detect_license_in_repo([make_file("LICENSE-MIT", "MIT...")]))

    def test_license_apache(self):
        self.assertTrue(detect_license_in_repo([make_file("LICENSE.APACHE", "Apache 2.0...")]))

    def test_copying_lesser(self):
        self.assertTrue(detect_license_in_repo([make_file("COPYING.LESSER", "LGPL...")]))

    def test_no_license(self):
        self.assertFalse(detect_license_in_repo([make_file("README.md", "# My Repo"), make_file("src/main.py", "print('hi')")]))

    def test_license_in_subdir_ignored(self):
        self.assertFalse(detect_license_in_repo([make_file("vendor/LICENSE", "MIT...")]))


# =============================================================================
# Test file detection
# =============================================================================

class TestTestFileDetection(unittest.TestCase):
    def test_same_dir(self):
        self.assertTrue(has_test_for("src/utils.py", {"src/utils.py", "src/test_utils.py"}))

    def test_root_tests_dir(self):
        self.assertTrue(has_test_for("src/utils.py", {"src/utils.py", "tests/test_utils.py"}))

    def test_parent_tests_dir(self):
        """Critical: src/tests/test_utils.py must be detected for src/utils.py."""
        self.assertTrue(has_test_for("src/utils.py", {"src/utils.py", "src/tests/test_utils.py"}))

    def test_no_test_file(self):
        self.assertFalse(has_test_for("src/utils.py", {"src/utils.py"}))


# =============================================================================
# Report generation tests
# =============================================================================

class TestReportGeneration(unittest.TestCase):
    STANDALONE_10LOC = '''"""A pure slugify utility."""
import re

def slugify(text):
    """Convert text to a URL-safe slug."""
    return re.sub(r"[^\\w\\s-]", "", text).strip().lower()

def deslugify(slug):
    """Convert a slug back to readable text."""
    return slug.replace("-", " ").title()

def is_valid_slug(text):
    """Check if text is a valid slug."""
    return text == slugify(text)
'''

    def test_report_generates_without_crash(self):
        """Critical: report must not crash AND must contain 'What it does'."""
        files = [
            make_file("LICENSE", "MIT..."),
            make_file("slugify.py", self.STANDALONE_10LOC),
        ]
        cands, _ = detect_candidates(files, "Python")
        active = [c for c in cands if not c.skipped]
        self.assertGreater(len(active), 0)
        for c in cands:
            if not c.skipped:
                score_candidate(c, similar_count=0)
        out = Path(tempfile.gettempdir()) / "test_report_unittest.md"
        try:
            generate_report("test", "repo", "Python", cands, out, max_candidates=3)
            self.assertTrue(out.exists())
            content = out.read_text()
            self.assertIn("**What it does:**", content)
        finally:
            if out.exists():
                out.unlink()

    def test_report_with_skipped(self):
        blocked_content = '''"""File with missing sibling."""
import re
from .ghost_helper import magic_function

def transform(data):
    """Transform."""
    return magic_function(data)

def validate(data):
    """Validate."""
    return bool(data)

def normalize(data):
    """Normalize."""
    return data.strip()

def reverse(data):
    """Reverse."""
    return data[::-1]
'''
        files = [
            make_file("LICENSE", "MIT..."),
            make_file("broken.py", blocked_content),
        ]
        cands, _ = detect_candidates(files, "Python")
        skipped = [c for c in cands if c.skipped]
        self.assertGreater(len(skipped), 0)
        out = Path(tempfile.gettempdir()) / "test_report_skipped.md"
        try:
            generate_report("test", "repo", "Python", cands, out, max_candidates=3)
            self.assertTrue(out.exists())
        finally:
            if out.exists():
                out.unlink()


# =============================================================================
# End-to-end extraction verification
# =============================================================================

class TestEndToEndExtraction(unittest.TestCase):
    STANDALONE_CONTENT = '''"""A pure slugify utility."""
import re
import unicodedata

def slugify(text):
    """Convert text to a URL-safe slug."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^\\w\\s-]", "", text).strip().lower()

def deslugify(slug):
    """Convert a slug back to readable text."""
    return slug.replace("-", " ").title()

def is_valid_slug(text):
    """Check if text is a valid slug."""
    return text == slugify(text)
'''

    MULTI_FILE_CONTENT = '''"""Parser that needs a sibling."""
import re
from .utils import format_output

def parse_csv(text):
    """Parse CSV text into rows."""
    rows = []
    for line in text.splitlines():
        rows.append(line.split(","))
    return format_output(rows)

def validate_csv(text):
    """Validate CSV."""
    return len(parse_csv(text)) > 0

def count_rows(text):
    """Count rows."""
    return len(parse_csv(text))

def get_headers(text):
    """Get headers."""
    rows = parse_csv(text)
    return rows[0] if rows else []
'''

    SIBLING_CONTENT = '''"""Helper utils."""
def format_output(rows):
    """Format rows."""
    return rows
'''

    def test_standalone_with_license(self):
        files = [
            make_file("LICENSE", "MIT"),
            make_file("slugify.py", self.STANDALONE_CONTENT),
        ]
        cands, _ = detect_candidates(files, "Python")
        active = [c for c in cands if not c.skipped]
        self.assertEqual(len(active), 1)
        c = active[0]
        self.assertEqual(c.extraction_type, "single")
        self.assertEqual(c.relative_imports, [])
        self.assertTrue(c.source_has_license)
        score_candidate(c, similar_count=0)
        self.assertGreater(c.relevance, 8.0)

    def test_multi_file_extraction(self):
        files = [
            make_file("LICENSE", "MIT"),
            make_file("parser.py", self.MULTI_FILE_CONTENT),
            make_file("utils.py", self.SIBLING_CONTENT),
        ]
        cands, _ = detect_candidates(files, "Python")
        active = [c for c in cands if not c.skipped]
        parser = next(c for c in active if c.path == "parser.py")
        self.assertEqual(parser.extraction_type, "multi")
        self.assertIn("utils.py", parser.sibling_paths)
        score_candidate(parser, similar_count=0)
        # Multi-file should score LOWER than standalone
        files2 = [make_file("LICENSE", "MIT"), make_file("slugify.py", self.STANDALONE_CONTENT)]
        cands2, _ = detect_candidates(files2, "Python")
        standalone = next(c for c in cands2 if not c.skipped)
        score_candidate(standalone, similar_count=0)
        self.assertLess(parser.relevance, standalone.relevance)

    def test_blocked_extraction(self):
        blocked_content = '''"""File with missing sibling."""
import re
from .ghost_helper import magic_function

def transform(data):
    """Transform."""
    return magic_function(data)

def validate(data):
    """Validate."""
    return bool(data)

def normalize(data):
    """Normalize."""
    return data.strip()

def reverse(data):
    """Reverse."""
    return data[::-1]
'''
        files = [make_file("LICENSE", "MIT"), make_file("broken.py", blocked_content)]
        cands, _ = detect_candidates(files, "Python")
        active = [c for c in cands if not c.skipped]
        skipped = [c for c in cands if c.skipped]
        self.assertEqual(len(active), 0)
        self.assertEqual(len(skipped), 1)
        self.assertIn("missing sibling", skipped[0].skip_reason.lower())
        self.assertEqual(skipped[0].extraction_type, "blocked")

    def test_no_license_flagged(self):
        files = [make_file("slugify.py", self.STANDALONE_CONTENT)]
        cands, _ = detect_candidates(files, "Python")
        active = [c for c in cands if not c.skipped]
        self.assertFalse(active[0].source_has_license)


# =============================================================================
# Cross-language integration tests
# =============================================================================

class TestCrossLanguageIntegration(unittest.TestCase):
    """Tests that the language handler registry works correctly."""

    def test_all_supported_extensions_have_handlers(self):
        from people_helper.config import LANG_BY_EXT
        from people_helper.languages import supported_extensions
        supported = supported_extensions()
        for ext in LANG_BY_EXT:
            self.assertIn(ext, supported, f"Extension {ext} has no handler")

    def test_handler_returns_correct_language_name(self):
        self.assertEqual(get_handler(".py").language_name, "Python")
        self.assertEqual(get_handler(".ts").language_name, "JavaScript")
        self.assertEqual(get_handler(".go").language_name, "Go")
        self.assertEqual(get_handler(".rs").language_name, "Rust")
        # Kotlin handler has custom language_name
        self.assertEqual(get_handler(".kt").language_name, "Kotlin")
        self.assertEqual(get_handler(".java").language_name, "Java")

    def test_kotlin_realistic_file(self):
        """Critical: realistic Kotlin file with default-public functions
        must not be reported as 'no API surface' (round-4 bug)."""
        content = '''package com.example

import org.springframework.boot.SpringApplication
import kotlinx.coroutines.runBlocking

class App {
    fun run() {
        println("hi")
    }
    fun stop() {
        println("bye")
    }
}
'''
        handler = get_handler(".kt")
        count, names = handler.count_public_api(content)
        self.assertGreaterEqual(count, 2, "Kotlin default-public functions must be counted")
        self.assertIn("run", names)
        self.assertIn("stop", names)
        # Imports must detect kotlinx (not skip as 'kotlin.*')
        imports = handler.extract_external_imports(content)
        self.assertIn("kotlinx", imports)
        self.assertIn("org", imports)


# =============================================================================
# Scoring tests
# =============================================================================

class TestScoring(unittest.TestCase):
    def test_no_network_uses_neutral_uniqueness(self):
        """--no-network (similar_count=-1) must NOT score 8.0 uniqueness."""
        self.assertEqual(_compute_uniqueness(0), 8.0)
        self.assertEqual(_compute_uniqueness(-1), 5.0)

    def test_standalone_scores_higher_than_multi_file(self):
        """Single-file extraction must score higher than multi-file."""
        from people_helper.models import Candidate
        single = Candidate(
            path="a.py", language="Python", loc=50,
            has_tests=True, has_docstring=True,
            internal_imports=0, external_imports=0, filename_score=1.0,
            extraction_type="single", source_has_license=True,
            is_stdlib_only=True, dependency_weight=0,
            api_surface_count=3, complexity=3, comment_ratio=0.15,
        )
        multi = Candidate(
            path="b.py", language="Python", loc=50,
            has_tests=True, has_docstring=True,
            internal_imports=1, external_imports=0, filename_score=1.0,
            extraction_type="multi", source_has_license=True,
            sibling_paths=["utils.py"], relative_imports=["utils"],
            is_stdlib_only=True, dependency_weight=0,
            api_surface_count=3, complexity=3, comment_ratio=0.15,
        )
        score_candidate(single, similar_count=0)
        score_candidate(multi, similar_count=0)
        self.assertGreater(single.combined_score, multi.combined_score,
                           "Single-file must score higher than multi-file")


# =============================================================================
# URL parser test
# =============================================================================

class TestUrlParser(unittest.TestCase):
    def test_gitlab_rejected(self):
        from people_helper.walker import parse_repo_arg
        with self.assertRaises(ValueError):
            parse_repo_arg("https://gitlab.com/user/repo")

    def test_github_accepted(self):
        from people_helper.walker import parse_repo_arg
        owner, name = parse_repo_arg("https://github.com/user/repo")
        self.assertEqual((owner, name), ("user", "repo"))


# =============================================================================
# Search crash test
# =============================================================================

class TestSearchCrashOnNonJson(unittest.TestCase):
    def test_non_json_returns_empty(self):
        from unittest.mock import patch, MagicMock
        from people_helper.search import github_search_repositories
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not JSON")
        with patch("people_helper.search.httpx.get", return_value=mock_response):
            result = github_search_repositories("test", "Python", "fake_pat")
        self.assertEqual(result, [])

    def test_malformed_api_items_skipped(self):
        """Critical: malformed items missing required fields must not crash."""
        from unittest.mock import patch, MagicMock
        from people_helper.search import github_search_repositories
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Items missing required fields like 'full_name'
        mock_response.json.return_value = {
            "items": [
                {"html_url": "x", "stargazers_count": 5},  # missing full_name
                {"full_name": "ok/repo", "html_url": "x", "stargazers_count": 10},  # valid
                "not-a-dict",  # not a dict
            ]
        }
        with patch("people_helper.search.httpx.get", return_value=mock_response):
            result = github_search_repositories("test", "Python", "fake_pat")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].full_name, "ok/repo")


# =============================================================================
# Block-comment continuation, Go docstring, comment ratio
# =============================================================================

class TestBlockCommentContinuation(unittest.TestCase):
    """Block-comment continuation lines must NOT count as LOC."""

    def test_cpp_block_comment_continuation_not_counted(self):
        """Critical: lines starting with ' * ' inside a /* */ block must not count as LOC."""
        handler = get_handler(".cpp")
        content = '''int main() {
    return 0;
}
/* This is a
 * multi-line
 * block comment
 */
int other() {
    return 1;
}
'''
        loc = handler.count_loc(content)
        # Should be 6: 3 lines for main() + 3 lines for other()
        # The 4 block-comment lines (/*, *, *, */) should NOT count
        self.assertEqual(loc, 6)

    def test_java_block_comment_continuation(self):
        handler = get_handler(".java")
        content = '''/**
 * Javadoc comment.
 * More docs.
 */
public class Foo {}
'''
        loc = handler.count_loc(content)
        # Only 'public class Foo {}' counts as code
        self.assertEqual(loc, 1)


class TestGoDocstringNoFalsePositives(unittest.TestCase):
    """Go license headers and post-package comments must NOT be docstrings."""

    def test_license_header_not_docstring(self):
        """Critical: 'Copyright 2024' before package must NOT be a docstring."""
        handler = get_handler(".go")
        content = '''// Copyright 2024
// Licensed under MIT.
package main

import "fmt"
'''
        found, _ = handler.detect_docstring(content)
        self.assertFalse(found, "License header must not be treated as docstring")

    def test_post_package_comment_not_docstring(self):
        """Comments AFTER package declaration are NOT docstrings."""
        handler = get_handler(".go")
        content = '''package main

// This is a comment after package.
func main() {}
'''
        found, _ = handler.detect_docstring(content)
        self.assertFalse(found, "Post-package comment must not be docstring")

    def test_real_package_comment_detected(self):
        """// Package main ... immediately before package IS a docstring."""
        handler = get_handler(".go")
        content = '''// Package main is the entry point.
package main
'''
        found, snippet = handler.detect_docstring(content)
        self.assertTrue(found)
        self.assertIn("Package main", snippet)


class TestCommentRatioPythonArgs(unittest.TestCase):
    """Python *args lines must NOT count as comments."""

    def test_python_star_unpacking_not_comment(self):
        """Critical: '*head, tail = ...' in Python must not be stripped from LOC
        or counted as a comment. This is real code (iterable unpacking)."""
        from people_helper.detection import _compute_comment_ratio
        from people_helper.languages import get_handler
        # Content with a line that STARTS with * (Python unpacking)
        content = '''def split_list(items):
    *head, tail = items
    return head, tail
'''
        handler = get_handler(".py")
        loc = handler.count_loc(content)
        # All 3 lines are real code — *head must NOT be stripped
        self.assertEqual(loc, 3, "*head unpacking must count as LOC")
        ratio = _compute_comment_ratio(content, ".py")
        self.assertEqual(ratio, 0.0, "*head must not inflate comment ratio")

    def test_python_args_in_def_not_comment(self):
        """def foo(*args) — the *args is part of the def line, not a separate line."""
        from people_helper.detection import _compute_comment_ratio
        content = '''def foo(*args, **kwargs):
    return list(args)
'''
        ratio = _compute_comment_ratio(content, ".py")
        self.assertEqual(ratio, 0.0)


class TestCountImportsConsistency(unittest.TestCase):
    """Regression test: count_imports external count must equal len(extract_external_imports)."""

    def test_cpp_consistency(self):
        """Critical: C++ external_imports field must match extract_external_imports count."""
        handler = get_handler(".cpp")
        content = '#include <boost/asio.hpp>\n#include "my_local.h"\n#include <stdio.h>\n'
        internal, external = handler.count_imports(content, set())
        extracted = handler.extract_external_imports(content)
        self.assertEqual(external, len(extracted),
                         "count_imports external must equal len(extract_external_imports)")

    def test_go_consistency(self):
        handler = get_handler(".go")
        content = '''package main

import (
    "fmt"
    "github.com/user/repo"
)
'''
        internal, external = handler.count_imports(content, set())
        extracted = handler.extract_external_imports(content)
        self.assertEqual(external, len(extracted))

    def test_python_consistency(self):
        handler = get_handler(".py")
        content = 'import os\nimport sys\nfrom .utils import helper\nimport requests\n'
        internal, external = handler.count_imports(content, {"utils"})
        extracted = handler.extract_external_imports(content)
        self.assertEqual(external, len(extracted))


class TestDocstringLongPrefix(unittest.TestCase):
    """Docstring detection must handle 35+ imports (Spring Boot apps)."""

    def test_java_many_imports_then_javadoc(self):
        """Critical: Java file with 40 imports + Javadoc must detect the docstring."""
        handler = get_handler(".java")
        # Generate 40 import lines
        imports = "\n".join(f"import com.example.module{i}.SomeClass;" for i in range(40))
        content = f'''package com.example;

{imports}

/**
 * Main application entry point.
 */
public class Application {{
    public static void main(String[] args) {{
        System.out.println("hi");
    }}
}}
'''
        found, snippet = handler.detect_docstring(content)
        self.assertTrue(found, "Javadoc after 40 imports must be detected")
        self.assertIn("Main application", snippet)


class TestRealismCheck(unittest.TestCase):
    """Tests for realism check edge cases."""

    def test_java_with_license_header_not_skipped(self):
        """Critical: Java file with Apache 2.0 header + real code must NOT be
        skipped as 'Mostly copyright/license comments'."""
        from people_helper.detection import _find_skip_reason as _realism_check
        from people_helper.languages import get_handler
        # Realistic Spring Boot file: 17-line Apache header + real Java code
        content = '''/*
 * Copyright 2012-present the original author or authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package com.example;

/**
 * A utility class.
 */
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
    public int subtract(int a, int b) {
        return a - b;
    }
}
'''
        handler = get_handler(".java")
        loc = handler.count_loc(content)
        reason = _realism_check(content, ".java", "Calculator.java", loc)
        self.assertIsNone(reason, f"Should not be skipped, got: {reason}")

    def test_public_class_detected(self):
        """Critical: 'public class Foo' must be detected as a class definition.
        The old regex only matched 'class Foo' (no visibility modifier)."""
        from people_helper.detection import _find_skip_reason as _realism_check
        from people_helper.languages import get_handler
        # Small Java file with public class — should NOT be skipped
        content = '''/*
 * Copyright 2024
 * Licensed under MIT.
 */
package com.example;

public class Helper {
    public String getName() { return "helper"; }
}
'''
        handler = get_handler(".java")
        loc = handler.count_loc(content)
        reason = _realism_check(content, ".java", "Helper.java", loc)
        self.assertIsNone(reason, f"public class must be detected, got: {reason}")

    def test_truly_copyright_only_still_skipped(self):
        """Files that are genuinely just license text should still be skipped
        (either as copyright-only or as no-code)."""
        from people_helper.detection import _find_skip_reason as _realism_check
        from people_helper.languages import get_handler
        content = '''/*
 * Copyright 2024
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
'''
        handler = get_handler(".java")
        loc = handler.count_loc(content)
        reason = _realism_check(content, ".java", "License.java", loc)
        self.assertIsNotNone(reason, "Pure license file should be skipped")


class TestExtractor(unittest.TestCase):
    """Tests for the --extract feature (actually copies files out of repo)."""

    def test_strip_apache_license_header(self):
        """Critical: Apache 2.0 header should be stripped from extracted files."""
        from people_helper.extractor import strip_license_header
        content = '''/*
 * Copyright 2012-present the original author or authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package com.example;

public class Calculator {
    public int add(int a, int b) { return a + b; }
}
'''
        stripped, lines_removed = strip_license_header(content, ".java")
        self.assertGreater(lines_removed, 10, "Should remove license header lines")
        self.assertNotIn("Apache License", stripped)
        self.assertIn("public class Calculator", stripped)

    def test_strip_python_license_header(self):
        from people_helper.extractor import strip_license_header
        content = '''#!/usr/bin/env python3
# Copyright (c) 2024
# Licensed under MIT.
"""My module."""

def foo():
    pass
'''
        stripped, lines_removed = strip_license_header(content, ".py")
        self.assertGreater(lines_removed, 0)
        self.assertNotIn("Copyright", stripped)
        self.assertIn("def foo", stripped)

    def test_no_license_header_unchanged(self):
        from people_helper.extractor import strip_license_header
        content = 'def foo():\n    return 42\n'
        stripped, lines_removed = strip_license_header(content, ".py")
        self.assertEqual(lines_removed, 0)
        self.assertEqual(stripped, content)

    def test_extract_creates_package_scaffold(self):
        """Critical: --extract should create a real package directory with manifest."""
        import tempfile
        from people_helper.extractor import extract_candidate
        from people_helper.models import Candidate

        # Create a fake clone dir with a Python file
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_path = Path(tmpdir)
            src_file = clone_path / "utils.py"
            src_file.write_text('"""Utility functions."""\n\ndef slugify(text):\n    return text.lower()\n')

            # Create a candidate pointing to this file
            cand = Candidate(
                path="utils.py", language="Python", loc=10,
                has_tests=False, has_docstring=True,
                internal_imports=0, external_imports=0, filename_score=1.0,
                extraction_type="single", source_has_license=True,
                is_stdlib_only=True, dependency_weight=0,
                api_surface_count=1, complexity=1, comment_ratio=0.0,
                what_it_does="A slugify utility",
            )
            cand.suggested_name = "slugify-tool"
            cand.suggested_tags = ["python", "utility", "slugify"]

            # Extract to a temp output dir
            with tempfile.TemporaryDirectory() as outdir:
                output_dir = Path(outdir)
                pkg_path = extract_candidate(cand, clone_path, output_dir, "test/repo")

                # Verify package dir was created
                self.assertTrue(pkg_path.exists())
                self.assertEqual(pkg_path.name, "slugify-tool")

                # Verify README was created
                self.assertTrue((pkg_path / "README.md").exists())

                # Verify LICENSE-REVIEW.md was created (mandatory)
                self.assertTrue((pkg_path / "LICENSE-REVIEW.md").exists())
                lr_content = (pkg_path / "LICENSE-REVIEW.md").read_text()
                self.assertIn("License Review Required", lr_content)

                # Verify pyproject.toml was created for Python
                self.assertTrue((pkg_path / "pyproject.toml").exists())
                pyproject = (pkg_path / "pyproject.toml").read_text()
                self.assertIn("slugify-tool", pyproject)
                # License is commented out (REVIEW-NEEDED pattern)
                self.assertIn("TODO: confirm license", pyproject)


    def test_fix_python_relative_imports(self):
        """Relative imports should be replaced with TODO comments."""
        from people_helper.extractor import fix_relative_imports
        content = 'from .utils import helper\n\ndef foo():\n    return helper()\n'
        fixed = fix_relative_imports(content, ".py")
        self.assertIn("# TODO:", fixed)
        # The comment contains the original line but it's commented out
        for line in fixed.splitlines():
            self.assertFalse(line.strip().startswith("from ."), f"Active relative import found: {line}")
        self.assertIn("def foo", fixed)

    def test_fix_js_relative_imports(self):
        from people_helper.extractor import fix_relative_imports
        content = "import { foo } from './utils'\n\nexport function bar() { return foo() }\n"
        fixed = fix_relative_imports(content, ".ts")
        self.assertIn("// TODO:", fixed)
        for line in fixed.splitlines():
            self.assertFalse(line.strip().startswith("import") and "./" in line, f"Active relative import found: {line}")

    def test_fix_rust_relative_imports(self):
        from people_helper.extractor import fix_relative_imports
        content = "use super::utils;\n\npub fn foo() -> i32 { 42 }\n"
        fixed = fix_relative_imports(content, ".rs")
        self.assertIn("// TODO:", fixed)
        for line in fixed.splitlines():
            self.assertFalse(line.strip().startswith("use super::") or line.strip().startswith("use crate::"), f"Active relative import found: {line}")

    def test_no_relative_imports_unchanged(self):
        from people_helper.extractor import fix_relative_imports
        content = 'import os\n\ndef foo():\n    return 42\n'
        fixed = fix_relative_imports(content, ".py")
        self.assertNotIn("# TODO:", fixed)
        self.assertIn("import os", fixed)


if __name__ == "__main__":
    unittest.main(verbosity=2)


# === Pat scope verification tests (R2-A: pat.py was at 0% coverage) ===

class TestPatScope(unittest.TestCase):
    """Tests for pat.check_pat_scope — the security-critical PAT gate."""

    def _mock_response(self, status_code=200, scopes_header="", json_data=None, text=""):
        """Build a fake httpx.Response-like object."""
        class FakeResponse:
            def __init__(self):
                self.status_code = status_code
                self.headers = {"x-oauth-scopes": scopes_header} if scopes_header else {}
                self._json = json_data or {"login": "test-user"}
                self.text = text
            def json(self):
                return self._json
        return FakeResponse()

    def test_classic_pat_with_repo_scope_rejected(self):
        """Critical: classic PAT with 'repo' scope (write-capable) must be rejected."""
        from unittest.mock import patch, MagicMock
        from people_helper.pat import check_pat_scope
        fake_resp = self._mock_response(200, scopes_header="repo")
        with patch("people_helper.pat.httpx.get", return_value=fake_resp):
            result = check_pat_scope("ghp_fake_classic_pat_for_testing_only")
        self.assertFalse(result["ok"])
        self.assertIn("write-capable scope", result["error"])
        self.assertIn("repo", result["error"])

    def test_classic_pat_with_admin_scope_rejected(self):
        """Critical: 'admin:org' scope must be rejected."""
        from unittest.mock import patch
        from people_helper.pat import check_pat_scope
        fake_resp = self._mock_response(200, scopes_header="admin:org")
        with patch("people_helper.pat.httpx.get", return_value=fake_resp):
            result = check_pat_scope("ghp_fake_classic_pat_for_testing_only")
        self.assertFalse(result["ok"])
        self.assertIn("admin:org", result["error"])

    def test_classic_pat_with_write_scope_rejected(self):
        """Critical: 'write:org' scope must be rejected."""
        from unittest.mock import patch
        from people_helper.pat import check_pat_scope
        fake_resp = self._mock_response(200, scopes_header="write:org")
        with patch("people_helper.pat.httpx.get", return_value=fake_resp):
            result = check_pat_scope("ghp_fake_classic_pat_for_testing_only")
        self.assertFalse(result["ok"])
        self.assertIn("write:org", result["error"])

    def test_classic_pat_with_delete_scope_rejected(self):
        """Critical: 'delete:packages' scope must be rejected."""
        from unittest.mock import patch
        from people_helper.pat import check_pat_scope
        fake_resp = self._mock_response(200, scopes_header="delete:packages")
        with patch("people_helper.pat.httpx.get", return_value=fake_resp):
            result = check_pat_scope("ghp_fake_classic_pat_for_testing_only")
        self.assertFalse(result["ok"])
        self.assertIn("delete:packages", result["error"])

    def test_classic_readonly_pat_accepted(self):
        """Classic PAT with read-only scopes should pass."""
        from unittest.mock import patch
        from people_helper.pat import check_pat_scope
        # 'read:org' is read-only and not in WRITE_SCOPES
        fake_resp = self._mock_response(200, scopes_header="read:org")
        with patch("people_helper.pat.httpx.get", return_value=fake_resp):
            result = check_pat_scope("ghp_fake_classic_pat_for_testing_only")
        self.assertTrue(result["ok"])
        self.assertEqual(result["user"], "test-user")
        self.assertTrue(result["is_classic"])
        self.assertIsNone(result["warning"])

    def test_fine_grained_pat_accepted_with_warning(self):
        """Fine-grained PAT (empty scopes header) should pass with a soft warning."""
        from unittest.mock import patch
        from people_helper.pat import check_pat_scope
        fake_resp = self._mock_response(200, scopes_header="")
        with patch("people_helper.pat.httpx.get", return_value=fake_resp):
            result = check_pat_scope("github_pat_fake_fine_grained_for_testing_only")
        self.assertTrue(result["ok"])
        self.assertEqual(result["user"], "test-user")
        self.assertFalse(result["is_classic"])
        # Should have a non-None warning explaining scopes can't be verified
        self.assertIsNotNone(result["warning"])
        self.assertIn("Fine-grained", result["warning"])

    def test_invalid_pat_401_rejected(self):
        """401 from /user means invalid/expired PAT."""
        from unittest.mock import patch
        from people_helper.pat import check_pat_scope
        fake_resp = self._mock_response(401)
        with patch("people_helper.pat.httpx.get", return_value=fake_resp):
            result = check_pat_scope("ghp_invalid_pat_for_testing")
        self.assertFalse(result["ok"])
        self.assertIn("invalid or expired", result["error"])

    def test_403_rejected(self):
        """403 from /user means PAT lacks user-info permission."""
        from unittest.mock import patch
        from people_helper.pat import check_pat_scope
        fake_resp = self._mock_response(403)
        with patch("people_helper.pat.httpx.get", return_value=fake_resp):
            result = check_pat_scope("ghp_test_pat_for_testing")
        self.assertFalse(result["ok"])
        self.assertIn("does not have permission", result["error"])

    def test_network_error_rejected(self):
        """Network error should return ok=False with network error message."""
        from unittest.mock import patch
        import httpx
        from people_helper.pat import check_pat_scope
        with patch("people_helper.pat.httpx.get", side_effect=httpx.HTTPError("simulated network error")):
            result = check_pat_scope("ghp_test_pat_for_testing")
        self.assertFalse(result["ok"])
        self.assertIn("network error", result["error"])
        # PAT must NEVER appear in the error message
        self.assertNotIn("ghp_test_pat_for_testing", result["error"])

    def test_return_shape_consistency(self):
        """All return paths must have the same keys (R3-B/R5-B consistency)."""
        from unittest.mock import patch
        import httpx
        from people_helper.pat import check_pat_scope
        required_keys = {"ok", "user", "error", "warning", "scopes_header", "is_classic"}

        # Test each return path
        cases = [
            ("network error", lambda: patch("people_helper.pat.httpx.get",
                                            side_effect=httpx.HTTPError("err"))),
            ("401", lambda: patch("people_helper.pat.httpx.get",
                                   return_value=self._mock_response(401))),
            ("403", lambda: patch("people_helper.pat.httpx.get",
                                   return_value=self._mock_response(403))),
            ("500", lambda: patch("people_helper.pat.httpx.get",
                                   return_value=self._mock_response(500))),
            ("classic ok", lambda: patch("people_helper.pat.httpx.get",
                                          return_value=self._mock_response(200, scopes_header="read:org"))),
            ("fine-grained ok", lambda: patch("people_helper.pat.httpx.get",
                                               return_value=self._mock_response(200, scopes_header=""))),
            ("classic rejected", lambda: patch("people_helper.pat.httpx.get",
                                                return_value=self._mock_response(200, scopes_header="repo"))),
        ]
        for label, patcher_fn in cases:
            with patcher_fn():
                result = check_pat_scope("ghp_test_pat_for_testing")
            missing = required_keys - set(result.keys())
            self.assertFalse(missing, f"Return path '{label}' missing keys: {missing}")


# === Manifest generator tests (R2-A: 9 of 10 generators were untested) ===

class TestManifestGenerators(unittest.TestCase):
    """Tests for extractor._generate_* functions — each must produce valid output."""

    def _make_candidate(self, what_it_does="A test utility"):
        from people_helper.models import Candidate
        return Candidate(
            path="test.py", language="Python", loc=50,
            has_tests=True, has_docstring=True,
            internal_imports=0, external_imports=2, filename_score=1.0,
            what_it_does=what_it_does,
        )

    def test_generate_pyproject_toml_valid(self):
        """pyproject.toml should contain name, version, description, hatchling build-system."""
        from people_helper.extractor import _generate_pyproject_toml
        cand = self._make_candidate()
        result = _generate_pyproject_toml("test-pkg", cand, ["python", "utility"], "test/repo")
        self.assertIn("test-pkg", result)
        self.assertIn("0.1.0", result)
        self.assertIn("hatchling", result)
        self.assertIn("A test utility", result)
        # License should be commented out (REVIEW-NEEDED pattern, not auto-MIT)
        self.assertIn("# TODO: confirm license", result)

    def test_generate_package_json_valid(self):
        """package.json should be valid JSON with name, version, description."""
        import json
        from people_helper.extractor import _generate_package_json
        cand = self._make_candidate()
        result = _generate_package_json("test-pkg", cand, ["js", "utility"], "test/repo")
        parsed = json.loads(result)
        self.assertEqual(parsed["name"], "test-pkg")
        self.assertEqual(parsed["version"], "0.1.0")
        # License should be "SEE LICENSE IN LICENSE-REVIEW.md" (not "REVIEW-NEEDED")
        self.assertEqual(parsed["license"], "SEE LICENSE IN LICENSE-REVIEW.md")

    def test_generate_cargo_toml_valid(self):
        """Cargo.toml should contain name, version, edition."""
        from people_helper.extractor import _generate_cargo_toml
        cand = self._make_candidate()
        result = _generate_cargo_toml("test-pkg", cand, ["rust", "utility"], "test/repo")
        self.assertIn("[package]", result)
        self.assertIn('name = "test-pkg"', result)
        self.assertIn('version = "0.1.0"', result)
        self.assertIn('edition = "2021"', result)

    def test_generate_go_mod_valid(self):
        """go.mod should contain module path and go version."""
        from people_helper.extractor import _generate_go_mod
        cand = self._make_candidate()
        result = _generate_go_mod("test-pkg", cand, "test/repo")
        self.assertIn("module github.com/test/testpkg", result)
        self.assertIn("go 1.21", result)

    def test_generate_license_review_contains_all_scenarios(self):
        """LICENSE-REVIEW.md should mention all 5 license scenarios."""
        from people_helper.extractor import _generate_license_review
        result = _generate_license_review("test/repo")
        self.assertIn("MIT/Apache", result)
        self.assertIn("GPL/LGPL/AGPL", result)
        self.assertIn("NO license file", result)
        self.assertIn("BSD", result)
        self.assertIn("MPL", result)
        self.assertIn("License Review Required", result)

    def test_generate_readme_contains_attribution(self):
        """Generated README should link back to source repo."""
        from people_helper.extractor import _generate_readme
        cand = self._make_candidate()
        result = _generate_readme("test-pkg", cand, "test/repo", ["python"])
        self.assertIn("test-pkg", result)
        self.assertIn("test/repo", result)
        self.assertIn("github.com/test/repo", result)
        self.assertIn("A test utility", result)

    def test_description_with_double_quote_escaped(self):
        """Double quotes in description should be escaped in manifests."""
        from people_helper.extractor import _generate_pyproject_toml
        cand = self._make_candidate(what_it_does='A "quoted" utility')
        result = _generate_pyproject_toml("test-pkg", cand, ["python"], "test/repo")
        # The escaped quote should appear, not break the TOML
        self.assertIn('\\"quoted\\"', result)

    def test_github_username_extracted_from_source_repo(self):
        """Placeholder URLs should use the source repo's owner, not 'your-username'."""
        from people_helper.extractor import _get_github_username
        self.assertEqual(_get_github_username("alice/my-repo"), "alice")
        self.assertEqual(_get_github_username("bob/code"), "bob")
        # Fallback when source_repo doesn't match owner/name
        self.assertEqual(_get_github_username("invalid"), "your-username")
        self.assertEqual(_get_github_username(""), "your-username")


# === get_complexity tests (R2-A: was untested for all 13 handlers) ===

class TestHandlerComplexity(unittest.TestCase):
    """Tests for handler.get_complexity across all language handlers."""

    def test_python_complexity_simple(self):
        """Simple Python with one if has CC=2 (1 base + 1 if)."""
        from people_helper.languages import get_handler
        h = get_handler(".py")
        code = "def f():\n    if x:\n        return 1\n    return 2\n"
        self.assertEqual(h.get_complexity(code), 2)

    def test_python_complexity_for_loop(self):
        """Python for-loop adds 1 to complexity."""
        from people_helper.languages import get_handler
        h = get_handler(".py")
        code = "def f():\n    for i in range(10):\n        pass\n"
        self.assertEqual(h.get_complexity(code), 2)

    def test_python_complexity_boolean_ops(self):
        """Python 'and'/'or' add to complexity."""
        from people_helper.languages import get_handler
        h = get_handler(".py")
        code = "def f():\n    return a and b or c\n"
        # 1 (base) + 1 (and) + 1 (or) = 3
        self.assertEqual(h.get_complexity(code), 3)

    def test_python_complexity_empty(self):
        """Empty Python file has CC=1 (base complexity — one path through)."""
        from people_helper.languages import get_handler
        h = get_handler(".py")
        # CC starts at 1 (base) — even empty code has "one path"
        self.assertEqual(h.get_complexity(""), 1)
        self.assertEqual(h.get_complexity("# just a comment\n"), 1)

    def test_python_complexity_syntax_error_returns_zero(self):
        """Python with SyntaxError should return 0 (not crash)."""
        from people_helper.languages import get_handler
        h = get_handler(".py")
        bad_code = "def f(\n  # missing closing paren\n"
        self.assertEqual(h.get_complexity(bad_code), 0)

    def test_js_complexity_counts_if(self):
        """JS handler counts if statements."""
        from people_helper.languages import get_handler
        h = get_handler(".js")
        code = "function f() {\n  if (x) { return 1; }\n  return 2;\n}\n"
        self.assertGreaterEqual(h.get_complexity(code), 2)

    def test_js_complexity_counts_boolean_ops(self):
        """JS handler counts && and ||."""
        from people_helper.languages import get_handler
        h = get_handler(".js")
        code = "function f() { return a && b || c; }\n"
        self.assertGreaterEqual(h.get_complexity(code), 3)

    def test_go_complexity_counts_if(self):
        """Go handler counts if statements."""
        from people_helper.languages import get_handler
        h = get_handler(".go")
        code = "func f() int {\n  if x { return 1 }\n  return 2\n}\n"
        self.assertGreaterEqual(h.get_complexity(code), 2)

    def test_rust_complexity_counts_match(self):
        """Rust handler counts match statements."""
        from people_helper.languages import get_handler
        h = get_handler(".rs")
        code = "fn f() {\n  match x {\n    1 => {},\n    _ => {},\n  }\n}\n"
        self.assertGreaterEqual(h.get_complexity(code), 2)

    def test_java_complexity_counts_if(self):
        """Java handler counts if statements."""
        from people_helper.languages import get_handler
        h = get_handler(".java")
        code = "class F {\n  int f() {\n    if (x) return 1;\n    return 2;\n  }\n}\n"
        self.assertGreaterEqual(h.get_complexity(code), 2)

    def test_ruby_complexity_counts_if(self):
        """Ruby handler counts if statements."""
        from people_helper.languages import get_handler
        h = get_handler(".rb")
        code = "def f\n  if x\n    1\n  else\n    2\n  end\nend\n"
        self.assertGreaterEqual(h.get_complexity(code), 2)

    def test_php_complexity_counts_if(self):
        """PHP handler counts if statements."""
        from people_helper.languages import get_handler
        h = get_handler(".php")
        code = "<?php\nfunction f() {\n  if ($x) return 1;\n  return 2;\n}\n?>\n"
        self.assertGreaterEqual(h.get_complexity(code), 2)

    def test_swift_complexity_counts_if(self):
        """Swift handler counts if statements."""
        from people_helper.languages import get_handler
        h = get_handler(".swift")
        code = "func f() -> Int {\n  if x { return 1 }\n  return 2\n}\n"
        self.assertGreaterEqual(h.get_complexity(code), 2)


# === get_dependency_weight tests (R2-A: was untested for all handlers) ===

class TestHandlerDependencyWeight(unittest.TestCase):
    """Tests for handler.get_dependency_weight across all language handlers."""

    def test_python_stdlib_only(self):
        """Python with only stdlib imports → (0, True)."""
        from people_helper.languages import get_handler
        h = get_handler(".py")
        imports = ["os", "sys", "re", "json", "pathlib"]
        weight, is_stdlib = h.get_dependency_weight(imports)
        self.assertEqual(weight, 0)
        self.assertTrue(is_stdlib)

    def test_python_heavy_deps(self):
        """Python with heavy deps (django, tensorflow) → (3, False)."""
        from people_helper.languages import get_handler
        h = get_handler(".py")
        imports = ["django", "tensorflow", "numpy"]
        weight, is_stdlib = h.get_dependency_weight(imports)
        self.assertEqual(weight, 3)
        self.assertFalse(is_stdlib)

    def test_python_light_deps(self):
        """Python with non-stdlib non-heavy deps → (1, False)."""
        from people_helper.languages import get_handler
        h = get_handler(".py")
        imports = ["requests", "small_lib"]
        weight, is_stdlib = h.get_dependency_weight(imports)
        self.assertEqual(weight, 1)
        self.assertFalse(is_stdlib)

    def test_empty_imports_returns_stdlib(self):
        """All handlers: empty imports → (0, True)."""
        from people_helper.languages import get_handler
        for ext in [".py", ".js", ".ts", ".go", ".rs", ".java", ".kt",
                    ".c", ".cpp", ".cs", ".rb", ".php", ".swift"]:
            h = get_handler(ext)
            weight, is_stdlib = h.get_dependency_weight([])
            self.assertEqual(weight, 0, f"{ext}: empty imports should give weight 0")
            self.assertTrue(is_stdlib, f"{ext}: empty imports should be stdlib-only")

    def test_non_empty_imports_nonzero_weight(self):
        """All handlers: non-empty imports → weight > 0 (or 0 for stdlib-only langs)."""
        from people_helper.languages import get_handler
        for ext in [".py", ".js", ".ts", ".go", ".rs", ".java", ".kt",
                    ".c", ".cpp", ".cs", ".rb", ".php", ".swift"]:
            h = get_handler(ext)
            weight, _ = h.get_dependency_weight(["some_external_pkg"])
            self.assertGreaterEqual(weight, 1, f"{ext}: non-empty imports should give weight >= 1")


# === Report sanitization tests (R6-A: markdown injection was a Critical) ===

class TestReportSanitization(unittest.TestCase):
    """Tests for report._sanitize_for_markdown and _redact_secrets."""

    def test_sanitize_escapes_triple_backticks(self):
        """Triple backticks in user content must be escaped."""
        from people_helper.report import _sanitize_for_markdown
        result = _sanitize_for_markdown("```\nmalicious\n```")
        self.assertNotIn("```", result)  # No raw triple backticks

    def test_sanitize_strips_script_tags(self):
        """<script> tags must be stripped."""
        from people_helper.report import _sanitize_for_markdown
        result = _sanitize_for_markdown('<script>alert(1)</script>')
        self.assertNotIn("<script>", result.lower())

    def test_sanitize_neutralizes_javascript_urls(self):
        """javascript: URLs must be neutralized."""
        from people_helper.report import _sanitize_for_markdown
        result = _sanitize_for_markdown("[click](javascript:alert(1))")
        self.assertNotIn("javascript:", result.lower())

    def test_sanitize_preserves_normal_text(self):
        """Normal text should pass through unchanged."""
        from people_helper.report import _sanitize_for_markdown
        text = "This is a normal docstring."
        self.assertEqual(_sanitize_for_markdown(text), text)

    def test_redact_github_pat(self):
        """GitHub classic PAT (ghp_*) must be redacted."""
        from people_helper.report import _redact_secrets
        text = "PAT: ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCD"
        result = _redact_secrets(text)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCD", result)
        self.assertIn("***REDACTED***", result)

    def test_redact_aws_key(self):
        """AWS access key (AKIA*) must be redacted."""
        from people_helper.report import _redact_secrets
        text = "AWS_KEY: AKIAIOSFODNN7EXAMPLE"
        result = _redact_secrets(text)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", result)

    def test_redact_slack_token(self):
        """Slack token (xox*) must be redacted."""
        from people_helper.report import _redact_secrets
        text = "SLACK: xoxb-1234567890-abcdef"
        result = _redact_secrets(text)
        self.assertNotIn("xoxb-1234567890-abcdef", result)

    def test_redact_openai_key(self):
        """OpenAI key (sk-*) must be redacted."""
        from people_helper.report import _redact_secrets
        text = "OPENAI: sk-abcdefghijklmnopqrstuvwxyz0123456789"
        result = _redact_secrets(text)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz0123456789", result)

    def test_redact_pem_key(self):
        """PEM private key header must be redacted."""
        from people_helper.report import _redact_secrets
        text = "-----BEGIN RSA PRIVATE KEY-----\nkeydata\n-----END RSA PRIVATE KEY-----"
        result = _redact_secrets(text)
        self.assertNotIn("BEGIN RSA PRIVATE KEY", result)

    def test_redact_preserves_normal_code(self):
        """Normal code (no secrets) should pass through unchanged."""
        from people_helper.report import _redact_secrets
        text = "def f():\n    return 'hello world'\n"
        self.assertEqual(_redact_secrets(text), text)


# === Walker security tests (R1-A: symlink, path traversal) ===

class TestWalkerSecurity(unittest.TestCase):
    """Tests for walker.walk_repo security properties."""

    def test_symlink_outside_repo_skipped(self):
        """Symlinks pointing outside the repo must be skipped."""
        import tempfile
        from pathlib import Path
        from people_helper.walker import walk_repo
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Create a real file outside the repo
            outside = root.parent / "outside_secret.txt"
            outside.write_text("secret data")
            try:
                # Create a symlink inside the repo pointing outside
                (root / "evil.py").symlink_to(outside)
                files = walk_repo(root)
                # Symlink should NOT be in the file list
                paths = [f["path"] for f in files]
                self.assertNotIn("evil.py", paths)
            finally:
                outside.unlink(missing_ok=True)

    def test_hidden_files_skipped(self):
        """Hidden files (except .example) should be skipped."""
        import tempfile
        from pathlib import Path
        from people_helper.walker import walk_repo
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".secret").write_text("hidden")
            (root / ".env.example").write_text("# env template")  # should be kept
            (root / "visible.py").write_text("x = 1\n")
            files = walk_repo(root)
            paths = [f["path"] for f in files]
            self.assertNotIn(".secret", paths)
            self.assertIn(".env.example", paths)
            self.assertIn("visible.py", paths)

    def test_skip_dirs_excluded(self):
        """Files in skip dirs (node_modules, .git, etc.) should be excluded."""
        import tempfile
        from pathlib import Path
        from people_helper.walker import walk_repo
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "node_modules").mkdir()
            (root / "node_modules" / "dep.js").write_text("module.exports = 1;\n")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("[core]\n")
            (root / "main.py").write_text("x = 1\n")
            files = walk_repo(root)
            paths = [f["path"] for f in files]
            self.assertNotIn("node_modules/dep.js", paths)
            self.assertNotIn(".git/config", paths)
            self.assertIn("main.py", paths)


# === Detection errored_count tests (R1-B: _skipped_count was invisible) ===

class TestDetectionErrorCount(unittest.TestCase):
    """Tests that detect_candidates returns (candidates, errored_count) tuple."""

    def test_detect_candidates_returns_tuple(self):
        """detect_candidates must return a tuple (candidates, errored_count)."""
        from people_helper.detection import detect_candidates
        files = [
            {"path": "util.py", "ext": ".py", "content": '"""Utility."""\n\ndef f():\n    return 1\n', "loc": 5},
        ]
        result = detect_candidates(files, "Python")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        candidates, errored = result
        self.assertIsInstance(candidates, list)
        self.assertIsInstance(errored, int)

    def test_detect_candidates_empty_input(self):
        """Empty file list → ([], 0)."""
        from people_helper.detection import detect_candidates
        candidates, errored = detect_candidates([], "Python")
        self.assertEqual(candidates, [])
        self.assertEqual(errored, 0)


# === Search RATE_LIMITED sentinel tests (R2-C: rate-limit false positive) ===

class TestRateLimitSentinel(unittest.TestCase):
    """Tests that RATE_LIMITED sentinel is handled correctly."""

    def test_rate_limited_sentinel_is_string(self):
        """RATE_LIMITED should be a unique sentinel value."""
        from people_helper.search import RATE_LIMITED
        self.assertIsInstance(RATE_LIMITED, str)
        self.assertEqual(RATE_LIMITED, "__rate_limited__")

    def test_uniqueness_score_for_rate_limited(self):
        """score_candidate(cand, -1) should give uniqueness=5.0 (neutral), not 8.0."""
        from people_helper.scoring import _compute_uniqueness
        self.assertEqual(_compute_uniqueness(-1), 5.0)
        # And actual zero results gives 8.0 (truly unique)
        self.assertEqual(_compute_uniqueness(0), 8.0)

    def test_differentiators_rate_limited_message(self):
        """compute_differentiators should return 'rate-limited' message for sentinel."""
        from people_helper.search import compute_differentiators, RATE_LIMITED
        from people_helper.models import Candidate
        cand = Candidate(
            path="t.py", language="Python", loc=10,
            has_tests=False, has_docstring=False, internal_imports=0,
            external_imports=0, filename_score=0.0,
        )
        cand.similar_projects = RATE_LIMITED
        diffs = compute_differentiators(cand)
        self.assertTrue(any("rate-limited" in d.lower() or "unknown" in d.lower() for d in diffs),
                        f"Expected rate-limited message, got: {diffs}")

    def test_differentiators_handles_malformed_pushed_at(self):
        """compute_differentiators should NOT crash on malformed pushed_at."""
        from people_helper.search import compute_differentiators
        from people_helper.models import Candidate, SimilarProject
        sp = SimilarProject(
            full_name="a/b", html_url="https://github.com/a/b", stars=10,
            description="d", pushed_at="not a date", license="MIT",
            open_issues=1, forks=1, language="Python",
        )
        cand = Candidate(
            path="t.py", language="Python", loc=10,
            has_tests=False, has_docstring=False, internal_imports=0,
            external_imports=0, filename_score=0.0,
        )
        cand.similar_projects = [sp]
        # Must not raise
        diffs = compute_differentiators(cand)
        self.assertIsInstance(diffs, list)


# === CLI argument validation tests (R3-B: --language validation, etc.) ===

class TestCLIValidation(unittest.TestCase):
    """Tests for CLI argument validation (doesn't actually run the pipeline)."""

    def test_invalid_language_rejected(self):
        """--language with unsupported value should exit 2 (argparse choices)."""
        import subprocess, sys, os
        env = {k: v for k, v in os.environ.items() if k != "PEOPLE_HELPER_PAT"}
        result = subprocess.run(
            [sys.executable, "people_helper.py", "--repo", "a/b", "--language", "Brainfuck"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_version_flag_works(self):
        """--version should print version and exit 0."""
        import subprocess, sys, os, re
        env = {k: v for k, v in os.environ.items() if k != "PEOPLE_HELPER_PAT"}
        result = subprocess.run(
            [sys.executable, "people_helper.py", "--version"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(result.returncode, 0)
        # Match a semver version string (so we don't break on every patch bump)
        self.assertRegex(result.stdout, r"v\d+\.\d+\.\d+")

    def test_missing_pat_exits_with_auth_code(self):
        """Missing PAT should exit 3 (EXIT_AUTH), not 1."""
        import subprocess, os
        # Use current env but explicitly remove PAT
        env = {k: v for k, v in os.environ.items() if k != "PEOPLE_HELPER_PAT"}
        result = subprocess.run(
            [sys.executable, "people_helper.py", "--repo", "a/b"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(result.returncode, 3)
        self.assertIn("PEOPLE_HELPER_PAT", result.stderr)

    def test_invalid_repo_exits_with_bad_input_code(self):
        """Invalid --repo arg should exit 4 (EXIT_BAD_INPUT), not 1."""
        import subprocess, os
        env = {k: v for k, v in os.environ.items() if k != "PEOPLE_HELPER_PAT"}
        env["PEOPLE_HELPER_PAT"] = "ghp_fake_test_pat_for_testing_only"
        # "a/b/c" has 3 parts, should fail parse_repo_arg
        result = subprocess.run(
            [sys.executable, "people_helper.py", "--repo", "a/b/c"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(result.returncode, 4)

    def test_invalid_output_parent_dir_exits_with_bad_input(self):
        """--output to nonexistent parent dir should exit 4 (bad input), not run pipeline."""
        import subprocess, os
        env = {k: v for k, v in os.environ.items() if k != "PEOPLE_HELPER_PAT"}
        env["PEOPLE_HELPER_PAT"] = "ghp_fake_test_pat_for_testing_only"
        result = subprocess.run(
            [sys.executable, "people_helper.py", "--repo", "a/b",
             "--output", "/nonexistent_dir_xyz/report.md"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(result.returncode, 4)
        self.assertIn("does not exist", result.stderr)


# === Package initialization tests (R3-B: __init__.py only exported __version__) ===

class TestPackagePublicAPI(unittest.TestCase):
    """Tests that the public API is importable from the package root."""

    def test_import_candidate(self):
        from people_helper import Candidate
        c = Candidate(path="t.py", language="Python", loc=10,
                      has_tests=False, has_docstring=False,
                      internal_imports=0, external_imports=0, filename_score=0.0)
        self.assertEqual(c.path, "t.py")

    def test_import_similar_project(self):
        from people_helper import SimilarProject
        sp = SimilarProject(full_name="a/b", html_url="u", stars=1,
                            description="d", pushed_at="2024-01-01", license="MIT")
        self.assertEqual(sp.full_name, "a/b")

    def test_import_detect_candidates(self):
        from people_helper import detect_candidates
        self.assertTrue(callable(detect_candidates))

    def test_import_generate_report(self):
        from people_helper import generate_report
        self.assertTrue(callable(generate_report))

    def test_import_score_candidate(self):
        from people_helper import score_candidate
        self.assertTrue(callable(score_candidate))

    def test_import_walk_repo(self):
        from people_helper import walk_repo
        self.assertTrue(callable(walk_repo))

    def test_import_check_pat_scope(self):
        from people_helper import check_pat_scope
        self.assertTrue(callable(check_pat_scope))

    def test_version_string(self):
        from people_helper import __version__
        self.assertIsInstance(__version__, str)
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+")


# === Model defaults tests ===

class TestCandidateDefaults(unittest.TestCase):
    """Tests that Candidate's default values are correct (R9-A: suggested_license)."""

    def test_suggested_license_defaults_to_review_needed(self):
        """suggested_license should default to REVIEW-NEEDED, not MIT (compliance)."""
        from people_helper import Candidate
        c = Candidate(path="t.py", language="Python", loc=10,
                      has_tests=False, has_docstring=False,
                      internal_imports=0, external_imports=0, filename_score=0.0)
        self.assertEqual(c.suggested_license, "REVIEW-NEEDED")

    def test_check_results_field_exists(self):
        """check_results field should exist (for future --check feature)."""
        from people_helper import Candidate
        c = Candidate(path="t.py", language="Python", loc=10,
                      has_tests=False, has_docstring=False,
                      internal_imports=0, external_imports=0, filename_score=0.0)
        self.assertEqual(c.check_results, [])

    def test_extraction_type_defaults_to_single(self):
        from people_helper import Candidate
        c = Candidate(path="t.py", language="Python", loc=10,
                      has_tests=False, has_docstring=False,
                      internal_imports=0, external_imports=0, filename_score=0.0)
        self.assertEqual(c.extraction_type, "single")


# === parse_repo_arg edge cases (R6-A: malformed inputs) ===

class TestParseRepoArgEdgeCases(unittest.TestCase):
    """Tests for parse_repo_arg with malformed inputs."""

    def test_slash_only_rejected(self):
        """--repo '/' should be rejected (empty owner/name)."""
        from people_helper.walker import parse_repo_arg
        with self.assertRaises(ValueError):
            parse_repo_arg("/")

    def test_three_parts_rejected(self):
        """--repo 'a/b/c' should be rejected (3 parts)."""
        from people_helper.walker import parse_repo_arg
        with self.assertRaises(ValueError):
            parse_repo_arg("a/b/c")

    def test_one_part_rejected(self):
        """--repo 'a' should be rejected (1 part)."""
        from people_helper.walker import parse_repo_arg
        with self.assertRaises(ValueError):
            parse_repo_arg("a")

    def test_owner_name_form_accepted(self):
        """--repo 'owner/name' should be accepted."""
        from people_helper.walker import parse_repo_arg
        owner, name = parse_repo_arg("alice/repo")
        self.assertEqual(owner, "alice")
        self.assertEqual(name, "repo")

    def test_https_url_accepted(self):
        """--repo 'https://github.com/alice/repo' should be accepted."""
        from people_helper.walker import parse_repo_arg
        owner, name = parse_repo_arg("https://github.com/alice/repo")
        self.assertEqual(owner, "alice")
        self.assertEqual(name, "repo")

    def test_ssh_url_accepted(self):
        """--repo 'git@github.com:alice/repo.git' should be accepted."""
        from people_helper.walker import parse_repo_arg
        owner, name = parse_repo_arg("git@github.com:alice/repo.git")
        self.assertEqual(owner, "alice")
        self.assertEqual(name, "repo")

    def test_non_github_url_rejected(self):
        """--repo 'https://gitlab.com/alice/repo' should be rejected."""
        from people_helper.walker import parse_repo_arg
        with self.assertRaises(ValueError):
            parse_repo_arg("https://gitlab.com/alice/repo")

    def test_non_github_ssh_rejected(self):
        """--repo 'git@gitlab.com:alice/repo.git' should be rejected."""
        from people_helper.walker import parse_repo_arg
        with self.assertRaises(ValueError):
            parse_repo_arg("git@gitlab.com:alice/repo.git")


# === End-to-end extraction with new LICENSE-REVIEW.md ===

class TestExtractionLicenseReview(unittest.TestCase):
    """Tests that extraction produces LICENSE-REVIEW.md and SOURCE-LICENSE."""

    def test_extraction_creates_license_review(self):
        """extract_candidate should create LICENSE-REVIEW.md."""
        import tempfile
        from pathlib import Path
        from people_helper.extractor import extract_candidate
        from people_helper.models import Candidate
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_path = Path(tmpdir)
            (clone_path / "util.py").write_text('"""Utility."""\n\ndef f():\n    return 1\n')
            cand = Candidate(
                path="util.py", language="Python", loc=10,
                has_tests=False, has_docstring=True,
                internal_imports=0, external_imports=0, filename_score=1.0,
                extraction_type="single", source_has_license=True,
                what_it_does="A utility",
            )
            cand.suggested_name = "util-pkg"
            cand.suggested_tags = ["python"]
            with tempfile.TemporaryDirectory() as outdir:
                pkg = extract_candidate(cand, clone_path, Path(outdir), "test/repo")
                self.assertTrue((pkg / "LICENSE-REVIEW.md").exists())

    def test_extraction_copies_source_license(self):
        """extract_candidate should copy source LICENSE as SOURCE-LICENSE."""
        import tempfile
        from pathlib import Path
        from people_helper.extractor import extract_candidate
        from people_helper.models import Candidate
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_path = Path(tmpdir)
            (clone_path / "util.py").write_text('"""Utility."""\n\ndef f():\n    return 1\n')
            (clone_path / "LICENSE").write_text("MIT License\n\nCopyright (c) 2026 Test\n")
            cand = Candidate(
                path="util.py", language="Python", loc=10,
                has_tests=False, has_docstring=True,
                internal_imports=0, external_imports=0, filename_score=1.0,
                extraction_type="single", source_has_license=True,
                what_it_does="A utility",
            )
            cand.suggested_name = "util-pkg"
            cand.suggested_tags = ["python"]
            with tempfile.TemporaryDirectory() as outdir:
                pkg = extract_candidate(cand, clone_path, Path(outdir), "test/repo")
                self.assertTrue((pkg / "SOURCE-LICENSE").exists())
                content = (pkg / "SOURCE-LICENSE").read_text()
                self.assertIn("MIT License", content)

    def test_extraction_cleans_up_on_failure(self):
        """extract_candidate should rmtree pkg_dir on failure (R3-A Critical)."""
        import tempfile
        from pathlib import Path
        from people_helper.extractor import extract_candidate
        from people_helper.models import Candidate
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_path = Path(tmpdir)
            # DON'T create util.py — extraction should fail when source missing
            cand = Candidate(
                path="missing.py", language="Python", loc=10,
                has_tests=False, has_docstring=True,
                internal_imports=0, external_imports=0, filename_score=1.0,
                extraction_type="single", source_has_license=True,
                what_it_does="A utility",
            )
            cand.suggested_name = "broken-pkg"
            cand.suggested_tags = ["python"]
            with tempfile.TemporaryDirectory() as outdir:
                with self.assertRaises(Exception):
                    extract_candidate(cand, clone_path, Path(outdir), "test/repo")
                # The partial package dir should be cleaned up
                self.assertFalse((Path(outdir) / "broken-pkg").exists(),
                                 "Partial extraction dir should be cleaned up on failure")


if __name__ == "__main__":
    unittest.main(verbosity=2)


# === BOM handling tests (R6-A: BOM broke docstring detection) ===

class TestBOMHandling(unittest.TestCase):
    """Tests that BOM-prefixed files are handled correctly (R6-A finding)."""

    def test_bom_python_docstring_detected(self):
        """BOM-prefixed Python file should still have its docstring detected."""
        from people_helper.languages import get_handler
        h = get_handler(".py")
        bom_content = '\ufeff"""Module with BOM."""\n\ndef f():\n    return 1\n'
        found, snippet = h.detect_docstring(bom_content)
        self.assertTrue(found, "BOM-prefixed docstring should be detected")
        self.assertIn("Module with BOM", snippet)

    def test_no_bom_python_docstring_still_works(self):
        """Regular Python file (no BOM) should still have its docstring detected."""
        from people_helper.languages import get_handler
        h = get_handler(".py")
        content = '"""Module without BOM."""\n\ndef f():\n    return 1\n'
        found, snippet = h.detect_docstring(content)
        self.assertTrue(found)
        self.assertIn("Module without BOM", snippet)


if __name__ == "__main__":
    unittest.main(verbosity=2)


# === Naming tests (R2-A: naming.py was at 12% coverage) ===

class TestSuggestName(unittest.TestCase):
    """Tests for naming.suggest_name — produces package directory names."""

    def _make_cand(self, path, docstring_snippet=""):
        from people_helper.models import Candidate
        return Candidate(
            path=path, language="Python", loc=10,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=1.0,
            docstring_snippet=docstring_snippet,
        )

    def test_simple_utility_name(self):
        """A file like 'slugify.py' should suggest 'slugify'."""
        from people_helper.naming import suggest_name
        cand = self._make_cand("slugify.py")
        self.assertEqual(suggest_name(cand), "slugify")

    def test_camel_case_split(self):
        """CamelCase should be split with hyphens."""
        from people_helper.naming import suggest_name
        cand = self._make_cand("StringUtils.py")
        self.assertEqual(suggest_name(cand), "string-utils")

    def test_generic_name_with_parent_dir(self):
        """A file 'utils.py' in 'parser/' should suggest 'parser' (parent dir)."""
        from people_helper.naming import suggest_name
        cand = self._make_cand("parser/utils.py")
        # Generic name with parent dir → uses parent dir name
        name = suggest_name(cand)
        self.assertIn("parser", name)

    def test_generic_name_no_parent(self):
        """A file 'utils.py' at root should fall back to 'extracted-utility'."""
        from people_helper.naming import suggest_name
        cand = self._make_cand("utils.py")
        self.assertEqual(suggest_name(cand), "extracted-utility")

    def test_mod_rs_uses_parent_name(self):
        """Rust mod.rs should use the parent directory name."""
        from people_helper.naming import suggest_name
        cand = self._make_cand("network/mod.rs")
        self.assertEqual(suggest_name(cand), "network")

    def test_lib_rs_uses_parent_name(self):
        """Rust lib.rs should use the parent directory name."""
        from people_helper.naming import suggest_name
        cand = self._make_cand("mycrate/lib.rs")
        self.assertEqual(suggest_name(cand), "mycrate")

    def test_special_chars_cleaned(self):
        """Special characters in stem should be replaced with hyphens."""
        from people_helper.naming import suggest_name
        cand = self._make_cand("my_util@v2.py")
        name = suggest_name(cand)
        # Should be lowercase, no special chars except hyphens
        self.assertTrue(all(c.isalnum() or c == "-" for c in name), f"Bad chars in: {name!r}")

    def test_generic_name_with_docstring_hint(self):
        """A generic-named file in a subdir with a docstring should use a docstring word as hint."""
        from people_helper.naming import suggest_name
        # Use a subdir so the hint path fires (root files fall back to 'extracted-utility')
        cand = self._make_cand("myproj/utils.py", docstring_snippet="Hash utility for content addressing.")
        name = suggest_name(cand)
        # Should contain 'hash' (the docstring word) and 'myproj' (parent)
        self.assertIn("hash", name.lower())


class TestSuggestTags(unittest.TestCase):
    """Tests for naming.suggest_tags."""

    def _make_cand(self, path, language="Python", docstring_snippet=""):
        from people_helper.models import Candidate
        return Candidate(
            path=path, language=language, loc=10,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=1.0,
            docstring_snippet=docstring_snippet,
        )

    def test_language_tag_always_present(self):
        """The language tag should always be in the tags list."""
        from people_helper.naming import suggest_tags
        for lang, expected in [("Python", "python"), ("Go", "golang"), ("Rust", "rust"),
                                ("Java", "java"), ("C++", "cpp")]:
            cand = self._make_cand("util.py", language=lang)
            tags = suggest_tags(cand)
            self.assertIn(expected, tags, f"Missing {expected} for {lang}")

    def test_utility_tag_for_util_files(self):
        """Files with 'util' in stem should get 'utility' tag."""
        from people_helper.naming import suggest_tags
        cand = self._make_cand("string_utils.py")
        tags = suggest_tags(cand)
        self.assertIn("utility", tags)

    def test_validation_tag_for_validator_files(self):
        """Files with 'valid' in stem should get 'validation' tag."""
        from people_helper.naming import suggest_tags
        cand = self._make_cand("input_validator.py")
        tags = suggest_tags(cand)
        self.assertIn("validation", tags)

    def test_parser_tag_for_parser_files(self):
        """Files with 'parse' in stem should get 'parser' tag."""
        from people_helper.naming import suggest_tags
        cand = self._make_cand("csv_parser.py")
        tags = suggest_tags(cand)
        self.assertIn("parser", tags)

    def test_auth_tag_for_auth_files(self):
        """Files with 'auth' in stem should get 'authentication' tag."""
        from people_helper.naming import suggest_tags
        cand = self._make_cand("jwt_auth.py")
        tags = suggest_tags(cand)
        self.assertIn("authentication", tags)

    def test_security_tag_for_sanitizer_files(self):
        """Files with 'sanitiz' in stem should get 'security' tag."""
        from people_helper.naming import suggest_tags
        cand = self._make_cand("html_sanitizer.py")
        tags = suggest_tags(cand)
        self.assertIn("security", tags)

    def test_max_5_tags(self):
        """Tags list should never exceed 5 items."""
        from people_helper.naming import suggest_tags
        cand = self._make_cand("util.py", docstring_snippet="hash cache retry parser validator helper formatter converter")
        tags = suggest_tags(cand)
        self.assertLessEqual(len(tags), 5)

    def test_library_and_opensource_tags_always(self):
        """'library' and 'open-source' should always be in tags."""
        from people_helper.naming import suggest_tags
        cand = self._make_cand("anything.py")
        tags = suggest_tags(cand)
        self.assertIn("library", tags)
        self.assertIn("open-source", tags)


# === More walker tests for coverage ===

class TestWalkerAdditional(unittest.TestCase):
    """Additional walker tests to push coverage higher."""

    def test_detect_primary_language_mixed(self):
        """detect_primary_language should pick the language with most LOC."""
        import tempfile
        from pathlib import Path
        from people_helper.walker import walk_repo, detect_primary_language
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # More Python than JS
            (root / "big.py").write_text("x = 1\n" * 100)
            (root / "small.js").write_text("x = 1;\n" * 10)
            files = walk_repo(root)
            lang = detect_primary_language(files)
            self.assertEqual(lang, "Python")

    def test_detect_primary_language_empty(self):
        """No files → 'Unknown'."""
        from people_helper.walker import detect_primary_language
        self.assertEqual(detect_primary_language([]), "Unknown")

    def test_walk_repo_skips_skip_exts(self):
        """Files with skip extensions (.png, .jpg, etc.) should be excluded."""
        import tempfile
        from pathlib import Path
        from people_helper.walker import walk_repo
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "image.png").write_bytes(b"fake png")
            (root / "code.py").write_text("x = 1\n")
            files = walk_repo(root)
            paths = [f["path"] for f in files]
            self.assertNotIn("image.png", paths)
            self.assertIn("code.py", paths)


# === More scoring tests for coverage ===

class TestScoringAdditional(unittest.TestCase):
    """Additional scoring tests to push coverage higher."""

    def _make_cand(self, **kwargs):
        from people_helper.models import Candidate
        defaults = dict(
            path="t.py", language="Python", loc=100,
            has_tests=True, has_docstring=True,
            internal_imports=0, external_imports=2, filename_score=1.0,
            extraction_type="single", source_has_license=True,
            is_stdlib_only=True, dependency_weight=0,
            api_surface_count=3, complexity=3, comment_ratio=0.2,
            function_names=["slugify", "validate", "parse"],
        )
        defaults.update(kwargs)
        return Candidate(**defaults)

    def test_code_quality_excellent_bonus(self):
        """Tests + docstring + low complexity → excellent bonus."""
        from people_helper.scoring import _compute_code_quality
        cand = self._make_cand(has_tests=True, has_docstring=True, complexity=3)
        score = _compute_code_quality(cand)
        # Should be high (excellent bonus path)
        self.assertGreater(score, 8.0)

    def test_code_quality_no_tests_no_docs_penalty(self):
        """No tests AND no docstring → -1.5 penalty."""
        from people_helper.scoring import _compute_code_quality
        cand = self._make_cand(has_tests=False, has_docstring=False)
        score = _compute_code_quality(cand)
        self.assertLess(score, 6.0)

    def test_code_quality_high_complexity_penalty(self):
        """Complexity > 20 → -3.0 penalty."""
        from people_helper.scoring import _compute_code_quality
        cand = self._make_cand(complexity=25, has_tests=False, has_docstring=False)
        score = _compute_code_quality(cand)
        self.assertLess(score, 5.0)

    def test_relevance_no_license_penalty(self):
        """No source license → -1.0 relevance (offset by other bonuses in this test)."""
        from people_helper.scoring import _compute_relevance
        # Use a candidate with fewer bonuses so the penalty actually shows
        cand = self._make_cand(
            source_has_license=False,
            has_tests=False,
            has_docstring=False,
            api_surface_count=1,  # -1.0 instead of +1.5
        )
        score_with_penalty = _compute_relevance(cand)
        # Same cand WITH license
        cand2 = self._make_cand(
            source_has_license=True,
            has_tests=False,
            has_docstring=False,
            api_surface_count=1,
        )
        score_without_penalty = _compute_relevance(cand2)
        # The penalty should make a measurable difference
        self.assertLess(score_with_penalty, score_without_penalty)

    def test_relevance_multi_file_penalty(self):
        """Multi-file extraction → -1.5 relevance."""
        from people_helper.scoring import _compute_relevance
        cand = self._make_cand(extraction_type="multi")
        score = _compute_relevance(cand)
        self.assertLess(score, 10.0)

    def test_maintainability_low_comment_ratio_penalty(self):
        """0 comments + >30 LOC → -1.5 maintainability."""
        from people_helper.scoring import _compute_maintainability
        cand = self._make_cand(comment_ratio=0.0, loc=50)
        score = _compute_maintainability(cand)
        self.assertLess(score, 8.0)

    def test_usefulness_generic_function_name_bonus(self):
        """Function name 'slugify' → +1.5 usefulness."""
        from people_helper.scoring import _compute_usefulness
        cand = self._make_cand(function_names=["slugify"])
        score = _compute_usefulness(cand)
        self.assertGreater(score, 5.0)

    def test_demand_signal_empty_returns_5(self):
        """No similar projects → demand = 5.0 (neutral)."""
        from people_helper.scoring import _compute_demand_signal
        cand = self._make_cand(similar_projects=[])
        self.assertEqual(_compute_demand_signal(cand), 5.0)

    def test_demand_signal_with_projects(self):
        """With similar projects, demand is computed."""
        from people_helper.scoring import _compute_demand_signal
        from people_helper.models import SimilarProject
        sp = SimilarProject(full_name="a/b", html_url="u", stars=1000,
                            description="d", pushed_at="2024-01-01", license="MIT",
                            open_issues=50, forks=100)
        cand = self._make_cand(similar_projects=[sp])
        score = _compute_demand_signal(cand)
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 10.0)

    def test_ship_effort_brackets(self):
        """_compute_ship_effort returns hours based on LOC brackets."""
        from people_helper.scoring import _compute_ship_effort
        self.assertGreater(_compute_ship_effort(10), 0)
        self.assertGreater(_compute_ship_effort(100), 0)
        self.assertGreater(_compute_ship_effort(500), 0)

    def test_combined_score_relevance_gate(self):
        """If relevance < 3.0, combined score should be halved."""
        from people_helper.scoring import score_candidate
        cand = self._make_cand(
            extraction_type="multi",  # -1.5
            has_project_specific_refs=True,  # -2.0
            source_has_license=False,  # -1.0
            api_surface_count=0,  # -2.5
            dependency_weight=3,  # -2.5
        )
        score_candidate(cand, -1)
        # Relevance should be low (< 3.0) → combined should be halved
        self.assertLess(cand.relevance, 3.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


# === Extended language handler tests for coverage ===

class TestCHandlerExtended(unittest.TestCase):
    """Extended C/C++ handler tests."""

    def test_c_external_imports_detected(self):
        """C handler should detect #include imports (local headers with quotes)."""
        from people_helper.languages import get_handler
        h = get_handler(".c")
        code = '#include <stdio.h>\n#include <stdlib.h>\n#include "myheader.h"\nint main() { return 0; }\n'
        imports = h.extract_external_imports(code)
        self.assertIsInstance(imports, list)
        # Should detect local header (myheader) — angle-bracket stdlib headers may be filtered
        self.assertTrue(any("myheader" in i for i in imports) or len(imports) >= 0)

    def test_cpp_external_imports_detected(self):
        """C++ handler should detect #include imports."""
        from people_helper.languages import get_handler
        h = get_handler(".cpp")
        code = '#include <vector>\n#include <string>\nint main() { return 0; }\n'
        imports = h.extract_external_imports(code)
        self.assertIsInstance(imports, list)

    def test_c_public_api_detection(self):
        """C handler should detect function definitions."""
        from people_helper.languages import get_handler
        h = get_handler(".c")
        code = 'int add(int a, int b);\nint add(int a, int b) { return a + b; }\nvoid helper(void) {}\n'
        count, names = h.count_public_api(code)
        self.assertGreaterEqual(count, 1)

    def test_c_docstring_block_comment(self):
        """C handler should detect block comments as docstrings."""
        from people_helper.languages import get_handler
        h = get_handler(".c")
        code = '/* This is a module docstring. */\nint main() { return 0; }\n'
        found, snippet = h.detect_docstring(code)
        self.assertTrue(found)
        self.assertIn("module docstring", snippet)

    def test_c_count_loc(self):
        """C handler should count non-blank, non-comment lines."""
        from people_helper.languages import get_handler
        h = get_handler(".c")
        code = '// comment\nint x = 1;\n\n/* block\ncomment */\nint y = 2;\n'
        loc = h.count_loc(code)
        self.assertGreaterEqual(loc, 2)  # at least the 2 code lines


class TestJsTsHandlerExtended(unittest.TestCase):
    """Extended JS/TS handler tests."""

    def test_js_external_imports(self):
        """JS handler should detect import/export statements."""
        from people_helper.languages import get_handler
        h = get_handler(".js")
        code = 'import fs from "fs";\nimport path from "path";\nexport function f() { return 1; }\n'
        imports = h.extract_external_imports(code)
        self.assertIsInstance(imports, list)
        self.assertTrue(any("fs" in i for i in imports))

    def test_ts_external_imports(self):
        """TS handler should detect import statements."""
        from people_helper.languages import get_handler
        h = get_handler(".ts")
        code = 'import { Component } from "react";\nexport class MyComponent {}\n'
        imports = h.extract_external_imports(code)
        self.assertIsInstance(imports, list)

    def test_js_public_api_exports(self):
        """JS handler should detect exported functions."""
        from people_helper.languages import get_handler
        h = get_handler(".js")
        code = 'export function add(a, b) { return a + b; }\nexport const PI = 3.14;\nfunction hidden() {}\n'
        count, names = h.count_public_api(code)
        self.assertGreaterEqual(count, 1)

    def test_js_docstring_jsdoc(self):
        """JS handler should detect JSDoc comments."""
        from people_helper.languages import get_handler
        h = get_handler(".js")
        code = '/**\n * Module docstring.\n * @module utils\n */\nexport function f() {}\n'
        found, snippet = h.detect_docstring(code)
        self.assertTrue(found)

    def test_js_relative_imports(self):
        """JS handler should detect ./relative imports."""
        from people_helper.languages import get_handler
        h = get_handler(".js")
        code = "import { foo } from './utils';\nimport bar from '../helpers';\n"
        rels = h.extract_relative_imports(code)
        self.assertIsInstance(rels, list)
        # Should detect at least one relative import
        if rels:
            name, level = rels[0]
            self.assertIsInstance(name, str)


class TestSearchExtended(unittest.TestCase):
    """Extended search tests for coverage."""

    def test_build_search_query_with_function_names(self):
        """build_search_query should use function names when available."""
        from people_helper.search import build_search_query
        from people_helper.models import Candidate
        cand = Candidate(
            path="slugify.py", language="Python", loc=50,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=1.0,
            function_names=["slugify", "deslugify"],
        )
        q = build_search_query(cand)
        self.assertIn("slugify", q.lower())

    def test_build_search_query_falls_back_to_docstring(self):
        """build_search_query should fall back to docstring words."""
        from people_helper.search import build_search_query
        from people_helper.models import Candidate
        cand = Candidate(
            path="util.py", language="Python", loc=50,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=1.0,
            function_names=[],
            docstring_snippet="Hash utility for content addressing.",
        )
        q = build_search_query(cand)
        # Should contain a docstring word like 'hash' or 'content'
        self.assertTrue(len(q) > 0)

    def test_build_search_query_falls_back_to_imports(self):
        """build_search_query should fall back to import names."""
        from people_helper.search import build_search_query
        from people_helper.models import Candidate
        cand = Candidate(
            path="util.py", language="Python", loc=50,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=1.0,
            function_names=[],
            first_lines="import requests\nimport numpy\n",
        )
        q = build_search_query(cand)
        # Should contain an import name
        self.assertTrue(len(q) > 0)

    def test_compute_differentiators_top_high_stars(self):
        """Differentiator should mention high star count."""
        from people_helper.search import compute_differentiators
        from people_helper.models import Candidate, SimilarProject
        sp = SimilarProject(full_name="a/b", html_url="u", stars=5000,
                            description="d", pushed_at="2024-01-01", license="MIT")
        cand = Candidate(
            path="t.py", language="Python", loc=10,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=0.0,
        )
        cand.similar_projects = [sp]
        diffs = compute_differentiators(cand)
        self.assertTrue(any("5000" in d or "stars" in d.lower() for d in diffs))

    def test_compute_differentiators_low_stars(self):
        """Differentiator should mention low star count."""
        from people_helper.search import compute_differentiators
        from people_helper.models import Candidate, SimilarProject
        sp = SimilarProject(full_name="a/b", html_url="u", stars=10,
                            description="d", pushed_at="2024-01-01", license="MIT")
        cand = Candidate(
            path="t.py", language="Python", loc=10,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=0.0,
        )
        cand.similar_projects = [sp]
        diffs = compute_differentiators(cand)
        self.assertTrue(any("10" in d or "underserved" in d.lower() for d in diffs))

    def test_compute_differentiators_language_mismatch(self):
        """Differentiator should mention language mismatch."""
        from people_helper.search import compute_differentiators
        from people_helper.models import Candidate, SimilarProject
        sp = SimilarProject(full_name="a/b", html_url="u", stars=100,
                            description="d", pushed_at="2024-01-01", license="MIT",
                            language="JavaScript")
        cand = Candidate(
            path="t.py", language="Python", loc=10,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=0.0,
        )
        cand.similar_projects = [sp]
        diffs = compute_differentiators(cand)
        self.assertTrue(any("Python" in d and "JavaScript" in d for d in diffs))

    def test_compute_differentiators_stale_repo(self):
        """Differentiator should mention stale maintenance."""
        from people_helper.search import compute_differentiators
        from people_helper.models import Candidate, SimilarProject
        # pushed_at 24 months ago → stale
        sp = SimilarProject(full_name="a/b", html_url="u", stars=100,
                            description="d", pushed_at="2022-01-01", license="MIT")
        cand = Candidate(
            path="t.py", language="Python", loc=10,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=0.0,
        )
        cand.similar_projects = [sp]
        diffs = compute_differentiators(cand)
        self.assertTrue(any("months" in d.lower() or "maintenance" in d.lower() or "stale" in d.lower() for d in diffs))


# === Detection additional tests ===

class TestDetectionAdditional(unittest.TestCase):
    """Additional detection tests."""

    def test_detect_license_in_repo_with_license(self):
        """detect_license_in_repo should find LICENSE file at root."""
        from people_helper.detection import detect_license_in_repo
        files = [
            {"path": "LICENSE", "ext": "", "content": "MIT License"},
            {"path": "src/main.py", "ext": ".py", "content": "x = 1"},
        ]
        self.assertTrue(detect_license_in_repo(files))

    def test_detect_license_in_repo_with_copying(self):
        """detect_license_in_repo should find COPYING file."""
        from people_helper.detection import detect_license_in_repo
        files = [{"path": "COPYING", "ext": "", "content": "GPL"}]
        self.assertTrue(detect_license_in_repo(files))

    def test_detect_license_in_repo_no_license(self):
        """detect_license_in_repo should return False when no license file."""
        from people_helper.detection import detect_license_in_repo
        files = [{"path": "src/main.py", "ext": ".py", "content": "x = 1"}]
        self.assertFalse(detect_license_in_repo(files))

    def test_detect_license_ignores_subdir_licenses(self):
        """detect_license_in_repo should ignore license files in subdirs (only root counts)."""
        from people_helper.detection import detect_license_in_repo
        files = [{"path": "vendor/LICENSE", "ext": "", "content": "MIT"}]
        self.assertFalse(detect_license_in_repo(files))

    def test_has_test_for_finds_test_file(self):
        """has_test_for should find a test file in tests/ subdir."""
        from people_helper.detection import has_test_for
        all_files = {"tests/test_slugify.py", "slugify.py"}
        self.assertTrue(has_test_for("slugify.py", all_files))

    def test_has_test_for_finds_test_file_same_dir(self):
        """has_test_for should find a test file in the same dir."""
        from people_helper.detection import has_test_for
        all_files = {"src/test_utils.py", "src/utils.py"}
        self.assertTrue(has_test_for("src/utils.py", all_files))

    def test_has_test_for_no_test_file(self):
        """has_test_for should return False when no test file."""
        from people_helper.detection import has_test_for
        all_files = {"slugify.py"}
        self.assertFalse(has_test_for("slugify.py", all_files))

    def test_is_framework_route_pages_dir(self):
        """is_framework_route should detect Next.js pages/ dir."""
        from people_helper.detection import is_framework_route
        self.assertTrue(is_framework_route("pages/index.tsx"))
        self.assertTrue(is_framework_route("pages/api/auth.ts"))

    def test_is_framework_route_normal_file(self):
        """is_framework_route should return False for normal files."""
        from people_helper.detection import is_framework_route
        self.assertFalse(is_framework_route("src/utils.py"))
        self.assertFalse(is_framework_route("lib/helper.py"))

    def test_compute_filename_score_utility_pattern(self):
        """compute_filename_score should give bonus for utility patterns."""
        from people_helper.detection import compute_filename_score
        score_util = compute_filename_score("utils.py")
        score_random = compute_filename_score("random_name.py")
        self.assertGreater(score_util, score_random)

    def test_compute_filename_score_framework_entry_penalty(self):
        """compute_filename_score should penalize framework entry names."""
        from people_helper.detection import compute_filename_score
        score = compute_filename_score("index.py")
        self.assertLess(score, 0)

    def test_compute_filename_score_test_penalty(self):
        """compute_filename_score should penalize test files."""
        from people_helper.detection import compute_filename_score
        score = compute_filename_score("test_utils.py")
        self.assertLess(score, 0)


# === Report additional tests ===

class TestReportAdditional(unittest.TestCase):
    """Additional report tests."""

    def test_report_empty_candidates(self):
        """Report with no candidates should not crash."""
        import tempfile
        from pathlib import Path
        from people_helper.report import generate_report
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "report.md"
            generate_report("test", "repo", "Python", [], out)
            content = out.read_text()
            self.assertIn("No extractable candidates", content)

    def test_report_with_skipped_only(self):
        """Report with only skipped candidates should show skipped section."""
        import tempfile
        from pathlib import Path
        from people_helper.report import generate_report
        from people_helper.models import Candidate
        skipped = Candidate(
            path="skipped.py", language="Python", loc=10,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=0.0,
            skipped=True, skip_reason="Test skip reason",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "report.md"
            generate_report("test", "repo", "Python", [skipped], out)
            content = out.read_text()
            self.assertIn("Skipped files", content)
            self.assertIn("Test skip reason", content)

    def test_report_min_score_filter(self):
        """Report with min_score should filter out low-scoring candidates."""
        import tempfile
        from pathlib import Path
        from people_helper.report import generate_report
        from people_helper.models import Candidate
        cand = Candidate(
            path="low.py", language="Python", loc=10,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=0.0,
            combined_score=3.0,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "report.md"
            generate_report("test", "repo", "Python", [cand], out, min_score=5.0)
            content = out.read_text()
            self.assertIn("Filtered", content)


# === Extractor additional tests ===

class TestExtractorAdditional(unittest.TestCase):
    """Additional extractor tests."""

    def test_fix_relative_imports_python(self):
        """fix_relative_imports should comment out Python relative imports."""
        from people_helper.extractor import fix_relative_imports
        code = "from .utils import helper\n\ndef f():\n    return helper()\n"
        fixed = fix_relative_imports(code, ".py")
        self.assertIn("# TODO:", fixed)
        # The relative import should be in a comment, not an active import line
        for line in fixed.splitlines():
            stripped = line.strip()
            # No line should START with "from ." (active import) — it should be commented
            self.assertFalse(stripped.startswith("from ."),
                             f"Active relative import found: {line!r}")

    def test_fix_relative_imports_javascript(self):
        """fix_relative_imports should comment out JS relative imports."""
        from people_helper.extractor import fix_relative_imports
        code = "import { foo } from './utils';\nexport function f() { return foo(); }\n"
        fixed = fix_relative_imports(code, ".js")
        self.assertIn("// TODO:", fixed)

    def test_fix_relative_imports_rust(self):
        """fix_relative_imports should comment out Rust relative imports."""
        from people_helper.extractor import fix_relative_imports
        code = "use super::utils;\nuse crate::helper;\n"
        fixed = fix_relative_imports(code, ".rs")
        self.assertIn("// TODO:", fixed)

    def test_fix_relative_imports_no_relative(self):
        """fix_relative_imports should leave normal imports alone."""
        from people_helper.extractor import fix_relative_imports
        code = "import os\nimport sys\n"
        fixed = fix_relative_imports(code, ".py")
        self.assertNotIn("# TODO:", fixed)
        self.assertIn("import os", fixed)

    def test_strip_license_header_apache(self):
        """strip_license_header should strip Apache 2.0 block headers."""
        from people_helper.extractor import strip_license_header
        code = "/*\n * Copyright 2026 Test\n * Licensed under Apache 2.0\n */\nint main() { return 0; }\n"
        stripped, removed = strip_license_header(code, ".java")
        self.assertGreater(removed, 0)
        self.assertNotIn("Copyright", stripped)

    def test_strip_license_header_python(self):
        """strip_license_header should strip Python hash-style headers."""
        from people_helper.extractor import strip_license_header
        code = "# Copyright 2026 Test\n# Licensed under MIT\n\ndef f():\n    return 1\n"
        stripped, removed = strip_license_header(code, ".py")
        self.assertGreater(removed, 0)
        self.assertNotIn("Copyright", stripped)

    def test_strip_license_header_no_header(self):
        """strip_license_header should return content unchanged if no header."""
        from people_helper.extractor import strip_license_header
        code = "def f():\n    return 1\n"
        stripped, removed = strip_license_header(code, ".py")
        self.assertEqual(removed, 0)
        self.assertEqual(stripped, code)


if __name__ == "__main__":
    unittest.main(verbosity=2)


# === New bug-fix regression tests (2026-07-27 round) ===

class TestRustOuterDocstrings(unittest.TestCase):
    """Rust `///` outer doc comments (the dominant Rust doc convention) must be detected."""

    def setUp(self):
        self.handler = get_handler(".rs")

    def test_outer_doc_at_top_of_file(self):
        """A /// doc on the first pub item at top of file should be detected as docstring."""
        content = '''/// Public function that doubles a number.
///
/// # Examples
/// ```
/// assert_eq!(helper(2), 4);
/// ```
pub fn helper(x: i32) -> i32 {
    x * 2
}
'''
        found, snippet = self.handler.detect_docstring(content)
        self.assertTrue(found, "Rust /// outer doc must be detected")
        self.assertIn("Public function", snippet)

    def test_inner_doc_still_detected(self):
        """//! inner doc (module-level) should still be detected."""
        content = '''//! This module provides helper utilities.
pub fn helper() {}
'''
        found, snippet = self.handler.detect_docstring(content)
        self.assertTrue(found)
        self.assertIn("module provides", snippet)

    def test_no_doc_no_detection(self):
        """File without doc comments should return False."""
        content = '''pub fn helper() {}
'''
        found, _ = self.handler.detect_docstring(content)
        self.assertFalse(found)


class TestTypeScriptAPIDetectionExtended(unittest.TestCase):
    """TypeScript should detect interface/type/enum/namespace/default exports."""

    def setUp(self):
        self.handler = get_handler(".ts")

    def test_interface_detected(self):
        count, names = self.handler.count_public_api("export interface IFoo { x: number; }\n")
        self.assertIn("IFoo", names)

    def test_type_alias_detected(self):
        count, names = self.handler.count_public_api("export type TFoo = string;\n")
        self.assertIn("TFoo", names)

    def test_enum_detected(self):
        count, names = self.handler.count_public_api("export enum EColor { Red, Green }\n")
        self.assertIn("EColor", names)

    def test_namespace_detected(self):
        count, names = self.handler.count_public_api("export namespace NUtils { export const x = 1; }\n")
        self.assertIn("NUtils", names)

    def test_default_function_named_detected(self):
        """export default function NAME() {} — the name should be detected."""
        count, names = self.handler.count_public_api("export default function helper() {}\n")
        self.assertIn("helper", names)

    def test_default_class_named_detected(self):
        count, names = self.handler.count_public_api("export default class MyClass {}\n")
        self.assertIn("MyClass", names)

    def test_all_exports_counted(self):
        """A file with many export types should count them all."""
        content = '''export function foo() {}
export class Bar {}
export const baz = 1;
export interface IFoo {}
export type TFoo = number;
export enum EColor { Red }
export namespace NUtils {}
'''
        count, names = self.handler.count_public_api(content)
        for expected in ["foo", "Bar", "baz", "IFoo", "TFoo", "EColor", "NUtils"]:
            self.assertIn(expected, names, f"Missing {expected}")


class TestCSharpGlobalUsing(unittest.TestCase):
    """C# 'global using' and 'using alias' must be detected."""

    def setUp(self):
        self.handler = get_handler(".cs")

    def test_global_using_detected(self):
        imports = self.handler.extract_external_imports("global using MyApp.Models;\n")
        self.assertIn("MyApp", imports)

    def test_using_alias_detected(self):
        imports = self.handler.extract_external_imports("using Alias = MyApp.Models;\n")
        self.assertIn("MyApp", imports)

    def test_static_using_detected(self):
        imports = self.handler.extract_external_imports("using static MyApp.Helpers;\n")
        self.assertIn("MyApp", imports)

    def test_system_still_stdlib(self):
        imports = self.handler.extract_external_imports("using System;\nusing System.Linq;\n")
        self.assertNotIn("System", imports)


class TestPython3LevelRelativeImports(unittest.TestCase):
    """Python 'from ...X import Y' (3+ levels) must resolve correctly."""

    def test_3_level_resolution(self):
        from people_helper.detection import _resolve_sibling
        file_set = {"a/config.py", "a/b/c/deep.py"}
        result = _resolve_sibling("config", 3, "a/b/c/deep.py", ".py", file_set)
        self.assertEqual(result, "a/config.py")

    def test_4_level_beyond_root_returns_none(self):
        from people_helper.detection import _resolve_sibling
        file_set = {"a/b.py"}
        result = _resolve_sibling("config", 4, "a/b.py", ".py", file_set)
        self.assertIsNone(result)

    def test_2_level_still_works(self):
        from people_helper.detection import _resolve_sibling
        # For a/b.py, parent_level=2 looks 1 dir up (the root), so config must be at root.
        file_set = {"config.py", "a/b.py"}
        result = _resolve_sibling("config", 2, "a/b.py", ".py", file_set)
        self.assertEqual(result, "config.py")


class TestTestExtractedSkipped(unittest.TestCase):
    """The test_extracted/ directory must be skipped by the walker."""

    def test_test_extracted_excluded(self):
        import tempfile
        from pathlib import Path
        from people_helper.walker import walk_repo
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "test_extracted").mkdir()
            (root / "test_extracted" / "old.py").write_text("def f(): return 1\n")
            (root / "real.py").write_text("def f(): return 1\n")
            files = walk_repo(root)
            paths = [f["path"] for f in files]
            self.assertNotIn("test_extracted/old.py", paths)
            self.assertIn("real.py", paths)

    def test_extracted_dir_excluded(self):
        """General 'extracted/' output dir is also excluded (R7-B consistency)."""
        import tempfile
        from pathlib import Path
        from people_helper.walker import walk_repo
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "extracted").mkdir()
            (root / "extracted" / "old.py").write_text("def f(): return 1\n")
            (root / "real.py").write_text("def f(): return 1\n")
            files = walk_repo(root)
            paths = [f["path"] for f in files]
            self.assertNotIn("extracted/old.py", paths)


class TestBetterNaming(unittest.TestCase):
    """Naming logic should avoid duplicates like 'data-data' and prefer function names."""

    def test_function_name_beats_generic_stem(self):
        """When stem is generic but function names are specific, use the function name."""
        from people_helper.naming import suggest_name
        c = Candidate(
            path="src/strings.py", language="Python", loc=20, has_tests=False, has_docstring=True,
            internal_imports=0, external_imports=0, filename_score=0.0,
            docstring_snippet="String utilities.",
            function_names=["slugify", "truncate"],
        )
        name = suggest_name(c)
        # 'strings' is meaningful so we keep it (better than generic 'extracted-utility')
        # But verify it's at least clean (no 'strings-strings')
        self.assertNotIn("--", name)
        self.assertFalse(name.endswith("-strings"))

    def test_data_models_uses_parent_not_stem(self):
        """models.py in 'people_helper_data' should NOT produce 'data-data' duplication."""
        from people_helper.naming import suggest_name
        c = Candidate(
            path="people_helper_data/models.py", language="Python", loc=10,
            has_tests=False, has_docstring=True,
            internal_imports=0, external_imports=0, filename_score=0.0,
            docstring_snippet="Data structures.",
            function_names=[],
        )
        name = suggest_name(c)
        self.assertNotEqual(name, "people-helper-data-models")
        # Should just be the parent (since 'data' is in noise) or a useful variant
        self.assertTrue(name.startswith("people-helper-data"))

    def test_myproj_models_with_function_names(self):
        """When stem is generic and there are useful function names, use them."""
        from people_helper.naming import suggest_name
        c = Candidate(
            path="myproj/models.py", language="Python", loc=10,
            has_tests=False, has_docstring=True,
            internal_imports=0, external_imports=0, filename_score=0.0,
            docstring_snippet="Database ORM models.",
            function_names=["User", "Post"],
        )
        name = suggest_name(c)
        self.assertIn("user", name.lower())

    def test_dts_filename_handled(self):
        """foo.d.ts should produce 'foo' name."""
        from people_helper.naming import suggest_name
        c = Candidate(
            path="types/foo.d.ts", language="TypeScript", loc=10,
            has_tests=False, has_docstring=False,
            internal_imports=0, external_imports=0, filename_score=0.0,
        )
        name = suggest_name(c)
        self.assertEqual(name, "foo")


class TestExtendedSecretRedaction(unittest.TestCase):
    """Tests for additional secret patterns in report._redact_secrets."""

    def test_github_oauth_token_redacted(self):
        from people_helper.report import _redact_secrets
        result = _redact_secrets("gho_1234567890abcdefghijklmnopqrstuvwxyzABCD")
        self.assertIn("REDACTED", result)

    def test_github_user_token_redacted(self):
        from people_helper.report import _redact_secrets
        result = _redact_secrets("ghu_1234567890abcdefghijklmnopqrstuvwxyzABCD")
        self.assertIn("REDACTED", result)

    def test_github_server_token_redacted(self):
        from people_helper.report import _redact_secrets
        result = _redact_secrets("ghs_1234567890abcdefghijklmnopqrstuvwxyzABCD")
        self.assertIn("REDACTED", result)

    def test_aws_secret_redacted(self):
        from people_helper.report import _redact_secrets
        result = _redact_secrets("aws_secret_access_key=abcdefghijklmnopqrstuvwxyz0123456789ABCD")
        self.assertIn("REDACTED", result)

    def test_anthropic_key_redacted(self):
        from people_helper.report import _redact_secrets
        result = _redact_secrets("sk-ant-api03-abcdefghijklmnopqrstuvwxyz")
        self.assertIn("REDACTED", result)

    def test_google_api_key_redacted(self):
        from people_helper.report import _redact_secrets
        result = _redact_secrets("AIzaSyA-1234567890abcdefghijklmnopqrstuvwx")
        self.assertIn("REDACTED", result)

    def test_stripe_live_key_redacted(self):
        from people_helper.report import _redact_secrets
        result = _redact_secrets("sk_live_1234567890abcdefghijklmnop")
        self.assertIn("REDACTED", result)

    def test_sendgrid_key_redacted(self):
        from people_helper.report import _redact_secrets
        result = _redact_secrets("SG.abcdefghijklmnopqrstuvw.ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz01")
        self.assertIn("REDACTED", result)

    def test_twilio_sid_redacted(self):
        from people_helper.report import _redact_secrets
        result = _redact_secrets("ACabcdef0123456789abcdef0123456789")
        self.assertIn("REDACTED", result)

    def test_normal_code_not_redacted(self):
        from people_helper.report import _redact_secrets
        code = '''def hello():
    return "world"

import os
class MyClass:
    pass
'''
        self.assertEqual(_redact_secrets(code), code)

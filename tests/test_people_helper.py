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
        self.assertIn("github.com", imports)

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
        cands = detect_candidates(files, "Python")
        active = [c for c in cands if not c.skipped]
        self.assertGreater(len(active), 0)
        for c in cands:
            if not c.skipped:
                score_candidate(c, similar_count=0)
        out = Path("/tmp/test_report_unittest.md")
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
        cands = detect_candidates(files, "Python")
        skipped = [c for c in cands if c.skipped]
        self.assertGreater(len(skipped), 0)
        out = Path("/tmp/test_report_skipped.md")
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
        cands = detect_candidates(files, "Python")
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
        cands = detect_candidates(files, "Python")
        active = [c for c in cands if not c.skipped]
        parser = next(c for c in active if c.path == "parser.py")
        self.assertEqual(parser.extraction_type, "multi")
        self.assertIn("utils.py", parser.sibling_paths)
        score_candidate(parser, similar_count=0)
        # Multi-file should score LOWER than standalone
        files2 = [make_file("LICENSE", "MIT"), make_file("slugify.py", self.STANDALONE_CONTENT)]
        cands2 = detect_candidates(files2, "Python")
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
        cands = detect_candidates(files, "Python")
        active = [c for c in cands if not c.skipped]
        skipped = [c for c in cands if c.skipped]
        self.assertEqual(len(active), 0)
        self.assertEqual(len(skipped), 1)
        self.assertIn("missing sibling", skipped[0].skip_reason.lower())
        self.assertEqual(skipped[0].extraction_type, "blocked")

    def test_no_license_flagged(self):
        files = [make_file("slugify.py", self.STANDALONE_CONTENT)]
        cands = detect_candidates(files, "Python")
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
        from people_helper.detection import _realism_check
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
        from people_helper.detection import _realism_check
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
        from people_helper.detection import _realism_check
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

                # Verify LICENSE was created
                self.assertTrue((pkg_path / "LICENSE").exists())
                license_content = (pkg_path / "LICENSE").read_text()
                self.assertIn("MIT", license_content)

                # Verify pyproject.toml was created for Python
                self.assertTrue((pkg_path / "pyproject.toml").exists())
                pyproject = (pkg_path / "pyproject.toml").read_text()
                self.assertIn("slugify-tool", pyproject)
                self.assertIn("MIT", pyproject)


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

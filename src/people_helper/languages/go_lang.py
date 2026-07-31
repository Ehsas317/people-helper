"""Go language handler."""

import re

from ..config import GO_HEAVY, GO_STDLIB
from .base import LanguageHandler


class GoHandler(LanguageHandler):
    language_name = "Go"
    comment_prefixes = ("//", "/*")

    # Go has no relative imports — all imports are absolute paths
    def extract_relative_imports(self, content: str) -> list:
        return []

    def extract_external_imports(self, content: str) -> list:
        imports = []
        for line in content.splitlines():
            # Match: import "github.com/user/repo"  (single-line form)
            m = re.match(r'^\s*(?:import\s+)?"([\w./\-]+)"', line)
            if m and "/" in m.group(1):
                # Return the full import path (not just the first component)
                # so get_dependency_weight can check for heavy packages like "gin"
                mod = m.group(1)
                if mod and mod not in imports:
                    imports.append(mod)
        return imports

    def count_public_api(self, content: str) -> tuple:
        count, names = 0, []
        # Go: capitalized = exported (public)
        for m in re.finditer(r"^\s*func\s+([A-Z]\w*)", content, re.MULTILINE):
            count += 1
            names.append(m.group(1))
        for m in re.finditer(r"^\s*type\s+([A-Z]\w*)", content, re.MULTILINE):
            count += 1
            names.append(m.group(1))
        return (count, names)

    def detect_docstring(self, content: str) -> tuple:
        """Detect Go package comment.

        Per godoc convention, the package comment is a // comment block
        IMMEDIATELY BEFORE the `package` declaration. Comments BEFORE that
        (e.g. license headers) are NOT docstrings. Comments AFTER `package`
        are NOT docstrings either.

        ALSO checks for doc comments on exported declarations (functions, types)
        when no package-level docstring is found. This provides useful description
        text for Go files that lack a package comment.
        """
        lines = content.splitlines()
        if not lines:
            return False, ""
        # Find the `package` declaration line
        package_line_idx = None
        for i, line in enumerate(lines[:100]):
            if line.strip().startswith("package "):
                package_line_idx = i
                break
        if package_line_idx is None:
            return False, ""
        # Collect consecutive // comments IMMEDIATELY BEFORE the package line
        # (allowing blank lines between them)
        comment_block: list[str] = []
        for j in range(package_line_idx - 1, -1, -1):
            stripped = lines[j].strip()
            if stripped.startswith("//"):
                comment_block.insert(0, lines[j])
            elif not stripped:
                # Allow blank lines between comment and package
                continue
            else:
                # Hit non-comment, non-blank line → stop
                break
        # Filter out license-header-only comments
        # (e.g. "Copyright 2024", "Licensed under MIT")
        if comment_block:
            # If ALL comment lines are copyright/license, treat as license header not docstring
            copyright_lines: int = sum(
                1
                for l in comment_block
                if "copyright" in l.lower() or "license" in l.lower() or "licensed" in l.lower()
            )
            if copyright_lines == len(comment_block):
                comment_block = []
            else:
                return True, "\n".join(comment_block).strip()

        # Fallback: look for doc comments on exported functions/types
        # Go convention: a comment immediately before `func FooName(...)` or `type FooName`
        # where FooName starts with uppercase is the docstring for that declaration.
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Check if next non-blank line is an exported declaration
            if not stripped:
                continue
            # Look for exported func/type/var declaration
            m = re.match(r"^(func|type|var)\s+([A-Z])\w*", stripped)
            if not m:
                continue
            # Collect comment lines immediately before this declaration
            decl_doc: list[str] = []
            for j in range(i - 1, -1, -1):
                js = lines[j].strip()
                if js.startswith("//"):
                    # Strip the // prefix for cleaner output
                    decl_doc.insert(0, js[2:].strip() if js.startswith("// ") else js[2:].strip())
                elif not js:
                    continue
                else:
                    break
            if decl_doc:
                # Filter out license-only comment blocks
                copyright_lines = sum(
                    1 for l in decl_doc
                    if "copyright" in l.lower() or "license" in l.lower() or "licensed" in l.lower()
                )
                if copyright_lines == len(decl_doc):
                    continue
                doc_text = "\n".join(decl_doc).strip()
                return True, doc_text

        return False, ""

    # Go: can't reliably tell internal from external without go.mod module path
    def is_internal_import(self, line: str, _project_modules: set) -> bool:
        return False

    def get_dependency_weight(self, imports: list) -> tuple:
        if not imports:
            return (0, True)
        max_weight, all_stdlib = 0, True
        for mod in imports:
            ml = mod.lower()
            # Check if stdlib (exact match against the first path component)
            first_part = ml.split("/")[0]
            if first_part in GO_STDLIB:
                w = 0
            # Check if heavy — use substring match on full path so
            # "github.com/gin-gonic/gin" matches "gin" in GO_HEAVY
            elif any(h in ml for h in GO_HEAVY) or "k8s.io" in ml:
                w = 3
                all_stdlib = False
            else:
                w = 1
                all_stdlib = False
            max_weight = max(max_weight, w)
        return (max_weight, all_stdlib)

    def get_complexity(self, content: str) -> int:
        """Regex-based cyclomatic complexity for Go.

        Counts: if, for, switch case, select case, &&, ||.
        """
        cc = 1
        cc += len(re.findall(r"\bif\s+", content))
        cc += len(re.findall(r"\bfor\s+", content))
        cc += len(re.findall(r"\bcase\s+", content))
        cc += len(re.findall(r"&&", content))
        cc += len(re.findall(r"\|\|", content))
        return cc

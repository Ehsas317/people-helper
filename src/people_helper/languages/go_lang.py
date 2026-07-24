"""Go language handler."""
import re
from .base import LanguageHandler
from ..config import GO_STDLIB, GO_HEAVY


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
                mod = m.group(1).split("/")[0]
                if mod and mod not in imports:
                    imports.append(mod)
        return imports

    def count_public_api(self, content: str) -> tuple:
        count, names = 0, []
        # Go: capitalized = exported (public)
        for m in re.finditer(r"^\s*func\s+([A-Z]\w*)", content, re.MULTILINE):
            count += 1; names.append(m.group(1))
        for m in re.finditer(r"^\s*type\s+([A-Z]\w*)", content, re.MULTILINE):
            count += 1; names.append(m.group(1))
        return (count, names)

    def detect_docstring(self, content: str) -> tuple:
        """Detect Go package comment.

        Per godoc convention, the package comment is a // comment block
        IMMEDIATELY BEFORE the `package` declaration. Comments BEFORE that
        (e.g. license headers) are NOT docstrings. Comments AFTER `package`
        are NOT docstrings either.
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
        comment_block = []
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
            joined = "\n".join(comment_block).lower()
            # If ALL comment lines are copyright/license, treat as license header not docstring
            copyright_lines = sum(1 for l in comment_block
                                  if "copyright" in l.lower() or "license" in l.lower() or "licensed" in l.lower())
            if copyright_lines == len(comment_block):
                return False, ""
            return True, "\n".join(comment_block).strip()
        return False, ""

    # Go: can't reliably tell internal from external without go.mod module path
    def is_internal_import(self, line: str, _project_modules: set) -> bool:
        return False

    def _is_external_import_line(self, line: str) -> bool:
        # Only count imports with "/" (stdlib imports like "fmt" have no "/")
        return bool(re.match(r'^\s*"[\w./\-]+/[\w./\-]+"', line))

    def get_dependency_weight(self, imports: list) -> tuple:
        if not imports:
            return (0, True)
        max_weight, all_stdlib = 0, True
        for mod in imports:
            ml = mod.lower()
            if ml in GO_STDLIB:
                w = 0
            elif ml in GO_HEAVY or "k8s.io" in ml:
                w = 3; all_stdlib = False
            else:
                w = 1; all_stdlib = False
            max_weight = max(max_weight, w)
        return (max_weight, all_stdlib)

    def get_complexity(self, content: str) -> int:
        """Regex-based cyclomatic complexity for Go.

        Counts: if, for, switch case, select case, &&, ||.
        """
        cc = 1
        cc += len(re.findall(r'\bif\s+', content))
        cc += len(re.findall(r'\bfor\s+', content))
        cc += len(re.findall(r'\bcase\s+', content))
        cc += len(re.findall(r'&&', content))
        cc += len(re.findall(r'\|\|', content))
        return cc

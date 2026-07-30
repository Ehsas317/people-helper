"""PHP language handler."""

import re

from .base import LanguageHandler


class PhpHandler(LanguageHandler):
    language_name = "PHP"
    comment_prefixes = ("//", "#", "/*")

    def extract_relative_imports(self, content: str) -> list:
        return []

    def extract_external_imports(self, content: str) -> list:
        imports = []
        for line in content.splitlines():
            m = re.match(r"^\s*use\s+([\w\\]+)", line)
            if m:
                mod = m.group(1).lstrip("\\").split("\\")[0]
                if mod and mod not in imports:
                    imports.append(mod)
        return imports

    def count_public_api(self, content: str) -> tuple:
        count, names = 0, []
        for m in re.finditer(r"^\s*(?:public\s+|protected\s+|static\s+)*function\s+(\w+)", content, re.MULTILINE):
            count += 1
            names.append(m.group(1))
        for m in re.finditer(r"^\s*(?:final\s+|abstract\s+)*(?:class|interface|trait)\s+(\w+)", content, re.MULTILINE):
            count += 1
            names.append(m.group(1))
        return (count, names)

    def detect_docstring(self, content: str) -> tuple:
        lines = content.splitlines()
        if not lines:
            return False, ""
        # Skip <?php, namespace, use, //, blank lines
        start = 0
        for i, line in enumerate(lines[:100]):
            stripped = line.strip()
            if not stripped:
                start = i + 1
                continue
            if stripped.startswith("<?php"):
                start = i + 1
                continue
            if stripped.startswith("//"):
                start = i + 1
                continue
            if stripped.startswith(("namespace ", "use ")):
                start = i + 1
                continue
            start = i
            break
        if start < len(lines) and lines[start].strip().startswith(("/**", "/*")):
            snippet_lines = []
            for line in lines[start : start + 30]:
                snippet_lines.append(line)
                if line.strip().endswith("*/"):
                    break
            return True, "\n".join(snippet_lines).strip()
        return False, ""

    def is_internal_import(self, line: str, _project_modules: set) -> bool:
        return False

    def get_dependency_weight(self, imports: list) -> tuple:
        if not imports:
            return (0, True)
        return (1, False)

    def get_complexity(self, content: str) -> int:
        """Regex-based cyclomatic complexity for PHP."""
        cc = 1
        cc += len(re.findall(r"\bif\s*\(", content))
        cc += len(re.findall(r"\bfor\s*\(", content))
        cc += len(re.findall(r"\bwhile\s*\(", content))
        cc += len(re.findall(r"\bcase\s+", content))
        cc += len(re.findall(r"\bcatch\s*\(", content))
        cc += len(re.findall(r"&&", content))
        cc += len(re.findall(r"\|\|", content))
        cc += len(re.findall(r"\?\s*[^?]", content))
        return cc

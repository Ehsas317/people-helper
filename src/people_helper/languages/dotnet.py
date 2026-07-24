"""C# / .NET language handler.

Fixes round-4 bug: /// XML documentation comments (Microsoft's dominant
convention) were not detected. Now we detect /// in addition to /** */.
"""
import re
from .base import LanguageHandler


class DotNetHandler(LanguageHandler):
    language_name = "C#"
    comment_prefixes = ("//", "/*")

    def extract_relative_imports(self, content: str) -> list:
        return []

    def extract_external_imports(self, content: str) -> list:
        imports = []
        for line in content.splitlines():
            m = re.match(r"^\s*using\s+([\w.]+)\s*;", line)
            if m:
                full = m.group(1)
                # System.* is stdlib
                if full.startswith("System") or full in {"Microsoft"}:
                    continue
                mod = full.split(".")[0]
                if mod and mod not in imports:
                    imports.append(mod)
        return imports

    def count_public_api(self, content: str) -> tuple:
        count, names = 0, []
        for m in re.finditer(r"^\s*public\s+(?:sealed\s+|abstract\s+|static\s+|virtual\s+|override\s+|async\s+)*(?:class|interface|struct|enum)\s+(\w+)", content, re.MULTILINE):
            count += 1; names.append(m.group(1))
        for m in re.finditer(r"^\s*public\s+(?:sealed\s+|abstract\s+|static\s+|virtual\s+|override\s+|async\s+)*(?:[\w<>\[\],?\s]+)\s+(\w+)\s*\(", content, re.MULTILINE):
            name = m.group(1)
            if name not in {"class", "interface", "struct", "enum"}:
                count += 1; names.append(name)
        return (count, names)

    def detect_docstring(self, content: str) -> tuple:
        lines = content.splitlines()
        if not lines:
            return False, ""
        # Skip: using, //, blank lines
        start = 0
        for i, line in enumerate(lines[:100]):
            stripped = line.strip()
            if not stripped:
                start = i + 1
                continue
            if stripped.startswith("//"):
                start = i + 1
                continue
            if stripped.startswith("using "):
                start = i + 1
                continue
            if stripped.startswith("namespace"):
                start = i + 1
                continue
            start = i
            break
        # Check for /** */ block comment
        if start < len(lines) and lines[start].strip().startswith(("/**", "/*")):
            snippet_lines = []
            for line in lines[start:start + 30]:
                snippet_lines.append(line)
                if line.strip().endswith("*/"):
                    break
            return True, "\n".join(snippet_lines).strip()
        # Check for /// XML documentation (Microsoft's dominant convention)
        # Collect consecutive /// lines
        xml_lines = []
        for line in lines[:30]:
            if line.strip().startswith("///"):
                xml_lines.append(line)
            elif xml_lines:
                break
        if xml_lines:
            return True, "\n".join(xml_lines).strip()
        return False, ""

    def is_internal_import(self, line: str, _project_modules: set) -> bool:
        return False

    def _is_external_import_line(self, line: str) -> bool:
        return bool(re.match(r"^\s*using\s+[\w.]+\s*;", line))

    def get_dependency_weight(self, imports: list) -> tuple:
        if not imports:
            return (0, True)
        return (1, False)

    def get_complexity(self, content: str) -> int:
        """Regex-based cyclomatic complexity for C#."""
        cc = 1
        cc += len(re.findall(r'\bif\s*\(', content))
        cc += len(re.findall(r'\bfor\s*\(', content))
        cc += len(re.findall(r'\bwhile\s*\(', content))
        cc += len(re.findall(r'\bcase\s+', content))
        cc += len(re.findall(r'\bcatch\s*\(', content))
        cc += len(re.findall(r'&&', content))
        cc += len(re.findall(r'\|\|', content))
        cc += len(re.findall(r'\?\s*[^?]', content))
        return cc

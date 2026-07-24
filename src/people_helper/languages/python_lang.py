"""Python language handler."""
import ast
import re
from .base import LanguageHandler
from ..config import PYTHON_STDLIB, PYTHON_HEAVY


_REL_IMPORT_PY = re.compile(r"^\s*from\s+(\.+)([\w.]*)\s+import\s+(.+)$")


def _strip_inline_comment_py(line: str) -> str:
    """Strip # comments from a Python line, respecting string literals."""
    result = []
    i = 0
    in_string = None
    while i < len(line):
        ch = line[i]
        if in_string:
            if ch == "\\" and i + 1 < len(line):
                result.append(ch)
                result.append(line[i + 1])
                i += 2
                continue
            if ch == in_string:
                in_string = None
            result.append(ch)
        else:
            if ch in ('"', "'"):
                in_string = ch
                result.append(ch)
            elif ch == "#":
                break
            else:
                result.append(ch)
        i += 1
    return "".join(result)


class PythonHandler(LanguageHandler):
    language_name = "Python"
    comment_prefixes = ("#",)

    def extract_relative_imports(self, content: str) -> list:
        siblings = []
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = _strip_inline_comment_py(lines[i])
            m = _REL_IMPORT_PY.match(line)
            if not m:
                i += 1
                continue
            dots, mod_name, rest = m.group(1), m.group(2), m.group(3).strip()
            parent_level = len(dots)
            # For nested module names like .sub.module, only first component is sibling
            if mod_name and "." in mod_name:
                mod_name = mod_name.split(".")[0]
            # Multi-line: rest starts with "(" and doesn't end with ")"
            if rest.startswith("(") and not rest.rstrip().endswith(")"):
                block = [rest]
                i += 1
                while i < len(lines):
                    stripped = _strip_inline_comment_py(lines[i])
                    block.append(stripped)
                    if stripped.rstrip().endswith(")"):
                        break
                    i += 1
                rest = " ".join(block)
            rest = rest.replace("(", " ").replace(")", " ")
            if mod_name:
                siblings.append((mod_name, parent_level))
            else:
                for item in rest.split(","):
                    name = item.strip().split(" as ")[0].strip()
                    if name and name != "*" and not name.startswith("."):
                        siblings.append((name, parent_level))
            i += 1
        # Dedupe by (name, level), preserve order
        seen, result = set(), []
        for s in siblings:
            if s not in seen:
                seen.add(s)
                result.append(s)
        return result

    def extract_external_imports(self, content: str) -> list:
        imports = []
        for line in content.splitlines():
            if re.match(r"^\s*from\s+\.", line):
                continue
            m = re.match(r"^\s*from\s+([\w.]+)\s+import", line)
            if m:
                mod = m.group(1).split(".")[0]
                if mod and mod not in imports:
                    imports.append(mod)
                continue
            m = re.match(r"^\s*import\s+([\w.]+)", line)
            if m:
                mod = m.group(1).split(".")[0]
                if mod and mod not in imports:
                    imports.append(mod)
        return imports

    def count_public_api(self, content: str) -> tuple:
        count, names = 0, []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if not node.name.startswith("_"):
                        count += 1
                        names.append(node.name)
        except SyntaxError:
            pass
        return (count, names)

    def detect_docstring(self, content: str) -> tuple:
        lines = content.splitlines()
        if not lines:
            return False, ""
        # Skip shebang, coding declarations, __future__ imports, and comments
        start = 0
        for i, line in enumerate(lines[:10]):
            stripped = line.strip()
            if not stripped:
                start = i + 1
                continue
            if stripped.startswith("#!"):
                start = i + 1
                continue
            if stripped.startswith("# -*- coding") or "coding:" in stripped:
                start = i + 1
                continue
            if stripped.startswith("#"):
                start = i + 1
                continue
            if stripped.startswith(("from __future__", "import __future__")):
                start = i + 1
                continue
            start = i
            break
        if start < len(lines):
            first_line = lines[start].strip()
            if first_line.startswith(('"""', "'''")):
                end_quote = '"""' if '"""' in first_line else "'''"
                snippet_lines = [lines[start].lstrip()]
                if first_line.count(end_quote) >= 2:
                    return True, "\n".join(snippet_lines).strip()
                for line in lines[start + 1:start + 21]:
                    snippet_lines.append(line)
                    if end_quote in line:
                        break
                return True, "\n".join(snippet_lines).strip()
        return False, ""

    def is_internal_import(self, line: str, project_modules: set) -> bool:
        if re.match(r"^\s*from\s+\.", line):
            return True
        m = re.match(r"^\s*from\s+([\w.]+)\s+import", line)
        if m:
            return m.group(1).split(".")[0] in project_modules
        m = re.match(r"^\s*import\s+([\w.]+)", line)
        if m:
            return m.group(1).split(".")[0] in project_modules
        return False

    def _is_external_import_line(self, line: str) -> bool:
        return bool(re.match(r"^\s*(import|from)\s+", line))

    def get_complexity(self, content: str) -> int:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return 0
        cc = 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.Assert)):
                cc += 1
            elif isinstance(node, ast.BoolOp):
                cc += max(0, len(node.values) - 1)
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for gen in node.generators:
                    cc += 1 + len(gen.ifs)
            elif isinstance(node, ast.IfExp):
                cc += 1
        return cc

    def get_dependency_weight(self, imports: list) -> tuple:
        """Return (max_weight, is_stdlib_only) for a list of import names."""
        if not imports:
            return (0, True)
        max_weight, all_stdlib = 0, True
        for mod in imports:
            ml = mod.lower()
            if ml in PYTHON_STDLIB or ml == "__future__":
                w = 0
            elif ml in PYTHON_HEAVY:
                w = 3; all_stdlib = False
            else:
                w = 1; all_stdlib = False
            max_weight = max(max_weight, w)
        return (max_weight, all_stdlib)

"""JavaScript/TypeScript language handler."""

import re

from ..config import EXTERNAL_SCOPES, JS_HEAVY
from .base import LanguageHandler

_REL_IMPORT_JS = re.compile(r"""(?:from|require\()\s*['"](\.{1,2}/[\w./@\-~]+)['"]""")
_IMPORT_FROM_RE = re.compile(r'^\s*import\s+.*from\s+["' + chr(39) + r"]([\w./@\-~]+)")
_REQUIRE_RE = re.compile(
    r'^\s*(?:const|let|var)\s+\w+\s*=\s*require\(["' + chr(39) + r"]([\w./@\-~]+)[" + chr(39) + r"]\)"
)


class JsTsHandler(LanguageHandler):
    language_name = "JavaScript"
    comment_prefixes = ("//", "/*")

    def extract_relative_imports(self, content: str) -> list:
        siblings = []
        for m in _REL_IMPORT_JS.finditer(content):
            path = m.group(1)
            if path.startswith("./"):
                parent_level = 1
            elif path.startswith("../"):
                parent_level = 2 + path.count("../") - 1
            else:
                continue
            clean_path = path.lstrip(".").lstrip("/")
            name = clean_path.rstrip("/").split("/")[-1]
            if not name:
                continue
            for ext_to_strip in [".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"]:
                if name.endswith(ext_to_strip):
                    name = name[: -len(ext_to_strip)]
                    break
            if name == "index":
                parts = clean_path.rstrip("/").split("/")
                if len(parts) >= 2 and parts[-2]:
                    siblings.append((parts[-2], parent_level))
            elif name:
                siblings.append((name, parent_level))
        seen, result = set(), []
        for s in siblings:
            if s not in seen:
                seen.add(s)
                result.append(s)
        return result

    def extract_external_imports(self, content: str) -> list:
        imports = []
        for line in content.splitlines():
            m = re.search(r"(?:from|require\()\s*['\"]([\w@/\-]+)['\"]", line)
            if m:
                path = m.group(1)
                if path.startswith(".") or path.startswith("/"):
                    continue
                mod = path.lstrip("@").split("/")[0]
                if mod and mod not in imports:
                    imports.append(mod)
        return imports

    def count_public_api(self, content: str) -> tuple:
        count, names = 0, []
        # Match: export function/class/const/let/var/interface/type/enum/namespace
        # Also: export default function/class/... (anonymous default doesn't add to count
        # unless there's a name we can extract).
        for m in re.finditer(
            r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type|enum|namespace)\s+(\w+)",
            content,
            re.MULTILINE,
        ):
            name = m.group(1)
            if name in {"default"}:  # 'export default { ... }' has no identifier
                continue
            if name not in names:
                count += 1
                names.append(name)
        return (count, names)

    def detect_docstring(self, content: str) -> tuple:
        lines = content.splitlines()
        if not lines:
            return False, ""
        start = 0
        for i, line in enumerate(lines[:10]):
            stripped = line.strip()
            if not stripped:
                start = i + 1
                continue
            if stripped.startswith("#!"):
                start = i + 1
                continue
            if stripped.startswith("//") or (stripped.startswith("/*") and not stripped.startswith("/**")):
                start = i + 1
                continue
            start = i
            break
        if start < len(lines) and lines[start].strip().startswith("/**"):
            snippet_lines = []
            for line in lines[start : start + 30]:
                snippet_lines.append(line)
                if line.strip().endswith("*/"):
                    break
            return True, "\n".join(snippet_lines).strip()
        return False, ""

    def is_internal_import(self, line: str, _project_modules: set) -> bool:
        m = _IMPORT_FROM_RE.match(line)
        if m:
            path = m.group(1)
            if path.startswith(".") or path.startswith("/") or path.startswith("@/") or path.startswith("~/"):
                return True
            if path.startswith("@") and "/" in path[1:]:
                scope = path[1:].split("/")[0]
                if scope not in EXTERNAL_SCOPES:
                    return True
        m = _REQUIRE_RE.match(line)
        if m:
            path = m.group(1)
            if path.startswith(".") or path.startswith("@/") or path.startswith("~/"):
                return True
        return False

    def get_dependency_weight(self, imports: list) -> tuple:
        if not imports:
            return (0, True)
        max_weight, all_stdlib = 0, True
        for mod in imports:
            ml = mod.lower()
            if ml in JS_HEAVY:
                w = 3
                all_stdlib = False
            else:
                w = 1
                all_stdlib = False
            max_weight = max(max_weight, w)
        return (max_weight, all_stdlib)

    def get_complexity(self, content: str) -> int:
        """Regex-based cyclomatic complexity for JS/TS.

        Counts: if, else if, for, while, case, catch, &&, ||, ?, &&=, ||=, ??.
        This is an approximation (no AST) but gives non-zero scores for JS/TS
        so they're not systematically penalized vs Python.
        """
        cc = 1
        # if / else if
        cc += len(re.findall(r"\bif\s*\(", content))
        # for / while / do-while
        cc += len(re.findall(r"\bfor\s*\(", content))
        cc += len(re.findall(r"\bwhile\s*\(", content))
        # switch case (each case adds a path)
        cc += len(re.findall(r"\bcase\s+", content))
        # catch
        cc += len(re.findall(r"\bcatch\s*\(", content))
        # ternary operator
        cc += len(re.findall(r"\?\s*[^?]", content))
        # logical operators (each && or || adds a branch)
        cc += len(re.findall(r"&&", content))
        cc += len(re.findall(r"\|\|", content))
        # nullish coalescing
        cc += len(re.findall(r"\?\?", content))
        return cc

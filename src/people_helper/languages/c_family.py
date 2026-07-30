"""C/C++ language handler.

Fixes round-4 bug: angle-bracket includes for boost/opencv/eigen were
treated as stdlib. Now we maintain explicit stdlib header sets.
"""

import re

from .base import LanguageHandler

# Known C standard library headers (skip these — they're stdlib)
_C_STDLIB = {
    "stdio",
    "stdlib",
    "string",
    "math",
    "ctype",
    "errno",
    "assert",
    "time",
    "signal",
    "setjmp",
    "locale",
    "stdarg",
    "stddef",
    "limits",
    "float",
    "iso646",
    "wchar",
    "wctype",
    "complex",
    "tgmath",
    "fenv",
    "inttypes",
    "stdint",
    "stdbool",
    "unistd",
    "pthread",
    "dlfcn",
    "sys",
    "netdb",
    "netinet",
    "arpa",
    "fcntl",
    "syslog",
}

# Known C++ standard library headers (skip these — they're stdlib)
_CPP_STDLIB = {
    "iostream",
    "fstream",
    "sstream",
    "iomanip",
    "vector",
    "list",
    "deque",
    "queue",
    "stack",
    "map",
    "unordered_map",
    "set",
    "unordered_set",
    "algorithm",
    "numeric",
    "functional",
    "memory",
    "utility",
    "tuple",
    "string",
    "array",
    "iterator",
    "exception",
    "stdexcept",
    "typeinfo",
    "type_traits",
    "chrono",
    "ratio",
    "atomic",
    "thread",
    "mutex",
    "condition_variable",
    "future",
    "regex",
    "random",
    "locale",
    "codecvt",
    "filesystem",
    "optional",
    "variant",
    "any",
    "bitset",
    "valarray",
    "complex",
    "new",
    "cassert",
    "cstdio",
    "cstdlib",
    "cstring",
    "cmath",
    "cerrno",
    "ctime",
    "cctype",
    "cwchar",
    "cwctype",
    "cfloat",
    "climits",
    "cstdint",
    "cstdarg",
    "cstddef",
}


class CFamilyHandler(LanguageHandler):
    language_name = "C"
    comment_prefixes = ("//", "/*")
    preprocessor_prefix = "#"  # C/C++ preprocessor lines ARE code

    def extract_relative_imports(self, content: str) -> list:
        # C/C++ has no relative imports (uses #include with paths)
        return []

    def extract_external_imports(self, content: str) -> list:
        imports = []
        for line in content.splitlines():
            # Quoted includes: "foo.h" — external (project or third-party)
            m = re.match(r'^\s*#include\s+"([^"]+)"', line)
            if m:
                mod = m.group(1).split("/")[0].split(".")[0]
                if mod and mod not in imports:
                    imports.append(mod)
                continue
            # Angle-bracket includes: <foo> or <foo/bar>
            # These are usually stdlib, BUT third-party libs like boost, opencv,
            # eigen, gtest also use angle brackets.
            m = re.match(r"^\s*#include\s+<([^>]+)>", line)
            if m:
                full = m.group(1)
                top = full.split("/")[0].split(".")[0]
                if top in _C_STDLIB or top in _CPP_STDLIB:
                    continue
                if top and top not in imports:
                    imports.append(top)
        return imports

    def count_public_api(self, content: str) -> tuple:
        count, names = 0, []
        # C: function definitions (not static)
        # C++: free functions and class methods
        # Match: return_type function_name(...) {  (definition, not declaration)
        for m in re.finditer(r"^\s*(?!static\b)([\w][\w\s\*<>:,&]*?)\s+(\w+)\s*\([^)]*\)\s*\{", content, re.MULTILINE):
            name = m.group(2)
            if name not in {"if", "for", "while", "switch", "return", "sizeof"}:
                count += 1
                names.append(name)
        # Also count function declarations in headers (no body) — for .h files
        # Pattern: return_type function_name(...);
        for m in re.finditer(r"^\s*(?!static\b)([\w][\w\s\*<>:,&]*?)\s+(\w+)\s*\([^)]*\)\s*;", content, re.MULTILINE):
            name = m.group(2)
            if name not in names and name not in {"if", "for", "while", "switch", "return", "sizeof"}:
                count += 1
                names.append(name)
        return (count, names)

    def detect_docstring(self, content: str) -> tuple:
        lines = content.splitlines()
        if not lines:
            return False, ""
        # Skip: #include, #define, //, blank lines
        start = 0
        for i, line in enumerate(lines[:100]):
            stripped = line.strip()
            if not stripped:
                start = i + 1
                continue
            if stripped.startswith("//"):
                start = i + 1
                continue
            if stripped.startswith("#"):
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
        # Can't reliably tell internal from external #include "..." without project structure
        return False

    def get_dependency_weight(self, imports: list) -> tuple:
        if not imports:
            return (0, True)
        # Any non-stdlib include is at least weight 1
        return (1, False)

    def get_complexity(self, content: str) -> int:
        """Regex-based cyclomatic complexity for C/C++."""
        cc = 1
        cc += len(re.findall(r"\bif\s*\(", content))
        cc += len(re.findall(r"\bfor\s*\(", content))
        cc += len(re.findall(r"\bwhile\s*\(", content))
        cc += len(re.findall(r"\bcase\s+", content))
        cc += len(re.findall(r"&&", content))
        cc += len(re.findall(r"\|\|", content))
        cc += len(re.findall(r"\?\s*[^?]", content))
        return cc

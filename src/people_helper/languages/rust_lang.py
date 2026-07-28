"""Rust language handler."""

import re

from ..config import RUST_LIGHT, RUST_STDLIB
from .base import LanguageHandler

_REL_IMPORT_RS = re.compile(r"^\s*use\s+(super|crate|self)(?:::([\w.]+))?")


class RustHandler(LanguageHandler):
    language_name = "Rust"
    comment_prefixes = ("//",)

    def extract_relative_imports(self, content: str) -> list:
        siblings = []
        for m in _REL_IMPORT_RS.finditer(content):
            keyword = m.group(1)
            inner = m.group(2)
            if not inner:
                continue
            # For nested paths like super::sub::module, only first component is sibling
            if "." in inner or "::" in inner:
                inner = inner.split("::")[0].split(".")[0]
            if keyword == "super":
                siblings.append((inner, 2))
            elif keyword in ("crate", "self"):
                siblings.append((inner, 1))
        seen, result = set(), []
        for s in siblings:
            if s not in seen:
                seen.add(s)
                result.append(s)
        return result

    def extract_external_imports(self, content: str) -> list:
        imports = []
        for line in content.splitlines():
            if re.match(r"^\s*use\s+(super|crate|self)::", line):
                continue
            m = re.match(r"^\s*use\s+([\w:]+)", line)
            if m:
                mod = m.group(1).split("::")[0]
                if mod and mod not in imports:
                    imports.append(mod)
        return imports

    def count_public_api(self, content: str) -> tuple:
        count, names = 0, []
        for m in re.finditer(r"^\s*pub\s+(?:async\s+)?fn\s+(\w+)", content, re.MULTILINE):
            count += 1
            names.append(m.group(1))
        for m in re.finditer(r"^\s*pub\s+(?:struct|enum|trait)\s+(\w+)", content, re.MULTILINE):
            count += 1
            names.append(m.group(1))
        return (count, names)

    def detect_docstring(self, content: str) -> tuple:
        lines = content.splitlines()
        if not lines:
            return False, ""
        # Rust supports two kinds of doc comments:
        #   //!  — inner doc comment (documents the enclosing item, used at module level)
        #   ///  — outer doc comment (documents the next item, used on functions/structs)
        # We treat BOTH as module-level documentation if they appear at the top of the file.
        # Most Rust libraries use /// on their first pub item, which lands at the top of the
        # file when the file is a single-purpose module.
        comment_block = []
        for line in lines[:30]:
            stripped = line.strip()
            if stripped.startswith(("///", "//!")):
                comment_block.append(line)
            elif comment_block:
                break
        if comment_block:
            return True, "\n".join(comment_block).strip()
        return False, ""

    def is_internal_import(self, line: str, _project_modules: set) -> bool:
        return bool(re.match(r"^\s*use\s+(crate|super|self)", line))

    def get_dependency_weight(self, imports: list) -> tuple:
        if not imports:
            return (0, True)
        max_weight, all_stdlib = 0, True
        for mod in imports:
            ml = mod.lower()
            if ml in RUST_STDLIB or ml.startswith(("std::", "core::", "alloc::")):
                w = 0
            elif ml in RUST_LIGHT:
                w = 1
                all_stdlib = False
            else:
                w = 1
                all_stdlib = False
            max_weight = max(max_weight, w)
        return (max_weight, all_stdlib)

    def get_complexity(self, content: str) -> int:
        """Regex-based cyclomatic complexity for Rust.

        Counts: if, match arm, for, while, loop, &&, ||.
        """
        cc = 1
        cc += len(re.findall(r"\bif\s+", content))
        cc += len(re.findall(r"\bmatch\s+", content))
        cc += len(re.findall(r"\bfor\s+", content))
        cc += len(re.findall(r"\bwhile\s+", content))
        cc += len(re.findall(r"\bloop\s*\{", content))
        cc += len(re.findall(r"&&", content))
        cc += len(re.findall(r"\|\|", content))
        return cc

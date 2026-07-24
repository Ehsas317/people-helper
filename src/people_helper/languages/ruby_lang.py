"""Ruby language handler."""
import re
from .base import LanguageHandler


class RubyHandler(LanguageHandler):
    language_name = "Ruby"
    comment_prefixes = ("#",)

    def extract_relative_imports(self, content: str) -> list:
        # require_relative is structural, but the path resolution is complex
        # (Ruby resolves relative to __dir__, not the file itself)
        # For simplicity, we don't track Ruby siblings
        return []

    def extract_external_imports(self, content: str) -> list:
        imports = []
        for line in content.splitlines():
            # require 'foo' — external; require_relative is internal (skip)
            m = re.match(r"^\s*require\s+['\"]([^'\"]+)['\"]", line)
            if m and not line.strip().startswith("require_relative"):
                mod = m.group(1).split("/")[0]
                if mod and mod not in imports:
                    imports.append(mod)
        return imports

    def count_public_api(self, content: str) -> tuple:
        count, names = 0, []
        # Ruby: def method_name (public by default), class Foo, module Bar
        for m in re.finditer(r"^\s*def\s+(?:self\.)?(\w+)", content, re.MULTILINE):
            count += 1; names.append(m.group(1))
        for m in re.finditer(r"^\s*(?:module|class)\s+(\w+)", content, re.MULTILINE):
            count += 1; names.append(m.group(1))
        return (count, names)

    def detect_docstring(self, content: str) -> tuple:
        lines = content.splitlines()
        if not lines:
            return False, ""
        # Ruby: =begin/=end block comments at the top, or # comments
        # Most common: # frozen_string_literal: true comment then class def
        # We accept consecutive # comments at the top as a docstring
        comment_block = []
        for line in lines[:20]:
            stripped = line.strip()
            if stripped.startswith("#"):
                # Skip magic comments
                if "frozen_string_literal" in stripped or "encoding:" in stripped or "coding:" in stripped:
                    continue
                comment_block.append(line)
            elif comment_block:
                break
        if len(comment_block) >= 1:
            return True, "\n".join(comment_block).strip()
        # Check for =begin/=end block
        for i, line in enumerate(lines[:100]):
            if line.strip() == "=begin":
                block = [line]
                for ln in lines[i + 1:i + 30]:
                    block.append(ln)
                    if ln.strip() == "=end":
                        break
                return True, "\n".join(block).strip()
        return False, ""

    def is_internal_import(self, line: str, _project_modules: set) -> bool:
        return bool(re.match(r"^\s*require_relative\s+", line))

    def _is_external_import_line(self, line: str) -> bool:
        if re.match(r"^\s*require\s+", line) and not re.match(r"^\s*require_relative\s+", line):
            return True
        return False

    def get_dependency_weight(self, imports: list) -> tuple:
        if not imports:
            return (0, True)
        return (1, False)

    def get_complexity(self, content: str) -> int:
        """Regex-based cyclomatic complexity for Ruby."""
        cc = 1
        cc += len(re.findall(r'\bif\b', content))
        cc += len(re.findall(r'\belsif\b', content))
        cc += len(re.findall(r'\bfor\b', content))
        cc += len(re.findall(r'\bwhile\b', content))
        cc += len(re.findall(r'\bunless\b', content))
        cc += len(re.findall(r'\bcase\b', content))
        cc += len(re.findall(r'\bwhen\b', content))
        cc += len(re.findall(r'\brescue\b', content))
        cc += len(re.findall(r'&&', content))
        cc += len(re.findall(r'\|\|', content))
        return cc

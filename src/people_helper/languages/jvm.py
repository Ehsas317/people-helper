"""JVM language handler (Java + Kotlin).

Key difference: Java requires semicolons, Kotlin does NOT.
Kotlin's `public` is the DEFAULT visibility and rarely written explicitly.
"""
import re
from .base import LanguageHandler


_JAVA_STDLIB_PREFIXES = ("java.", "javax.", "javafx.", "jdk.", "sun.", "com.sun.", "org.w3c.", "org.xml.", "org.ietf.")


class JvmHandler(LanguageHandler):
    comment_prefixes = ("//", "/*")

    def __init__(self, language: str = "Java"):
        self.language_name = language
        self.is_kotlin = (language == "Kotlin")

    def extract_relative_imports(self, content: str) -> list:
        # Java/Kotlin have no relative imports (uses fully-qualified package paths)
        return []

    def extract_external_imports(self, content: str) -> list:
        imports = []
        if self.is_kotlin:
            # Kotlin: import com.foo.Bar (NO semicolon)
            # Also handles aliases: import com.foo.Bar as Baz
            for line in content.splitlines():
                m = re.match(r"^\s*import\s+([\w.]+)(?:\s+as\s+\w+)?\s*$", line)
                if m:
                    full = m.group(1)
                    # kotlin.* is stdlib, but kotlinx.* is EXTERNAL
                    if full.startswith(_JAVA_STDLIB_PREFIXES) or full.startswith("kotlin."):
                        continue
                    mod = full.split(".")[0]
                    if mod and mod not in imports:
                        imports.append(mod)
        else:
            # Java: import com.foo.Bar;
            for line in content.splitlines():
                m = re.match(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", line)
                if m:
                    full = m.group(1)
                    if full.startswith(_JAVA_STDLIB_PREFIXES):
                        continue
                    mod = full.split(".")[0]
                    if mod and mod not in imports:
                        imports.append(mod)
        return imports

    def count_public_api(self, content: str) -> tuple:
        count, names = 0, []
        if self.is_kotlin:
            # Kotlin: `public` is the DEFAULT and rarely written.
            # Count: fun, class, object, interface, enum class, data class
            # Skip private/internal/protected functions.
            for m in re.finditer(r"^\s*(?:public\s+|open\s+|final\s+|abstract\s+|sealed\s+)*(?:fun|override\s+fun)\s+(\w+)", content, re.MULTILINE):
                count += 1; names.append(m.group(1))
            for m in re.finditer(r"^\s*(?:public\s+|open\s+|final\s+|abstract\s+|sealed\s+)*(?:class|object|interface|enum\s+class|data\s+class)\s+(\w+)", content, re.MULTILINE):
                count += 1; names.append(m.group(1))
            # Also count top-level functions without visibility modifier (default public)
            for m in re.finditer(r"^\s*fun\s+(\w+)", content, re.MULTILINE):
                if m.group(1) not in names:
                    count += 1; names.append(m.group(1))
        else:
            # Java: explicit public keyword required
            for m in re.finditer(r"^\s*public\s+(?:final\s+|abstract\s+|static\s+)*(?:class|interface|enum)\s+(\w+)", content, re.MULTILINE):
                count += 1; names.append(m.group(1))
            for m in re.finditer(r"^\s*public\s+(?:final\s+|abstract\s+|static\s+|synchronized\s+)*(?:[\w<>\[\],?\s]+)\s+(\w+)\s*\(", content, re.MULTILINE):
                name = m.group(1)
                if name not in {"class", "interface", "enum"}:
                    count += 1; names.append(name)
        return (count, names)

    def detect_docstring(self, content: str) -> tuple:
        lines = content.splitlines()
        if not lines:
            return False, ""
        # Skip: package, import, using, #include, //, blank lines
        start = 0
        for i, line in enumerate(lines[:100]):
            stripped = line.strip()
            if not stripped:
                start = i + 1
                continue
            if stripped.startswith("//"):
                start = i + 1
                continue
            if stripped.startswith(("package ", "import ")):
                start = i + 1
                continue
            start = i
            break
        if start < len(lines) and lines[start].strip().startswith(("/**", "/*")):
            snippet_lines = []
            for line in lines[start:start + 30]:
                snippet_lines.append(line)
                if line.strip().endswith("*/"):
                    break
            return True, "\n".join(snippet_lines).strip()
        return False, ""

    def is_internal_import(self, line: str, _project_modules: set) -> bool:
        # Without project package metadata, treat all imports as external
        return False

    def _is_external_import_line(self, line: str) -> bool:
        if self.is_kotlin:
            return bool(re.match(r"^\s*import\s+[\w.]+", line))
        return bool(re.match(r"^\s*import\s+(?:static\s+)?[\w.]+\s*;", line))

    def get_dependency_weight(self, imports: list) -> tuple:
        if not imports:
            return (0, True)
        # JVM: any non-stdlib import is at least weight 1
        return (1, False)

    def get_complexity(self, content: str) -> int:
        """Regex-based cyclomatic complexity for Java/Kotlin.

        Counts: if, for, while, case, catch, &&, ||, ?:.
        """
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

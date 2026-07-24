"""Base class for language handlers.

Defines the interface every language module must implement.
Subclasses override only what they need; defaults are sensible no-ops.
"""
from abc import ABC, abstractmethod


class LanguageHandler(ABC):
    """Abstract base for language-specific code analysis.

    Each handler knows how to analyze ONE language family. The detection
    module delegates to handlers instead of containing all the logic itself.
    """

    # Subclasses set these
    language_name: str = "Unknown"
    # Comment prefixes for count_loc (lines starting with these are comments)
    comment_prefixes: tuple = ("//",)
    # Preprocessor prefix (e.g. "#" for C/C++) — these lines ARE code, not comments
    preprocessor_prefix: str | None = None

    def extract_relative_imports(self, content: str) -> list:
        """Return list of (sibling_name, parent_level) tuples for relative imports.

        Relative imports are STRUCTURAL dependencies — the file cannot run
        without its sibling. Most languages don't have relative imports
        (Java, Go, C, C++, C#, Swift, etc.) — default is empty.
        """
        return []

    @abstractmethod
    def extract_external_imports(self, content: str) -> list:
        """Return list of external (non-stdlib, non-relative) import names."""
        ...

    @abstractmethod
    def count_public_api(self, content: str) -> tuple:
        """Return (count, function_names_list) for public API surface."""
        ...

    @abstractmethod
    def detect_docstring(self, content: str) -> tuple:
        """Return (found: bool, snippet: str) for module-level documentation."""
        ...

    def is_internal_import(self, line: str, project_modules: set) -> bool:
        """Return True if the line is an internal (project) import.

        Default: False (can't tell without project structure metadata).
        """
        return False

    def count_imports(self, content: str, project_modules: set) -> tuple:
        """Return (internal_count, external_count) for all imports in content.

        IMPORTANT: external_count is derived from extract_external_imports()
        to ensure consistency. The Candidate's external_imports field MUST
        match the imports used for dependency_weight calculation.
        """
        internal, external = 0, 0
        for line in content.splitlines():
            if not line.strip():
                continue
            if self.is_internal_import(line, project_modules):
                internal += 1
        # external count = number of external imports (consistent with extract_external_imports)
        external = len(self.extract_external_imports(content))
        return internal, external

    def _is_external_import_line(self, line: str) -> bool:
        """Override in subclasses to identify external import lines.

        Default returns False — subclasses must override if they have imports.
        """
        return False

    def count_loc(self, content: str) -> int:
        """Count lines of code (non-blank, non-comment).

        For languages with a preprocessor (C/C++), preprocessor lines ARE code.
        Handles block-comment continuation lines (e.g. ' * continuation' inside
        a /* ... */ block) which should NOT be counted as code.

        IMPORTANT: The ' * ' continuation rule only applies to C-family
        languages (C/C++/Java/C#/JS/TS/Swift/PHP) where ' * ' is a block-comment
        continuation. In Python/Ruby, '*args' and '*head, tail = ...' are real
        code and must NOT be stripped.
        """
        # C-family languages where ' * ' is a block-comment continuation
        # Python and Ruby use '*' for unpacking (*args, *head) — must not strip
        is_c_family = self.language_name in {"C", "C++", "Java", "Kotlin", "C#",
                                              "JavaScript", "TypeScript", "PHP", "Swift"}

        count = 0
        in_block_comment = False
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            # Track block comment state (/* ... */ spans multiple lines)
            if in_block_comment:
                if "*/" in stripped:
                    in_block_comment = False
                continue  # Skip lines inside block comments
            # Check for block comment start
            if "/*" in stripped and "*/" not in stripped:
                before = stripped.split("/*")[0].strip()
                if before and not before.startswith("//"):
                    count += 1
                in_block_comment = True
                continue
            # Preprocessor lines (C/C++) are real code
            if self.preprocessor_prefix and stripped.startswith(self.preprocessor_prefix):
                count += 1
                continue
            # Skip block-comment continuation lines (start with * but not /*)
            # ONLY for C-family languages — Python/Ruby use * for unpacking
            if is_c_family and stripped.startswith("*") and not stripped.startswith("*/"):
                continue
            # Comment lines
            if any(stripped.startswith(p) for p in self.comment_prefixes) and len(stripped) > 2:
                continue
            count += 1
        return count

    def get_complexity(self, content: str) -> int:
        """Return cyclomatic complexity (0 if not implemented for this language).

        Default: 0 (only Python implements this via AST).
        """
        return 0

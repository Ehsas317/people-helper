"""Language abstraction layer.

Each language family module exposes a `LanguageHandler` with these methods:
  - extract_relative_imports(content) -> list[(name, parent_level)]
  - extract_external_imports(content) -> list[str]
  - count_public_api(content) -> (count, names)
  - detect_docstring(content) -> (bool, str)
  - is_internal_import(line, project_modules) -> bool
  - count_imports(content, project_modules) -> (internal, external)

Each language lives in its own module so adding a language or fixing a
language-specific behavior touches exactly one file.
"""

from .base import LanguageHandler
from .c_family import CFamilyHandler
from .dotnet import DotNetHandler
from .go_lang import GoHandler
from .js_ts import JsTsHandler
from .jvm import JvmHandler
from .php_lang import PhpHandler
from .python_lang import PythonHandler
from .ruby_lang import RubyHandler
from .rust_lang import RustHandler
from .swift_lang import SwiftHandler

# Registry: extension → handler instance
_HANDLERS = {
    ".py": PythonHandler(),
    ".ts": JsTsHandler(),
    ".tsx": JsTsHandler(),
    ".js": JsTsHandler(),
    ".jsx": JsTsHandler(),
    ".go": GoHandler(),
    ".rs": RustHandler(),
    ".java": JvmHandler(language="Java"),
    ".kt": JvmHandler(language="Kotlin"),
    ".c": CFamilyHandler(),
    ".h": CFamilyHandler(),
    ".cpp": CFamilyHandler(),
    ".hpp": CFamilyHandler(),
    ".cs": DotNetHandler(),
    ".rb": RubyHandler(),
    ".php": PhpHandler(),
    ".swift": SwiftHandler(),
}


def get_handler(ext: str) -> LanguageHandler | None:
    """Return the language handler for a file extension, or None if unsupported."""
    return _HANDLERS.get(ext.lower())


def supported_extensions() -> set:
    """Return the set of all supported file extensions."""
    return set(_HANDLERS.keys())

"""Suggest package names for extractable candidates."""

import re
from pathlib import Path

GENERIC_NAMES = {
    "route",
    "index",
    "main",
    "app",
    "server",
    "utils",
    "util",
    "helpers",
    "helper",
    "common",
    "lib",
    "types",
    "constants",
    "config",
    "conf",
    "api",
    "models",
    "model",
    "schema",
    "db",
    "auth",
    "middleware",
    "mod",
    "init",
    "test",
    "spec",
    "data",
    "struct",
    "structures",
    "interfaces",
    "impl",
    "base",
    "core",
    "shared",
}

# Directory names that are conventional code-organisation (don't include them in
# the package name — they describe WHERE the code lives, not WHAT it does).
NEUTRAL_DIRS = {".", "src", "lib", "app", "pkg", "crates", "compiler", "internal", "core", "include"}


def _docstring_hint(docstring_snippet: str, function_names: list) -> str:
    """Extract a useful word from the docstring OR function names to disambiguate
    generic filenames like models.py or utils.py.

    Preference order:
      1. A distinctive function/class name (often the best signal)
      2. A non-noise word from the docstring
    """
    noise = {
        "the",
        "this",
        "that",
        "module",
        "class",
        "function",
        "and",
        "for",
        "with",
        "from",
        "file",
        "import",
        "export",
        "const",
        "let",
        "var",
        "return",
        "package",
        "provides",
        "data",
        "structure",
        "structures",
        "type",
        "types",
        "object",
        "objects",
        "utility",
        "utilities",
        "helper",
    }
    # Try function/class names first — usually the most specific
    for name in function_names or []:
        if name and name.lower() not in noise and len(name) >= 3 and not name.startswith("_"):
            return name.lower()
    # Fall back to docstring words
    if docstring_snippet:
        for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", docstring_snippet):
            if w.lower() not in noise:
                return w.lower()
    return ""


def _stem_already_in_parent(stem: str, parent: str) -> bool:
    """True when the parent directory name already conveys the stem meaning,
    e.g. parent='people_helper_data' + stem='models' would yield
    'people-helper-data-models' which is redundant — 'data' already implies models.

    Heuristic: if the cleaned parent ends with the cleaned stem (or vice versa),
    or if they share a key noun, skip the stem suffix to avoid 'data-data' style names.
    """
    if not parent or not stem:
        return False
    p, s = _clean(parent), _clean(stem)
    if not p or not s:
        return False
    # If parent ends with stem (e.g. 'app-data' + 'data' → redundant)
    if p.endswith("-" + s) or p == s:
        return True
    # If the last meaningful component of parent equals the stem
    last_part = p.rsplit("-", 1)[-1]
    return last_part == s


def suggest_name(cand) -> str:
    p = Path(cand.path)
    stem, parent = p.stem, p.parent.name
    # Special-case Rust mod.rs / lib.rs → use parent dir name
    if stem in {"mod", "lib"}:
        if parent and parent not in NEUTRAL_DIRS:
            return _clean(parent)
        for ancestor in reversed(p.parents):
            aname = ancestor.name
            if aname and aname not in NEUTRAL_DIRS and aname != "":
                return _clean(aname)
    # Strip .d.ts extension for naming purposes
    if p.name.endswith(".d.ts"):
        stem = p.name[:-5]
    # CamelCase / PascalCase → kebab-case
    stem_split = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", stem)
    stem_split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", stem_split)
    stem_split = stem_split.lower()
    # If stem is meaningful, use it directly
    if stem.lower() not in GENERIC_NAMES:
        return _clean(stem_split) or "extracted-utility"
    # Generic stem: try parent + hint
    if parent and parent not in NEUTRAL_DIRS:
        hint = _docstring_hint(cand.docstring_snippet, getattr(cand, "function_names", []))
        if hint and not _stem_already_in_parent(hint, parent):
            return _clean(f"{parent}-{hint}")
        # Parent already conveys the meaning (e.g. 'people_helper_data' + 'models.py' → 'people-helper-data')
        # Don't append the stem to avoid 'data-data' style duplicates.
        return _clean(parent)
    # No useful parent: try hint only
    hint = _docstring_hint(cand.docstring_snippet, getattr(cand, "function_names", []))
    if hint:
        return _clean(hint)
    return "extracted-utility"


def _clean(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", s.lower())).strip("-")


def suggest_tags(cand) -> list:
    tags, seen = [], set()

    def _add(t):
        if t not in seen:
            tags.append(t)
            seen.add(t)

    lang_tags = {
        "Python": "python",
        "TypeScript": "typescript",
        "JavaScript": "javascript",
        "Go": "golang",
        "Rust": "rust",
        "Java": "java",
        "Kotlin": "kotlin",
        "C": "c",
        "C++": "cpp",
        "C#": "csharp",
        "Ruby": "ruby",
        "PHP": "php",
        "Swift": "swift",
    }
    if cand.language in lang_tags:
        _add(lang_tags[cand.language])
    stem = Path(cand.path).stem.lower()
    if any(p in stem for p in ["util", "helper", "common"]):
        _add("utility")
    if any(p in stem for p in ["valid", "guard", "check"]):
        _add("validation")
    if any(p in stem for p in ["parse", "format", "convert", "transform"]):
        _add("parser")
    if any(p in stem for p in ["auth", "jwt", "token", "oauth"]):
        _add("authentication")
    if any(p in stem for p in ["cache", "memoiz"]):
        _add("caching")
    if any(p in stem for p in ["retry", "backoff"]):
        _add("resilience")
    if any(p in stem for p in ["sanitiz", "escape", "xss"]):
        _add("security")
    _add("library")
    _add("open-source")
    noise = {
        "the",
        "this",
        "that",
        "module",
        "class",
        "function",
        "and",
        "for",
        "with",
        "from",
        "file",
        "import",
        "export",
        "const",
        "let",
        "var",
        "return",
        "package",
        "provides",
        "dict",
        "list",
        "tuple",
        "set",
        "str",
        "int",
        "float",
        "bool",
        "none",
        "true",
        "false",
        "def",
        "self",
        "cls",
        "type",
        "args",
        "data",
        "value",
        "also",
        "can",
        "has",
        "not",
        "are",
        "was",
        "were",
        "will",
        "should",
        "could",
        "would",
        "does",
        "than",
        "small",
        "string",
        "strings",
    }
    if cand.docstring_snippet:
        for word in cand.docstring_snippet.lower().split():
            w = word.strip(".,;:!?()[]{}'")
            if 3 < len(w) < 20 and w.isalpha() and w not in noise and w not in seen:
                _add(w)
            if len(tags) >= 5:
                break
    return tags[:5]

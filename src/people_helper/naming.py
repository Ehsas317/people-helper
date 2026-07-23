"""Suggest package names for extractable candidates."""

import re
from pathlib import Path

GENERIC_NAMES = {
    "route", "index", "main", "app", "server", "utils", "util",
    "helpers", "common", "lib", "types", "constants", "config",
    "api", "models", "schema", "db", "auth", "middleware",
}


def suggest_name(cand) -> str:
    """
    Suggest a name based on the file path, parent directory, and content.
    Avoids generic names. Uses parent dir context when the file name is too generic.
    """
    p = Path(cand.path)
    stem = p.stem
    parent = p.parent.name

    # Generic file names should use parent context
    if stem.lower() in GENERIC_NAMES and parent and parent not in {".", "src", "lib", "app", "pkg"}:
        hint = ""
        if cand.docstring_snippet:
            noise = {
                "the", "this", "that", "module", "class", "function",
                "and", "for", "with", "from", "file", "import", "export",
                "const", "let", "var", "return", "package", "provides",
            }
            words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", cand.docstring_snippet)
            for w in words:
                if w.lower() not in noise:
                    hint = w.lower()
                    break
        if hint:
            return re.sub(r"-+", "-", f"{parent}-{hint}")
        return re.sub(r"[^a-z0-9-]", "-", parent.lower()).strip("-")

    if stem.lower() in GENERIC_NAMES:
        if parent and parent not in {".", "src", "lib", "app", "pkg"}:
            return re.sub(r"[^a-z0-9-]", "-", f"{parent}-{stem}".lower()).strip("-")
        return "extracted-utility"

    # Normal case: clean the file stem
    name = re.sub(r"[^a-z0-9-]", "-", stem.lower())
    name = re.sub(r"-+", "-", name).strip("-")
    return name or "extracted-utility"


def suggest_tags(cand) -> list:
    """
    Suggest GitHub topic tags based on the candidate's traits.
    """
    tags = set()
    stem = Path(cand.path).stem.lower()

    # Language tag
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
        tags.add(lang_tags[cand.language])

    # Type tags from filename patterns
    if any(p in stem for p in ["util", "helper", "common"]):
        tags.add("utility")
    if any(p in stem for p in ["valid", "guard", "check"]):
        tags.add("validation")
    if any(p in stem for p in ["parse", "format", "convert", "transform"]):
        tags.add("parser")
    if any(p in stem for p in ["serializ", "deserializ"]):
        tags.add("serialization")
    if any(p in stem for p in ["auth", "jwt", "token", "oauth"]):
        tags.add("authentication")
    if any(p in stem for p in ["rate", "limit", "throttl"]):
        tags.add("rate-limiting")
    if any(p in stem for p in ["log", "logger"]):
        tags.add("logging")
    if any(p in stem for p in ["cache", "memoiz"]):
        tags.add("caching")
    if any(p in stem for p in ["retry", "backoff"]):
        tags.add("resilience")
    if any(p in stem for p in ["sanitiz", "escape", "xss"]):
        tags.add("security")

    # Generic tags
    tags.add("library")
    tags.add("open-source")

    # Extract from docstring (with noise filtering)
    _tag_noise = {
        "the", "this", "that", "module", "class", "function",
        "and", "for", "with", "from", "file", "import", "export",
        "const", "let", "var", "return", "package", "provides",
        "dict", "list", "tuple", "set", "str", "int", "float",
        "bool", "none", "true", "false", "def", "self", "cls",
        "type", "args", "kwargs", "data", "value", "values",
        "also", "can", "has", "not", "are", "was", "were",
        "will", "should", "could", "would", "does", "than",
    }
    if cand.docstring_snippet:
        for word in cand.docstring_snippet.lower().split():
            w = word.strip(".,;:!?()[]{}'")
            if 3 < len(w) < 20 and w.isalpha() and w not in _tag_noise:
                tags.add(w)

    # Cap at 8 tags, prioritize specific ones
    result = list(tags)[:8]
    return result

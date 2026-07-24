"""string_utils.py — small, self-contained string utilities.

Provides functions for normalizing, truncating, and escaping strings
in a way that is safe for use in URLs, filenames, and HTML output.
"""


def slugify(text: str, separator: str = "-") -> str:
    """Convert text to a URL-safe slug.

    Lowercases, strips non-alphanumeric characters, and joins words
    with the given separator.
    """
    import re
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", separator, text)
    return text.strip(separator)


def truncate(text: str, max_length: int, suffix: str = "…") -> str:
    """Truncate text to max_length, appending suffix if cut."""
    if len(text) <= max_length:
        return text
    if max_length <= len(suffix):
        return suffix[:max_length]
    return text[: max_length - len(suffix)] + suffix


def escape_html(text: str) -> str:
    """Escape the 5 XML/HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

"""Tests for string_utils."""
from src.string_utils import escape_html, slugify, truncate


def test_slugify_basic():
    assert slugify("Hello World!") == "hello-world"


def test_slugify_custom_separator():
    assert slugify("Hello World", "_") == "hello_world"


def test_slugify_strips_punctuation():
    assert slugify("  hello,  world!!  ") == "hello-world"


def test_truncate_short():
    assert truncate("hi", 10) == "hi"


def test_truncate_exact():
    assert truncate("hello", 5) == "hello"


def test_truncate_long():
    assert truncate("hello world", 8) == "hello w…"


def test_escape_html():
    assert escape_html('<a href="x">&</a>') == "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;"

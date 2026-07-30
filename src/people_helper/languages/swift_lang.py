"""Swift language handler."""

import re

from .base import LanguageHandler

_SWIFT_STDLIB = {
    "Foundation",
    "UIKit",
    "SwiftUI",
    "Combine",
    "CoreData",
    "CoreGraphics",
    "CoreImage",
    "CoreLocation",
    "CoreText",
    "MapKit",
    "WebKit",
    "CloudKit",
    "StoreKit",
    "AVFoundation",
    "AVKit",
    "AudioToolbox",
    "CoreAudio",
    "CoreMedia",
    "CoreVideo",
    "CoreAnimation",
    "AppKit",
    "Security",
    "CryptoKit",
    "Network",
    "OSLog",
    "XCTest",
    "Swift",
    "Dispatch",
    "Metal",
}


class SwiftHandler(LanguageHandler):
    language_name = "Swift"
    comment_prefixes = ("//", "/*")

    def extract_relative_imports(self, content: str) -> list:
        return []

    def extract_external_imports(self, content: str) -> list:
        imports = []
        for line in content.splitlines():
            m = re.match(r"^\s*import\s+(\w+)", line)
            if m:
                mod = m.group(1)
                if mod in _SWIFT_STDLIB:
                    continue
                if mod and mod not in imports:
                    imports.append(mod)
        return imports

    def count_public_api(self, content: str) -> tuple:
        count, names = 0, []
        # Swift: func foo(), struct Foo, class Foo, enum Foo, protocol Foo
        # Public by default if no access modifier (internal is default but treated as public here)
        for m in re.finditer(
            r"^\s*(?:public\s+|open\s+|internal\s+|fileprivate\s+|private\s+)?func\s+(\w+)", content, re.MULTILINE
        ):
            name = m.group(1)
            # Skip private funcs (don't count)
            if "private" in m.group(0):
                continue
            count += 1
            names.append(name)
        for m in re.finditer(
            r"^\s*(?:public\s+|open\s+|internal\s+|fileprivate\s+|private\s+)?(?:struct|class|enum|protocol)\s+(\w+)",
            content,
            re.MULTILINE,
        ):
            if "private" in m.group(0):
                continue
            count += 1
            names.append(m.group(1))
        return (count, names)

    def detect_docstring(self, content: str) -> tuple:
        lines = content.splitlines()
        if not lines:
            return False, ""
        # Skip: import, //, blank lines
        start = 0
        for i, line in enumerate(lines[:100]):
            stripped = line.strip()
            if not stripped:
                start = i + 1
                continue
            if stripped.startswith("//"):
                start = i + 1
                continue
            if stripped.startswith("import "):
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
        return False

    def get_dependency_weight(self, imports: list) -> tuple:
        if not imports:
            return (0, True)
        return (1, False)

    def get_complexity(self, content: str) -> int:
        """Regex-based cyclomatic complexity for Swift."""
        cc = 1
        cc += len(re.findall(r"\bif\s+", content))
        cc += len(re.findall(r"\bfor\s+", content))
        cc += len(re.findall(r"\bwhile\s+", content))
        cc += len(re.findall(r"\bcase\s+", content))
        cc += len(re.findall(r"\bcatch\s*\{", content))
        cc += len(re.findall(r"&&", content))
        cc += len(re.findall(r"\|\|", content))
        return cc

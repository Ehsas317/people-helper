"""Stage 3+4: Module mapping and extractable candidate detection."""

import re
from pathlib import Path

from .config import (
    LANG_BY_EXT, SKIP_DIRS, UTILITY_PATTERNS, FRAMEWORK_ENTRY_NAMES,
    FRAMEWORK_SPECIAL_FILES, FRAMEWORK_DIRS, EXTERNAL_SCOPES,
)
from .models import Candidate


def count_loc(content: str) -> int:
    """Count non-empty, non-comment-only lines."""
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "//")) and len(stripped) > 2:
            continue
        count += 1
    return count


def detect_docstring(content: str, ext: str) -> tuple:
    """Detect module-level documentation. Returns (has_doc, snippet)."""
    lines = content.splitlines()
    if not lines:
        return False, ""

    if ext == ".py":
        first_nonblank = next((i for i, l in enumerate(lines) if l.strip()), None)
        if first_nonblank is None:
            return False, ""
        if lines[first_nonblank].strip().startswith(('"""', "'''")):
            end_quote = '"""' if '"""' in lines[first_nonblank] else "'''"
            snippet_lines = [lines[first_nonblank].lstrip()]
            for line in lines[first_nonblank + 1:first_nonblank + 21]:
                snippet_lines.append(line)
                if end_quote in line:
                    break
            return True, "\n".join(snippet_lines).strip()

    if ext in {".ts", ".tsx", ".js", ".jsx"}:
        if lines[0].strip().startswith("/**"):
            snippet_lines = []
            for line in lines[:30]:
                snippet_lines.append(line)
                if line.strip().endswith("*/"):
                    break
            return True, "\n".join(snippet_lines).strip()
        comment_block = []
        for line in lines[:30]:
            stripped = line.strip()
            if stripped.startswith("//"):
                comment_block.append(line)
            elif stripped == "":
                if len(comment_block) >= 5:
                    break
                continue
            else:
                break
        if len(comment_block) >= 5:
            return True, "\n".join(comment_block).strip()

    if ext == ".go":
        comment_block = []
        for line in lines[:20]:
            if line.strip().startswith("//"):
                comment_block.append(line)
            elif comment_block:
                break
        if len(comment_block) >= 2:
            return True, "\n".join(comment_block).strip()

    if ext == ".rs":
        comment_block = []
        for line in lines[:20]:
            if line.strip().startswith("//!"):
                comment_block.append(line)
            elif comment_block:
                break
        if comment_block:
            return True, "\n".join(comment_block).strip()

    if ext in {".java", ".kt", ".c", ".cpp", ".hpp", ".h", ".cs"}:
        if lines[0].strip().startswith("/**"):
            snippet_lines = []
            for line in lines[:30]:
                snippet_lines.append(line)
                if line.strip().endswith("*/"):
                    break
            return True, "\n".join(snippet_lines).strip()
        if lines[0].strip().startswith("/*"):
            snippet_lines = []
            for line in lines[:30]:
                snippet_lines.append(line)
                if line.strip().endswith("*/"):
                    break
            return True, "\n".join(snippet_lines).strip()

    return False, ""


def _is_internal_import_py(line: str, project_files: set) -> bool:
    if re.match(r"^\s*from\s+\.", line):
        return True
    m = re.match(r"^\s*from\s+([\w.]+)\s+import", line)
    if m:
        mod = m.group(1).split(".")[0]
        if mod in project_files or any(mod in pf for pf in project_files):
            return True
    m = re.match(r"^\s*import\s+([\w.]+)", line)
    if m:
        mod = m.group(1).split(".")[0]
        if mod in project_files or any(mod in pf for pf in project_files):
            return True
    return False


_IMPORT_FROM_RE = re.compile(r'^\s*import\s+.*from\s+["' + chr(39) + r']([\w./@\-~]+)')
_REQUIRE_RE = re.compile(r'^\s*(?:const|let|var)\s+\w+\s*=\s*require\(["' + chr(39) + r']([\w./@\-~]+)[' + chr(39) + r']\)')

def _is_internal_import_js(line: str, _project_files: set) -> bool:
    m = _IMPORT_FROM_RE.match(line)
    if m:
        path = m.group(1)
        if path.startswith("."):
            return True
        if path.startswith("/"):
            return True
        if path.startswith("@/") or path.startswith("~/"):
            return True
        if path.startswith("@") and "/" in path[1:]:
            scope = path[1:].split("/")[0]
            if scope not in EXTERNAL_SCOPES:
                return True
    m = _REQUIRE_RE.match(line)
    if m:
        path = m.group(1)
        if path.startswith(".") or path.startswith("@/") or path.startswith("~/"):
            return True
    return False


def _is_internal_import_go(line: str, _project_files: set) -> bool:
    m = re.match(r'^\s*"([\w./\-]+)"', line)
    if m:
        if "/" not in m.group(1):
            return True
    return False


def _is_internal_import_rs(line: str, _project_files: set) -> bool:
    return bool(re.match(r"^\s*use\s+(crate|super|self)", line))


_INTERNAL_CHECKERS = {
    ".py": _is_internal_import_py,
    ".ts": _is_internal_import_js,
    ".tsx": _is_internal_import_js,
    ".js": _is_internal_import_js,
    ".jsx": _is_internal_import_js,
    ".go": _is_internal_import_go,
    ".rs": _is_internal_import_rs,
}


def count_imports(content: str, ext: str, project_files: set) -> tuple:
    internal = 0
    external = 0
    checker = _INTERNAL_CHECKERS.get(ext)
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if checker and checker(line, project_files):
            internal += 1
            continue
        if ext == ".py":
            if re.match(r"^\s*(import|from)\s+", line):
                external += 1
        elif ext in {".ts", ".tsx", ".js", ".jsx"}:
            if re.match(r"^\s*import\s+", line):
                external += 1
            elif re.match(r"^\s*(?:const|let|var)\s+\w+\s*=\s*require\(", line):
                external += 1
        elif ext == ".go":
            if re.match(r'^\s*"[\w./\-]+/[\w./\-]+"', line):
                external += 1
        elif ext == ".rs":
            if re.match(r"^\s*use\s+", line) and not re.match(r"^\s*use\s+(crate|super|self)", line):
                external += 1
    return internal, external


def compute_filename_score(path: str) -> float:
    name = Path(path).stem.lower()
    score = 0.0
    for pattern in UTILITY_PATTERNS:
        if pattern in name:
            score += 0.5
    if name in FRAMEWORK_ENTRY_NAMES:
        score -= 3.0
    if "test" in name or "spec" in name:
        score -= 2.0
    return score


def is_framework_route(path: str) -> bool:
    p = Path(path)
    parts = p.parts
    for part in parts:
        if part.lower() in FRAMEWORK_DIRS:
            return True
    if p.name in FRAMEWORK_SPECIAL_FILES:
        return True
    return False


def has_test_for(file_path: str, all_files: set) -> bool:
    p = Path(file_path)
    stem = p.stem
    ext = p.suffix
    candidates = [
        f"tests/test_{stem}{ext}",
        f"test/test_{stem}{ext}",
        f"__tests__/{stem}{ext}",
        f"__tests__/{stem}.test{ext}",
        f"__tests__/{stem}.spec{ext}",
        f"{stem}_test{ext}",
        f"{stem}Test{ext}",
        f"{stem}.test{ext}",
        f"{stem}.spec{ext}",
    ]
    return any(c in all_files for c in candidates)


def _extract_what_it_does(docstring: str, first_lines: str, path: str) -> str:
    # Lines that look like code, not descriptions
    _code_prefixes = (
        'from ', 'import ', 'const ', 'let ', 'var ', 'export ',
        'require(', 'function ', 'def ', 'class ', 'async ',
        'return ', 'if ', 'for ', 'while ', 'try:', 'except',
        'with ', '@', '#!', 'package ', 'use ', 'mod ',
    )
    if docstring:
        for line in docstring.splitlines():
            cleaned = re.sub(r"^[\s*/#" + chr(39) + chr(34) + r"]+\s*", "", line).strip()
            cleaned = cleaned.rstrip(chr(39) + chr(34)).strip()
            # Skip decorative lines (tildes, dashes, equals) and module-path headers
            if not cleaned or len(cleaned) <= 5:
                continue
            if re.match(r'^[~\-=]+$', cleaned):
                continue
            # Skip JSDoc / annotation lines that start with @
            if cleaned.startswith('@'):
                continue
            if re.match(r'^[\w.]+$', cleaned) and '.' in cleaned and not any(w in cleaned.lower() for w in ('provides', 'implements', 'contains', 'handles', 'manages', 'offers')):
                continue
            if len(cleaned) > 200:
                return cleaned[:197] + "..."
            return cleaned
    for line in first_lines.splitlines()[:15]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "//", "/*", "*")):
            continue
        # Skip import/export statements and code-like lines
        if any(stripped.startswith(p) for p in _code_prefixes):
            continue
        # Skip quoted strings (function/method docstrings in code)
        if stripped.startswith((chr(34)*3, chr(39)*3)):
            continue
        # Skip function signatures (e.g. "owner: str,")
        if re.match(r'^[a-z_]\w*\s*[:=]', stripped) and len(stripped) < 60 and not any(c in stripped for c in '.!?'):
            continue
        # Skip assignment lines (e.g. "now = datetime.now(...)")
        if re.match(r'^[a-z_]\w*\s*=\s*.+$', stripped) and len(stripped) > 15:
            continue
        # Skip lines that are mostly symbols/operators
        alpha_ratio = sum(1 for c in stripped if c.isalpha()) / max(len(stripped), 1)
        if alpha_ratio < 0.5:
            continue
        if len(stripped) > 10:
            if len(stripped) > 200:
                return stripped[:197] + "..."
            return stripped
    return f"Module at {path}"


def _build_why_extractable(cand) -> list:
    reasons = []
    if cand.has_tests:
        reasons.append("Has corresponding test file")
    if cand.has_docstring:
        reasons.append("Has module-level documentation")
    if cand.internal_imports == 0:
        reasons.append("Zero internal project imports -- fully self-contained")
    elif cand.internal_imports == 1:
        reasons.append("Only 1 internal import -- loosely coupled")
    if cand.external_imports <= 3:
        reasons.append(f"Small dependency footprint ({cand.external_imports} external import(s))")
    if cand.loc < 50:
        reasons.append(f"Very small ({cand.loc} LOC) -- easy to extract and maintain")
    elif cand.loc < 150:
        reasons.append(f"Manageable size ({cand.loc} LOC)")
    if cand.filename_score > 0:
        reasons.append("Filename suggests a reusable utility")
    if not reasons:
        reasons.append("Passed extractable heuristics (size, import count, and filename analysis)")
    return reasons


def detect_candidates(files: list, primary_language: str) -> list:
    file_set = {f["path"] for f in files}
    candidates = []
    for f in files:
        ext = f["ext"]
        lang = LANG_BY_EXT.get(ext)
        if not lang:
            continue
        path_str = f["path"]
        path_lower = path_str.lower()
        if any(part in path_lower for part in ["/test/", "/tests/", "__tests__"]):
            continue
        stem = Path(path_str).stem.lower()
        if any(x in stem for x in ["test_", "_test", ".test", ".spec", "conftest"]):
            continue
        if Path(path_str).name in {"__init__.py", "conftest.py"}:
            continue
        loc = count_loc(f["content"])
        if loc < 10 or loc > 500:
            continue
        if is_framework_route(path_str):
            continue
        has_doc, doc_snippet = detect_docstring(f["content"], ext)
        internal, external = count_imports(f["content"], ext, file_set)
        fscore = compute_filename_score(path_str)
        tested = has_test_for(path_str, file_set)
        if internal >= 2:
            cand = Candidate(
                path=path_str, language=lang, loc=loc,
                has_tests=tested, has_docstring=has_doc,
                internal_imports=internal, external_imports=external,
                filename_score=fscore, skipped=True,
                skip_reason=f"{internal} internal imports -- tightly coupled",
            )
            candidates.append(cand)
            continue
        if fscore < -0.5:
            continue
        first_lines = "\n".join(f["content"].splitlines()[:30])
        what_it_does = _extract_what_it_does(doc_snippet, first_lines, path_str)
        cand = Candidate(
            path=path_str, language=lang, loc=loc,
            has_tests=tested, has_docstring=has_doc,
            internal_imports=internal, external_imports=external,
            filename_score=fscore, docstring_snippet=doc_snippet,
            first_lines=first_lines, what_it_does=what_it_does,
        )
        cand.why_extractable = _build_why_extractable(cand)
        candidates.append(cand)
    return candidates

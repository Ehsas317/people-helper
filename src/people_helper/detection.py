"""Stage 3+4: Module mapping and extractable candidate detection.

Heuristics (in order):
  1. Size: 10-500 LOC (non-comment, non-blank).
  2. Skip framework route files (Next.js pages, SvelteKit +page, etc.).
  3. Skip tests / conftest / __init__.
  4. Module-level docstring detection (per-language).
  5. Internal vs external import counting (per-language).
  6. Filename score (utility patterns +, framework entry -).
  7. Test file presence.
  8. Skip if internal_imports >= 2 (tightly coupled).
  9. NEW: Cyclomatic complexity (McCabe) — penalize god functions.
 10. NEW: Reverse fan-in / orphan detection — boost orphans.
 11. NEW: SCC cycle detection — skip files in import cycles.
"""
import ast
import re
from pathlib import Path

from .config import (
    EXTERNAL_SCOPES,
    FRAMEWORK_DIRS,
    FRAMEWORK_ENTRY_NAMES,
    FRAMEWORK_SPECIAL_FILES,
    LANG_BY_EXT,
    UTILITY_PATTERNS,
)
from .models import Candidate

# ----------------------------------------------------------------------
# Plain helpers
# ----------------------------------------------------------------------

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
        first_nonblank = next((i for i, line in enumerate(lines) if line.strip()), None)
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


# ----------------------------------------------------------------------
# Import analysis (per-language)
# ----------------------------------------------------------------------

def _is_internal_import_py(line: str, project_modules: set) -> bool:
    """A Python import is internal if it's relative OR the root module
    name matches a known project module name (no substring scan).

    `project_modules` is a set of TOP-LEVEL module names (e.g.
    {"people_helper", "string_utils"}) — NOT a set of file paths.
    """
    if re.match(r"^\s*from\s+\.", line):
        return True
    m = re.match(r"^\s*from\s+([\w.]+)\s+import", line)
    if m:
        mod = m.group(1).split(".")[0]
        if mod in project_modules:
            return True
        return False
    m = re.match(r"^\s*import\s+([\w.]+)", line)
    if m:
        mod = m.group(1).split(".")[0]
        if mod in project_modules:
            return True
    return False


_IMPORT_FROM_RE = re.compile(r'^\s*import\s+.*from\s+["' + chr(39) + r']([\w./@\-~]+)')
_REQUIRE_RE = re.compile(r'^\s*(?:const|let|var)\s+\w+\s*=\s*require\(["' + chr(39) + r']([\w./@\-~]+)[' + chr(39) + r']\)')


def _is_internal_import_js(line: str, _project_modules: set) -> bool:
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


def _is_internal_import_go(line: str, _project_modules: set) -> bool:
    m = re.match(r'^\s*"([\w./\-]+)"', line)
    if m:
        # Heuristic: bare module names (no domain / no slash) are internal.
        if "/" not in m.group(1):
            return True
    return False


def _is_internal_import_rs(line: str, _project_modules: set) -> bool:
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


def count_imports(content: str, ext: str, project_modules: set) -> tuple:
    """Returns (internal_count, external_count)."""
    internal = 0
    external = 0
    checker = _INTERNAL_CHECKERS.get(ext)
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if checker and checker(line, project_modules):
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


# ----------------------------------------------------------------------
# Filename / framework heuristics
# ----------------------------------------------------------------------

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
    """Check if any test file exists for the given source file.

    Tries multiple naming conventions AND multiple directory levels
    (same dir, parent dir, tests/ subdirs). Handles `src/foo.ts` finding
    `src/foo.test.ts`, `tests/test_foo.py`, etc.
    """
    p = Path(file_path)
    stem = p.stem
    ext = p.suffix
    parent = p.parent
    parent_str = str(parent) if str(parent) != "." else ""

    # Names without directory prefix
    bare_names = [
        f"test_{stem}{ext}",
        f"{stem}_test{ext}",
        f"{stem}Test{ext}",
        f"{stem}.test{ext}",
        f"{stem}.spec{ext}",
    ]

    # Directories to look in
    test_dirs = [""]
    if parent_str:
        test_dirs.append(parent_str + "/")
        # Parent of parent (for tests/ at the project root when source is in src/)
        grandparent = parent.parent
        if str(grandparent) != ".":
            test_dirs.append(str(grandparent) + "/tests/")
            test_dirs.append(str(grandparent) + "/test/")
    test_dirs.extend(["tests/", "test/", "__tests__/"])

    # Combinations
    candidates = set()
    for d in test_dirs:
        for name in bare_names:
            candidates.add(f"{d}{name}")
        # Also: tests/test_foo.py vs tests/foo_test.py — both common
        if d.endswith("tests/") or d.endswith("test/"):
            candidates.add(f"{d}{stem}{ext}")  # tests/foo.py
            candidates.add(f"{d}{stem}.test{ext}")
            candidates.add(f"{d}{stem}.spec{ext}")

    return any(c in all_files for c in candidates)


# ----------------------------------------------------------------------
# NEW: Cyclomatic complexity (Python only — uses ast)
# ----------------------------------------------------------------------

def cyclomatic_complexity_python(source: str) -> int:
    """Compute McCabe cyclomatic complexity for a Python source string.

    Returns 0 on syntax error. Counts: if, elif, for, while, except,
    with, assert, boolean ops (and/or), comprehensions, conditional
    expressions. Minimum complexity is 1 (a flat function).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0

    cc = 1  # base path
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                             ast.With, ast.Assert)):
            cc += 1
        elif isinstance(node, ast.BoolOp):
            # Each boolean op adds (n-1) decision points where n is the
            # number of operands. `a and b and c` adds 2.
            cc += max(0, len(node.values) - 1)
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            # Each comprehension clause (for/if inside) adds a decision.
            for gen in node.generators:
                cc += 1  # the `for` clause
                cc += len(gen.ifs)  # `if` clauses
        elif isinstance(node, ast.IfExp):
            # Ternary `a if cond else b`
            cc += 1
    return cc


# ----------------------------------------------------------------------
# NEW: Import graph + Tarjan's SCC + fan-in
# ----------------------------------------------------------------------

def _extract_internal_targets_py(content: str, project_modules: set) -> list:
    """Return list of TOP-LEVEL module names that this file imports internally."""
    targets = []
    seen = set()
    m = re.match(r"^\s*from\s+\.\s+import\s+(.+)", content, re.MULTILINE)
    # Simpler: scan line by line
    for line in content.splitlines():
        m = re.match(r"^\s*from\s+\.(\w+)\s+import", line)
        if m:
            mod = m.group(1)
            if mod not in seen:
                targets.append(mod)
                seen.add(mod)
            continue
        m = re.match(r"^\s*from\s+([\w.]+)\s+import", line)
        if m:
            mod = m.group(1).split(".")[0]
            if mod in project_modules and mod not in seen:
                targets.append(mod)
                seen.add(mod)
            continue
        m = re.match(r"^\s*import\s+([\w.]+)", line)
        if m:
            mod = m.group(1).split(".")[0]
            if mod in project_modules and mod not in seen:
                targets.append(mod)
                seen.add(mod)
    return targets


def build_import_graph(files: list) -> dict:
    """Build a directed import graph keyed by file path (relative).

    Edge A → B means "A imports B". Only Python files are analysed
    (other languages have no project-wide module index here).
    Returns {path: [target_paths]}.
    """
    # Build module-name → set of file paths mapping.
    # A file's stem is treated as its module name (so `cycle_a.py` → "cycle_a").
    # __init__.py maps to its parent directory name.
    module_to_paths: dict[str, set] = {}
    all_py_paths: set = set()

    for f in files:
        if f["ext"] != ".py":
            continue
        path = f["path"]
        p = Path(path)
        all_py_paths.add(path)
        module_to_paths.setdefault(p.stem, set()).add(path)
        # Also map top-level dir name → path (for absolute imports)
        if len(p.parts) > 1:
            module_to_paths.setdefault(p.parts[0], set()).add(path)
        if p.name == "__init__.py":
            module_to_paths.setdefault(p.parent.name, set()).add(path)

    graph: dict[str, list] = {}
    for f in files:
        if f["ext"] != ".py":
            continue
        src_path = f["path"]
        src_dir = Path(src_path).parent
        target_paths: list = []
        seen_targets: set = set()

        for line in f["content"].splitlines():
            # Relative import: from .foo import ...  OR  from . import foo
            m = re.match(r"^\s*from\s+\.(\w*)\s+import", line)
            if m:
                sibling_mod = m.group(1)
                if sibling_mod:
                    # from .foo import X → resolve to src_dir/foo.py
                    sibling_file = (
                        f"{sibling_mod}.py" if str(src_dir) == "."
                        else str(src_dir / f"{sibling_mod}.py")
                    )
                    if sibling_file in all_py_paths and sibling_file != src_path:
                        if sibling_file not in seen_targets:
                            target_paths.append(sibling_file)
                            seen_targets.add(sibling_file)
                    # Also try package: src_dir/foo/__init__.py
                    pkg_init = (
                        f"{sibling_mod}/__init__.py" if str(src_dir) == "."
                        else str(src_dir / sibling_mod / "__init__.py")
                    )
                    if pkg_init in all_py_paths and pkg_init != src_path:
                        if pkg_init not in seen_targets:
                            target_paths.append(pkg_init)
                            seen_targets.add(pkg_init)
                continue

            # Absolute project import: from foo import ... OR import foo
            m = re.match(r"^\s*from\s+([\w.]+)\s+import", line)
            if m:
                mod = m.group(1).split(".")[0]
                for tp in module_to_paths.get(mod, set()):
                    if tp != src_path and tp not in seen_targets:
                        target_paths.append(tp)
                        seen_targets.add(tp)
                continue
            m = re.match(r"^\s*import\s+([\w.]+)", line)
            if m:
                mod = m.group(1).split(".")[0]
                for tp in module_to_paths.get(mod, set()):
                    if tp != src_path and tp not in seen_targets:
                        target_paths.append(tp)
                        seen_targets.add(tp)

        graph[src_path] = target_paths
    return graph


def find_cycles_scc(graph: dict) -> list:
    """Tarjan's strongly-connected components algorithm.

    Returns a list of cycles — each cycle is a list of node paths.
    Only SCCs with >= 2 nodes (or self-loops) are returned.
    """
    index_counter = [0]
    stack = []
    lowlink: dict = {}
    index: dict = {}
    on_stack: dict = {}
    result: list = []

    def strongconnect(v):
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for w in graph.get(v, []):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            scc = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == v:
                    break
            # Only keep non-trivial SCCs (>= 2 nodes, or 1 node with a self-loop)
            if len(scc) >= 2:
                result.append(scc)
            elif len(scc) == 1 and scc[0] in graph.get(scc[0], []):
                result.append(scc)

    # Use iterative DFS to avoid recursion limit on big repos
    sys_recursion_limit = None
    import sys
    if len(graph) > 500:
        sys_recursion_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(sys_recursion_limit, len(graph) * 2 + 100))

    try:
        for v in list(graph.keys()):
            if v not in index:
                strongconnect(v)
    finally:
        if sys_recursion_limit is not None:
            sys.setrecursionlimit(sys_recursion_limit)

    return result


def compute_fan_in(graph: dict) -> dict:
    """Compute reverse fan-in: for each node, how many other nodes import it.

    Returns {path: int}.
    """
    fan_in: dict[str, int] = {node: 0 for node in graph}
    for _src, targets in graph.items():
        for tgt in targets:
            if tgt in fan_in:
                fan_in[tgt] += 1
    return fan_in


# ----------------------------------------------------------------------
# What it does / why extractable
# ----------------------------------------------------------------------

def _extract_what_it_does(docstring: str, first_lines: str, path: str) -> str:
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
            if not cleaned or len(cleaned) <= 5:
                continue
            if re.match(r'^[~\-=]+$', cleaned):
                continue
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
        if any(stripped.startswith(p) for p in _code_prefixes):
            continue
        if stripped.startswith((chr(34)*3, chr(39)*3)):
            continue
        if re.match(r'^[a-z_]\w*\s*[:=]', stripped) and len(stripped) < 60 and not any(c in stripped for c in '.!?'):
            continue
        if re.match(r'^[a-z_]\w*\s*=\s*.+$', stripped) and len(stripped) > 15:
            continue
        alpha_ratio = sum(1 for c in stripped if c.isalpha()) / max(len(stripped), 1)
        if alpha_ratio < 0.5:
            continue
        if len(stripped) > 10:
            if len(stripped) > 200:
                return stripped[:197] + "..."
            return stripped
    return f"Module at {path}"


def _build_why_extractable(cand, fan_in: int = -1, in_cycle: bool = False) -> list:
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

    # NEW signals
    if fan_in == 0:
        reasons.append("Zero fan-in (orphan) -- nothing else in the repo depends on it, ideal extraction target")
    elif fan_in == 1:
        reasons.append(f"Low fan-in ({fan_in} importer) -- minimal blast radius if extracted")
    if in_cycle:
        reasons.append("⚠ Part of an import cycle -- extraction requires breaking the cycle first")
    if cand.complexity > 0 and cand.complexity <= 5:
        reasons.append(f"Low cyclomatic complexity (cc={cand.complexity}) -- simple control flow")
    elif cand.complexity > 15:
        reasons.append(f"⚠ High cyclomatic complexity (cc={cand.complexity}) -- consider refactoring before extracting")

    if not reasons:
        reasons.append("Passed extractable heuristics (size, import count, and filename analysis)")
    return reasons


# ----------------------------------------------------------------------
# Main entry: detect_candidates
# ----------------------------------------------------------------------

def detect_candidates(files: list, primary_language: str) -> list:
    file_set = {f["path"] for f in files}

    # Build top-level module index for Python internal-import detection.
    # Previously this used `file_set` (paths) which caused false-positive
    # substring matches. Now we use clean top-level module names.
    project_modules: set = set()
    for f in files:
        if f["ext"] != ".py":
            continue
        p = Path(f["path"])
        if len(p.parts) == 1:
            project_modules.add(p.stem)
        else:
            project_modules.add(p.parts[0])
            if p.name == "__init__.py":
                project_modules.add(p.parent.name)

    # Build import graph (Python only) for fan-in + cycle detection.
    import_graph = build_import_graph(files)
    fan_in = compute_fan_in(import_graph)
    cycles = find_cycles_scc(import_graph)
    cycle_nodes: set = set()
    for cycle in cycles:
        for node in cycle:
            cycle_nodes.add(node)

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
        internal, external = count_imports(f["content"], ext, project_modules)
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

        # NEW: cyclomatic complexity (Python only)
        complexity = 0
        if ext == ".py":
            complexity = cyclomatic_complexity_python(f["content"])

        # NEW: fan-in for this file
        file_fan_in = fan_in.get(path_str, -1)
        in_cycle = path_str in cycle_nodes

        first_lines = "\n".join(f["content"].splitlines()[:30])
        what_it_does = _extract_what_it_does(doc_snippet, first_lines, path_str)
        cand = Candidate(
            path=path_str, language=lang, loc=loc,
            has_tests=tested, has_docstring=has_doc,
            internal_imports=internal, external_imports=external,
            filename_score=fscore, docstring_snippet=doc_snippet,
            first_lines=first_lines, what_it_does=what_it_does,
            complexity=complexity,
            fan_in=file_fan_in,
            in_cycle=in_cycle,
        )
        cand.why_extractable = _build_why_extractable(cand, file_fan_in, in_cycle)
        candidates.append(cand)
    return candidates

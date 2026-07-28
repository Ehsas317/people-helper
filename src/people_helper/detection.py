"""Stage 3+4: Candidate detection with standalone analysis.

ARCHITECTURE: Language-specific logic lives in `languages/` modules.
Each language handler exposes: extract_relative_imports, extract_external_imports,
count_public_api, detect_docstring, count_imports, count_loc, get_complexity.

This file contains language-AGNOSTIC logic: candidate assembly, filename scoring,
framework detection, test detection, license detection, sibling resolution,
realism filtering, and the Python-only import graph (fan-in, cycles).
"""

import re
import sys
from pathlib import Path

from .config import (
    FRAMEWORK_DIRS,
    FRAMEWORK_ENTRY_NAMES,
    FRAMEWORK_SPECIAL_FILES,
    LANG_BY_EXT,
    PROJECT_SPECIFIC_PATTERNS,
    UTILITY_PATTERNS,
)
from .languages import get_handler
from .models import Candidate

# === Language-agnostic helpers ===


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
    for part in p.parts:
        if part.lower() in FRAMEWORK_DIRS:
            return True
    return p.name in FRAMEWORK_SPECIAL_FILES


def has_test_for(file_path: str, all_files: set) -> bool:
    """Check if a test file exists for the given source file."""
    p = Path(file_path)
    stem, ext = p.stem, p.suffix
    bare_names = [
        f"test_{stem}{ext}",
        f"{stem}_test{ext}",
        f"{stem}Test{ext}",
        f"{stem}.test{ext}",
        f"{stem}.spec{ext}",
    ]
    test_subdirs = ["tests", "test", "__tests__", "test_utils"]
    candidates = set()
    for d in test_subdirs:
        for name in bare_names:
            candidates.add(f"{d}/{name}")
        candidates.add(f"{d}/{stem}{ext}")
    parent = p.parent
    parent_str = str(parent)
    if parent_str != ".":
        for name in bare_names:
            candidates.add(f"{parent}/{name}")
        for d in test_subdirs:
            for name in bare_names:
                candidates.add(f"{parent}/{d}/{name}")
            candidates.add(f"{parent}/{d}/{stem}{ext}")
        for ancestor in parent.parents:
            if str(ancestor) == ".":
                break
            for d in test_subdirs:
                for name in bare_names:
                    candidates.add(f"{ancestor}/{d}/{name}")
    return any(c in all_files for c in candidates)


# === Extraction verification (language-agnostic sibling resolution) ===


def _resolve_sibling(sib_name: str, parent_level: int, file_path: str, ext: str, file_set: set) -> str | None:
    """Try to find the sibling file in the directory `parent_level` dirs up.

    `parent_level` semantics: the number of dots in the relative import.
      - parent_level=1 → `from .x import y` → sibling in same directory
      - parent_level=2 → `from ..x import y` → sibling in parent directory
      - parent_level=3 → `from ...x import y` → sibling in grandparent directory
    """
    p = Path(file_path)
    target_dir = p.parent
    for _ in range(max(parent_level - 1, 0)):
        target_dir = target_dir.parent
    # If parent_level pushes us above the repo root, the import is unsatisfiable
    if target_dir == Path(".") or str(target_dir) == "":
        # Walked all the way to (or past) the root — can't resolve
        if parent_level > len(p.parts):
            return None
    target_str = str(target_dir)
    # IMPORTANT: file paths in file_set use forward slashes (git convention).
    # On Windows, Path / operator produces backslashes, which won't match.
    # Always normalize candidate paths to forward slashes.
    def _p(*parts):
        """Join path parts and normalize to forward slashes."""
        return "/".join(str(p) for p in parts)
    candidates = []
    if ext == ".py":
        if target_str == ".":
            candidates = [f"{sib_name}.py", f"{sib_name}/__init__.py"]
        else:
            candidates = [_p(target_dir, f"{sib_name}.py"), _p(target_dir, sib_name, "__init__.py")]
    elif ext in {".ts", ".tsx", ".js", ".jsx"}:
        if target_str == ".":
            candidates = [
                f"{sib_name}.ts",
                f"{sib_name}.tsx",
                f"{sib_name}.js",
                f"{sib_name}.jsx",
                f"{sib_name}/index.ts",
                f"{sib_name}/index.tsx",
                f"{sib_name}/index.js",
                f"{sib_name}/index.jsx",
            ]
        else:
            candidates = [
                _p(target_dir, f"{sib_name}.ts"),
                _p(target_dir, f"{sib_name}.tsx"),
                _p(target_dir, f"{sib_name}.js"),
                _p(target_dir, f"{sib_name}.jsx"),
                _p(target_dir, sib_name, "index.ts"),
                _p(target_dir, sib_name, "index.tsx"),
                _p(target_dir, sib_name, "index.js"),
                _p(target_dir, sib_name, "index.jsx"),
            ]
    elif ext == ".rs":
        if target_str == ".":
            candidates = [f"{sib_name}.rs", f"{sib_name}/mod.rs"]
        else:
            candidates = [_p(target_dir, f"{sib_name}.rs"), _p(target_dir, sib_name, "mod.rs")]
    for c in candidates:
        if c in file_set:
            return c
    return None


# === License detection ===

_LICENSE_FILENAMES = {
    "license",
    "license.md",
    "license.txt",
    "license.rst",
    "license-mit",
    "license.mit",
    "license_apache",
    "license.apache",
    "license-apache",
    "license-2.0.txt",
    "license-2.0",
    "copying",
    "copying.txt",
    "copying.less",
    "copying.lesser",
    "unlicense",
    "unlicense.txt",
    "notice",
    "notice.md",
    "copyright",
    "copyright.txt",
    "authors",
    "contributors",
}
_LICENSE_PREFIXES = ("license", "copying", "unlicense", "copyright")


def detect_license_in_repo(files: list) -> bool:
    """Check if the repo root has a license file."""
    for f in files:
        path = f["path"]
        if "/" in path or "\\" in path:
            continue
        name_lower = path.lower()
        if name_lower in _LICENSE_FILENAMES:
            return True
        stem = name_lower
        for ext_to_strip in [".md", ".txt", ".rst", ".less", ".lesser"]:
            if stem.endswith(ext_to_strip):
                stem = stem[: -len(ext_to_strip)]
                break
        if stem in _LICENSE_PREFIXES:
            return True
        if name_lower.startswith("license-") or name_lower.startswith("license."):
            return True
    return False


# === Comment ratio ===


def _compute_comment_ratio(content: str, ext: str) -> float:
    """Compute ratio of comment lines to total lines.

    Uses the language handler's comment prefixes to avoid false positives
    (e.g. Python '*args' lines were being counted as block-comment continuations).
    """
    # _compute_comment_ratio uses the module-level get_handler import — no inline re-import needed.
    lines = content.splitlines()
    if not lines:
        return 0.0
    handler = get_handler(ext)
    comment_lines = 0
    in_block_comment = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Track block comment state
        if in_block_comment:
            if "*/" in s:
                in_block_comment = False
            comment_lines += 1
            continue
        if "/*" in s and "*/" not in s:
            in_block_comment = True
            comment_lines += 1
            continue
        # Use handler's comment prefixes (defaults to ("//",) for most langs, ("#") for Python/Ruby)
        prefixes = handler.comment_prefixes if handler else ("//", "#", "/*", "*", "//!", "///")
        # For Python/Ruby: # is comment, but * is NOT (could be *args)
        # For C-family: * alone is block-comment continuation
        if ext in {".c", ".h", ".cpp", ".hpp", ".java", ".kt", ".cs", ".js", ".jsx", ".ts", ".tsx", ".php", ".swift"}:
            if s.startswith("*") and not s.startswith("*/"):
                comment_lines += 1
                continue
        if any(s.startswith(p) for p in prefixes):
            comment_lines += 1
            continue
    return comment_lines / len(lines)


# === Python import graph (fan-in, cycles) — Python only, documented ===


def build_import_graph(files: list) -> dict:
    """Build Python-only import graph for fan-in/cycle detection."""
    module_to_paths: dict[str, set] = {}
    all_py: set[str] = set()
    for f in files:
        if f["ext"] != ".py":
            continue
        path, p = f["path"], Path(f["path"])
        all_py.add(path)
        module_to_paths.setdefault(p.stem, set()).add(path)
        if len(p.parts) > 1:
            module_to_paths.setdefault(p.parts[0], set()).add(path)
        if p.name == "__init__.py":
            module_to_paths.setdefault(p.parent.name, set()).add(path)
    graph = {}
    for f in files:
        if f["ext"] != ".py":
            continue
        src_path, src_dir = f["path"], Path(f["path"]).parent
        targets, seen = [], set()
        for line in f["content"].splitlines():
            m = re.match(r"^\s*from\s+\.(\w*)\s+import", line)
            if m and m.group(1):
                sibling = m.group(1)
                sf = f"{sibling}.py" if str(src_dir) == "." else str(src_dir / f"{sibling}.py")
                if sf in all_py and sf != src_path and sf not in seen:
                    targets.append(sf)
                    seen.add(sf)
                pi = f"{sibling}/__init__.py" if str(src_dir) == "." else str(src_dir / sibling / "__init__.py")
                if pi in all_py and pi != src_path and pi not in seen:
                    targets.append(pi)
                    seen.add(pi)
                continue
            m = re.match(r"^\s*from\s+([\w.]+)\s+import", line)
            if m:
                for tp in module_to_paths.get(m.group(1).split(".")[0], set()):
                    if tp != src_path and tp not in seen:
                        targets.append(tp)
                        seen.add(tp)
                continue
            m = re.match(r"^\s*import\s+([\w.]+)", line)
            if m:
                for tp in module_to_paths.get(m.group(1).split(".")[0], set()):
                    if tp != src_path and tp not in seen:
                        targets.append(tp)
                        seen.add(tp)
        graph[src_path] = targets
    return graph


def find_cycles_scc(graph: dict) -> list:
    """Tarjan's SCC algorithm for cycle detection."""
    idx_ctr, stack = [0], []
    lowlink, index, on_stack = {}, {}, {}
    result = []

    def strongconnect(v):
        index[v] = lowlink[v] = idx_ctr[0]
        idx_ctr[0] += 1
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
            if len(scc) >= 2:
                result.append(scc)

    old = sys.getrecursionlimit()
    if len(graph) > 500:
        sys.setrecursionlimit(max(old, len(graph) * 2 + 100))
    try:
        for v in list(graph.keys()):
            if v not in index:
                strongconnect(v)
    finally:
        sys.setrecursionlimit(old)
    return result


def compute_fan_in(graph: dict) -> dict:
    fi = {n: 0 for n in graph}
    for _, targets in graph.items():
        for t in targets:
            if t in fi:
                fi[t] += 1
    return fi


# === Project-specific reference detection ===


def _has_project_specific_refs(content: str) -> bool:
    for pattern in PROJECT_SPECIFIC_PATTERNS:
        if re.search(pattern, content):
            return True
    return False


# === Realism filter ===


def _extract_what_it_does(docstring: str, path: str) -> str:
    if docstring:
        for line in docstring.splitlines():
            cleaned = re.sub(r"^[\s*/#'\"]+\s*", "", line).strip()
            cleaned = cleaned.rstrip("'\"").strip()
            if not cleaned or len(cleaned) <= 5:
                continue
            if re.match(r"^[~\-=]+$", cleaned) or cleaned.startswith("@"):
                continue
            return cleaned[:200]
    return f"Source file at {path}"


def _find_skip_reason(content: str, ext: str, path: str, loc: int):
    """Find a reason to skip this file as not-a-real-candidate. Returns str|None.

    Renamed from _realism_check (which misleadingly implied a bool return).
    """
    lines = content.splitlines()
    total_lines = len(lines)
    name = Path(path).name
    if name == "mod.rs" and loc <= 30:
        mod_lines = sum(1 for l in lines if l.strip().startswith(("pub mod ", "pub(crate) mod ")))
        if mod_lines >= loc * 0.5:
            return "Rust mod.rs with only module declarations"
    if name == "lib.rs" and loc <= 30:
        pub_lines = sum(1 for l in lines if l.strip().startswith(("pub mod ", "pub use ")))
        if pub_lines >= loc * 0.5:
            return "Rust lib.rs with only re-exports"
    if loc < 20:
        # Check for function/class definitions, handling visibility modifiers
        # (public, private, protected, final, abstract, static, open, sealed, etc.)
        # so that 'public class Foo' and 'public static void main' are detected.
        has_fn = bool(
            re.search(
                r"^\s*((public|private|protected|static|final|abstract|open|sealed|suspend|inline|"
                r"override|async|synchronized|internal|fileprivate|companion)*\s*"
                r"(def |func |fn |function |void |int |string |bool |var |let |const |"
                r"public |private |protected ))",
                content,
                re.MULTILINE,
            )
        )
        has_cls = bool(
            re.search(
                r"^\s*((public|private|protected|static|final|abstract|open|sealed|internal|"
                r"fileprivate|data|companion)*\s*"
                r"(class |struct |interface |enum |trait |impl |object |protocol |record ))",
                content,
                re.MULTILINE,
            )
        )
        if not has_fn and not has_cls:
            return "Under 20 LOC with no function/class definitions"
    if ext == ".py" and loc <= 50:
        assign_lines = sum(1 for l in lines if re.match(r"^\s*[A-Z_][A-Z_0-9]*\s*=", l))
        if assign_lines >= loc * 0.6:
            return "Mostly constant definitions"
    if path.endswith(".d.ts"):
        return "TypeScript declaration file (.d.ts)"
    if "automatically generated by SWIG" in content[:500]:
        return "SWIG auto-generated file"
    # Copyright/license check: only skip if the file is TRULY dominated by
    # license text with almost no real code. Compare against TOTAL lines
    # (not code-only loc) and require loc <= 30 (very small file).
    # This avoids false positives on Spring Boot-style files that have
    # a 17-line Apache 2.0 header followed by real Java code.
    actual_copyright_lines = sum(
        1
        for l in lines[:30]
        if "copyright" in l.lower()
        or "licensed under" in l.lower()
        or "apache license" in l.lower()
        or "mit license" in l.lower()
        or "permission is hereby granted" in l.lower()
    )
    # Only skip if: file is small (<=30 code lines), copyright text dominates
    # (>= 60% of TOTAL lines), and there's very little code (loc <= 15)
    if actual_copyright_lines >= total_lines * 0.6 and loc <= 15 and total_lines <= 40:
        return "Mostly copyright/license comments"
    if name in {"conf.py", "settings.py", "config.py", "settings_prod.py", "settings_dev.py"}:
        return "Configuration file"
    if ext == ".py":
        string_vars = list(re.finditer(r"^\s*([A-Z][A-Z_]+)\s*=\s*(r?)(\"\"\"|''')", content, re.MULTILINE))
        if string_vars:
            total = 0
            for match in string_vars:
                closing = match.group(3)
                end = content.find(closing, match.end())
                if end > 0:
                    total += content[match.start() : end + 3].count("\n")
            if total >= loc * 0.5 and loc > 10:
                return "Documentation-only file (string variables dominate)"
    return None


# === Why-extractable reason builder ===


def _build_why_extractable(cand, fan_in: int, in_cycle: bool) -> list:
    reasons = []
    if cand.has_tests:
        reasons.append("Has corresponding test file")
    if cand.has_docstring:
        reasons.append("Has module-level documentation")
    if cand.internal_imports == 0:
        reasons.append("Zero internal project imports — fully self-contained")
    elif cand.internal_imports == 1:
        reasons.append("Only 1 internal import — loosely coupled")
    if cand.external_imports <= 3:
        reasons.append(f"Small dependency footprint ({cand.external_imports} external import(s))")
    if cand.loc < 50:
        reasons.append(f"Very small ({cand.loc} LOC)")
    elif cand.loc < 150:
        reasons.append(f"Manageable size ({cand.loc} LOC)")
    if cand.filename_score > 0:
        reasons.append("Filename suggests a reusable utility")
    if fan_in == 0:
        reasons.append("Zero fan-in (orphan) — nothing else depends on it")
    elif fan_in == 1:
        reasons.append(f"Low fan-in ({fan_in} importer)")
    if in_cycle:
        reasons.append("⚠ Part of an import cycle — extraction requires breaking the cycle first")
    if 0 < cand.complexity <= 5:
        reasons.append(f"Low cyclomatic complexity (cc={cand.complexity})")
    elif cand.complexity > 15:
        reasons.append(f"⚠ High cyclomatic complexity (cc={cand.complexity})")
    if cand.is_stdlib_only:
        reasons.append("Stdlib-only — zero external dependencies, truly standalone")
    elif cand.dependency_weight >= 3:
        reasons.append(f"⚠ Heavy dependencies (weight={cand.dependency_weight})")
    if cand.api_surface_count >= 3:
        reasons.append(f"Rich API surface ({cand.api_surface_count} public functions/classes)")
    elif cand.api_surface_count == 1:
        reasons.append("⚠ Only 1 public function — snippet, not a full library")
    if cand.has_project_specific_refs:
        reasons.append("⚠ References framework internals")
    if cand.comment_ratio >= 0.15:
        reasons.append(f"Well-commented ({cand.comment_ratio:.0%} comment lines)")
    for name in cand.function_names:
        if name and any(
            p in name.lower()
            for p in [
                "slugify",
                "validate",
                "parse",
                "format",
                "encode",
                "decode",
                "hash",
                "cache",
                "sort",
                "filter",
                "search",
                "compress",
                "encrypt",
            ]
        ):
            reasons.append(f"Solves a common problem (function: {name})")
            break
    if cand.extraction_type == "single" and not cand.relative_imports:
        reasons.append("✓ Verified standalone — no relative imports, extractable as-is")
    elif cand.extraction_type == "multi":
        sibs = ", ".join(Path(s).name for s in cand.sibling_paths)
        reasons.append(f"⚠ Multi-file extraction — also needs: {sibs}")
    if not cand.source_has_license:
        reasons.append("⚠ Source repo has NO license file — extraction is legally risky")
    if not reasons:
        reasons.append("Passed extractable heuristics")
    return reasons


# === Main candidate detection ===


def detect_candidates(files: list, primary_language: str):
    """Detect extractable candidates from files.

    Returns a tuple (candidates, errored_count) where errored_count is the
    number of files that crashed during detection (silent before this fix).
    """
    file_set = {f["path"] for f in files}
    project_modules = set()
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
    import_graph = build_import_graph(files)
    fan_in = compute_fan_in(import_graph)
    cycles = find_cycles_scc(import_graph)
    cycle_nodes = {n for cycle in cycles for n in cycle}
    repo_has_license = detect_license_in_repo(files)

    candidates = []
    errored_count = 0
    for f in files:
        try:
            ext, lang = f["ext"], LANG_BY_EXT.get(f["ext"])
            if not lang:
                continue
            handler = get_handler(ext)
            if handler is None:
                continue

            path_str = f["path"]
            path_parts_lower = [p.lower() for p in Path(path_str).parts]
            if any(
                p in {"tests", "test", "__tests__", "test_utils", "testfixtures", "fixtures"} for p in path_parts_lower
            ):
                continue
            stem = Path(path_str).stem.lower()
            if any(x in stem for x in ["test_", "_test", ".test", ".spec", "conftest"]):
                continue
            if Path(path_str).name in {"__init__.py", "conftest.py"}:
                continue

            content = f["content"]
            loc = handler.count_loc(content)
            # Minimum sanity check: <10 LOC is a snippet, not a library — skip.
            # NO hard upper limit — large files get a graduated scoring penalty
            # in _compute_maintainability (-0.1 per 150 LOC over 500) instead of
            # being silently dropped. This lets users find extractable code in
            # larger files if they're willing to accept the maintainability hit.
            if loc < 10:
                continue
            if is_framework_route(path_str):
                continue

            skip_reason = _find_skip_reason(content, ext, path_str, loc)
            if skip_reason:
                candidates.append(
                    Candidate(
                        path=path_str,
                        language=lang,
                        loc=loc,
                        has_tests=False,
                        has_docstring=False,
                        internal_imports=0,
                        external_imports=0,
                        filename_score=0.0,
                        skipped=True,
                        skip_reason=skip_reason,
                        source_has_license=repo_has_license,
                    )
                )
                continue

            has_doc, doc_snippet = handler.detect_docstring(content)
            internal, external = handler.count_imports(content, project_modules)
            fscore = compute_filename_score(path_str)
            tested = has_test_for(path_str, file_set)

            if internal >= 2:
                candidates.append(
                    Candidate(
                        path=path_str,
                        language=lang,
                        loc=loc,
                        has_tests=tested,
                        has_docstring=has_doc,
                        internal_imports=internal,
                        external_imports=external,
                        filename_score=fscore,
                        skipped=True,
                        skip_reason=f"{internal} internal imports — tightly coupled",
                        source_has_license=repo_has_license,
                    )
                )
                continue
            if fscore < -0.5:
                candidates.append(
                    Candidate(
                        path=path_str,
                        language=lang,
                        loc=loc,
                        has_tests=tested,
                        has_docstring=has_doc,
                        internal_imports=internal,
                        external_imports=external,
                        filename_score=fscore,
                        skipped=True,
                        skip_reason="Filename is a framework entry point",
                        source_has_license=repo_has_license,
                    )
                )
                continue

            # === EXTRACTION VERIFICATION ===
            relative_imports = handler.extract_relative_imports(content)
            sibling_paths = []
            missing_siblings = []
            for sib_name, parent_level in relative_imports:
                resolved = _resolve_sibling(sib_name, parent_level, path_str, ext, file_set)
                if resolved:
                    sibling_paths.append(resolved)
                else:
                    missing_siblings.append(sib_name)

            if missing_siblings:
                candidates.append(
                    Candidate(
                        path=path_str,
                        language=lang,
                        loc=loc,
                        has_tests=tested,
                        has_docstring=has_doc,
                        internal_imports=internal,
                        external_imports=external,
                        filename_score=fscore,
                        skipped=True,
                        skip_reason=f"References missing sibling(s): {', '.join(missing_siblings)}",
                        relative_imports=[n for n, _ in relative_imports],
                        missing_siblings=missing_siblings,
                        extraction_type="blocked",
                        source_has_license=repo_has_license,
                    )
                )
                continue

            extraction_type = "multi" if sibling_paths else "single"

            # === Compute signals via handler ===
            complexity = handler.get_complexity(content)
            file_fan_in = fan_in.get(path_str, -1)
            in_cycle = path_str in cycle_nodes
            ext_imports = handler.extract_external_imports(content)
            dep_weight, is_stdlib = handler.get_dependency_weight(ext_imports)
            api_count, func_names = handler.count_public_api(content)
            has_proj_refs = _has_project_specific_refs(content)
            comment_ratio = _compute_comment_ratio(content, ext)

            first_lines = "\n".join(content.splitlines()[:30])
            what_it_does = _extract_what_it_does(doc_snippet, path_str)

            cand = Candidate(
                path=path_str,
                language=lang,
                loc=loc,
                has_tests=tested,
                has_docstring=has_doc,
                internal_imports=internal,
                external_imports=external,
                filename_score=fscore,
                docstring_snippet=doc_snippet,
                first_lines=first_lines,
                what_it_does=what_it_does,
                complexity=complexity,
                fan_in=file_fan_in,
                in_cycle=in_cycle,
                dependency_weight=dep_weight,
                api_surface_count=api_count,
                is_stdlib_only=is_stdlib,
                has_project_specific_refs=has_proj_refs,
                function_names=func_names,
                comment_ratio=comment_ratio,
                relative_imports=[n for n, _ in relative_imports],
                sibling_paths=sibling_paths,
                extraction_type=extraction_type,
                source_has_license=repo_has_license,
            )
            cand.why_extractable = _build_why_extractable(cand, file_fan_in, in_cycle)
            candidates.append(cand)
        except Exception:
            # Skip files that cause unexpected errors. Track count so caller
            # can surface it (was previously silent — users had no idea files crashed).
            errored_count += 1
            continue
    return candidates, errored_count

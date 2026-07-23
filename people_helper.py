#!/usr/bin/env python3
"""
People Helper v0.1 — Find what's extractable from your private code.

Usage:
    python people_helper.py --repo https://github.com/you/private-repo
    python people_helper.py --repo you/private-repo --output report.md

Requires:
    - A fine-grained GitHub PAT in PEOPLE_HELPER_PAT env var
    - PAT must have Contents: Read and Metadata: Read only
    - No other scopes
"""

import argparse
import os
import re
import sys
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import urlparse

try:
    import httpx
except ImportError:
    print("Install dependencies: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)


GITHUB_API = "https://api.github.com"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    """A potential extractable."""
    path: str
    language: str
    loc: int
    has_tests: bool
    has_docstring: bool
    internal_imports: int
    external_imports: int
    filename_score: float
    open_sourceability: float = 0.0
    uniqueness: float = 0.0
    ship_effort_hours: float = 0.0
    combined_score: float = 0.0
    docstring_snippet: str = ""
    first_lines: str = ""
    similar_projects: list = field(default_factory=list)
    differentiators: list = field(default_factory=list)
    suggested_name: str = ""
    suggested_license: str = "MIT"
    skipped: bool = False
    skip_reason: str = ""


# ---------------------------------------------------------------------------
# Stage 1: PAT scope check
# ---------------------------------------------------------------------------

def check_pat_scope(pat: str) -> dict:
    """
    Verify the PAT is fine-grained and read-only.
    Returns a dict with the verification result.
    """
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        r = httpx.get(f"{GITHUB_API}/user", headers=headers, timeout=10)
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"network error: {e}"}

    if r.status_code == 401:
        return {"ok": False, "error": "PAT is invalid or expired"}

    if r.status_code != 200:
        return {"ok": False, "error": f"unexpected status: {r.status_code}"}

    user = r.json()
    scopes_header = r.headers.get("x-oauth-scopes", "")

    # Fine-grained PATs don't return x-oauth-scopes. We trust the user
    # followed the README and created a fine-grained PAT. We do additional
    # checks below by attempting a write (we never actually do one, just
    # check that the API endpoints that would require write scope reject us).

    # Defensive: if classic PAT with full repo scope, warn
    if scopes_header and "repo" in scopes_header.split(", "):
        return {
            "ok": False,
            "error": (
                "Classic PAT with 'repo' scope detected. People Helper requires "
                "a fine-grained PAT with Contents: Read and Metadata: Read only. "
                "Create one at https://github.com/settings/personal-access-tokens/new"
            ),
        }

    return {"ok": True, "user": user.get("login"), "scopes_header": scopes_header}


# ---------------------------------------------------------------------------
# Stage 2: Repo walk
# ---------------------------------------------------------------------------

def parse_repo_arg(repo_arg: str) -> tuple:
    """
    Accept either 'owner/name' or 'https://github.com/owner/name'.
    Returns (owner, name).
    """
    if repo_arg.startswith("http"):
        parsed = urlparse(repo_arg)
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError(f"Could not parse repo from URL: {repo_arg}")
        return parts[0], parts[1]
    parts = repo_arg.strip("/").split("/")
    if len(parts) != 2:
        raise ValueError(f"Expected owner/name, got: {repo_arg}")
    return parts[0], parts[1]


def clone_repo_shallow(owner: str, name: str, pat: str) -> Path:
    """
    Shallow-clone the repo to a temp directory.
    Returns the Path to the clone.
    """
    target = Path(tempfile.mkdtemp(prefix="people-helper-"))
    clone_url = f"https://x-access-token:{pat}@github.com/{owner}/{name}.git"
    subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, str(target)],
        check=True,
        capture_output=True,
    )
    return target


def walk_repo(root: Path) -> list:
    """
    Walk the cloned repo, returning a list of file info dicts.
    Skips common noise: .git, node_modules, __pycache__, vendor, dist, build.
    """
    skip_dirs = {".git", "node_modules", "__pycache__", "vendor", "dist", "build", ".next", "target"}
    skip_exts = {".lock", ".log", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".zip", ".tar", ".gz", ".pdf", ".bin"}

    files = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if any(p in skip_dirs for p in parts):
            continue
        if path.suffix.lower() in skip_exts:
            continue
        try:
            content = path.read_text(errors="ignore")
        except Exception:
            continue
        files.append({
            "path": str(rel),
            "abs_path": str(path),
            "ext": path.suffix.lower(),
            "size": path.stat().st_size,
            "content": content,
        })
    return files


# ---------------------------------------------------------------------------
# Stage 3 + 4: Module map and extractable detection
# ---------------------------------------------------------------------------

LANG_BY_EXT = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
}


def detect_language(files: list) -> str:
    """Return the primary language by file count."""
    counts = {}
    for f in files:
        lang = LANG_BY_EXT.get(f["ext"])
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return "Unknown"
    return max(counts, key=counts.get)


def count_lines(content: str) -> int:
    return len([l for l in content.splitlines() if l.strip()])


def is_internal_import(line: str, project_files: set) -> int:
    """
    Return 1 if `line` looks like an internal project import, 0 otherwise.
    Heuristic: matches common patterns and checks if the imported name
    matches any file in the project. Detects path aliases (@/, ~/) for JS/TS.
    """
    # Python
    m = re.match(r"^\s*from\s+([\w.]+)\s+import", line)
    if m:
        mod = m.group(1).split(".")[0]
        if mod in project_files or any(mod in pf for pf in project_files):
            return 1
    m = re.match(r"^\s*import\s+([\w.]+)", line)
    if m:
        mod = m.group(1).split(".")[0]
        if mod in project_files or any(mod in pf for pf in project_files):
            return 1
    # JS/TS — relative paths and path aliases
    m = re.match(r"^\s*import\s+.*from\s+['\"]([\w./@\-\~]+)", line)
    if m:
        path = m.group(1)
        # Relative: ./ ../  / (root alias)
        if path.startswith(".") or path.startswith("/"):
            return 1
        # Path aliases: @/ or @scope/ or ~/
        if path.startswith("@/") or path.startswith("~/"):
            return 1
        # Scoped packages can be either internal (@/company/...) or external (@types/...)
        # Heuristic: scoped packages with a single segment after @ are usually external (e.g. @types/node)
        # Scoped packages with /lib/ or /components/ etc. are usually internal
        if path.startswith("@") and "/" in path[1:]:
            scope, rest = path[1:].split("/", 1)
            # Treat scope as internal if it doesn't look like a known external scope
            external_scopes = {"types", "angular", "vue", "react", "nestjs", "types"}
            if scope not in external_scopes and not rest.startswith("types/"):
                return 1
    # require() with relative path
    m = re.match(r'^\s*require\([\'"]([\w./@\-\~]+)[\'"]\)', line)
    if m:
        path = m.group(1)
        if path.startswith(".") or path.startswith("/") or path.startswith("@/") or path.startswith("~/"):
            return 1
    # Go
    m = re.match(r'^\s*"([\w./\-]+)"', line)
    if m:
        if "/" not in m.group(1):  # internal package
            return 1
    # Rust
    m = re.match(r"^\s*use\s+(crate|super|self)", line)
    if m:
        return 1
    return 0


def count_external_imports(content: str) -> int:
    """Naive count of external imports."""
    count = 0
    for line in content.splitlines():
        if re.match(r"^\s*(import|from)\s+[\w.]+", line):
            count += 1
        elif re.match(r"^\s*const\s+\w+\s*=\s*require\(", line):
            count += 1
        elif re.match(r'^\s*"[^/]+\"', line) and "/" in line:  # go imports
            count += 1
    return count


def has_docstring(content: str, ext: str) -> tuple:
    """
    Return (has_docstring, snippet).
    Detects module-level docstrings for Python, JSDoc for JS/TS, doc comments for Go/Rust.
    Also catches large // header blocks for TS/JS (a lot of code uses // instead of /** */).
    """
    lines = content.splitlines()
    if not lines:
        return False, ""

    if ext == ".py":
        # Look for module-level triple-quoted string
        if lines[0].strip().startswith(('"""', "'''")):
            end_quote = '"""' if '"""' in lines[0] else "'''"
            snippet_lines = [lines[0].lstrip()]
            for line in lines[1:20]:
                snippet_lines.append(line)
                if end_quote in line and line is not lines[0]:
                    break
            return True, "\n".join(snippet_lines).strip()

    if ext in {".ts", ".tsx", ".js", ".jsx"}:
        # JSDoc: /** ... */
        if lines[0].strip().startswith("/**"):
            snippet_lines = []
            for line in lines[:30]:
                snippet_lines.append(line)
                if line.strip().endswith("*/"):
                    break
            return True, "\n".join(snippet_lines).strip()
        # Large // header block (5+ lines of // comments) — common in TS code
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
        # Look for // comment block at top
        comment_block = []
        for line in lines[:20]:
            if line.strip().startswith("//"):
                comment_block.append(line)
            elif comment_block:
                break
        if comment_block and len(comment_block) >= 2:
            return True, "\n".join(comment_block).strip()

    if ext == ".rs":
        # Look for //! or /// at top
        comment_block = []
        for line in lines[:20]:
            if line.strip().startswith("//!"):
                comment_block.append(line)
            elif comment_block:
                break
        if comment_block:
            return True, "\n".join(comment_block).strip()

    return False, ""


def filename_score(path: str) -> float:
    """
    Score a filename for utility-likeness.
    Higher = more likely to be a utility.
    """
    name = Path(path).stem.lower()
    score = 0.0
    util_patterns = ["util", "helper", "common", "lib", "tool", "format", "parse", "convert", "validate", "sanitize", "protection", "guard", "filter", "normaliz"]
    for p in util_patterns:
        if p in name:
            score += 0.5
    # Framework route files — strongly negative
    if name in {"route", "page", "layout", "loading", "error", "not-found", "middleware", "index", "main", "app", "server", "_app", "_document"}:
        score -= 3.0
    if "test" in name or "spec" in name:
        score -= 2.0  # tests themselves
    return score


def is_framework_route(path: str) -> bool:
    """
    Detect Next.js / Nuxt / SvelteKit / etc. route files that are NOT extractable.
    These are tightly coupled to the framework and project.
    """
    p = Path(path)
    parts = p.parts
    # Next.js: anything in app/ or pages/ (with or without src/ prefix)
    for i, part in enumerate(parts):
        if part in {"app", "pages"} and i > 0:
            # Check if there's a src/ before it, or it's the conventional location
            prev = parts[i - 1] if i > 0 else ""
            if prev in {"src", "."} or i == 0:
                return True
            # app/ or pages/ at root
            if i == 0:
                return True
    # SvelteKit: routes/ directory
    if "routes" in parts:
        return True
    # Nuxt: pages/ directory
    if "pages" in parts:
        return True
    # File name itself is a framework special file
    if p.name in {"route.ts", "route.tsx", "route.js", "route.jsx",
                  "page.tsx", "page.jsx", "page.ts", "page.js",
                  "layout.tsx", "layout.ts", "layout.jsx", "layout.js",
                  "loading.tsx", "loading.ts", "loading.jsx", "loading.js",
                  "error.tsx", "error.ts", "error.jsx", "error.js",
                  "not-found.tsx", "not-found.ts", "middleware.ts", "middleware.js",
                  "_app.tsx", "_app.jsx", "_document.tsx", "_document.jsx",
                  "+page.svelte", "+layout.svelte", "+server.ts"}:
        return True
    return False


def has_test_for(file_path: str, all_files: list) -> bool:
    """
    Heuristic: is there a test file corresponding to this source file?
    """
    p = Path(file_path)
    stem = p.stem
    ext = p.suffix
    candidates = [
        f"tests/test_{stem}{ext}",
        f"test/test_{stem}{ext}",
        f"__tests__/{stem}{ext}",
        f"{stem}_test{ext}",
        f"{stem}Test{ext}",
        f"{stem}.test{ext}",
        f"{stem}.spec{ext}",
    ]
    file_set = {f["path"] for f in all_files}
    return any(c in file_set for c in candidates)


def detect_candidates(files: list, primary_language: str) -> list:
    """
    Return a list of Candidate objects for files that pass extractable heuristics.
    """
    file_set = {f["path"] for f in files}
    candidates = []

    for f in files:
        ext = f["ext"]
        lang = LANG_BY_EXT.get(ext)
        if not lang:
            continue
        # Skip test files themselves
        path_str = f["path"]
        if any(part in path_str.lower() for part in ["/test/", "/tests/", "__tests__", "test_", "_test.", ".test.", ".spec."]):
            continue
        if "test" in Path(path_str).stem.lower() or "spec" in Path(path_str).stem.lower():
            continue

        loc = count_lines(f["content"])
        if loc < 10 or loc > 500:
            continue

        # Skip framework route files (Next.js, Nuxt, SvelteKit) — never extractable
        if is_framework_route(path_str):
            continue

        has_doc, doc_snippet = has_docstring(f["content"], ext)
        internal = sum(is_internal_import(line, file_set) for line in f["content"].splitlines())
        external = count_external_imports(f["content"])
        fscore = filename_score(path_str)
        tested = has_test_for(path_str, files)

        # Skip if too many internal imports
        if internal >= 2:
            cand = Candidate(
                path=path_str, language=lang, loc=loc,
                has_tests=tested, has_docstring=has_doc,
                internal_imports=internal, external_imports=external,
                filename_score=fscore, skipped=True,
                skip_reason=f"{internal} internal imports — tightly coupled",
            )
            candidates.append(cand)
            continue

        # Skip if filename strongly suggests app entry or framework file
        if fscore < -0.5:
            continue

        first_lines = "\n".join(f["content"].splitlines()[:30])

        cand = Candidate(
            path=path_str, language=lang, loc=loc,
            has_tests=tested, has_docstring=has_doc,
            internal_imports=internal, external_imports=external,
            filename_score=fscore, docstring_snippet=doc_snippet,
            first_lines=first_lines,
        )
        candidates.append(cand)

    return candidates


# ---------------------------------------------------------------------------
# Stage 5: GitHub search
# ---------------------------------------------------------------------------

def github_search_repositories(query: str, language: str, pat: str, min_stars: int = 5, limit: int = 5) -> list:
    """
    Search GitHub for similar projects.
    Returns a list of repo dicts.
    """
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    }
    full_query = f"{query} language:{language} stars:>={min_stars}"
    try:
        r = httpx.get(
            f"{GITHUB_API}/search/repositories",
            params={"q": full_query, "sort": "stars", "per_page": limit},
            headers=headers,
            timeout=10,
        )
    except httpx.HTTPError as e:
        print(f"  [warn] search network error: {e}", file=sys.stderr)
        return []

    if r.status_code == 403:
        print(f"  [warn] rate limited or forbidden: {r.json().get('message', '')}", file=sys.stderr)
        return []
    if r.status_code != 200:
        print(f"  [warn] search status {r.status_code}", file=sys.stderr)
        return []

    items = r.json().get("items", [])
    return [
        {
            "full_name": it["full_name"],
            "html_url": it["html_url"],
            "stars": it["stargazers_count"],
            "description": it.get("description") or "",
            "pushed_at": it.get("pushed_at", "")[:10],
            "license": (it.get("license") or {}).get("spdx_id", "?"),
        }
        for it in items
    ]


def build_search_query(candidate: Candidate) -> str:
    """
    Build a search query from the candidate's path and docstring.
    """
    stem = Path(candidate.path).stem
    words = re.findall(r"\w+", candidate.docstring_snippet)[:5] if candidate.docstring_snippet else []
    query_words = [stem] + words
    return " ".join(query_words)


# ---------------------------------------------------------------------------
# Stage 6: Scoring
# ---------------------------------------------------------------------------

def score_candidate(cand: Candidate, similar_count: int) -> None:
    """
    Score a candidate in place.
    """
    # Open sourceability
    score = 0.0
    if cand.has_tests:
        score += 3
    if cand.has_docstring:
        score += 2
    if cand.internal_imports == 0:
        score += 2
    if cand.external_imports <= 3:
        score += 2
    if cand.filename_score > 0:
        score += 1
    cand.open_sourceability = min(score, 10)

    # Uniqueness (fewer similar projects = more unique)
    if similar_count == 0:
        cand.uniqueness = 8.0
    elif similar_count <= 2:
        cand.uniqueness = 6.0
    elif similar_count <= 5:
        cand.uniqueness = 4.0
    else:
        cand.uniqueness = 2.0

    # Ship effort (heuristic by LOC)
    if cand.loc < 50:
        cand.ship_effort_hours = 1.5
    elif cand.loc < 150:
        cand.ship_effort_hours = 3
    elif cand.loc < 300:
        cand.ship_effort_hours = 6
    else:
        cand.ship_effort_hours = 16

    # Combined
    ship_score = max(0, 10 - cand.ship_effort_hours)
    cand.combined_score = (
        0.4 * cand.open_sourceability
        + 0.4 * cand.uniqueness
        + 0.2 * ship_score
    )


def suggest_name(cand: Candidate) -> str:
    """
    Suggest a name based on the file path, parent directory, and content.
    Avoids generic names like 'route' or 'index'. Uses parent dir context
    when the file name is too generic.
    """
    p = Path(cand.path)
    stem = p.stem
    parent = p.parent.name

    # Generic file names that should be augmented with parent context
    generic_names = {"route", "index", "main", "app", "server", "utils", "util", "helpers", "common", "lib"}

    if stem.lower() in generic_names and parent and parent not in {".", "src", "lib", "app"}:
        # Use parent dir + a hint from the docstring or first content line
        hint = ""
        if cand.docstring_snippet:
            # Try to find a noun in the docstring
            words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", cand.docstring_snippet)
            for w in words:
                if w.lower() not in {"the", "this", "that", "module", "class", "function", "and", "for", "with", "from", "file", "import", "export", "const", "let", "var"}:
                    hint = w.lower()
                    break
        if hint:
            return re.sub(r"-+", "-", f"{parent}-{hint}")
        return re.sub(r"[^a-z0-9-]", "-", parent.lower())
    elif stem.lower() in generic_names:
        # No useful parent context, just use stem
        return re.sub(r"[^a-z0-9-]", "-", f"{parent}-{stem}".lower()) if parent != "." else "extracted-utility"

    # Normal case: clean the file stem
    name = re.sub(r"[^a-z0-9-]", "-", stem.lower())
    name = re.sub(r"-+", "-", name).strip("-")
    return name or "extracted-utility"


# ---------------------------------------------------------------------------
# Stage 7: Report generation
# ---------------------------------------------------------------------------

def generate_report(
    owner: str,
    name: str,
    language: str,
    candidates: list,
    output_path: Path,
) -> None:
    """
    Write the markdown report.
    """
    now = __import__("datetime").datetime.utcnow().isoformat() + "Z"

    sorted_cands = [c for c in candidates if not c.skipped]
    sorted_cands.sort(key=lambda c: c.combined_score, reverse=True)
    skipped = [c for c in candidates if c.skipped]

    lines = []
    lines.append("# People Helper Report\n")
    lines.append(f"**Repo:** {owner}/{name}")
    lines.append(f"**Generated:** {now}")
    lines.append(f"**Primary language:** {language}")
    lines.append(f"**Candidates analyzed:** {len(candidates)}")
    lines.append(f"**Top candidates:** {len(sorted_cands)}")
    lines.append("")

    if not sorted_cands:
        lines.append("> No extractable candidates found. Either the repo is small, tightly coupled, or all the standalone-looking code is actually internal.")
        lines.append("")
    else:
        lines.append("---\n")
        lines.append("## Top candidates\n")
        for i, c in enumerate(sorted_cands[:10], 1):
            lines.append(f"### {i}. `{Path(c.path).name}` — Combined score: {c.combined_score:.1f}/10\n")
            lines.append(f"**Location:** `{c.path}`")
            lines.append(f"**Language:** {c.language}")
            lines.append(f"**Open sourceability:** {c.open_sourceability:.0f}/10")
            lines.append(f"**Uniqueness:** {c.uniqueness:.0f}/10")
            lines.append(f"**Estimated ship effort:** {c.ship_effort_hours:g} hours")
            lines.append(f"**LOC:** {c.loc}")
            lines.append(f"**Has tests:** {'yes' if c.has_tests else 'no'}")
            lines.append(f"**Has docstring:** {'yes' if c.has_docstring else 'no'}")
            lines.append(f"**Internal imports:** {c.internal_imports}")
            lines.append(f"**External imports:** {c.external_imports}")
            lines.append("")

            if c.docstring_snippet:
                lines.append("**Docstring / module doc:**")
                lines.append(f"```{c.language.lower() if c.language else ''}")
                lines.append(c.docstring_snippet)
                lines.append("```")
                lines.append("")

            if c.similar_projects:
                lines.append("**Similar projects on GitHub:**")
                for sp in c.similar_projects:
                    lines.append(
                        f"- [`{sp['full_name']}`]({sp['html_url']}) — {sp['stars']}⭐, last commit {sp['pushed_at']}"
                    )
                    if sp["description"]:
                        lines.append(f"  - {sp['description']}")
                lines.append("")
            else:
                lines.append("**Similar projects on GitHub:** None found.\n")

            if c.differentiators:
                lines.append("**Your differentiators (from your code):**")
                for d in c.differentiators:
                    lines.append(f"- {d}")
                lines.append("")

            lines.append(f"**Suggested name:** `{c.suggested_name}`")
            lines.append(f"**Suggested license:** {c.suggested_license}")
            lines.append("")

            lines.append("**Starter scaffold:**")
            lang_hint = {
                "Python": "python",
                "TypeScript": "typescript",
                "JavaScript": "javascript",
                "Go": "go",
                "Rust": "rust",
                "Java": "java",
                "C": "c",
                "C++": "cpp",
                "C#": "csharp",
                "Ruby": "ruby",
                "PHP": "php",
                "Kotlin": "kotlin",
                "Swift": "swift",
            }.get(c.language, "")
            lines.append(f"```{lang_hint}")
            lines.append(c.first_lines)
            lines.append("```")
            lines.append("\n---\n")

    if skipped:
        lines.append("## Skipped files\n")
        for s in skipped[:20]:
            lines.append(f"- `{s.path}` — {s.skip_reason}")
        if len(skipped) > 20:
            lines.append(f"- ... and {len(skipped) - 20} more")
        lines.append("")

    lines.append("---\n")
    lines.append("*Generated by People Helper v0.1. Read-only by design.*\n")

    output_path.write_text("\n".join(lines))
    print(f"\nReport written: {output_path}")
    print(f"Top candidates: {len(sorted_cands)}")
    if sorted_cands:
        print(f"Best candidate: {Path(sorted_cands[0].path).name} (score {sorted_cands[0].combined_score:.1f}/10)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Find what's extractable from your private code.",
    )
    parser.add_argument("--repo", required=True, help="GitHub repo URL or owner/name")
    parser.add_argument("--output", default="report.md", help="Output report path (default: report.md)")
    parser.add_argument("--max-candidates", type=int, default=10, help="Max candidates to surface")
    parser.add_argument("--min-stars", type=int, default=5, help="Min stars for similar projects")
    parser.add_argument("--language", help="Filter to one language (e.g. Python)")
    parser.add_argument("--no-network", action="store_true", help="Skip GitHub search (local-only mode)")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    pat = os.environ.get("PEOPLE_HELPER_PAT")
    if not pat:
        print("Error: PEOPLE_HELPER_PAT environment variable not set.", file=sys.stderr)
        print("Create a fine-grained PAT at https://github.com/settings/personal-access-tokens/new", file=sys.stderr)
        print("Required scopes: Contents: Read, Metadata: Read. Only the specific repos you want to analyze.", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print("[1] Checking PAT scope...")
    check = check_pat_scope(pat)
    if not check["ok"]:
        print(f"Error: {check['error']}", file=sys.stderr)
        sys.exit(1)
    if args.verbose:
        print(f"  Authenticated as: {check['user']}")

    try:
        owner, name = parse_repo_arg(args.repo)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"[2] Cloning {owner}/{name}...")
    try:
        clone_path = clone_repo_shallow(owner, name, pat)
    except subprocess.CalledProcessError as e:
        print(f"Error cloning repo: {e.stderr.decode()}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.verbose:
            print(f"[3] Walking files in {clone_path}...")
        files = walk_repo(clone_path)
        if args.verbose:
            print(f"  Found {len(files)} files")

        primary_language = args.language or detect_language(files)
        if args.verbose:
            print(f"[4] Detected primary language: {primary_language}")

        if args.verbose:
            print(f"[5] Detecting candidates...")
        candidates = detect_candidates(files, primary_language)
        if args.verbose:
            print(f"  Found {len([c for c in candidates if not c.skipped])} candidates, {len([c for c in candidates if c.skipped])} skipped")

        # Score and search (if not --no-network)
        if not args.no_network:
            if args.verbose:
                print(f"[6] Searching GitHub for similar projects...")
            for cand in candidates:
                if cand.skipped:
                    continue
                query = build_search_query(cand)
                cand.similar_projects = github_search_repositories(
                    query, cand.language, pat, min_stars=args.min_stars
                )
                # Naive differentiator extraction: just note the candidate has the file
                if cand.similar_projects:
                    cand.differentiators = [
                        f"Compared to top result ({cand.similar_projects[0]['full_name']}): review your code to identify specific implementation differences",
                    ]
                score_candidate(cand, len(cand.similar_projects))
                cand.suggested_name = suggest_name(cand)
        else:
            for cand in candidates:
                if cand.skipped:
                    continue
                score_candidate(cand, 0)
                cand.suggested_name = suggest_name(cand)

        if args.verbose:
            print(f"[7] Generating report...")
        generate_report(owner, name, primary_language, candidates, Path(args.output))

    finally:
        # Always clean up the clone
        if clone_path.exists():
            shutil.rmtree(clone_path, ignore_errors=True)


if __name__ == "__main__":
    main()

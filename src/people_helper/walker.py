"""Stage 2: Repository cloning and file walking."""

import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from .config import LANG_BY_EXT, SKIP_DIRS, SKIP_EXTS


def parse_repo_arg(repo_arg: str) -> tuple:
    """
    Accept 'owner/name', 'https://github.com/owner/name', or 'git@github.com:owner/name.git'.
    Returns (owner, name).
    """
    cleaned = repo_arg.strip()

    # SSH format: git@github.com:owner/name.git
    if cleaned.startswith("git@"):
        # Extract owner/name from git@...:owner/name.git
        parts = cleaned.split(":")[-1].replace(".git", "").strip("/").split("/")
        if len(parts) < 2:
            raise ValueError(f"Could not parse repo from SSH URL: {repo_arg}")
        return parts[0], parts[1]

    # HTTPS format
    if cleaned.startswith("http"):
        parsed = urlparse(cleaned)
        path = parsed.path.strip("/").removesuffix(".git")
        parts = path.split("/")
        if len(parts) < 2:
            raise ValueError(f"Could not parse repo from URL: {repo_arg}")
        return parts[0], parts[1]

    # owner/name format (strip optional .git suffix)
    cleaned = cleaned.removesuffix(".git")
    parts = cleaned.split("/")
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
    result = subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Authentication failed" in stderr or "Permission denied" in stderr:
            raise subprocess.CalledProcessError(
                result.returncode, result.args,
                stderr="Authentication failed. Ensure your PAT has access to this repo."
            )
        if "not found" in stderr.lower() or "does not exist" in stderr.lower():
            raise subprocess.CalledProcessError(
                result.returncode, result.args,
                stderr=f"Repository {owner}/{name} not found or PAT doesn't have access."
            )
        raise subprocess.CalledProcessError(result.returncode, result.args, stderr=stderr)
    return target


def walk_repo(root: Path) -> list:
    """
    Walk the cloned repo, returning a list of file info dicts.
    Skips common noise directories and binary/media file extensions.
    """
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        parts = rel.parts

        # Skip noise directories
        if any(p.lower() in SKIP_DIRS for p in parts):
            continue

        # Skip binary/media extensions
        if path.suffix.lower() in SKIP_EXTS:
            continue

        # Skip hidden files (except .env.example which has docs value)
        if path.name.startswith(".") and not path.name.endswith(".example"):
            continue

        # Try to read as text
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


def detect_primary_language(files: list) -> str:
    """Return the primary language by file count."""
    counts = {}
    for f in files:
        lang = LANG_BY_EXT.get(f["ext"])
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return "Unknown"
    return max(counts, key=counts.get)

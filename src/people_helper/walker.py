"""Repository cloning and file walking."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from .config import LANG_BY_EXT, SKIP_DIRS, SKIP_EXTS


def parse_repo_arg(repo_arg: str) -> tuple:
    """Parse a GitHub repo argument. Accepts:
      - owner/name (e.g. "alice/repo")
      - HTTPS URL (e.g. "https://github.com/alice/repo")
      - SSH URL (e.g. "git@github.com:alice/repo.git")

    Returns (owner, name). Raises ValueError on invalid input.
    """
    cleaned = repo_arg.strip()
    if not cleaned:
        raise ValueError(f"Empty repo argument. Expected owner/name, got: {repo_arg!r}")
    if cleaned.startswith("git@"):
        if "github.com" not in cleaned:
            raise ValueError(f"Only GitHub repos are supported. Got: {repo_arg}")
        parts = cleaned.split(":")[-1].replace(".git", "").strip("/").split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Could not parse repo from SSH URL: {repo_arg}")
        return parts[0], parts[1]
    if cleaned.startswith("http"):
        parsed = urlparse(cleaned)
        if parsed.netloc not in ("github.com", "www.github.com"):
            raise ValueError(f"Only GitHub repos are supported. Got: {parsed.netloc}")
        path = parsed.path.strip("/").removesuffix(".git")
        parts = path.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Could not parse repo from URL: {repo_arg}")
        return parts[0], parts[1]
    cleaned = cleaned.removesuffix(".git")
    parts = cleaned.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Expected owner/name, got: {repo_arg}")
    return parts[0], parts[1]


def clone_repo_shallow(owner: str, name: str, pat: str) -> Path:
    """Shallow-clone a repo. Cleans up the temp dir on failure to avoid leaks.

    NOTE: The PAT is embedded in the clone URL. This exposes it in
    /proc/{pid}/cmdline to same-user processes during the clone. On a
    single-user dev machine this is acceptable. For multi-tenant environments,
    use a git credential helper instead.
    """
    target = Path(tempfile.mkdtemp(prefix="people-helper-"))
    try:
        clone_url = f"https://x-access-token:{pat}@github.com/{owner}/{name}.git"
        # SECURITY: Disable git filters to prevent .gitattributes RCE.
        # Use os.devnull for cross-platform portability (Windows uses 'nul', POSIX uses '/dev/null').
        # Also disable the user filtersfile to block any smudge/clean filters defined in user gitconfig.
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "-c",
                "core.attributesfile=" + (os.devnull if os.name == "nt" else "/dev/null"),
                "-c",
                "core.filtersfile=" + (os.devnull if os.name == "nt" else "/dev/null"),
                clone_url,
                str(target),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # Redact PAT from any error output (it shouldn't appear, but be safe)
            if pat in stderr:
                stderr = stderr.replace(pat, "***")
            if "Authentication failed" in stderr or "Permission denied" in stderr:
                raise subprocess.CalledProcessError(
                    result.returncode,
                    result.args,
                    stderr="Authentication failed. Ensure your PAT has access to this repo.",
                )
            if "not found" in stderr.lower() or "does not exist" in stderr.lower():
                raise subprocess.CalledProcessError(
                    result.returncode, result.args, stderr=f"Repository {owner}/{name} not found."
                )
            raise subprocess.CalledProcessError(result.returncode, result.args, stderr=stderr)
        # SECURITY: Scrub PAT from .git/config post-clone so it doesn't persist on disk.
        # The clone URL with embedded PAT is stored in .git/config — replace with clean URL.
        try:
            subprocess.run(
                ["git", "-C", str(target), "remote", "set-url", "origin", f"https://github.com/{owner}/{name}.git"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            pass  # Best-effort; not critical if it fails
        return target
    except subprocess.TimeoutExpired as te:
        shutil.rmtree(target, ignore_errors=True)
        raise subprocess.CalledProcessError(-1, [], stderr=f"git clone timed out after 300s for {owner}/{name}") from te
    except Exception:
        # Clean up temp dir on any failure to prevent leaks
        shutil.rmtree(target, ignore_errors=True)
        raise


def walk_repo(root: Path) -> list:
    """Walk repo and return list of file dicts. Skips symlinks, hidden files,
    and paths that resolve outside the repo root (defense against symlink attacks)."""
    files = []
    root_resolved = root.resolve()
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        # SECURITY: Skip symlinks entirely (could point outside repo)
        if path.is_symlink():
            continue
        rel = path.relative_to(root)
        if any(p.lower() in SKIP_DIRS for p in rel.parts):
            continue
        if path.suffix.lower() in SKIP_EXTS:
            continue
        if path.name.startswith(".") and not path.name.endswith(".example"):
            continue
        # SECURITY: Verify resolved path stays inside repo root
        try:
            if not path.resolve().relative_to(root_resolved):
                continue
        except (ValueError, OSError):
            continue
        try:
            content = path.read_text(errors="ignore")
            size = path.stat().st_size
        except (OSError, UnicodeError):
            continue
        # Strip BOM if present (Windows-created files often have one — R6-A finding)
        if content.startswith("\ufeff"):
            content = content[1:]
        loc = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        files.append(
            {
                "path": str(rel),
                "abs_path": str(path),
                "ext": path.suffix.lower(),
                "size": size,
                "content": content,
                "loc": loc,
            }
        )
    return files


def detect_primary_language(files: list) -> str:
    loc_by_lang: dict[str, int] = {}
    for f in files:
        lang = LANG_BY_EXT.get(f["ext"])
        if lang:
            loc_by_lang[lang] = loc_by_lang.get(lang, 0) + f.get("loc", 0)
    if not loc_by_lang:
        return "Unknown"
    return max(loc_by_lang, key=loc_by_lang.get)

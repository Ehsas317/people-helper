"""Repository cloning and file walking."""
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from .config import SKIP_DIRS, SKIP_EXTS, LANG_BY_EXT

def parse_repo_arg(repo_arg: str) -> tuple:
    cleaned = repo_arg.strip()
    if cleaned.startswith("git@"):
        if "github.com" not in cleaned:
            raise ValueError(f"Only GitHub repos are supported. Got: {repo_arg}")
        parts = cleaned.split(":")[-1].replace(".git", "").strip("/").split("/")
        if len(parts) < 2: raise ValueError(f"Could not parse repo from SSH URL: {repo_arg}")
        return parts[0], parts[1]
    if cleaned.startswith("http"):
        parsed = urlparse(cleaned)
        if parsed.netloc not in ("github.com", "www.github.com"):
            raise ValueError(f"Only GitHub repos are supported. Got: {parsed.netloc}")
        path = parsed.path.strip("/").removesuffix(".git")
        parts = path.split("/")
        if len(parts) < 2: raise ValueError(f"Could not parse repo from URL: {repo_arg}")
        return parts[0], parts[1]
    cleaned = cleaned.removesuffix(".git")
    parts = cleaned.split("/")
    if len(parts) != 2: raise ValueError(f"Expected owner/name, got: {repo_arg}")
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
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(target)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # Redact PAT from any error output (it shouldn't appear, but be safe)
            if pat in stderr:
                stderr = stderr.replace(pat, "***")
            if "Authentication failed" in stderr or "Permission denied" in stderr:
                raise subprocess.CalledProcessError(result.returncode, result.args, stderr="Authentication failed. Ensure your PAT has access to this repo.")
            if "not found" in stderr.lower() or "does not exist" in stderr.lower():
                raise subprocess.CalledProcessError(result.returncode, result.args, stderr=f"Repository {owner}/{name} not found.")
            raise subprocess.CalledProcessError(result.returncode, result.args, stderr=stderr)
        return target
    except Exception:
        # Clean up temp dir on any failure to prevent leaks
        shutil.rmtree(target, ignore_errors=True)
        raise

def walk_repo(root: Path) -> list:
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_dir(): continue
        rel = path.relative_to(root)
        if any(p.lower() in SKIP_DIRS for p in rel.parts): continue
        if path.suffix.lower() in SKIP_EXTS: continue
        if path.name.startswith(".") and not path.name.endswith(".example"): continue
        try:
            content = path.read_text(errors="ignore")
        except Exception: continue
        loc = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        files.append({"path": str(rel), "abs_path": str(path), "ext": path.suffix.lower(),
                      "size": path.stat().st_size, "content": content, "loc": loc})
    return files

def detect_primary_language(files: list) -> str:
    loc_by_lang = {}
    for f in files:
        lang = LANG_BY_EXT.get(f["ext"])
        if lang: loc_by_lang[lang] = loc_by_lang.get(lang, 0) + f.get("loc", 0)
    if not loc_by_lang: return "Unknown"
    return max(loc_by_lang, key=loc_by_lang.get)

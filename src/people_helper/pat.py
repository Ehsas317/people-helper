"""PAT scope verification — hard-rejects write-capable PATs."""
import httpx
from .config import GITHUB_API

WRITE_SCOPES = {
    "repo", "repo:status", "repo_deployment", "public_repo", "delete_repo",
    "admin:org", "admin:repo_hook", "admin:org_hook", "admin:public_key",
    "admin:gpg_key", "admin:ssh_signing_key", "write:packages", "write:org",
    "write:public_key", "write:gpg_key", "write:repo_hook", "write:org_hook",
    "write:discussion", "write:network_config", "delete:packages",
}

def _has_write_scope(scopes_header: str) -> tuple:
    if not scopes_header: return False, []
    scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]
    offending = [s for s in scopes if s in WRITE_SCOPES or s.startswith(("admin:", "write:", "delete:"))]
    return bool(offending), offending

def check_pat_scope(pat: str) -> dict:
    headers = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    try:
        r = httpx.get(f"{GITHUB_API}/user", headers=headers, timeout=10)
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"network error: {e}"}
    if r.status_code == 401: return {"ok": False, "error": "PAT is invalid or expired"}
    if r.status_code == 403: return {"ok": False, "error": "PAT does not have permission to access user info."}
    if r.status_code != 200: return {"ok": False, "error": f"unexpected status: {r.status_code}"}
    scopes_header = r.headers.get("x-oauth-scopes", "")
    has_write, offending = _has_write_scope(scopes_header)
    if has_write:
        return {"ok": False, "error": f"PAT has write-capable scope(s): {', '.join(offending)}. People Helper is read-only by design. Create a fine-grained PAT with Contents: Read + Metadata: Read only at https://github.com/settings/personal-access-tokens/new"}
    return {"ok": True, "user": r.json().get("login"), "scopes_header": scopes_header, "is_classic": bool(scopes_header)}

"""PAT scope verification — hard-rejects write-capable PATs.

Returns a dict with consistent shape:
    {"ok": bool, "user": str|None, "error": str|None, "warning": str|None,
     "scopes_header": str, "is_classic": bool}

Note: GitHub's API does not expose fine-grained PAT scopes to the client
(the x-oauth-scopes header is empty for fine-grained PATs). So we can only
HARD-verify classic PAT scopes. For fine-grained PATs we return a soft warning
that the user must verify manually.
"""

import httpx

from .config import GITHUB_API

# Classic PAT scopes that grant write access — hard-rejected.
WRITE_SCOPES = {
    "repo",
    "repo:status",
    "repo_deployment",
    "public_repo",
    "delete_repo",
    "admin:org",
    "admin:repo_hook",
    "admin:org_hook",
    "admin:public_key",
    "admin:gpg_key",
    "admin:ssh_signing_key",
    "write:packages",
    "write:org",
    "write:public_key",
    "write:gpg_key",
    "write:repo_hook",
    "write:org_hook",
    "write:discussion",
    "write:network_config",
    "delete:packages",
}

# Fine-grained PAT warning (returned when scopes can't be verified).
_FINE_GRAINED_WARNING = (
    "Fine-grained PAT detected — GitHub's API does not expose fine-grained PAT "
    "scopes to the client, so write-scope verification is not possible. Verify "
    "manually at https://github.com/settings/personal-access-tokens that your "
    "PAT has only Contents: Read + Metadata: Read."
)


def _has_write_scope(scopes_header: str) -> tuple:
    """Return (has_write: bool, offending_scopes: list)."""
    if not scopes_header:
        return False, []
    scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]
    offending = [s for s in scopes if s in WRITE_SCOPES or s.startswith(("admin:", "write:", "delete:"))]
    return bool(offending), offending


def check_pat_scope(pat: str) -> dict:
    """Verify PAT scope. Returns a dict with consistent keys:
    ok, user, error, warning, scopes_header, is_classic
    """
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        r = httpx.get(f"{GITHUB_API}/user", headers=headers, timeout=10)
    except httpx.HTTPError as e:
        return {
            "ok": False,
            "user": None,
            "error": f"network error: {e}",
            "warning": None,
            "scopes_header": "",
            "is_classic": False,
        }
    if r.status_code == 401:
        return {
            "ok": False,
            "user": None,
            "error": "PAT is invalid or expired",
            "warning": None,
            "scopes_header": "",
            "is_classic": False,
        }
    if r.status_code == 403:
        return {
            "ok": False,
            "user": None,
            "error": "PAT does not have permission to access user info.",
            "warning": None,
            "scopes_header": "",
            "is_classic": False,
        }
    if r.status_code != 200:
        return {
            "ok": False,
            "user": None,
            "error": f"unexpected status: {r.status_code}",
            "warning": None,
            "scopes_header": "",
            "is_classic": False,
        }
    scopes_header = r.headers.get("x-oauth-scopes", "")
    is_classic = bool(scopes_header)
    has_write, offending = _has_write_scope(scopes_header)
    if has_write:
        return {
            "ok": False,
            "user": None,
            "error": (
                f"PAT has write-capable scope(s): {', '.join(offending)}. "
                f"People Helper is read-only by design. Create a fine-grained PAT "
                f"with Contents: Read + Metadata: Read only at "
                f"https://github.com/settings/personal-access-tokens/new"
            ),
            "warning": None,
            "scopes_header": scopes_header,
            "is_classic": True,
        }
    # Success. For fine-grained PATs (empty scopes_header), add a soft warning
    # that we can't verify scopes — user must check manually.
    warning = _FINE_GRAINED_WARNING if not is_classic else None
    return {
        "ok": True,
        "user": r.json().get("login"),
        "error": None,
        "warning": warning,
        "scopes_header": scopes_header,
        "is_classic": is_classic,
    }

"""Stage 1: PAT scope verification."""

import httpx
from .config import GITHUB_API


def check_pat_scope(pat: str) -> dict:
    """
    Verify the PAT is fine-grained and read-only.

    Checks:
    1. PAT is valid (authenticates)
    2. Not a classic PAT with 'repo' scope
    3. User info returned

    Fine-grained PATs don't expose scopes in headers, so we trust
    the user followed setup instructions and verify the token works.
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

    if r.status_code == 403:
        return {"ok": False, "error": "PAT does not have permission to access user info. Check your fine-grained PAT scopes."}

    if r.status_code != 200:
        return {"ok": False, "error": f"unexpected status: {r.status_code}"}

    user = r.json()
    scopes_header = r.headers.get("x-oauth-scopes", "")

    # Fine-grained PATs don't return x-oauth-scopes.
    # If classic PAT with full repo scope is detected, reject it.
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

"""Stage 1: PAT scope verification.

v0.3 change: classic PATs are now allowed with a warning instead of
rejected outright. The original v0.2 logic was overly strict — many
users (including the maintainer) use a classic PAT for personal use
and the strict rejection made the tool unusable for them.

The check still:
  1. Validates the PAT works (authenticates against /user).
  2. Detects whether it's classic (with `repo` scope) vs fine-grained.
  3. Returns the warning string for classic PATs so the CLI can print it.
"""

import httpx

from .config import GITHUB_API


def check_pat_scope(pat: str) -> dict:
    """
    Verify the PAT is valid. Returns:
      {ok: True, user: str, scopes_header: str, is_classic: bool, warning: str | None}
    or
      {ok: False, error: str}

    Fine-grained PATs are preferred but classic PATs are allowed
    with a warning. The tool only ever does read operations, but
    classic PATs with `repo` scope technically grant write access —
    so we surface that to the user.
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
        return {
            "ok": False,
            "error": "PAT does not have permission to access user info. Check your PAT scopes.",
        }

    if r.status_code != 200:
        return {"ok": False, "error": f"unexpected status: {r.status_code}"}

    user = r.json()
    scopes_header = r.headers.get("x-oauth-scopes", "")
    is_classic = bool(scopes_header)
    has_repo_scope = is_classic and "repo" in scopes_header.split(", ")

    warning = None
    if has_repo_scope:
        warning = (
            "Classic PAT with 'repo' scope detected. People Helper only does "
            "read operations, but for safety we recommend a fine-grained PAT "
            "with Contents: Read + Metadata: Read only. "
            "Create one at https://github.com/settings/personal-access-tokens/new"
        )

    return {
        "ok": True,
        "user": user.get("login"),
        "scopes_header": scopes_header,
        "is_classic": is_classic,
        "warning": warning,
    }

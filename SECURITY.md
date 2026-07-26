# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in People Helper, please report it
responsibly:

1. **DO NOT open a public GitHub issue.**
2. Email the maintainer at: `security@example.com` (replace with real address)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)
4. You will receive an acknowledgment within 48 hours.
5. We will coordinate a fix and disclosure timeline with you.

## Security Model

People Helper is **read-only by design**:

- **PAT scope**: Hard-rejects classic PATs with write-capable scopes (`repo`, `admin:*`, `write:*`, `delete:*`). Fine-grained PAT scopes cannot be introspected via the API — users must verify manually.
- **No write operations**: No git push, no PR creation, no issue creation, no file modification of the source repo.
- **Network calls**: Only to `api.github.com` (PAT scope check + search) and `github.com` (git clone). No third-party endpoints.
- **Temp clone**: Created with `tempfile.mkdtemp` (random name, mode 0700). Cleaned up in `finally` block on all failure paths (including timeouts and Ctrl+C).
- **PAT redaction**: Scrubbed from `subprocess.CalledProcessError` args/stderr before raising. Scrubbed from `.git/config` post-clone. Defense-in-depth redaction in top-level exception handler.
- **Symlink protection**: `walk_repo` skips symlinks entirely AND verifies `path.resolve().relative_to(root.resolve())` stays inside the repo.
- **Git filter RCE mitigation**: `git clone` is invoked with `-c core.attributesfile=/dev/null -c core.filtersfile=/dev/null` to disable user-defined filters that could execute arbitrary code.
- **Subprocess safety**: All `subprocess.run` calls use list args (no `shell=True`). 300-second timeout on git clone.
- **Markdown injection**: User-controlled content (docstrings, code excerpts, descriptions) is sanitized before embedding in the report — triple backticks escaped, `<script>` stripped, `javascript:` URLs neutralized. Outer code fences use 4 backticks.
- **Secret redaction**: Common secrets (GitHub PATs, AWS keys, Slack tokens, OpenAI keys, JWTs, PEM private keys) are auto-redacted from "Starter scaffold" code previews in the report.
- **Path traversal**: `extract_candidate` sanitizes package names and verifies `pkg_dir.resolve().relative_to(output_dir.resolve())`.

## Known Limitations

- **Fine-grained PAT scopes** cannot be verified via the API. The tool warns but does not enforce.
- **PAT in `/proc/cmdline`** during git clone: visible to same-user processes on POSIX. Documented in `walker.py` docstring. For multi-tenant environments, use a git credential helper.
- **No TLS pinning**: Like most Python tools, we rely on the system CA bundle.

## Disclosure Timeline

- Day 0: Vulnerability reported.
- Day 1: Acknowledgment sent.
- Day 7: Initial assessment + fix timeline communicated.
- Day 30: Fix released (or sooner for critical issues).
- Day 45: Public disclosure (coordinated with reporter).

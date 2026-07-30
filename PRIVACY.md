# Privacy Policy

People Helper is designed to minimize data leaving your machine. This document
describes what data is sent where, so you can make an informed decision.

## What leaves your machine

### Always (even with `--no-network`)

- **Your PAT** (Personal Access Token):
  - Sent to `api.github.com/user` (HTTPS, Authorization header) for scope verification.
  - Sent to `github.com` (HTTPS, embedded in clone URL) for `git clone`.
  - **NOT** sent anywhere else. **NOT** written to disk (except briefly in `.git/config` of the temp clone, which is scrubbed post-clone and cleaned up on exit).
- **The repo URL** (`owner/name`):
  - Sent to `github.com` for `git clone`.

### Only when NOT using `--no-network`

For each candidate's GitHub search query, the following derived data is sent to
`api.github.com/search/repositories`:

- **The file's stem** (filename without extension, e.g. `slugify` from `slugify.py`).
  - Note: if the filename is project-specific (e.g. `acme_merger_target_utils.py`), this leaks competitively-sensitive information to GitHub.
- **Up to 2 function names** from the file (lowercased, ≥4 chars, non-noise).
- **Up to 2 docstring words** (if no function names found).
- **Up to 2 import module names** (if no function names or docstring words found).
- The candidate's language (e.g. `language:Python`).
- Filter constraints (`stars:>=5`, `pushed:>=YYYY-MM-DD`).

A privacy notice is printed to stderr before search runs (with a 3-second
cancel window in interactive mode).

## What stays on your machine

- **The full source code** of your repo (cloned to a temp dir, walked, analyzed locally).
- **The generated report** (`report.md` by default) — contains repo name, file paths, code excerpts, scores.
- **Extracted packages** (if `--extract` is used) — contains source code copies.

## What is NOT collected

- **No telemetry / analytics**: No posthog, amplitude, mixpanel, sentry, bugsnag, datadog, statsig, segment, or any other analytics SDK. Verified by grep.
- **No crash reporting**: No SDK that phones home on crash. Stack traces are only printed if you pass `--debug`.
- **No automatic updates**: The tool does not check for updates or phone home for version info.

## GDPR considerations (EU users)

If you are processing personal data subject to GDPR:

- The search-API data flow (function names, docstring words, import names, file stem) constitutes processing of derived data. GitHub (a US-based third party) receives this data.
- Ensure your GitHub Data Processing Agreement covers this search-API data flow before running with `--no-network` disabled on repos containing personal data.
- Use `--no-network` to keep all derived data on your machine.
- Cross-border transfer (Art. 44 GDPR): data is transferred to GitHub (US). Ensure your legal basis covers this.

## Data retention

- **Temp clone**: Deleted at end of every run (in `finally` block). Not retained.
- **Report**: Persists on your local disk until you delete it. May contain code excerpts — treat as you would the source code itself.
- **Extracted packages**: Persist on your local disk until you delete them. Contain full source code copies.

## Contact

For privacy questions, open a GitHub issue (do NOT include personal data in the issue).

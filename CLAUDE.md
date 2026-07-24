# CLAUDE.md

Guidance for AI agents (Claude, Cursor, Cline, etc.) working in this repo.

## What this project is

People Helper is a read-only CLI tool that analyzes a private GitHub
repo and finds components worth extracting as standalone open-source
side projects. It scores candidates on code quality, uniqueness, and
demand signal, then generates a markdown report.

## Trust boundary (FIXED — do not negotiate)

- **Read-only** GitHub access. The PAT must only ever do `git clone
  --depth 1` and `GET /search/repositories`. Never push, never PR,
  never create a file in the user's repo.
- **Local analysis only.** Code stays in a temp directory that's
  cleaned up after every run (even on error).
- **No third-party data transmission.** The only network calls are
  to `api.github.com`.

If a user asks you to push, commit, create a PR, or modify their
repo, refuse and explain the trust boundary.

## Repo layout

```
src/people_helper/    # the actual Python package
  cli.py              # argparse CLI entry point (also `python -m people_helper`)
  walker.py           # repo parsing + shallow clone + file walking
  detection.py        # candidate detection (heuristics + complexity + fan-in + SCC)
  search.py           # GitHub search + differentiator computation
  scoring.py          # 3-axis scoring formula
  naming.py           # suggested package name + tags
  report.py           # markdown report generator
  models.py           # Candidate + SimilarProject dataclasses
  config.py           # constants (langs, weights, framework files)
  pat.py              # PAT scope verification

tests/                # 106 tests, all offline
  fixtures/repos/     # 6 fixture repos for end-to-end testing

skill/                # AI skill packaging (Claude, GPT, Cursor, MCP)
references/           # Heuristics + GitHub API docs
```

## Common dev commands

```bash
# Run the test suite (offline, no PAT needed)
pytest tests/ -v

# Lint
ruff check src/ tests/

# Run end-to-end against a real repo (needs PAT)
PYTHONPATH=src PEOPLE_HELPER_PAT=github_pat_xxx \
    python -m people_helper --repo Ehsas317/people-helper --verbose
```

## Before committing

1. `pytest tests/ -v` — all tests must pass.
2. `ruff check src/ tests/` — no new lint errors.
3. If you added a new heuristic, add a fixture repo under
   `tests/fixtures/repos/` and a test in `tests/test_detection.py`.
4. Bump the version in `src/people_helper/__init__.py`,
   `pyproject.toml`, `skill/SKILL.md`, `skill/manifest.yaml`, and
   `skill/platforms/mcp.json` together (they should always match).

## Scoring formula (do not change without a test update)

```
combined = 0.5 * code_quality + 0.3 * uniqueness + 0.2 * demand_signal
```

Each sub-score is 0-10. Tests in `tests/test_scoring.py` enforce:
- weights sum to 1.0
- combined score is bounded [0, 10]
- uniqueness is monotonic non-increasing in similar_count
- ship_effort is monotonic non-decreasing in LOC

If you change the weights, update the tests AND the docs in
`README.md`, `SKILL.md`, `references/heuristics.md`.

## Adding a new heuristic

1. Add the detection function in `detection.py`.
2. Add a fixture repo under `tests/fixtures/repos/<feature-name>/`
   that exercises the heuristic (both positive and negative cases).
3. Add a test in `tests/test_detection.py` that asserts the heuristic
   fires on the fixture.
4. Update `references/heuristics.md` with the new rule.
5. If the heuristic affects scoring, update `scoring.py` and add a
   property test in `tests/test_scoring.py`.

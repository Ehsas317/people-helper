# Changelog

All notable changes to People Helper are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **LOC scoring: removed hard 500-LOC cutoff.** Files >500 LOC are no longer silently skipped. Instead, they get a graduated maintainability penalty: -0.1 per 150 LOC over 500 (e.g. 650 LOC → -0.1, 800 → -0.2, 950 → -0.3, 2000 → -1.0). Large but genuinely standalone files can now be detected, just with a lower score. The minimum sanity check (<10 LOC) remains.
- **Naming heuristic smarter for generic stems.** `models.py` in `people_helper_data/` no longer suggests `people-helper-data-models` or `people-helper-data-data` — the parent directory name is used directly when the generic stem would produce a redundant suffix. Function/class names from the source file are now preferred over docstring words when both are available.
- **Report now includes an "At a glance" summary block** showing extraction type counts (single/multi/blocked), total LOC across candidates, average cyclomatic complexity, stdlib-only ratio, and license-absence warnings.

### Added
- **More secret patterns auto-redacted in report previews.** Now also catches: GitHub user/server/refresh tokens (`ghu_`, `ghs_`, `ghr_`), Anthropic API keys (`sk-ant-`), Google API keys (`AIza...`), Stripe live keys (`sk_live_`/`pk_live_`), SendGrid keys, Twilio SIDs, and long high-entropy hex strings.
- **`test_extracted/` and `extracted/` added to walker `SKIP_DIRS`** — the walker no longer scans its own test outputs (was previously scoring `test_extracted/*.py` files as real candidates when present in the repo).

### Fixed
- **Rust `///` outer doc comments now detected** (was previously only detecting `//!` inner docs). Rust libraries primarily use `///` to document functions/structs, so most Rust docstrings were silently missed.
- **Python 3-level deep relative imports** (`from ...X import Y`) now resolve correctly. Previously only 1- and 2-level imports were handled; deeper imports would return `None` instead of finding the sibling file.
- **TypeScript `count_public_api` now detects `interface`, `type`, `enum`, `namespace`, and `default` exports.** Previously only `function`, `class`, and `const` were matched — meaning TypeScript files full of `interface IFoo {}` exports were reported as having zero public API.
- **C# `global using` and `using alias` now detected.** C# 10+'s `global using MyApp.Models;` was silently dropped by the import regex (which expected `using` at line start). C# 12's `using Alias = MyApp.X;` alias form was also missed.
- **Removed stale `test_extracted/` directory from the repo** (leftover from a prior manual run) and added it to `.gitignore` so it doesn't reappear.


### Fixed
- **Multi-file Python extraction bug**: siblings now moved into the package subdir alongside the main file (was previously leaving siblings at the package root, breaking relative imports like `from .compat import X`).
- **Missing `__init__.py`**: Python extractions now create a proper `__init__.py` in the package subdir (was previously only creating the directory, relying on namespace packages).
- **Off-by-one in LOC penalty formula**: graduated penalty now uses ceiling division to correctly match the documented behavior (650 LOC → -0.1, not -0.2).
- Markdown injection in report.py — user content is now sanitized (triple backticks escaped, `<script>` stripped, `javascript:` URLs neutralized) and outer code fences use 4 backticks so triple-backtick content can't break out.
- Secret redaction in report — common secrets (GitHub PATs, AWS keys, Slack tokens, OpenAI keys, JWTs, PEM private keys) are auto-redacted from "Starter scaffold" code previews before being written to report.md.
- Temp clone dir leak on `subprocess.CalledProcessError` — now cleaned up on ALL failure paths (was previously leaked on the most-common git-clone failure mode).
- Partial extraction dir leak — `extract_candidate` now `rmtree`s the partial package dir on any mid-extraction failure (was previously left behind with source-but-no-manifest).
- `--check` flag silently broken — `cand._check_results` was set but never read by report.py. The flag is now removed entirely (it never produced output); a future `--check` feature will be added when properly wired up.
- `_skipped_count` silently discarded — `detect_candidates` now returns `(candidates, errored_count)` and the CLI prints a warning when files crash during detection (was previously completely invisible).
- Rate-limit false-positive "truly unique" — `github_search_repositories` now returns a `RATE_LIMITED` sentinel on HTTP 403/422, which the CLI detects and passes `similar_count=-1` to `score_candidate`, yielding a neutral 5.0 uniqueness (was previously a misleading 8.0 "truly unique").
- `compute_differentiators` crash on malformed `pushed_at` — both date-parse sites now use a safe `_safe_months_since` helper that returns `None` on parse failure (was previously crashing on GitHub API returning `"not a date"`).
- `_realism_check` misnomer — renamed to `_find_skip_reason` (the function returns `str | None`, not `bool`).
- 2-space indentation in `detect_candidates` 100-line block (PEP 8 E111) — re-indented to 4 spaces throughout.
- `walker.py:46` `/dev/null` Windows portability — now uses `os.devnull` (which yields `nul` on Windows, `/dev/null` on POSIX).
- `walker.py` TOCTOU crash — `path.stat()` is now inside the try/except (was previously crashing if a file was deleted between `read_text` and `stat`).
- `walker.py` symlink protection — explicitly skips symlinks AND verifies `path.resolve()` stays inside `root.resolve()` (was previously only the latter).
- `walker.py` subprocess timeout — `git clone` now has a 300-second timeout (was previously hanging indefinitely on stalled network).
- `walker.py` PAT in `.git/config` — post-clone, the remote URL is scrubbed to remove the embedded PAT (was previously persisting on disk in `.git/config`).
- `extractor.py` `your-username` placeholder — now uses the source repo's owner name (or `your-username` fallback) and emits `# TODO: replace with your actual GitHub URL` comments.
- `extractor.py` source LICENSE preservation — copies the source repo's LICENSE file as `SOURCE-LICENSE` in the extracted package (required by MIT/Apache/BSD for attribution).
- `extractor.py` LICENSE-REVIEW.md — generated for every extraction, walking the user through 5 license scenarios (MIT/Apache, GPL/LGPL/AGPL, no-license, BSD/ISC, MPL-2.0).
- `package.json` and `composer.json` — replaced invalid `"license": "REVIEW-NEEDED"` (not a valid SPDX identifier) with `"license": "SEE LICENSE IN LICENSE-REVIEW.md"` (npm/Composer-recognized pattern).
- `pyproject.toml` license field — commented out with `# TODO: confirm license and uncomment` instead of auto-assigning MIT (which would be a compliance bug for GPL/AGPL sources).
- `models.py` `suggested_license` default — changed from `"MIT"` to `"REVIEW-NEEDED"` (auto-MIT would be a compliance bug).
- `models.py` unused `asdict` import — removed.
- `models.py` `check_results` field — added (for future `--check` feature).
- `scoring.py` `is_` variable — renamed to `issue_score` (was cryptic 2-letter abbreviation).
- `search.py` non-JSON 5xx responses — now prints a warning instead of silently returning `[]`.
- `pat.py` return-shape inconsistency — `check_pat_scope` now always includes the `warning` key (was previously missing on some success branches).
- `pat.py` fine-grained PAT warning — now returns a soft warning that scopes can't be verified (was previously silently accepting any fine-grained PAT).
- `report.py` ASCII 'x' for multiplication — replaced with Unicode '×' to match README, SKILL.md, and scoring.py.
- `report.py` dimension order — now in weight order (quality 25% → usefulness 20% → ... → demand 10%) to match the formula.
- `report.py` missing module docstring — added.
- `report.py` missing type hints — added to all parameters.
- `report.py` `dep_labels[5]` unreachable branch — removed (no handler returns weight 5).
- `people_helper.py` no `--version` flag — added.
- `people_helper.py` no `--debug` flag — added (shows stack traces).
- `people_helper.py` no `--language` validation — now uses `choices=` so typos fail fast.
- `people_helper.py` step labels misnumbered `[1/7]`...`[7/8]` — now consistent `[1/8]`...`[8/8]`.
- `people_helper.py` `time.sleep(3)` non-interruptible — now only sleeps in interactive (TTY) mode and catches `KeyboardInterrupt`.
- `people_helper.py` verbose-only warnings — extraction failures and errored_count now ALWAYS print to stderr (not just in verbose mode).
- `people_helper.py` no exit code taxonomy — now uses 0/1/2/3/4/5/130 (was previously all 1).
- `people_helper.py` no `--output` parent dir validation — now validates up front (was previously running the full pipeline then failing at the end).
- `people_helper.py` no `--extract` path validation — now validates up front.
- `people_helper.py` no `--repo` arg validation before network — now validates syntax BEFORE calling GitHub API.
- `people_helper.py` no range validation — `--max-candidates`, `--max-extract`, `--min-score` now validated.
- `people_helper.py` top-level exception handler leaks PAT — now redacts PAT from all error messages (defense in depth).
- `people_helper.py` no `KeyboardInterrupt` handling — now caught cleanly with exit 130.

### Added
- `pyproject.toml` — PEP 621 project metadata with `[build-system]`, `[project]` (name, version, description, requires-python, license, authors, keywords, classifiers, dependencies, optional-dependencies, urls, scripts), `[tool.hatch.build]`, `[tool.ruff]`, `[tool.mypy]`, `[tool.coverage]`.
- `src/people_helper/__main__.py` — `python -m people_helper` entry point.
- `src/people_helper/cli.py` — CLI `main()` function (importable by both `people_helper.py` script and `__main__.py`).
- `src/people_helper/__init__.py` — re-exports public API (`Candidate`, `SimilarProject`, `detect_candidates`, `generate_report`, `extract_candidates`, `score_candidate`, `walk_repo`, `parse_repo_arg`, `check_pat_scope`, etc.).
- `[project.scripts] people-helper` — console entry point (so `pip install people-helper` provides a `people-helper` shell command).
- `SECURITY.md` — vulnerability reporting policy.
- `PRIVACY.md` — data-flow disclosure.
- `CODE_OF_CONDUCT.md` — Contributor Covenant.
- `CITATION.cff` — citation metadata for academic use.
- `.github/ISSUE_TEMPLATE/bug_report.md` — bug report template.
- `.github/workflows/ci.yml` — CI workflow (tests on Python 3.10/3.11/3.12/3.13 × ubuntu/macos/windows).
- `.pre-commit-config.yaml` — pre-commit hooks (ruff, end-of-file-fixer, trailing-whitespace, check-yaml, check-toml).
- `RATE_LIMITED` sentinel in `search.py` — distinguishes "search failed" from "search succeeded with no results".
- `report.py` `_redact_secrets` — regex-based redaction of common secrets in code previews.
- `report.py` `_sanitize_for_markdown` — escapes triple backticks, strips `<script>`, neutralizes `javascript:` URLs.
- `extractor.py` `_get_author_info` — reads `PEOPLE_HELPER_AUTHOR_NAME` / `PEOPLE_HELPER_AUTHOR_EMAIL` env vars.
- `extractor.py` `_get_github_username` — extracts owner from `source_repo` for placeholder URLs.
- `extractor.py` `_generate_license_review` — generates LICENSE-REVIEW.md walking through 5 license scenarios.
- `walker.py` symlink skip + `path.resolve().relative_to(root_resolved)` check.
- `walker.py` 300-second `subprocess.run` timeout.
- `walker.py` `.git/config` PAT scrub via `git remote set-url origin`.
- `detection.py` `_find_skip_reason` (renamed from `_realism_check`).
- `detection.py` `detect_candidates` now returns `(candidates, errored_count)` tuple.
- `base.py` `get_dependency_weight` default implementation (so new handlers don't crash if they forget to override).

### Changed
- `requirements.txt` — `httpx>=0.25` → `httpx>=0.25,<1.0` (upper bound prevents silent breakage when httpx 1.0 ships).
- `README.md` — comprehensive rewrite: Quick Start, badges, corrected rate-limit claim (30/min not 5000/hour), architecture diagram with all modules, privacy section, --version/--debug documentation, venv/pipx install guidance, optional author env vars documented.
- `people_helper.py` — refactored to delegate to `people_helper.cli.main()` (no more logic in the repo-root script).
- `extractor.py` — extraction now PRESERVES source copyright headers (was previously stripping them, which violates MIT/Apache/BSD attribution requirements).

### Removed
- `extractor.py` `--strip-license-headers` flag reference (the flag never existed; the function `strip_license_header` is kept for backward compat but not called by `extract_candidate`).
- `report.py` `dep_labels[5]` unreachable branch (no handler returns weight 5).
- `detection.py` redundant inline `from .languages import get_handler` (already imported at module top).

## [1.0.0] — 2026-07-26

First public release.

### Added
- 6-dimension scoring: code quality (25%), usefulness (20%), uniqueness (15%), relevance (15%), maintainability (15%), demand signal (10%)
- Extraction verification: relative import detection, sibling resolution, hard-block missing siblings
- License detection: flags repos without LICENSE/COPYING/UNLICENSE as legally risky
- Hard gate: if relevance < 3.0, combined score is halved
- 13 languages: Python, TypeScript, JavaScript, Go, Rust, Java, Kotlin, C, C++, C#, Ruby, PHP, Swift
- Per-language handler architecture under `src/people_helper/languages/`
- Python: full AST-based analysis (cyclomatic complexity, fan-in, import cycle detection)
- All languages: relative import detection, external import extraction, public API counting, docstring detection, LOC counting
- Fine-grained PAT model: hard-rejects write-capable scopes (`repo`, `admin`, `write:*`)
- Read-only by design: no pushes, no PRs, no issue creation
- PAT redaction in error messages
- Temp directory cleanup on all failure paths
- Installable skill for Claude, GPT, Cursor, Cline, Hermes, and MCP
- 253 unit tests covering all language handlers, extraction verification, and edge cases

[Unreleased]: https://github.com/Ehsas317/people-helper/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Ehsas317/people-helper/releases/tag/v1.0.0

# People Helper — Detailed Heuristics

This document is the reference for the extractable detection logic. The CLI in `scripts/people_helper.py` implements these heuristics directly. The skill prompt (in `SKILL.md`) summarizes them.

## Universal heuristics

A source file is a **strong extractable** if it satisfies most of:

| Heuristic | Points | Notes |
|---|---|---|
| Has tests | +3 | Corresponding test file exists in `tests/`, `__tests__/`, or as `<name>_test.<ext>`, `<name>Test.<ext>`, `<name>.test.<ext>`, `<name>.spec.<ext>` |
| Has docstring | +2 | Module-level docstring (Python), JSDoc (JS/TS), package comment (Go), `//!` (Rust) |
| Zero internal imports | +2 | Doesn't import other modules from the same project |
| ≤3 external imports | +2 | Small dependency footprint |
| Utility filename | +1 | `util*`, `helper*`, `common*`, `lib*`, `tool*`, `format*`, `parse*`, `convert*`, `validate*`, `sanitize*` |
| Not a CLI entry point | required | No `if __name__ == "__main__":`, no `func main()`, no `process.argv` reference |
| No env var deps | required | Doesn't read `os.environ`, `process.env`, `std::env::var`, etc. for required config |
| No external service deps | required | Doesn't connect to databases, HTTP APIs, or services at import time |

Open sourceability score = sum of applicable points, capped at 10.

## Per-language specifics

### Python

- Skip files matching `test_*`, `*_test.py`, `conftest.py`
- Detect module-level docstring: first non-blank line is `"""` or `'''`
- Detect internal imports: `from .{module}` (relative), `from <project_module>` (matches project files)
- Skip `__init__.py` (rarely extractable)
- Skip files in `migrations/`, `alembic/`, `scripts/`

### TypeScript / JavaScript

- Skip `.test.ts`, `.spec.ts`, `__tests__/`
- Detect JSDoc: first non-blank line is `/**`
- Detect internal imports: `from './...'`, `from '../...'`, `from '@scope/...'`
- Skip React component files (`.tsx` with JSX, default export that looks like a component)
- Skip files in `pages/`, `app/`, `routes/` (Next.js style — usually app-specific)

### Go

- Skip `*_test.go`
- Detect package comment: `// Package <name> ...` at top, or comment block before `package` declaration
- Detect internal imports: unaliased paths without `/` in import path
- Skip `main.go` and files with `package main` containing `func main()`
- Skip `cmd/` directory entirely

### Rust

- Skip files in `tests/`, `benches/`, `examples/`
- Detect doc comments: `//!` at top of file (inner doc), `///` for items
- Detect internal imports: `use crate::...`, `use super::...`, `use self::...`
- Skip `main.rs` and `lib.rs` itself
- Skip files with binary-only attributes (`#[tokio::main]`, etc.)

### Java

- Skip `*Test.java`, `*Tests.java`
- Detect Javadoc: `/** ... */` before class declaration
- Detect internal imports: package paths matching project structure
- Skip `Application.java`, `*Application.java`, `Main.java`
- Skip files in `src/main/java/<company>/<app>/` that import Spring/J2EE heavily

### C / C++

- Skip files in `test/`, `tests/`
- Detect file header comment block
- Detect internal includes: `#include "..."` with project-relative paths
- Skip `main.c`, `main.cpp`, `main.cc`
- Skip files heavily dependent on project-specific headers

## Scoring

### Uniqueness

Based on GitHub search result count for the same language and ≥5 stars:

| Results | Score | Interpretation |
|---|---|---|
| 0 | 8 | Niche, no existing project |
| 1-2 | 6 | Few existing, may have gaps |
| 3-5 | 4 | Crowded but possibly differentiated |
| 6+ | 2 | Crowded, hard to differentiate |

### Ship effort (heuristic by LOC)

| LOC | Hours |
|---|---|
| < 50 | 1.5 |
| 50-149 | 3 |
| 150-299 | 6 |
| 300-499 | 16 |

These estimates assume the candidate is a self-contained module. If refactoring is needed to remove project coupling, multiply by 2-3x.

### Combined

```
ship_score = max(0, 10 - ship_effort_hours)
combined = 0.4 * open_sourceability + 0.4 * uniqueness + 0.2 * ship_score
```

Maximum 10.

## Suggesting names

Default rule: take the file stem, lowercase, replace non-alphanumeric with `-`, collapse multiple dashes.

Examples:
- `rate_limited.py` → `rate-limited`
- `JwtHelper.ts` → `jwt-helper`
- `string_utils.go` → `string-utils`

Skip if name conflicts with a well-known package (heuristic: contains "request", "express", "react", "django", "flask", "spring"). In that case, prefix with project context.

## LLM-assisted detection (v2)

Pure heuristics miss:
- Multi-file extractables (e.g., a class split across 3 files)
- Internal libraries that aren't named like utilities (e.g., `parser/`, `validator/`)
- Modules that *look* coupled but could be decoupled with light refactoring

For v2, after heuristic detection, optionally:
1. Pass the repo structure to a local LLM (Ornith-9B)
2. Ask: "Given this repo, list 5-10 extractable components that pure heuristics would miss"
3. Merge with heuristic results, deduplicate, re-score

This is opt-in. The CLI defaults to heuristics-only for reproducibility and speed.

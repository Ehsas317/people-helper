# People Helper — Heuristics Reference

## Scoring (v0.2)

### Code quality (50% weight)

| Heuristic | Points | Notes |
|---|---|---|
| Has tests | +3 | Test file exists in tests/, __tests__/, or as name_test.*, nameTest.*, name.test.*, name.spec.* |
| Has docstring | +2 | Module-level docstring (Python), JSDoc (JS/TS), package comment (Go/Rust), Javadoc (Java/C#) |
| Zero internal imports | +2 | No imports from same project |
| 1 internal import | +1 | Loosely coupled |
| <=3 external imports | +2 | Small dependency footprint |
| 4-5 external imports | +1 | Moderate |
| Utility filename | +1 | util*, helper*, common*, lib*, tool*, format*, parse*, convert*, validate*, sanitize*, guard*, filter*, normaliz* |

Capped at 10.

### Uniqueness (30% weight)

| Similar results | Score |
|---|---|
| 0 | 8 |
| 1-2 | 6 |
| 3-5 | 4 |
| 6+ | 2 |

GitHub search filtered by: language, min 5 stars, pushed in last 24 months.

### Demand signal (20% weight)

Computed from similar projects using log-scaled metrics:
- Star signal: min(10, stars / 100)
- Fork signal: min(5, forks / 50)
- Issue signal: min(3, open_issues / 10)

Weighted by search rank (top result matters most). If no similar projects, defaults to 5.0 (moderate niche demand).

**Combined:** `0.5 * code_quality + 0.3 * uniqueness + 0.2 * demand_signal`

## Detection heuristics

### Universal

- 10-500 LOC (non-empty, non-comment lines)
- Not a test file
- Not a framework route file (Next.js pages, SvelteKit routes, etc.)
- Not a CLI entry point
- Not __init__.py, conftest.py

### Per-language

**Python:** Skip test_*, *_test.py, conftest.py, __init__.py, migrations/, alembic/. Detect `from .module` (relative) and project-name imports as internal.

**TypeScript/JavaScript:** Skip .test.*, .spec.*, __tests__/. Detect `from './...'`, `from '@scope/...'` (non-external scope) as internal. Skip framework route files.

**Go:** Skip *_test.go, main.go, cmd/. Detect unaliased import paths (no domain) as internal.

**Rust:** Skip tests/, benches/, examples/, main.rs, lib.rs. Detect `use crate::`, `use super::`, `use self::` as internal.

**Java/Kotlin:** Skip *Test.java, Application.java, Main.java. Detect package paths matching project structure as internal.

**C/C++:** Skip test directories, main.c/cpp. Detect `#include "..."` as internal.

## Ship effort

| LOC | Hours |
|---|---|
| < 50 | 1.5 |
| 50-149 | 3 |
| 150-299 | 6 |
| 300-499 | 16 |
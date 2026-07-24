# People Helper — Heuristics Reference (v1.0)

## Extraction verification (the fundamental check)

Before any scoring happens, every candidate is verified for actual standalone-ness:

### Step 1: Extract relative imports

Relative imports are STRUCTURAL dependencies — the file literally cannot run without its sibling.

| Language | Relative import syntax | Example |
|---|---|---|
| Python | `from . import X` / `from .X import Y` / `from .. import X` | `from .utils import helper` |
| TypeScript/JavaScript | `from './X'` / `from '../X'` / `require('./X')` | `import { foo } from './utils'` |
| Rust | `use super::X` / `use crate::X` / `use self::X` | `use super::utils;` |
| Go | (no relative imports — all paths are absolute) | — |

### Step 2: Resolve siblings

For each relative import, check if the sibling file exists in the same directory:

- Python: `utils.py` or `utils/__init__.py`
- TS/JS: `utils.ts` / `utils.tsx` / `utils.js` / `utils.jsx` / `utils/index.ts` (etc.)
- Rust: `utils.rs` or `utils/mod.rs`

### Step 3: Determine extraction type

| Condition | Extraction type | Action |
|---|---|---|
| No relative imports | `single` | Verified standalone — extract as-is |
| Relative imports, all siblings exist | `multi` | Extract together with siblings |
| Relative imports, any sibling missing | `blocked` | HARD SKIP — would produce broken code |

### Step 4: License check

Check if the repo root has a license file: `LICENSE`, `LICENSE.md`, `LICENSE.txt`, `COPYING`, `UNLICENSE`, `NOTICE`, etc.

- License present → extraction is legally clear
- No license → default copyright applies (all rights reserved) → flagged as legally risky, -1.0 to relevance score

## Scoring (6 dimensions)

All scores are 0-10. Quality and maintainability start from 0; relevance, usefulness, and maintainability start from 4.0 — scores must be earned through positive signals.

### Code quality (25% weight)

Starts from 0. Quality must be earned through multiple positive signals.

| Heuristic | Points | Notes |
|---|---|---|
| Has tests | +2.5 | Test file exists in tests/, __tests__/, or as name_test.*, nameTest.*, name.test.*, name.spec.* |
| Has docstring | +1.5 | Module-level docstring (Python), JSDoc (JS/TS), package comment (Go/Rust), Javadoc (Java/C#) |
| Zero internal imports | +1.5 | No imports from same project |
| 1 internal import | +0.5 | Loosely coupled |
| ≤3 external imports | +1.5 | Small dependency footprint |
| 4-5 external imports | +0.5 | Moderate |
| Utility filename | +0.5 | util*, helper*, common*, lib*, tool*, format*, parse*, convert*, validate*, sanitize*, guard*, filter*, normaliz* |
| Fan-in = 0 | +0.5 | Orphan — nothing else depends on it |
| Verified standalone (single, no relative imports) | +1.0 | Extraction verification bonus |
| Multi-file extraction | -1.0 | Needs siblings |
| Cyclomatic complexity > 20 | -3.0 | Very high complexity |
| Cyclomatic complexity 11-20 | -1.5 | High complexity |
| Cyclomatic complexity 6-10 | -0.5 | Moderate complexity |
| In import cycle | -2.0 | Cycle must be broken first |
| No tests AND no docstring | -1.5 | Mediocre |
| Excellent: tests + docstring + low complexity (cc 1-5) | +1.0 | Bonus for well-rounded quality |

Capped at 0-10.

### Usefulness (20% weight)

Starts from 4.0. Usefulness must be earned through solving a real problem.

| Heuristic | Points | Notes |
|---|---|---|
| Base | 4.0 | Neutral starting point |
| Generic function name found | +1.5 | slugify, sanitize, escape, encode, decode, format, parse, validate, convert, transform, compress, encrypt, decrypt, hash, checksum, sort, filter, search, match, replace, split, join, merge, cache, memoize, retry, backoff, timeout, serialize, deserialize, levenshtein, distance, similarity |
| Generic filename | +1.0 | utils, helpers, common, validators, sanitizer, parser, formatter, converter, serializer, cache, retry, auth, crypto, hash, encode, decode, structures, collections |
| 50-300 LOC | +1.0 | Sweet spot for a utility package |
| < 20 LOC | -1.5 | Too small to be useful |
| Has tests | +0.5 | Tested = more useful |
| API surface ≥ 3 | +1.0 | Rich API = more useful |
| API surface = 1 | -0.5 | Snippet, not a library |
| Stdlib-only | +0.5 | Zero external deps = easy to adopt |
| Long/obscure function name | -1.0 | >25 chars or >3 underscores (project-specific) |
| No API surface (0 functions) | -1.0 | Not useful as a library |

### Uniqueness (15% weight)

| Similar results | Score |
|---|---|
| -1 (unknown, --no-network mode) | 5.0 (neutral) |
| 0 | 8 |
| 1-2 | 6 |
| 3-5 | 4 |
| 6+ | 2 |

GitHub search filtered by: language, min 5 stars, pushed in last 24 months.

### Relevance (15% weight)

**Is this genuinely standalone and reusable?** Starts from 4.0.

| Heuristic | Points | Notes |
|---|---|---|
| Base | 4.0 | Must be earned |
| Verified single-file (no relative imports) | +2.5 | **The gold standard** — extractable as-is |
| Multi-file extraction | -1.5 | Needs siblings — less standalone |
| Dependency weight 0 (stdlib only) | +2.0 | Zero external deps |
| Dependency weight 1 (light deps) | +0.5 | Pip-installable |
| Dependency weight 3 (heavy deps) | -2.5 | TensorFlow, Django, etc. |
| Dependency weight 5 (framework-tied) | -4.0 | Cannot extract without the framework |
| API surface ≥ 3 | +1.5 | Rich library |
| API surface = 2 | +0.5 | Small library |
| API surface = 1 | -1.0 | Snippet |
| API surface = 0 | -2.5 | No public API |
| Has project-specific refs | -2.0 | tf.logging, ansible_module, django.conf, etc. |
| 50-200 LOC | +0.5 | Sweet spot |
| < 20 LOC | -1.5 | Too small |
| > 400 LOC | -0.5 | Too large |
| Has tests | +0.5 | |
| Has docstring | +0.5 | |
| Zero internal imports | +0.5 | |
| No license in source repo | -1.0 | Legally risky |

### Maintainability (15% weight)

Starts from 4.0.

| Heuristic | Points | Notes |
|---|---|---|
| Base | 4.0 | Must be earned |
| Comment ratio ≥ 15% | +2.0 | Well-commented |
| Comment ratio 5-15% | +1.0 | Moderately commented |
| No comments + LOC > 30 | -1.5 | Uncommented |
| Has docstring | +1.0 | |
| Cyclomatic complexity 1-5 | +1.5 | Simple, easy to maintain |
| Cyclomatic complexity 6-10 | +0.5 | Moderate |
| Cyclomatic complexity 16-20 | -1.0 | Complex |
| Cyclomatic complexity > 20 | -2.0 | Very complex |
| 50-200 LOC | +1.0 | Manageable |
| > 400 LOC | -0.5 | Large |
| Has tests | +0.5 | |

### Demand signal (10% weight)

Computed from similar projects using capped linear metrics:
- Star signal: min(10, stars / 100)
- Fork signal: min(5, forks / 50)
- Issue signal: min(3, open_issues / 10)

Weighted by search rank (top result matters most). If no similar projects, defaults to 5.0 (moderate niche demand).

### Combined formula

```
combined = 0.25×quality + 0.20×usefulness + 0.15×uniqueness
         + 0.15×relevance + 0.15×maintainability + 0.10×demand
```

**Hard gate:** If `relevance < 3.0`, combined is halved — a file that isn't genuinely standalone can't be saved by good code quality alone.

## Dependency weight classification

| Weight | Meaning | Examples |
|---|---|---|
| 0 | Stdlib only | Python: os, re, json, typing. Go: fmt, net/http. Rust: std, core, alloc. |
| 1 | Light deps | Any non-stdlib, non-heavy package (requests, lodash, serde) |
| 3 | Heavy deps | Python: tensorflow, torch, numpy, pandas, django, flask. JS: react, vue, next, webpack. Go: k8s.io, grpc. |

Framework-tied code (e.g. `tf.logging`, `ansible_module`, `django.conf`) is detected separately via `has_project_specific_refs` and penalized -2.0 in the relevance score.

## Detection heuristics

### Universal

- 10-500 LOC (non-empty, non-comment lines)
- Not a test file
- Not a framework route file (Next.js pages, SvelteKit routes, etc.)
- Not a CLI entry point
- Not __init__.py, conftest.py
- Not a config file (conf.py, settings.py, etc.)
- Not a SWIG auto-generated file
- Not a TypeScript declaration file (.d.ts)
- Not a documentation-only file

### Realism filter

Files are skipped if they match any of:
- Rust `mod.rs` with only module declarations
- Rust `lib.rs` with only re-exports
- Under 20 LOC with no function/class definitions
- Mostly constant definitions
- Mostly copyright/license comments
- Documentation-only file (string variables dominate)

### Per-language

**Python:** Skip test_*, *_test.py, conftest.py, __init__.py, migrations/, alembic/. Detect `from .module` (relative) and project-name imports as internal. Full AST-based analysis: cyclomatic complexity, fan-in, import cycles.

**TypeScript/JavaScript:** Skip .test.*, .spec.*, __tests__/. Detect `from './...'`, `from '@scope/...'` (non-external scope) as internal. Skip framework route files.

**Go:** Skip *_test.go, main.go, cmd/. No relative imports. Cannot reliably distinguish internal from external without go.mod module path — all imports with `/` are treated as external. Package comments (// immediately before `package`) detected as docstrings; license headers are NOT.

**Rust:** Skip tests/, benches/, examples/, main.rs, lib.rs. Detect `use crate::`, `use super::`, `use self::` as internal. `//!` doc comments detected.

**Java:** Skip *Test.java, Application.java, Main.java. Imports require semicolons. `/** Javadoc */` after package+imports detected. Cannot distinguish internal from external imports without project package metadata.

**Kotlin:** Skip *Test.k. Imports do NOT use semicolons. Default-public functions (`fun` without explicit `public` keyword) are counted. `kotlin.*` is stdlib; `kotlinx.*` is external. Import aliases (`import com.foo.Bar as Baz`) supported.

**C/C++:** Skip test directories, main.c/cpp. `#include "..."` treated as external (could be project or third-party). `#include <stdio.h>` is stdlib (skipped). `#include <boost/...>`, `<opencv2/...>`, `<Eigen/...>` correctly detected as external. Preprocessor directives (`#include`, `#define`, `#ifdef`) counted as LOC.

**C#:** `using` statements detected. `System.*` is stdlib. Both `/** */` block comments and `///` XML documentation comments detected.

**Ruby:** `require` is external; `require_relative` is internal. `def`, `class`, `module` counted as public API. `#` comments and `=begin`/`=end` blocks detected as docstrings.

**PHP:** `use` namespace imports detected. `function`, `class`, `interface`, `trait` counted as public API. `/** */` after `<?php`/`namespace`/`use` detected.

**Swift:** `import` statements detected. `Foundation`, `UIKit`, `SwiftUI`, etc. are stdlib. `func`, `struct`, `class`, `enum`, `protocol` counted as public API.

## Ship effort

| LOC | Hours |
|---|---|
| < 50 | 1.5 |
| 50-149 | 3 |
| 150-299 | 6 |
| 300-499 | 16 |

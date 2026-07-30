# People Helper

> Find code worth extracting — and verify it's actually standalone.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 286](https://img.shields.io/badge/tests-286%20passing-brightgreen.svg)](#testing)

People Helper reads your GitHub repository (read-only, always), identifies self-contained components worth extracting, verifies they can actually stand on their own, searches GitHub for similar projects, and produces a structured report with scores, differentiators, and suggested names. With `--extract`, it can also copy files out and generate package scaffolds (pyproject.toml, package.json, Cargo.toml, go.mod, README, LICENSE-REVIEW.md, SOURCE-LICENSE).

## What it does (and doesn't)

**Does:**
- Discovers extractable code in your repo
- Verifies it's actually standalone (relative imports, sibling resolution, missing-sibling blocking)
- Scores candidates on 6 dimensions (code quality, usefulness, uniqueness, relevance, maintainability, demand)
- Searches GitHub for similar projects to gauge demand and uniqueness
- Generates a structured markdown report
- With `--extract`: copies files out, preserves source copyright headers, generates package scaffolds, copies source LICENSE as SOURCE-LICENSE, generates LICENSE-REVIEW.md walking you through 5 license scenarios

**Doesn't:**
- Write tests for you
- Adjust imports automatically (you review and fix)
- Publish to PyPI/npm/crates.io
- Handle monorepos with cross-package dependencies well
- Auto-assign a license (you MUST review and choose — see LICENSE-REVIEW.md)

## Quick start

```bash
pipx install people-helper
export PEOPLE_HELPER_PAT=github_pat_your_token_here
people-helper --repo your-username/your-repo
```

Or from source:

```bash
git clone https://github.com/Ehsas317/people-helper.git
cd people-helper
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
people-helper --repo your-username/your-repo
```

## Limitations

Be aware of these before using:

1. **Cyclomatic complexity is available for all 13 languages.** Python uses AST-based complexity (most accurate). Other languages use regex-based complexity (counts if/for/while/case/catch/&&/||/? — an approximation but gives fair scores). Fan-in and import cycle detection are Python-only.

2. **Large repos (>50K files) may be slow.** The tool walks every file. For repos with 150K+ files (like gcc, Azure SDK), consider using `--language` to filter.

3. **Language detection follows GitHub linguist rules** (by line count). A repo like numpy will be detected as C (more C extension code than Python), even though it's "a Python library." This is correct behavior but may surprise you.

4. **The `--extract` feature produces a starting point, not a finished package.** Source copyright headers are preserved (required by most licenses). A LICENSE-REVIEW.md file is generated — you MUST determine the correct license before publishing. The source repo's LICENSE file is copied as SOURCE-LICENSE for reference. You still need to review the code, adjust imports, add tests, and validate compilation.

5. **GitHub Search API rate limits** are **30 req/min for authenticated requests** (the same as unauthenticated). The Core API is 5000/hour, but Search is much lower. For large analyses, use `--no-network` and run search separately. When rate-limited, the tool returns a neutral uniqueness score (5.0), not a misleading "truly unique" 8.0.

## How it works

```
Your repo
       │
       ▼
┌────────────────┐    ┌────────────────────┐    ┌─────────────────────┐
│ Shallow clone  │───▶│  Detect files      │───▶│  Verify extraction  │
│ (read-only)    │    │  that pass         │    │  • relative imports │
└────────────────┘    │  extractable       │    │  • sibling resolve  │
                      │  heuristics        │    │  • license present  │
                      └────────────────────┘    └──────────┬──────────┘
                                                            │
┌────────────────────┐    ┌─────────────────────┐           │
│ Markdown report    │◀───│  Score candidates   │◀──────────┘
│ • 6 dimensions     │    │  6 dimensions,      │
│ • Extraction type  │    │  verified           │
│ • License status   │    │  standalone-ness    │
│ • Starter code     │    └─────────────────────┘
└────────────────────┘
```

## The fundamental question: "Is it ACTUALLY standalone?"

Most tools that find "extractable" code just check heuristics — file size, import count, docstring presence. But a file can pass all those checks and **still break the moment you extract it**, because it has a relative import like `from .utils import helper`.

People Helper **verifies** standalone-ness, not just guesses it:

| Signal | What it checks | Why it matters |
|---|---|---|
| **Relative imports** | `from . import X`, `from .X import Y`, `./utils`, `super::X` | These are STRUCTURAL dependencies — the file literally cannot run without its sibling |
| **Sibling resolution** | Does the referenced sibling file exist in the repo? | If yes → multi-file extraction. If no → HARD BLOCK (would produce broken code) |
| **License presence** | Does the repo root have LICENSE/COPYING/UNLICENSE? | Without a license, extraction is legally all-rights-reserved |

Every candidate is tagged with an **extraction type**:

- `✅ single` — verified standalone, no relative imports, extract as-is
- `⚠ multi` — needs sibling files too (listed in the report)
- `⛔ blocked` — references missing siblings, would produce broken code (skipped)

## Scoring

Six dimensions, all computed from the FULL file content:

| Dimension | Weight | What it measures |
|---|---|---|
| **Code quality** | 25% | Tests (+2.5), docs (+1.5), no internal imports (+1.5), few external deps (+1.5), verified standalone (+1.0), utility filename (+0.5), fan-in=0 (+0.5); penalties for high complexity, cycles, no-tests-no-docs (-1.5); excellent bonus (+1.0) |
| **Usefulness** | 20% | Generic function names (+1.5), generic filename (+1.0), 50-300 LOC (+1.0), API surface ≥3 (+1.0), stdlib-only (+0.5); penalties for no API (-1.0), snippet-only (-0.5) |
| **Uniqueness** | 15% | Fewer similar projects on GitHub = higher score (0 results: 8, 1-2: 6, 3-5: 4, 6+: 2). --no-network mode or rate-limited: neutral 5.0 |
| **Relevance** | 15% | Verified single-file (+2.5), multi-file (-1.5), stdlib-only (+2.0), API ≥3 (+1.5), no license (-1.0), project-specific refs (-2.0) |
| **Maintainability** | 15% | Comment ratio ≥15% (+2.0), docstring (+1.0), low complexity (+1.5), 50-200 LOC (+1.0), tests (+0.5) |
| **Demand signal** | 10% | Star count, fork count, and open issues of similar projects (capped linear, rank-weighted) |

**Formula:** `combined = 0.25×quality + 0.20×usefulness + 0.15×uniqueness + 0.15×relevance + 0.15×maintainability + 0.10×demand`

If `relevance < 3.0`, the combined score is halved — a file that isn't genuinely standalone can't be saved by good code quality alone.

## Install

### Option A: pipx (recommended for CLI use)

```bash
pipx install people-helper
```

### Option B: From source

```bash
git clone https://github.com/Ehsas317/people-helper.git
cd people-helper
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### Option C: Just run the script (no install)

```bash
git clone https://github.com/Ehsas317/people-helper.git
cd people-helper
pip install -r requirements.txt  # only httpx
python people_helper.py --repo you/repo
```

**Requires Python 3.10+** (uses PEP 604 `X | None` syntax).

## Setup (one time)

Create a **fine-grained GitHub PAT**:

1. Go to [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new)
2. Resource owner: you
3. Repository access: **Only select repositories** → pick the repo(s) you want to analyze
4. Permissions:
   - **Contents**: Read
   - **Metadata**: Read (auto-selected)
5. Expiration: 90 days or less
6. Copy the token

```bash
export PEOPLE_HELPER_PAT=github_pat_your_token_here
```

### Optional: author info for extracted packages

If you use `--extract`, the generated manifests (pyproject.toml, package.json, etc.) include author info. Set these to avoid the "Your Name" placeholder:

```bash
export PEOPLE_HELPER_AUTHOR_NAME="Jane Doe"
export PEOPLE_HELPER_AUTHOR_EMAIL="jane@example.com"
```

## Usage

```bash
# Basic usage (produces report.md)
people-helper --repo your-username/your-repo

# With output path
people-helper --repo your-username/your-repo --output my-report.md

# Verbose mode (see each step)
people-helper --repo your-username/your-repo --verbose

# Debug mode (show stack traces on errors)
people-helper --repo your-username/your-repo --debug

# Show version
people-helper --version

# Local-only (no GitHub search, faster)
people-helper --repo your-username/your-repo --no-network

# Filter by language (validated against supported languages)
people-helper --repo your-username/your-repo --language Python

# Extract top candidates to ./extracted/ (creates package scaffolds)
people-helper --repo your-username/your-repo --extract ./extracted/

# Extract with custom thresholds
people-helper --repo your-username/your-repo --extract ./extracted/ --max-extract 3 --extract-min-score 7.0

# Control output size
people-helper --repo your-username/your-repo --max-candidates 5 --min-stars 10
```

You can also invoke as a Python module:

```bash
python -m people_helper --repo you/repo
```

Or from a clone without installing:

```bash
python people_helper.py --repo you/repo
```

## What it detects

A file is a **strong extractable candidate** if it:

- Has at least 10 lines of actual code (no hard upper limit — large files get a graduated maintainability penalty: -0.1 per 150 LOC over 500)
- Has a module-level docstring, JSDoc, or package comment
- Has zero or one internal project import (self-contained)
- Has few external imports (small dependency footprint)
- Has a corresponding test file
- Has a utility-like filename (`util`, `helper`, `parser`, `validator`, etc.)
- Is **verified standalone** (no relative imports, OR siblings exist for multi-file extraction)
- Is **not** a framework route file (Next.js pages, SvelteKit routes, etc.)
- Is **not** a test file itself
- Is **not** a CLI entry point
- Is **not** a config file, SWIG output, or declaration file

## Report output

The generated markdown report includes for each candidate:

- **Scores**: all 6 dimensions + combined
- **Extraction type**: `✅ single`, `⚠ multi`, or `⛔ blocked`
- **Required siblings**: if multi-file, which files must be extracted together
- **Source repo license**: whether the repo has a license file
- **What it does**: extracted from docstring or code
- **Why it's extractable**: grounded reasons from the analysis
- **Similar projects**: GitHub search results with stars, forks, last commit date
- **Your differentiators**: concrete comparison points
- **Suggested name**: clean, publishable package name
- **Suggested tags**: GitHub topics for discoverability
- **Starter scaffold (first 30 lines)**: code preview with secrets auto-redacted

## Trust boundary

People Helper is **read-only by design**:

- Fine-grained PAT with **Contents: Read** and **Metadata: Read** only
- Hard-rejects classic PATs with write-capable scopes (`repo`, `admin:*`, `write:*`, `delete:*`)
- Note: classic-PAT scopes are hard-verified; fine-grained PAT scopes cannot be introspected via the API, so users must follow the setup instructions correctly — the tool will warn but not enforce.
- No write operations — no pushes, no PRs, no issue creation
- Code stays on your machine; only GitHub's public search API is called
- Temp clone is cleaned up after every run (on all failure paths including timeouts)
- PAT is scrubbed from `.git/config` post-clone (defense in depth)
- PAT is redacted from all error messages and exception args
- Report content is sanitized: triple backticks escaped, `<script>` stripped, `javascript:` URLs neutralized, common secrets (GitHub PATs, AWS keys, Slack tokens, JWTs, PEM keys) auto-redacted from code previews

## Privacy

**What leaves your machine** (when not using `--no-network`):

- Your PAT (sent to `api.github.com/user` for scope verification, and to `github.com` for `git clone`)
- The repo URL (for `git clone`)
- For each candidate's GitHub search query: the file's stem (name without extension), up to 2 function names, up to 2 docstring words, and up to 2 import module names

A privacy notice is printed before search runs (with a 3-second cancel window in interactive mode).

Use `--no-network` to skip GitHub search entirely (PAT and repo URL still traverse GitHub for clone — that's unavoidable).

## Supported languages

All 13 languages have full import detection, public API counting, docstring detection, and cyclomatic complexity:

| Language | Relative imports | Import detection | Public API | Docstring | Complexity |
|---|---|---|---|---|---|
| Python | ✓ (`from .`) | ✓ | ✓ (AST) | ✓ (`"""`) | ✓ (AST) |
| TypeScript/JS | ✓ (`./X`) | ✓ | ✓ (`export`) | ✓ (`/** */`) | ✓ (regex) |
| Go | — | ✓ | ✓ (capitalized) | ✓ (`//`) | ✓ (regex) |
| Rust | ✓ (`super::`) | ✓ | ✓ (`pub`) | ✓ (`//!`) | ✓ (regex) |
| Java | — | ✓ | ✓ (`public`) | ✓ (`/** */`) | ✓ (regex) |
| Kotlin | — | ✓ (no `;`) | ✓ (default public) | ✓ (`/** */`) | ✓ (regex) |
| C/C++ | — | ✓ (boost/opencv/eigen) | ✓ | ✓ (`/** */`) | ✓ (regex) |
| C# | — | ✓ | ✓ | ✓ (`/** */` + `///`) | ✓ (regex) |
| Ruby | — | ✓ (`require`) | ✓ (`def`) | ✓ (`#`) | ✓ (regex) |
| PHP | — | ✓ (`use`) | ✓ (`function`) | ✓ (`/** */`) | ✓ (regex) |
| Swift | — | ✓ | ✓ (`func`) | ✓ (`/** */`) | ✓ (regex) |

Python uses AST-based complexity (most accurate). Other languages use regex-based complexity (counts if/for/while/case/catch/&&/||/?). Fan-in and import cycle detection are Python-only.

## Real-world findings

People Helper has been extensively tested on **50+ major open-source repositories** (including Google, Facebook, Microsoft, and Netflix) to find high-value standalone components.

| Source Repo | Component | Score | Why it's a winner |
|---|---|---|---|
| `golang/go` | `pkg.go` | **8.2** | Perfectly structured documentation utility. |
| `facebook/fboss` | `IPv6Hdr.cpp` | **7.9** | Standalone network header parser. |
| `rails/rails` | `deep_mergeable.rb` | **7.8** | Isolated deep-merge logic for hashes. |
| `google/gvisor` | `checksum.go` | **7.8** | Optimized network checksum implementation. |

See the full [SHOWCASE.md](SHOWCASE.md) for the complete list of 50+ discoveries and deep dives.

## Architecture

```
src/people_helper/
├── languages/           # Language-specific handlers (one per family)
│   ├── base.py          # Abstract LanguageHandler interface
│   ├── python_lang.py   # Python (AST-based)
│   ├── js_ts.py         # JavaScript/TypeScript
│   ├── go_lang.py       # Go
│   ├── rust_lang.py     # Rust
│   ├── jvm.py           # Java + Kotlin
│   ├── c_family.py      # C/C++
│   ├── dotnet.py        # C#
│   ├── ruby_lang.py     # Ruby
│   ├── php_lang.py      # PHP
│   └── swift_lang.py    # Swift
├── detection.py         # Language-agnostic candidate assembly
├── scoring.py           # 6-dimension scoring
├── walker.py            # Repo cloning + file walking
├── search.py            # GitHub search for similar projects
├── report.py            # Markdown report generation
├── extractor.py         # --extract: copy files + generate scaffolds
├── naming.py            # Package name + tag suggestions
├── pat.py               # PAT scope verification
├── cli.py               # CLI entry point (main function)
├── __main__.py          # `python -m people_helper` entry
├── __init__.py          # Public API re-exports
└── models.py            # Candidate + SimilarProject dataclasses
```

Each language handler exposes a consistent interface:
- `extract_relative_imports(content)` → list of (sibling_name, parent_level)
- `extract_external_imports(content)` → list of import names
- `count_public_api(content)` → (count, function_names)
- `detect_docstring(content)` → (found, snippet)
- `count_imports(content, project_modules)` → (internal, external)
- `count_loc(content)` → int
- `get_complexity(content)` → int (AST for Python, regex for others)
- `get_dependency_weight(imports)` → (weight, is_stdlib_only)

This separation keeps each language isolated: adding a new language or fixing a language-specific behavior only touches one file.

## Skill packaging

People Helper is also packaged as an installable AI skill for Claude, GPT, Cursor, Cline, Hermes, and MCP. See the `skill/` directory.

## Testing

286 unit tests covering all language handlers, extraction verification, scoring, search, PAT scope verification, manifest generators, security (symlink/path-traversal/markdown-injection/secret-redaction), CLI argument validation, and edge cases:

```bash
python -m unittest tests.test_people_helper
```

## License

MIT — see [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Privacy

See [PRIVACY.md](PRIVACY.md) for data-flow details.

## Status

v1.0.0 — 286 unit tests, all passing. Battle-tested on public repos during development.

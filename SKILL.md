---
name: people-helper
description: >-
  Analyze a private GitHub repo to find extractable components worth shipping as
  standalone side projects or open-source contributions. Use when the user asks to
  analyze my repo, find extractables, scan a private repo, find side projects in my
  code, discover open source opportunities, check what can I open source from my
  code, or figure out what's worth shipping from this codebase.
license: MIT
metadata:
  version: "1.0.0"
  author: Ehsas317
  homepage: https://github.com/Ehsas317/people-helper
  triggers:
    - "analyze my repo"
    - "find extractables"
    - "what can I open source from my code"
    - "scan my private repo"
    - "what can I extract"
    - "find side projects in my code"
    - "open source opportunities"
    - "what's worth shipping from this"
  keywords:
    - github
    - open-source
    - code-analysis
    - extractables
    - side-projects
    - read-only
    - fine-grained-pat
    - competitive-analysis
allowed-tools: Read Bash Glob Grep
---

# People Helper

Read-only analysis skill that scans a GitHub repository, identifies components
extractable as standalone projects, and produces a ranked report with
scaffolds.

## 7-Step Workflow

1. **Clone** — shallow-clone the target repo to a temp directory using the PAT.
2. **Walk** — traverse the file tree; classify each file by type and role.
3. **Detect** — apply heuristics to flag extractable candidates.
   See `references/heuristics.md` for the full detection rule set.
4. **Search** — query the GitHub API for similar projects per candidate.
   See `references/github-api.md` for endpoint details.
5. **Score** — rank candidates with the formula below.
6. **Name** — generate a suggested package/repo name per candidate.
7. **Report** — produce the structured output described below.

## Setup

1. **Create a fine-grained GitHub PAT** with only `Contents: Read` and
   `Metadata: Read` permissions. Do NOT add write scopes.
2. Export it: `export PEOPLE_HELPER_PAT=ghp_...`
3. Install: `pip install -e .` (or `pipx install people-helper` from PyPI)
4. Optional: `export PEOPLE_HELPER_AUTHOR_NAME="Your Name"` and
   `PEOPLE_HELPER_AUTHOR_EMAIL="you@example.com"` for extracted packages.

## CLI Flags

```
people-helper --repo owner/name [options]

  --repo REPO          GitHub repo URL or owner/name (required)
  --output PATH        Output report path (default: report.md)
  --extract DIR        Extract top candidates to DIR (creates package scaffolds)
  --max-candidates N   Max candidates in report (default: 10)
  --max-extract N      Max candidates to extract (default: 5)
  --min-score N        Only show candidates with score >= this (default: 0.0)
  --extract-min-score  Min score for extraction (default: 6.0)
  --min-stars N        Min stars for similar projects search (default: 5)
  --language LANG      Filter to one language (choices: Python, TypeScript, etc.)
  --no-network         Skip GitHub search (local-only mode)
  --verbose            Verbose step-by-step progress output
  --debug              Show stack traces on errors (for bug reports)
  --version            Print version and exit
```

Exit codes: 0=success, 1=error, 2=argparse, 3=auth, 4=bad input, 5=repo error, 130=interrupted.

## Trust Boundary (Read-Only)

- GitHub access is **read-only** via fine-grained PAT (Contents + Metadata read).
- **No write operations** — no pushes, PRs, issues, or file edits.
- Code stays local; the only network calls go to `api.github.com` for search.
- No private code is transmitted to any third party.

## Scoring Formula

```
combined = 0.25×quality + 0.20×usefulness + 0.15×uniqueness
         + 0.15×relevance + 0.15×maintainability + 0.10×demand
```

| Dimension | Weight | How it's measured |
|-----------|--------|-------------------|
| Code quality | 25% | Tests (+2.5), docs (+1.5), no internal imports (+1.5), few external deps (+1.5), verified standalone (+1.0), utility filename (+0.5), fan-in=0 (+0.5); penalties: high complexity (-3 to -0.5), cycle (-2.0), no-tests-no-docs (-1.5), >400 LOC (-0.5); excellent bonus (+1.0) |
| Usefulness | 20% | Generic function names (+1.5), generic filename (+1.0), 50-300 LOC (+1.0), API ≥3 (+1.0), stdlib-only (+0.5); penalties: no API (-1.0), snippet-only (-0.5) |
| Uniqueness | 15% | GitHub search: 0 → 8, 1-2 → 6, 3-5 → 4, 6+ → 2. --no-network or rate-limited: neutral 5.0 |
| Relevance | 15% | Verified single-file (+2.5), multi-file (-1.5), stdlib-only (+2.0), API ≥3 (+1.5), no license (-1.0), project-specific refs (-2.0) |
| Maintainability | 15% | Comment ratio ≥15% (+2.0), docstring (+1.0), low complexity (+1.5), 50-200 LOC (+1.0), tests (+0.5); penalties: >400 LOC (-0.5), **>500 LOC graduated penalty: -0.1 per 150 LOC over 500** |
| Demand signal | 10% | Stars, forks, issues of similar projects (capped linear, rank-weighted) |

**LOC scoring note:** There is **no hard LOC ceiling** — files >500 LOC are detected but get a graduated maintainability penalty (-0.1 per 150 LOC over 500). Minimum: 10 LOC (below that = snippet, skipped).

**Hard gate:** If `relevance < 3.0`, combined is halved — a file that isn't genuinely standalone can't be saved by good code quality alone.

## Extraction Verification (the fundamental check)

Every candidate is verified for actual standalone-ness before scoring:

1. **Extract relative imports** — `from . import X`, `./utils`, `super::X`
2. **Resolve siblings** — check if referenced files exist in the repo
3. **Determine extraction type**:
   - `✅ single` — no relative imports, verified standalone
   - `⚠ multi` — needs sibling files too (listed in report)
   - `⛔ blocked` — references missing siblings, HARD SKIPPED
4. **License check** — flag repos without a LICENSE file as legally risky

## Output Format

For each candidate the report includes:

- **Scores** — per-dimension and combined.
- **Summary** — what the component does and why it's extractable.
- **Similar projects** — up to 5 nearest matches with star counts.
- **Differentiators** — concrete ways the candidate improves on existing work.
- **Suggested name** — a package-friendly repo name.
- **Tags** — up to 5 relevant tags.
- **Starter scaffold** — first 30 lines of the source file, ready to lift out (may need manual cleanup of mid-function truncation).

## Language Support

All 13 supported languages have full import detection, public API counting, and docstring detection:
- **Python**: full support (complexity, fan-in, import cycle detection via AST)
- **TypeScript/JavaScript**: relative imports, JSDoc, export tracking
- **Go**: package comments, capitalized-function export detection
- **Rust**: `//!` doc comments, `pub fn`/`pub struct` tracking
- **Java**: `/** Javadoc */`, semicolon-required imports
- **Kotlin**: default-public functions (no `public` keyword needed), no-semicolon imports
- **C/C++**: preprocessor directives counted as LOC, boost/opencv/eigen detected via angle-bracket includes
- **C#**: both `/** */` and `///` XML documentation detected
- **Ruby**: `require`/`require_relative` distinction, `def`/`class`/`module` tracking
- **PHP**: `use` namespace imports, `function`/`class`/`interface`/`trait` tracking
- **Swift**: `import` detection with Foundation/UIKit stdlib filtering

Note: Cyclomatic complexity is available for all 13 languages (AST-based for Python, regex-based for others). Fan-in and import cycle detection are Python-only.

## What This Skill Never Does

- Modify the user's repo, push code, create PRs, or file issues.
- Transmit private code to any third party.
- Fabricate search results or overstate differentiators.
- Operate on a PAT that has write scopes.
- Skip temp-directory cleanup.

## Companion Files

- `scripts/people_helper.py` — standalone CLI entry point.
- `references/heuristics.md` — full detection heuristic rules.
- `references/github-api.md` — GitHub API endpoints and pagination details.

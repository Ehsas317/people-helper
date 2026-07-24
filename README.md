# People Helper

> Find what's extractable from your private code — then ship it as open source.

People Helper reads your private GitHub repository (read-only, always), identifies self-contained components worth extracting, searches GitHub for similar projects, and produces a structured report with scores, differentiators, suggested names, and starter scaffolds.

## How it works

```
Your private repo
       │
       ▼
┌──────────────┐    ┌─────────────────┐    ┌──────────────────┐
│ Shallow clone │───▶│  Detect files    │───▶│  Score candidates │
│ (read-only)   │    │  that pass       │    │                  │
└──────────────┘    │  extractable     │    │  50% code quality │
                    │  heuristics      │    │  30% uniqueness    │
                    │  + complexity    │    │  20% demand signal │
                    │  + fan-in        │    └────────┬─────────┘
                    │  + cycle check   │             │
                    └─────────────────┘             │
┌──────────────────┐                                │
│ Search GitHub    │◀───────────────────────────────┘
│ for similar      │
│ projects         │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Markdown report  │
│ • Scores         │
│ • Differentiators│
│ • Starter code   │
│ • Suggested name │
└──────────────────┘
```

## Scoring

Each candidate is scored on three dimensions:

| Dimension | Weight | What it measures |
|---|---|---|
| **Code quality** | 50% | Tests (+3), docs (+2), no internal imports (+2), few external deps (+2), utility filename (+1). Bonuses: orphan/fan-in=0 (+1). Penalties: high cyclomatic complexity (-0.5 to -3), import cycle (-1.5) |
| **Uniqueness** | 30% | Fewer similar projects on GitHub = higher score (0 results: 8, 1-2: 6, 3-5: 4, 6+: 2) |
| **Demand signal** | 20% | Star count, fork count, open issues, stars-per-fork ratio of similar projects indicate real demand |

**Formula:** `combined = 0.5 × code_quality + 0.3 × uniqueness + 0.2 × demand_signal`

## Install

### From source (recommended for now)

```bash
git clone https://github.com/Ehsas317/people-helper.git
cd people-helper

# Option A: install as a package (creates a `people-helper` console script)
pip install -e .

# Option B: run directly without install (sets PYTHONPATH)
PYTHONPATH=src python -m people_helper --help
```

### Dependencies

Only `httpx>=0.25`. Tests need `pytest>=8`.

```bash
pip install -e ".[dev]"   # installs httpx + pytest + ruff
```

## Setup (one time)

Create a **fine-grained GitHub PAT** (recommended):

1. Go to [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new)
2. Resource owner: you
3. Repository access: **Only select repositories** → pick the private repo(s) you want to analyze
4. Permissions:
   - **Contents**: Read
   - **Metadata**: Read (auto-selected)
5. Expiration: 90 days or less
6. Copy the token

```bash
export PEOPLE_HELPER_PAT=github_pat_your_token_here
```

> ⚠️ Classic PATs with `repo` scope are also accepted (with a warning), but
> fine-grained PATs are safer. The tool only ever does read operations.

## Usage

```bash
# Using the installed console script
people-helper --repo your-username/your-private-repo

# Or via python -m
python -m people_helper --repo your-username/your-private-repo

# With output path
python -m people_helper --repo your-username/your-private-repo --output my-report.md

# Verbose mode (see each step)
python -m people_helper --repo your-username/your-private-repo --verbose

# Local-only (no GitHub search, faster)
python -m people_helper --repo your-username/your-private-repo --no-network

# Filter by language
python -m people_helper --repo your-username/your-private-repo --language Python

# Control output size
python -m people_helper --repo your-username/your-private-repo --max-candidates 5 --min-stars 10
```

## What it detects

A file is a **strong extractable candidate** if it:

- Has 10-500 lines of actual code
- Has a module-level docstring, JSDoc, or package comment
- Has zero or one internal project import (self-contained)
- Has few external imports (small dependency footprint)
- Has a corresponding test file
- Has a utility-like filename (`util`, `helper`, `parser`, `validator`, etc.)
- Is **not** a framework route file (Next.js pages, SvelteKit routes, etc.)
- Is **not** a test file itself
- Is **not** a CLI entry point

### New in v0.3: deeper signals

- **Cyclomatic complexity (McCabe)** — god functions get penalized even if they pass the LOC check. A 200-LOC function with `cc=30` is no longer flagged as extractable.
- **Reverse fan-in / orphan detection** — a file with `fan_in=0` is a great extraction target (nothing else in the repo depends on it). Files with `fan_in=1` are also flagged as low-blast-radius.
- **SCC cycle detection (Tarjan)** — files in a non-trivial import cycle get an `in_cycle` flag and a complexity penalty, since extraction would require breaking the cycle first.
- **Stars-per-fork engagement ratio** — a similar project with 5,000 stars but only 10 forks is "curiosity, not usage"; one with 50 stars and 20 forks has real fork-and-extend demand.
- **Stale-niche detection** — if 3+ of your similar projects are >12 months stale, that's flagged as a clear opening.

## Report output

The generated markdown report includes for each candidate:

- **Scores**: code quality, uniqueness, demand signal, combined
- **Cyclomatic complexity**: with a plain-English label (low / moderate / high / very high)
- **Fan-in**: how many other files in the repo import this one
- **Import cycle**: ⚠ flag if the file is part of an SCC
- **What it does**: extracted from docstring or code
- **Why it's extractable**: grounded reasons from the analysis
- **Similar projects**: GitHub search results with stars, forks, last commit date
- **Your differentiators**: concrete comparison points
- **Suggested name**: clean, publishable package name
- **Suggested tags**: GitHub topics for discoverability
- **Starter scaffold**: first 30 lines of the file, ready to lift out

## Trust boundary

People Helper is **read-only by design**:

- Fine-grained PAT with **Contents: Read** and **Metadata: Read** only (classic PATs allowed with warning)
- No write operations — no pushes, no PRs, no issue creation
- Code stays on your machine; only GitHub's public search API is called
- Temp clone is cleaned up after every run (even on error)

## Supported languages

Python, TypeScript, JavaScript, Go, Rust, Java, Kotlin, C, C++, C#, Ruby, PHP, Swift

## Development

```bash
# Run the test suite (106 tests, fully offline)
pytest tests/ -v

# Lint + format
ruff check src/ tests/
ruff format src/ tests/

# Run end-to-end on the people-helper repo itself
PYTHONPATH=src PEOPLE_HELPER_PAT=github_pat_xxx \
    python -m people_helper --repo Ehsas317/people-helper --verbose
```

### Test fixtures

The test suite uses 6 fixture repos in `tests/fixtures/repos/`:

| Fixture | What it tests |
|---|---|
| `clean-utility/` | A small, well-documented Python utility with tests — should be flagged as extractable with a high score |
| `coupled-core/` | A config_loader.py with 3 internal imports — should be skipped as tightly coupled |
| `import-cycle/` | Two files that import each other — should be flagged by SCC detection |
| `god-function/` | A 200-LOC function with cc≈30 — should be penalized for high complexity |
| `orphan-leaf/` | A self-contained module nobody imports — should be flagged with `fan_in=0` |
| `multi-language/` | Python + TS + Go files — tests language detection |

All tests run offline (no PAT, no network) using `httpx.MockTransport` for the network-mocked tests.

## Project structure

```
people-helper/
├── pyproject.toml              # PEP 621 project metadata + ruff + pytest config
├── README.md
├── SKILL.md                    # AI skill prompt (Anthropic Skills spec)
├── src/
│   └── people_helper/
│       ├── __init__.py         # version = 0.3.0
│       ├── __main__.py         # enables `python -m people_helper`
│       ├── cli.py              # CLI entry point (argparse)
│       ├── pat.py              # PAT scope verification
│       ├── walker.py           # repo parsing + shallow clone + file walking
│       ├── detection.py        # candidate detection (LOC, imports, complexity, fan-in, SCC)
│       ├── search.py           # GitHub search + differentiator computation
│       ├── scoring.py          # 3-axis scoring formula
│       ├── naming.py           # suggested package name + tags
│       ├── report.py           # markdown report generator
│       ├── models.py           # Candidate + SimilarProject dataclasses
│       └── config.py           # constants (langs, weights, framework files)
├── tests/
│   ├── conftest.py             # shared fixtures (paths)
│   ├── test_walker.py          # repo parsing + walk
│   ├── test_detection.py       # heuristics + complexity + fan-in + SCC
│   ├── test_scoring.py         # score formula + property tests
│   ├── test_search.py          # query building + differentiators + 403 mock
│   ├── test_naming.py          # name + tag generation
│   ├── test_report.py          # markdown output
│   ├── test_end_to_end.py      # full pipeline against fixture repos
│   └── fixtures/repos/         # 6 fixture repos for offline testing
├── references/                 # Heuristics + GitHub API docs
└── skill/                      # AI skill packaging (Claude, GPT, Cursor, MCP)
```

## Skill packaging

People Helper is also packaged as an installable AI skill for Claude, GPT, Cursor, Cline, Hermes, and MCP. See the `skill/` directory.

## License

MIT

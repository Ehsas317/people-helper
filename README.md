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
                    └─────────────────┘    │  20% demand signal │
                                              └────────┬─────────┘
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
| **Code quality** | 50% | Tests (+3), docs (+2), no internal imports (+2), few external deps (+2), utility filename (+1) |
| **Uniqueness** | 30% | Fewer similar projects on GitHub = higher score (0 results: 8, 1-2: 6, 3-5: 4, 6+: 2) |
| **Demand signal** | 20% | Star count, fork count, and open issues of similar projects indicate real demand |

**Formula:** `combined = 0.5 × code_quality + 0.3 × uniqueness + 0.2 × demand_signal`

## Install

```bash
git clone https://github.com/Ehsas317/people-helper.git
cd people-helper
pip install -r requirements.txt
```

## Setup (one time)

Create a **fine-grained GitHub PAT**:

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

## Usage

```bash
# Basic usage
python people_helper.py --repo your-username/your-private-repo

# With output path
python people_helper.py --repo your-username/your-private-repo --output my-report.md

# Verbose mode (see each step)
python people_helper.py --repo your-username/your-private-repo --verbose

# Local-only (no GitHub search, faster)
python people_helper.py --repo your-username/your-private-repo --no-network

# Filter by language
python people_helper.py --repo your-username/your-private-repo --language Python

# Control output size
python people_helper.py --repo your-username/your-private-repo --max-candidates 5 --min-stars 10
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

## Report output

The generated markdown report includes for each candidate:

- **Scores**: code quality, uniqueness, demand signal, combined
- **What it does**: extracted from docstring or code
- **Why it's extractable**: grounded reasons from the analysis
- **Similar projects**: GitHub search results with stars, forks, last commit date
- **Your differentiators**: concrete comparison points
- **Suggested name**: clean, publishable package name
- **Suggested tags**: GitHub topics for discoverability
- **Starter scaffold**: first 30 lines of the file, ready to lift out

## Trust boundary

People Helper is **read-only by design**:

- Fine-grained PAT with **Contents: Read** and **Metadata: Read** only
- No write operations — no pushes, no PRs, no issue creation
- Code stays on your machine; only GitHub's public search API is called
- Temp clone is cleaned up after every run
- Rejects classic PATs with broad `repo` scope

## Supported languages

Python, TypeScript, JavaScript, Go, Rust, Java, Kotlin, C, C++, C#, Ruby, PHP, Swift

## Skill packaging

People Helper is also packaged as an installable AI skill for Claude, GPT, Cursor, Cline, Hermes, and MCP. See the `skill/` directory.

## License

MIT

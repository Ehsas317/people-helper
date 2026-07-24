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
  version: "0.3.0"
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
3. Install dependencies: `pip install -r requirements.txt`

## Trust Boundary (Read-Only)

- GitHub access is **read-only** via fine-grained PAT (Contents + Metadata read).
- **No write operations** — no pushes, PRs, issues, or file edits.
- Code stays local; the only network calls go to `api.github.com` for search.
- No private code is transmitted to any third party.

## Scoring Formula

```
combined = 0.5 * code_quality + 0.3 * uniqueness + 0.2 * demand_signal
```

| Dimension   | Weight | How it's measured |
|-------------|--------|-------------------|
| Code quality | 50 %   | Tests (+3), docs (+2), no internal imports (+2), few external deps (+2), utility filename (+1) |
| Uniqueness  | 30 %   | GitHub search results: 0 → 8, 1-2 → 6, 3-5 → 4, 6+ → 2 |
| Demand signal | 20 %  | Stars, forks, issues of similar projects (log-scaled) |

## Output Format

For each candidate the report includes:

- **Scores** — per-dimension and combined.
- **Summary** — what the component does and why it's extractable.
- **Similar projects** — up to 5 nearest matches with star counts.
- **Differentiators** — concrete ways the candidate improves on existing work.
- **Suggested name** — a package-friendly repo name.
- **Tags** — up to 5 relevant tags.
- **Starter scaffold** — minimal file skeleton to bootstrap the project.

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

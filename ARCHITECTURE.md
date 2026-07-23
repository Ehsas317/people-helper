# People Helper — Architecture

## Design principles

1. **Read-only, always.** The skill never writes to the user's repository. This is enforced at the PAT scope level (fine-grained token, contents:read, metadata:read only) and at the code level (no `git push`, no API write calls).
2. **Local-first.** All analysis runs on the user's machine. Code never leaves the local filesystem. The only network call is to GitHub's public API for repo search.
3. **Boring tech.** Python, stdlib where possible, one HTTP library (httpx), one markdown library. No framework, no orchestrator, no hidden magic.
4. **Small surface area.** The CLI is one file. The system prompt is one file. Adding a new heuristic is a function. There is no plugin system.

## Inputs

| Input | Source | Notes |
|---|---|---|
| Target repo | CLI flag or env | GitHub URL or `owner/name` |
| Fine-grained PAT | env `PEOPLE_HELPER_PAT` | contents:read + metadata:read only |
| Min stars filter | CLI flag | Filters out low-signal GitHub search results |
| Max candidates | CLI flag | Caps report size |
| Language filter | CLI flag | Optional, restricts extractables to one language |

## Pipeline

```
┌─────────────────┐
│  1. PAT scope   │   Verify fine-grained, read-only scopes only
│     check       │   Refuse to run if scopes are too broad
└────────┬────────┘
         │
┌────────▼────────┐
│  2. Repo walk   │   Shallow clone to /tmp/people-helper-{hash}
│     (local)     │   Or walk via GitHub API (no clone)
└────────┬────────┘
         │
┌────────▼────────┐
│  3. Module map  │   Detect language(s), build file tree
│                 │   Identify package boundaries (pyproject, package.json, etc.)
└────────┬────────┘
         │
┌────────▼────────┐
│  4. Extractable │   Heuristics + (optional) LLM call
│     detection   │   Per-language extractable patterns
└────────┬────────┘
         │
┌────────▼────────┐
│  5. GitHub      │   For each candidate, search for similar projects
│     search      │   Filter by min-stars, recency, language
└────────┬────────┘
         │
┌────────▼────────┐
│  6. Scoring     │   open_sourceability + uniqueness + ship_effort
│                 │   Combined score = weighted sum
└────────┬────────┘
         │
┌────────▼────────┐
│  7. Report      │   Markdown template, sorted by score
│     generation  │   Includes starter scaffolds for top 3
└─────────────────┘
```

## Stage 1: PAT scope check

Before doing anything, verify the PAT is fine-grained and has only the required scopes. This is non-negotiable.

**Required scopes (fine-grained PAT):**
- Repository access: specific repos only (not "all repos" or "public repos")
- Permissions: Contents (read), Metadata (read)

**Forbidden scopes (refuse to run if any are present):**
- Any write permission
- Administration
- Actions / Workflows
- Code scanning / Secret scanning
- Issues, Pull requests, Projects
- Packages, Pages
- Any org-level scope

**Verification approach:**
- For fine-grained PATs, call `GET /user` to confirm auth
- Inspect the `X-OAuth-Scopes` header (classic PATs) or fine-grained equivalent
- If the token has wider access than needed, warn the user loudly

## Stage 2: Repo walk

Two modes:

**Shallow clone (default):**
- `git clone --depth 1 {url} /tmp/people-helper-{hash}`
- Walk the local filesystem
- Pro: works with any GitHub URL, no API rate limits
- Con: requires the PAT to be cloneable (private repos only with valid PAT)

**API walk (`--no-clone`):**
- `GET /repos/{owner}/{repo}/contents/{path}` recursively
- Pro: no local clone
- Con: rate limits (5000/hr for authenticated), slower for large repos

## Stage 3: Module map

Detect:
- Primary language(s) — GitHub API returns this directly
- Build/config files — `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`, `Gemfile`, `setup.py`, `requirements.txt`, etc.
- Source directories — `src/`, `lib/`, `internal/`, `app/`, `cmd/`
- Test directories — `tests/`, `test/`, `__tests__/`, `*_test.go`, `*Test.java`
- Documentation — `README*`, `docs/`, `*.md`, `LICENSE*`
- Configuration — `*.yaml`, `*.json` (excluding `package.json` etc.)

Build a tree: directory → files → detected role (source, test, config, doc).

## Stage 4: Extractable detection

Heuristics per language. A file is "extractable" if it satisfies most of these:

**Universal heuristics:**
- Small to medium size (10–500 LOC)
- Has docstrings / comments / doc comments
- Few or no imports of internal modules
- Has corresponding tests
- File name suggests utility: `util*`, `helper*`, `common*`, `lib*`, `*helper*`
- Doesn't depend on environment variables or external services
- Doesn't import main app modules (i.e., not coupled to the project)

**Per-language:**
- Python: standalone module, no relative imports of project internals, no CLI entry points
- TypeScript/JS: pure function, no React/Vue component context, no DOM dependencies
- Go: package is `package <name>`, no main, exported identifiers only
- Rust: `pub` items in a lib crate, no binary-specific code
- Java: public classes with no Spring/J2EE dependencies
- C/C++: header + impl pair, no main, no project-specific types

**Optional LLM-assisted detection:**
If running with an LLM backend (Hermes skill mode), the LLM can propose extractables that pure heuristics miss. Pass the repo structure + file contents (chunked) to the LLM, ask for "list of standalone utilities worth extracting as open source."

This is opt-in. The CLI defaults to heuristics-only for reproducibility and speed.

## Stage 5: GitHub search

For each candidate:
1. Build a search query: function/class name + key concepts from docstring + language
2. Call `GET /search/repositories?q={query}+language:{lang}`
3. Filter results:
   - `stars >= min-stars`
   - `pushed_at` within last 24 months (active)
   - Same primary language
   - Not the user's own other repos
4. For top 5 results, fetch README snippet via `GET /repos/{owner}/{repo}/readme`
5. Compare: what does the candidate do that existing doesn't? Same? Different approach?

**Rate limit handling:**
- GitHub allows 5000 req/hr for authenticated users
- People Helper makes ~3-5 API calls per candidate
- 10 candidates = ~50 calls. Well within limits.
- If rate-limited, surface a clear error and offer to wait or skip

## Stage 6: Scoring

Each candidate gets three scores (0-10):

**open_sourceability:**
- + Has tests (file or directory present)
- + Has clear docstrings
- + Low dependency footprint (≤3 internal, ≤5 external)
- + License-compatible (no GPL if MIT is the target, no proprietary imports)
- + Self-contained (no environment vars, no external services)
- − Uses internal types not extractable
- − Tightly coupled to project conventions

**uniqueness:**
- − GitHub search returns 10+ similar projects with high stars
- − Existing projects are actively maintained
- + Existing projects are abandoned (last commit > 2 years)
- + Existing projects don't cover a key feature the candidate has
- + Candidate has a different approach (faster, simpler, etc.)

**ship_effort (lower is better, displayed as "estimated hours"):**
- 1-2 hours: standalone function, just needs README + pyproject
- 3-6 hours: small module, needs tests + docs
- 1-2 days: medium module, needs refactoring + comprehensive tests
- 3+ days: large module, needs significant cleanup

**Combined score:** `0.4 * open_sourceability + 0.4 * uniqueness + 0.2 * (10 - normalize(ship_effort))`

Top N (default 10) by combined score go in the report.

## Stage 7: Report generation

Markdown template, filled with scored candidates. Structure:

```markdown
# People Helper Report

**Repo:** {owner}/{name}
**Generated:** {ISO timestamp}
**Primary language:** {lang}
**Candidates analyzed:** {N}
**Top candidates:** {N}

---

## Top candidates

### 1. {name} — Combined score: {score}/10

**Location:** `path/to/file.ext:lines`
**Language:** {lang}
**Open sourceability:** {x}/10
**Uniqueness:** {x}/10
**Estimated ship effort:** {hours}

**What it does:**
{1-2 sentence description from docstring}

**Why it's extractable:**
- {bullet from heuristic}

**Similar projects on GitHub:**
- [{repo1}](url) — {stars}⭐, last commit {date}
  - {comparison: what's the same, what's different}
- [{repo2}](url) — {stars}⭐, last commit {date}
  - {comparison}
- (or "No similar projects found" if zero results)

**Your differentiators (from your code):**
- {bullet grounded in the actual code}

**Suggested name:** {suggested_name}
**Suggested license:** {MIT|Apache-2.0|BSD-3}
**Suggested tags:** {keywords}

**Starter scaffold:**
```{lang}
{first 30 lines of the candidate, ready to be lifted out}
```

---

### 2. {next candidate}
...
```

After top N, a **Lower-ranked candidates** section with one-liner each. Then a **Skipped files** section explaining why each was rejected.

## Threat model

**What we're defending against:**

1. **Accidental data leakage.** The skill reads private code. It must not transmit that code anywhere except to GitHub's official API (and only for the specific repo the user authorized).

2. **Token misuse.** A user accidentally pastes a wide-scope PAT. The skill must refuse to run.

3. **Scope creep.** A future contributor adds a write operation. The architecture review must catch it.

**What we explicitly don't defend against:**

- A malicious user deliberately running the skill on someone else's code
- A compromised machine (sketch on disk can be exfiltrated)
- The user running the skill against their own code and then publishing the report publicly (the report is theirs to share or not)

**Safety mechanisms:**

- PAT scope check at startup, refuses to run with broad scopes
- All network calls go to `api.github.com` only (no other hosts)
- No `git push` anywhere in the codebase
- No write API calls (POST, PUT, PATCH, DELETE)
- Local clone is in a temp directory, cleaned up on exit
- Report generation is fully local

## Future extensions (v2+)

These are out of scope for v0.1 but documented so the architecture doesn't paint us into a corner:

- **Multiple repo analysis** — find shared utilities across a user's repos
- **Auto-scaffolding** — actually create the new public repo with the extracted code (would require a write PAT, opt-in)
- **Diff against existing projects** — show line-by-line what your implementation does differently
- **License compatibility checker** — flag if any imported dependency is GPL
- **Continuous monitoring** — re-run weekly, alert when new similar projects appear
- **Team workflows** — share reports, vote on candidates, assign extraction tasks

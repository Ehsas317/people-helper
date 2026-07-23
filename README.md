# People Helper

**Find what's extractable from your private code, before someone else does.**

People Helper reads a GitHub repository (private or public) and identifies components that could be spun off as standalone side projects or contributed to open source. It then searches GitHub for similar projects, scores the competitive landscape, and produces a structured report showing **what's worth extracting, what's already out there, and how yours can be better**.

Read-only by design. The skill never modifies the target repository.

---

## What it does

1. Walks the repository and builds a module map
2. Detects candidate extractables: standalone utilities, reusable patterns, algorithms, scripts
3. Scores each candidate on open-sourceability, uniqueness, and ship effort
4. Searches GitHub for similar projects and compares them
5. Produces a markdown report with differentiators, suggested names, and starter scaffolds

## What it doesn't do

- **Never writes to your repo.** Read-only. That's the whole point.
- **Never requires write/admin scopes** on the GitHub PAT.
- **Never makes network calls beyond GitHub's public API.**
- **Never sends your code anywhere.** Analysis is local.

## Quick start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Create a fine-grained PAT at https://github.com/settings/personal-access-tokens/new
#    - Resource owner: only the repos you want to analyze
#    - Permissions: Contents (read-only), Metadata (read-only)
#    - No other scopes
#    - No expiration longer than 90 days

# 3. Configure
cp .env.example .env
# Edit .env and set PEOPLE_HELPER_PAT=github_pat_...

# 4. Run
python people_helper.py --repo https://github.com/you/your-private-repo
# Or by owner/name:
python people_helper.py --repo you/your-private-repo

# 5. Read the report
cat report.md
```

## CLI flags

| Flag | Default | Description |
|---|---|---|
| `--repo` | (required) | GitHub repo URL or `owner/name` |
| `--output` | `report.md` | Output report path |
| `--max-candidates` | `10` | Max extractables to surface |
| `--min-stars` | `5` | Min stars for similar projects to surface |
| `--language` | (auto) | Filter extractables to a specific language |
| `--no-network` | off | Skip GitHub search (local-only mode) |
| `--verbose` | off | Verbose logging |

## Output

A single markdown file containing:

- **Top candidates** (sorted by combined score)
- For each candidate: location, why extractable, similar projects, your differentiators, suggested name, license, starter scaffold
- **Lower-ranked candidates** (one-line summary each)
- **Skipped files** (and why)

## Use as a Hermes skill

See `SYSTEM_PROMPT.md`. Drop the prompt into a Hermes skill definition and the model becomes People Helper.

## License

MIT

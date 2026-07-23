# People Helper

**You have a private repo with a function that would make someone's week.**

You just don't know which function. And you definitely don't know if it already exists on GitHub.

People Helper reads your repo (read-only, you keep your secrets), finds the parts of your code that could stand on their own as a side project or an open-source library, checks if anyone else has already built it, and tells you **what to ship, why yours is different, and how to start**.

No write access. No code leaves your machine. No hype. Just: "here's the gold in your private repo, and here's whether anyone's already panned that stream."

---

## Look, you've been here before

You wrote a clever retry-with-rate-limit decorator six months ago. It's 87 lines, has tests, works beautifully, and lives in `src/utils/` of a project nobody outside your team will ever see.

Or maybe it's a SSRF-protection module. Or a `loop_detection.py` that notices when an agent is stuck. Or a config loader. Or a `subdomain_takeover.py` with 43 fingerprints. Things that would take someone else a week to write from scratch, sitting in your private repo, slowly going stale.

You told yourself you'd extract it "someday." Then someday didn't show up.

**People Helper is someday-with-a-deadline.** It reads the repo, surfaces the candidates, scores them, and tells you the top 3 to ship. You can ignore it. But you'll know.

---

## What it actually does

1. **Reads your repo** with a fine-grained GitHub PAT (Contents: Read + Metadata: Read only). It will refuse to run if you give it a classic PAT or any write scope. This is enforced in the code, not in the docs.
2. **Walks the file tree** and finds candidate components: small, docstringed, tested, low-coupling, utility-named files that don't import the rest of your app.
3. **Skips the noise** — Next.js route files, framework pages, `__init__.py`, test files, config files, anything that screams "I am coupled to this project on purpose."
4. **Searches GitHub** for similar projects. Filters by language, star count, and recency.
5. **Scores each candidate** on open-sourceability (tests, docs, low coupling, license-clean), uniqueness (how crowded the existing landscape is), and ship effort (hours, not days).
6. **Writes a markdown report** ranking the top 10 candidates with: location, scores, similar projects, your differentiators (grounded in the actual code, not vibes), suggested name and license, and a 30-line starter scaffold you can lift straight out.

No LLM. No magic. Heuristics + the GitHub API. Reproducible. Auditable. Boring tech on purpose.

---

## What it doesn't do

- **Never writes to your repo.** Read-only. The whole point.
- **Never requires write or admin scopes.** If your PAT is broader than Contents: Read + Metadata: Read, the CLI refuses to run.
- **Never transmits your code anywhere** except to `api.github.com` for the search calls. The repo is shallow-cloned to a temp dir and deleted on exit, every time.
- **Never makes stuff up.** If GitHub search returns zero similar projects, the report says "no similar projects found." No fabricated alternatives, no hallucinated competitors, no "this is a revolutionary new approach" when it isn't.

---

## Quick start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Create a fine-grained PAT
#    Go to https://github.com/settings/personal-access-tokens/new
#    - Resource owner: only the repos you want to analyze
#    - Permissions: Contents (Read), Metadata (Read). Nothing else.
#    - Expiration: 90 days or less
#
#    DO NOT use a classic PAT. The CLI will refuse to run.

# 3. Set the PAT
cp .env.example .env
# Edit .env and paste your PAT after PEOPLE_HELPER_PAT=

# 4. Run it on something
python people_helper.py --repo owner/private-repo
# Or just owner/name, or the full URL — all three work.

# 5. Read the report
cat report.md
```

That's it. The report is a single markdown file. No signup, no dashboard, no telemetry, no "create an account to see your results."

---

## What the report actually looks like

Real output from running on `Ehsas317/lizard-810` (a TypeScript bug bounty platform):

```markdown
### 1. `ssrf-protection.ts` — Combined score: 7.4/10

**Location:** `src/lib/ssrf-protection.ts`
**Language:** TypeScript
**Open sourceability:** 7/10
**Uniqueness:** 8/10
**Estimated ship effort:** 3 hours
**LOC:** 92
**Has tests:** no
**Has docstring:** yes

**Docstring / module doc:**
\`\`\`typescript
// ═══════════════════════════════════════════════════════════════════════════════
// Lizard810 — SSRF Protection Module
// ═══════════════════════════════════════════════════════════════════════════════
// Prevents the tool from scanning internal/private IPs.
// Without this, a malicious target URL could make the scanner hit:
//   - 127.0.0.1:11434 (your Ollama instance)
//   - 169.254.169.254 (AWS/IMDS metadata endpoint)
//   - 10.x.x.x (internal services)
//   - 192.168.x.x (LAN devices)
\`\`\`

**Similar projects on GitHub:** None found.

**Suggested name:** `ssrf-protection`
**Suggested license:** MIT

**Starter scaffold:**
\`\`\`typescript
[first 30 lines of the file, ready to lift out into a new repo]
\`\`\`
```

The report tells you: this file is 92 lines, has clear docs, has no internal dependencies, would take 3 hours to package, and as far as GitHub knows, nobody has built a focused SSRF IP-blocklist module like this. **You should ship it.**

The model doesn't say "you should ship it." It just shows you the score and lets you decide.

---

## CLI flags

| Flag | Default | What it does |
|---|---|---|
| `--repo` | (required) | GitHub URL, `owner/name`, or `git@github.com:owner/name.git` |
| `--output` | `report.md` | Where to write the report |
| `--max-candidates` | `10` | Cap the top-N list size |
| `--min-stars` | `5` | Only surface similar projects with at least this many stars |
| `--language` | (auto) | Force-restrict to one language (Python, TypeScript, Go, ...) |
| `--no-network` | off | Skip GitHub search. Local-only mode. Useful for air-gapped analysis. |
| `--verbose` | off | Show what the CLI is doing at each stage |

---

## How scoring works

Each candidate gets three numbers, all 0-10:

**Open sourceability** — can it be packaged and published without weeks of cleanup?
- +3 has tests
- +2 has docstring / module-level comment
- +2 zero internal imports (doesn't depend on the rest of the project)
- +2 ≤3 external dependencies
- +1 utility-named (helper, util, protection, guard, ...)

**Uniqueness** — is there a gap on GitHub for this thing?
- 0 search results → 8 (very niche, no existing project)
- 1-2 results → 6
- 3-5 results → 4
- 6+ results → 2 (crowded, hard to differentiate)

**Ship effort** — how much work, in hours, to turn this into a shippable artifact?
- < 50 LOC → 1.5h
- 50-149 LOC → 3h
- 150-299 LOC → 6h
- 300-499 LOC → 16h

**Combined** = `0.4 × open_sourceability + 0.4 × uniqueness + 0.2 × (10 − ship_effort_hours)`

Maximum 10. The top 10 by combined score go in the report.

---

## The trust boundary, in case you skipped to here

People Helper is read-only by design. It will not:

- Push code, create commits, or modify your repo
- Create issues, pull requests, or new repos
- Transmit your private code to any third party
- Operate on a PAT with any write scope

This is enforced in the code, not just documented. The CLI checks the PAT scope at startup and refuses to run with anything broader than fine-grained Contents: Read + Metadata: Read. The clone is created with `git clone --depth 1` (read-only fetch), lived in a temp dir, and deleted on exit. All GitHub API calls are GET only.

If you ask the skill (in any of its installed forms) to push, commit, or modify the repo, it declines. This is a feature, not a missing feature.

---

## Use it as a skill in your favorite LLM

The `skill/` directory has ready-to-install exports for:

- **Claude Skills** — `SKILL.md`, upload the whole `skill/` as a `.skill` archive
- **OpenAI Custom GPTs** — `platforms/gpt.md` as Instructions, `platforms/mcp.json` as Actions
- **Hermes Agent** — `platforms/hermes.yaml`
- **Cursor** — `platforms/cursor.md` as `.cursorrules`
- **Cline** — `platforms/cline.md` as Custom Instructions
- **MCP server** — `platforms/mcp.json`

All six enforce the same read-only trust boundary. The skill is the same idea, just phrased in each platform's native vocabulary.

Build the portable archive with:

```bash
cd skill && ./build.sh
# Output: ../people-helper.skill (a tar.gz, uploadable to Claude Skills)
```

---

## Why I built this

I have a private repo with 167 MB of code. Some of it is genuinely useful to other people. Some of it already exists on GitHub and I shouldn't bother. I had no way to tell which was which without opening every file and googling every idea. People Helper is the missing tool.

If you've ever written a private utility and thought "this is too small to extract but also too good to leave buried" — this is for you.

---

## License

MIT

# People Helper — Skill Package

This directory contains the People Helper skill in multiple formats, ready to install in any LLM platform that supports skills or custom instructions.

## What's in here

```
skill/
├── SKILL.md              # Claude Skills format (primary)
├── manifest.yaml         # Skill metadata
├── build.sh              # Builds the .skill archive
├── platforms/
│   ├── claude.md         # (alias for SKILL.md)
│   ├── gpt.md            # OpenAI Custom GPT instructions
│   ├── hermes.yaml       # Hermes Agent config
│   ├── cursor.md         # Cursor .cursorrules
│   ├── cline.md          # Cline system prompt
│   └── mcp.json          # MCP server config
├── references/
│   ├── heuristics.md     # Detailed extractable detection
│   └── github-api.md     # GitHub API endpoints
└── scripts/
    └── people_helper.py  # Standalone CLI implementation
```

## Install

### Claude Skills

```bash
./build.sh
# Upload the resulting ../people-helper.skill to Claude
```

Or copy `SKILL.md` directly into a Claude Project's custom instructions.

### OpenAI Custom GPT

1. Create a new GPT at https://chatgpt.com/gpts/editor
2. Paste the contents of `platforms/gpt.md` into the **Instructions** field
3. Add conversation starters (also in `gpt.md`)
4. Configure Actions using the OpenAPI schema in `platforms/mcp.json`

### Hermes Agent

Copy `platforms/hermes.yaml` into your Hermes skills directory. The `system_prompt` field contains the full skill prompt.

### Cursor

Copy `platforms/cursor.md` to `.cursorrules` in the root of the repo you want to analyze.

### Cline

In Cline's settings, paste the contents of `platforms/cline.md` into the **Custom Instructions** field.

### MCP server

Use `platforms/mcp.json` as the server definition. The `analyze_repo` tool is the entry point.

## Use

Once installed, the skill activates when a user asks things like:
- "Analyze my repo"
- "Find extractables"
- "What can I open source from my code?"
- "Scan my private repo"
- "People helper"

The user must provide a fine-grained GitHub PAT with:
- Contents: Read
- Metadata: Read
- Only the specific repos to analyze
- 90 days or less expiration

The skill refuses to run with broader scopes.

## Trust boundary

This skill is **read-only by design**. It will not:
- Push code
- Create repos
- File issues or PRs
- Edit files in the target repository
- Transmit the user's code to any third party

If the user asks for any of those things, the skill declines and explains.

## Build the .skill archive

```bash
./build.sh
```

This creates `../people-helper.skill` (a tar.gz containing the package). Upload this to Claude as a skill, or distribute it as a portable artifact.

## License

MIT


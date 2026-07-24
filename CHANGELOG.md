# Changelog

## [1.0.0] — 2024-07-24

First public release.

### Core
- 6-dimension scoring: code quality (25%), usefulness (20%), uniqueness (15%), relevance (15%), maintainability (15%), demand signal (10%)
- Extraction verification: relative import detection, sibling resolution, hard-block missing siblings
- License detection: flags repos without LICENSE/COPYING/UNLICENSE as legally risky
- Hard gate: if relevance < 3.0, combined score is halved

### Language Support
- 13 languages: Python, TypeScript, JavaScript, Go, Rust, Java, Kotlin, C, C++, C#, Ruby, PHP, Swift
- Per-language handler architecture under `src/people_helper/languages/`
- Python: full AST-based analysis (cyclomatic complexity, fan-in, import cycle detection)
- All languages: relative import detection, external import extraction, public API counting, docstring detection, LOC counting

### Security
- Fine-grained PAT model: hard-rejects write-capable scopes (`repo`, `admin`, `write:*`)
- Read-only by design: no pushes, no PRs, no issue creation
- PAT redaction in error messages
- Temp directory cleanup on all failure paths
- Privacy contract: never leaks analyzed-repo details in persisted output

### AI Skill Packaging
- Installable skill for Claude, GPT, Cursor, Cline, Hermes, and MCP
- See `skill/` directory for platform-specific exports

### Testing
- 92 unit tests covering all language handlers, extraction verification, and edge cases
- Validated against 110 open-source repositories (449,283 files, 0 crashes)

# Contributing to People Helper

Thanks for your interest in contributing! This document covers everything you need to get started.

## Getting Started

1. Fork the repo on GitHub
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/people-helper.git`
3. Set up a virtualenv (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
4. Install dependencies: `pip install -r requirements.txt`
5. Install in development mode: `pip install -e .`
6. Install dev tools (optional but recommended): `pip install -e ".[dev]"`
7. Run tests: `python -m unittest tests.test_people_helper -v`

## Development Workflow

1. Create a branch: `git checkout -b my-fix`
2. Make changes
3. Run tests: `python -m unittest tests.test_people_helper`
4. Run coverage (optional): `coverage run -m unittest tests.test_people_helper && coverage report`
5. Commit: `git commit -m "Fix: description"`
6. Push: `git push origin my-fix`
7. Open a PR

### Pre-commit hooks (optional)

Install pre-commit hooks to catch issues before pushing:

```bash
pip install pre-commit
pre-commit install
```

## Architecture

People Helper uses a language-handler architecture:

```
src/people_helper/
├── languages/           # One module per language family
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
├── search.py            # GitHub search
├── report.py            # Markdown report generation
├── extractor.py         # --extract: copy files + scaffolds
├── naming.py            # Package name + tag suggestions
├── pat.py               # PAT scope verification
├── cli.py               # CLI main() function
├── __main__.py          # `python -m people_helper` entry
├── __init__.py          # Public API re-exports
└── models.py            # Candidate + SimilarProject dataclasses
```

Each language handler exposes a consistent interface:
- `extract_relative_imports(content)` → `[(name, parent_level), ...]`
- `extract_external_imports(content)` → `[name, ...]`
- `count_public_api(content)` → `(count, [names])`
- `detect_docstring(content)` → `(found, snippet)`
- `count_imports(content, project_modules)` → `(internal, external)`
- `count_loc(content)` → `int`
- `get_complexity(content)` → `int` (AST for Python, regex for others)
- `get_dependency_weight(imports)` → `(weight, is_stdlib_only)` (has a default in base.py)

## Adding a New Language

Adding a new language is NOT a one-file change — there are several touch points.
The handler abstraction isolates language-specific DETECTION logic, but other
parts of the codebase need updating too:

1. **Create the handler**: `src/people_helper/languages/your_lang.py`
   - Subclass `LanguageHandler` and implement all abstract methods
2. **Register the handler**: `src/people_helper/languages/__init__.py`
   - Add to `_HANDLERS` dict mapping each file extension to your handler instance
3. **Add the extension**: `LANG_BY_EXT` in `config.py`
4. **Add language tags**: `lang_tags` dict in `report.py` (for markdown code-fence language)
5. **Add manifest generator** (if `--extract` should support it): `extractor.py`
   - Add a `_generate_<lang>_manifest` function
   - Add a branch in `extract_candidate`'s manifest dispatch
6. **Add README install/usage** (if `--extract` should support it): `extractor.py` `_generate_readme`
7. **Add fix-relative-imports support** (if the language has relative imports): `extractor.py` `fix_relative_imports`
8. **Add tests**: `tests/test_people_helper.py` (create a `TestYourLangHandler` class)
9. **Update documentation**:
   - Language table in `README.md` (§Supported languages)
   - Language table in `SKILL.md`
   - `CHANGELOG.md` (under `[Unreleased]` → `### Added`)
   - `references/heuristics.md` if the language has unusual relative-import syntax

## Testing

- All tests in `tests/test_people_helper.py`
- Run with: `python -m unittest tests.test_people_helper -v`
- 253 tests covering all language handlers, extraction verification, scoring, search, and edge cases
- Tests run in <1 second
- Coverage: ~69% (config.py, models.py at 100%; pat.py and checks.py at 0% — contributions welcome)

## Security

People Helper is **read-only by design**. Never add:
- Write operations to GitHub (no push, no PR, no issue creation)
- File modifications to the analyzed repo
- Third-party data transmission (no analytics, no telemetry)
- PAT logging or echo (the PAT must be redacted in ALL error messages)
- `shell=True` in subprocess calls (always use list args)
- Skipping of symlink protection in `walk_repo`

See [SECURITY.md](SECURITY.md) for the full security model.

## Reporting Bugs

Open an issue using the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
Include:

1. The repo you were analyzing (or a minimal reproducer)
2. The exact command you ran
3. The error or unexpected output
4. Run with `--debug` and include the stack trace (if applicable)
5. People Helper version (`people-helper --version`)
6. Python version (`python --version`)
7. Your OS
8. PAT type (classic / fine-grained)
9. Whether you used `--no-network`, `--check`, or `--extract`

## Reporting Security Vulnerabilities

DO NOT open a public issue. See [SECURITY.md](SECURITY.md) for the reporting process.

## Code Style

- PEP 8 (line length 120, not 79)
- 4-space indentation (no tabs)
- f-strings preferred over `.format()` or `%`
- Type hints encouraged (especially on public functions)
- Module-level docstring at the top of every `.py` file
- Functions should be <50 LOC; refactor longer ones
- No `print()` for diagnostic output in library modules (use `logging` or return structured data)

## License

By contributing, you agree that your contributions will be licensed under the
MIT license (see [LICENSE](LICENSE)).

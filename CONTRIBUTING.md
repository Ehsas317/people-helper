# Contributing to People Helper

## Getting Started

1. Fork the repo
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/people-helper.git`
3. Install dependencies: `pip install -r requirements.txt`
4. Run tests: `python -m unittest tests.test_people_helper -v`

## Development Workflow

1. Create a branch: `git checkout -b my-fix`
2. Make changes
3. Run tests: `python -m unittest tests.test_people_helper`
4. Commit: `git commit -m "Fix: description"`
5. Push: `git push origin my-fix`
6. Open a PR

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
└── ...
```

Each language handler exposes a consistent interface:
- `extract_relative_imports(content)` → `[(name, parent_level), ...]`
- `extract_external_imports(content)` → `[name, ...]`
- `count_public_api(content)` → `(count, [names])`
- `detect_docstring(content)` → `(found, snippet)`
- `count_imports(content, project_modules)` → `(internal, external)`
- `count_loc(content)` → `int`
- `get_complexity(content)` → `int` (Python only)
- `get_dependency_weight(imports)` → `(weight, is_stdlib_only)`

## Adding a New Language

1. Create `src/people_helper/languages/your_lang.py`
2. Subclass `LanguageHandler` and implement all abstract methods
3. Register in `src/people_helper/languages/__init__.py`
4. Add the extension to `LANG_BY_EXT` in `config.py`
5. Add tests in `tests/test_people_helper.py`
6. Update the language table in `README.md` and `SKILL.md`

## Testing

- All tests in `tests/test_people_helper.py`
- Run with: `python -m unittest tests.test_people_helper -v`
- 92 tests covering all language handlers, extraction verification, and edge cases
- Tests verified against 110 open-source repos (see `material` repo for batch test results)

## Security

People Helper is **read-only by design**. Never add:
- Write operations to GitHub
- File modifications to the analyzed repo
- Third-party data transmission
- PAT logging or echo

## Reporting Bugs

Open an issue with:
1. The repo you were analyzing (or a minimal reproducer)
2. The command you ran
3. The error or unexpected output
4. Your OS and Python version

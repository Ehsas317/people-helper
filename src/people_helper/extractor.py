"""Stage 8: Extraction — actually copy files out of the repo.

This is the feature that turns People Helper from a discovery tool into an
extraction tool. Given a candidate and the cloned repo, it:

1. Copies the candidate file (and any siblings for multi-file extractions)
2. Strips license headers (Apache 2.0, MIT, etc.) — they belong to the
   source repo, not the extracted package
3. Generates a minimal pyproject.toml / package.json / Cargo.toml / go.mod
   with the suggested name, license (MIT), and dependencies
4. Writes a README.md with what-it-does, usage, and attribution

The extracted package is NOT ready to publish — the user still needs to:
- Review the code
- Adjust imports if needed
- Add tests
- Choose a final license

But it's a real starting point, not just "first 30 lines of the file".
"""
import re
import shutil
from pathlib import Path
from .naming import suggest_name, suggest_tags
from .models import Candidate


# License header patterns to strip (multi-line block comments at the top)
_LICENSE_HEADER_PATTERNS = [
    # Apache 2.0: /*\n * Copyright ...\n * Licensed under ...\n */
    (r'^/\*\s*\n(\s*\*.*\n)+?\s*\*/\s*\n', "Apache 2.0 block"),
    # MIT: /*\n * Copyright (c) ...\n * Permission is hereby granted...\n */
    (r'^/\*\s*\n(\s*\*.*\n)+?\s*\*/\s*\n', "MIT block"),
    # Python: #!/usr/bin/env python3\n# Copyright...\n# ...\n
    (r'^(#!.*\n)?(#\s*(Copyright|Licensed|Permission is hereby|MIT License|Apache License).*\n)+(#\s*.*\n)*', "Python hash"),
    # Go: // Copyright ...\n// Licensed ...\n
    (r'^(//\s*(Copyright|Licensed|Permission is hereby|MIT License|Apache License).*\n)+(//\s*.*\n)*', "Go line"),
    # Rust: //! Copyright ... or //! Licensed ...
    (r'^(//!\s*(Copyright|Licensed|Permission is hereby|MIT License|Apache License).*\n)+(//!\s*.*\n)*', "Rust doc"),
]


def strip_license_header(content: str, ext: str) -> tuple:
    """Strip license header from content. Returns (stripped_content, lines_removed)."""
    original_lines = content.count("\n")
    for pattern, _name in _LICENSE_HEADER_PATTERNS:
        m = re.match(pattern, content, re.MULTILINE)
        if m:
            stripped = content[m.end():]
            # Don't strip if it removes more than 50 lines (probably not a license)
            lines_removed = m.group(0).count("\n")
            if lines_removed <= 50:
                return stripped.lstrip("\n"), lines_removed
    return content, 0


def _generate_pyproject_toml(name: str, candidate: Candidate, tags: list) -> str:
    """Generate a minimal pyproject.toml for a Python package."""
    return f"""[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
description = "{candidate.what_it_does[:100] if candidate.what_it_does else 'Extracted utility'}"
readme = "README.md"
requires-python = ">=3.9"
license = {{ text = "MIT" }}
authors = [{{ name = "Your Name", email = "you@example.com" }}]
keywords = {tags}
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

[project.urls]
Homepage = "https://github.com/your-username/{name}"

[tool.hatch.build.targets.wheel]
packages = ["{name.replace('-', '_')}"]
"""


def _generate_package_json(name: str, candidate: Candidate, tags: list) -> str:
    """Generate a minimal package.json for a JS/TS package."""
    return f"""{{
  "name": "{name}",
  "version": "0.1.0",
  "description": "{candidate.what_it_does[:100] if candidate.what_it_does else 'Extracted utility'}",
  "main": "index.js",
  "types": "index.d.ts",
  "scripts": {{
    "test": "echo \\"Error: no test specified\\" && exit 1",
    "build": "tsc"
  }},
  "keywords": {tags},
  "author": "Your Name <you@example.com>",
  "license": "MIT",
  "repository": {{
    "type": "git",
    "url": "https://github.com/your-username/{name}.git"
  }}
}}
"""


def _generate_cargo_toml(name: str, candidate: Candidate, tags: list) -> str:
    """Generate a minimal Cargo.toml for a Rust package."""
    return f"""[package]
name = "{name}"
version = "0.1.0"
edition = "2021"
description = "{candidate.what_it_does[:100] if candidate.what_it_does else 'Extracted utility'}"
license = "MIT"
keywords = {tags}
repository = "https://github.com/your-username/{name}"

[dependencies]
"""


def _generate_go_mod(name: str, candidate: Candidate) -> str:
    """Generate a minimal go.mod for a Go package."""
    # Sanitize module name for Go (lowercase, no dashes)
    module_name = re.sub(r"[^a-z0-9/]", "", name.lower().replace("-", ""))
    return f"""module github.com/your-username/{module_name}

go 1.21
"""


def _generate_readme(name: str, candidate: Candidate, source_repo: str, tags: list) -> str:
    """Generate a README.md with usage and attribution."""
    what_it_does = candidate.what_it_does or "Extracted utility"
    tags_str = " ".join(f"`{t}`" for t in tags) if tags else "utility"
    return f"""# {name}

{what_it_does}

## Installation

```bash
pip install {name}
```

## Usage

```python
import {name.replace('-', '_')}
```

## License

MIT

## Attribution

This package was extracted from [`{source_repo}`](https://github.com/{source_repo}).
Original code is under that repo's license; this extraction is MIT-licensed.

## Tags

{tags_str}
"""


def fix_relative_imports(content: str, ext: str) -> str:
    """Fix relative imports in extracted code.

    For single-file extractions, relative imports point to siblings that
    aren't included. We replace them with comments so the code doesn't
    crash on import — the user must implement or install the dependency.
    """
    lines = content.splitlines()
    fixed = []
    for line in lines:
        stripped = line.strip()
        if ext == ".py":
            # from . import X / from .X import Y / from .. import Z
            if re.match(r'^\s*from\s+\.+', line):
                fixed.append(f"# TODO: {stripped} — relative import, provide this module or install it")
                continue
        elif ext in {".ts", ".tsx", ".js", ".jsx"}:
            # import { foo } from './utils' / require('./utils')
            if re.search(r"""(?:from|require\()\s*['"]\.{1,2}/""", line):
                fixed.append(f"// TODO: {stripped} — relative import, provide this module or install it")
                continue
        elif ext == ".rs":
            # use super::X / use crate::X / use self::X
            if re.match(r'^\s*use\s+(super|crate|self)::', line):
                fixed.append(f"// TODO: {stripped} — relative import, provide this module or install it")
                continue
        fixed.append(line)
    return "\n".join(fixed)


def extract_candidate(candidate: Candidate, clone_path: Path, output_dir: Path, source_repo: str) -> Path:
    """Extract a single candidate (and its siblings) to output_dir.

    Returns the path to the extracted package directory.
    """
    name = candidate.suggested_name or suggest_name(candidate)
    tags = candidate.suggested_tags or suggest_tags(candidate)
    pkg_dir = output_dir / name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # Collect files to copy (candidate + siblings for multi-file)
    files_to_copy = [(candidate.path, Path(candidate.path).name)]
    for sib in candidate.sibling_paths:
        files_to_copy.append((sib, Path(sib).name))

    # Copy files, stripping license headers and fixing relative imports
    for src_rel, dest_name in files_to_copy:
        src = clone_path / src_rel
        if not src.exists():
            continue
        content = src.read_text(errors="ignore")
        stripped, lines_removed = strip_license_header(content, candidate.language)
        # Fix relative imports (only for single-file — multi-file keeps siblings)
        if candidate.extraction_type == "single":
            stripped = fix_relative_imports(stripped, Path(candidate.path).suffix.lower())
        dest = pkg_dir / dest_name
        dest.write_text(stripped)

    # Generate package manifest
    ext = Path(candidate.path).suffix.lower()
    if ext == ".py":
        (pkg_dir / "pyproject.toml").write_text(_generate_pyproject_toml(name, candidate, tags))
        # Create __init__.py for the package
        pkg_init = pkg_dir / f"{name.replace('-', '_')}" / "__init__.py"
        pkg_init.parent.mkdir(exist_ok=True)
        # Move the main file into the package dir
        main_file = pkg_dir / Path(candidate.path).name
        if main_file.exists():
            shutil.move(str(main_file), str(pkg_init.parent / main_file.name))
    elif ext in {".ts", ".tsx", ".js", ".jsx"}:
        (pkg_dir / "package.json").write_text(_generate_package_json(name, candidate, tags))
    elif ext == ".rs":
        (pkg_dir / "Cargo.toml").write_text(_generate_cargo_toml(name, candidate, tags))
    elif ext == ".go":
        (pkg_dir / "go.mod").write_text(_generate_go_mod(name, candidate))

    # Generate README
    (pkg_dir / "README.md").write_text(_generate_readme(name, candidate, source_repo, tags))

    # Generate LICENSE
    (pkg_dir / "LICENSE").write_text(
        "MIT License\n\nCopyright (c) 2024 Your Name\n\n"
        "Permission is hereby granted, free of charge, to any person obtaining a copy "
        "of this software and associated documentation files (the \"Software\"), to deal "
        "in the Software without restriction, including without limitation the rights "
        "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell "
        "copies of the Software, and to permit persons to whom the Software is "
        "furnished to do so, subject to the following conditions:\n\n"
        "The above copyright notice and this permission notice shall be included in all "
        "copies or substantial portions of the Software.\n\n"
        "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR "
        "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, "
        "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE "
        "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER "
        "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, "
        "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE "
        "SOFTWARE.\n"
    )

    return pkg_dir


def extract_candidates(candidates: list, clone_path: Path, output_dir: Path, source_repo: str,
                       max_extract: int = 5, min_score: float = 6.0, verbose: bool = False) -> list:
    """Extract top candidates to output_dir.

    Only extracts candidates with score >= min_score (default 6.0).
    Returns list of extracted package paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    active = sorted([c for c in candidates if not c.skipped],
                    key=lambda c: c.combined_score, reverse=True)
    to_extract = [c for c in active if c.combined_score >= min_score][:max_extract]

    extracted = []
    for i, cand in enumerate(to_extract, 1):
        if verbose:
            print(f"  [{i}/{len(to_extract)}] Extracting {cand.path} (score {cand.combined_score:.1f})...")
        try:
            pkg_path = extract_candidate(cand, clone_path, output_dir, source_repo)
            extracted.append({
                "candidate": cand.path,
                "package": pkg_path.name,
                "score": cand.combined_score,
                "extraction_type": cand.extraction_type,
                "siblings": cand.sibling_paths,
            })
        except Exception as e:
            if verbose:
                print(f"    WARNING: extraction failed: {e}")

    return extracted

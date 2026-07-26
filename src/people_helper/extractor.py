"""Stage 8: Extraction — actually copy files out of the repo.

Given a candidate and the cloned repo, this module:
1. Copies the candidate file (and any siblings for multi-file extractions)
2. Preserves source copyright headers (required by MIT/Apache/BSD)
3. Generates a minimal pyproject.toml / package.json / Cargo.toml / go.mod
4. Writes a README.md with what-it-does, usage, and attribution
5. Copies the source repo's LICENSE file as SOURCE-LICENSE (for attribution)
6. Writes LICENSE-REVIEW.md walking the user through 5 license scenarios

The extracted package is NOT ready to publish — the user must:
- Review the code
- Adjust imports if needed
- Add tests
- Choose a final license (see LICENSE-REVIEW.md)
"""

import os
import re
import shutil
from pathlib import Path

from .models import Candidate
from .naming import suggest_name, suggest_tags

# License header patterns (used by strip_license_header — kept for backward compat
# and potential future --strip-license-headers flag). Currently extract_candidate
# PRESERVES source copyright headers (required by MIT/Apache/BSD).
_LICENSE_HEADER_PATTERNS = [
    # Apache 2.0: /*\n * Copyright ...\n * Licensed under ...\n */
    (r"^/\*\s*\n(\s*\*.*\n)+?\s*\*/\s*\n", "Apache 2.0 block"),
    # MIT: /*\n * Copyright (c) ...\n * Permission is hereby granted...\n */
    (r"^/\*\s*\n(\s*\*.*\n)+?\s*\*/\s*\n", "MIT block"),
    # Python: #!/usr/bin/env python3\n# Copyright...\n# ...\n
    (
        r"^(#!.*\n)?(#\s*(Copyright|Licensed|Permission is hereby|MIT License|Apache License).*\n)+(#\s*.*\n)*",
        "Python hash",
    ),
    # Go: // Copyright ...\n// Licensed ...\n
    (r"^(//\s*(Copyright|Licensed|Permission is hereby|MIT License|Apache License).*\n)+(//\s*.*\n)*", "Go line"),
    # Rust: //! Copyright ... or //! Licensed ...
    (r"^(//!\s*(Copyright|Licensed|Permission is hereby|MIT License|Apache License).*\n)+(//!\s*.*\n)*", "Rust doc"),
]


def strip_license_header(content: str, ext: str) -> tuple:
    """Strip license header from content. Returns (stripped_content, lines_removed).

    NOTE: This function is provided for completeness but is NOT called by
    extract_candidate — extraction PRESERVES source copyright headers (required
    by MIT/Apache/BSD). This may be wired up to a future --strip-license-headers
    flag for users who explicitly want stripping.
    """
    for pattern, _name in _LICENSE_HEADER_PATTERNS:
        m = re.match(pattern, content, re.MULTILINE)
        if m:
            stripped = content[m.end() :]
            # Don't strip if it removes more than 50 lines (probably not a license)
            lines_removed = m.group(0).count("\n")
            if lines_removed <= 50:
                return stripped.lstrip("\n"), lines_removed
    return content, 0


def _get_author_info() -> tuple:
    """Get author name/email from env vars (with sensible defaults)."""
    name = os.environ.get("PEOPLE_HELPER_AUTHOR_NAME", "Your Name")
    email = os.environ.get("PEOPLE_HELPER_AUTHOR_EMAIL", "you@example.com")
    return name, email


def _get_github_username(source_repo: str) -> str:
    """Extract GitHub username from source_repo (owner/name) for placeholder URLs.

    Falls back to 'your-username' if the source_repo doesn't match owner/name.
    The user should still grep for 'your-username' and replace it.
    """
    if "/" in source_repo:
        owner = source_repo.split("/")[0]
        if owner and re.match(r"^[A-Za-z0-9_-]+$", owner):
            return owner
    return "your-username"


def _generate_pyproject_toml(name: str, candidate: Candidate, tags: list, source_repo: str) -> str:
    """Generate a minimal pyproject.toml for a Python package."""
    author_name, author_email = _get_author_info()
    gh_user = _get_github_username(source_repo)
    desc = (candidate.what_it_does or "Extracted utility")[:100]
    # Escape any double-quotes in description
    desc = desc.replace('"', '\\"')
    # TOML array format: ["a", "b", "c"]
    tags_toml = "[" + ", ".join(f'"{t}"' for t in tags) + "]"
    return f"""[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
description = "{desc}"
readme = "README.md"
requires-python = ">=3.9"
# TODO: confirm license and uncomment. See LICENSE-REVIEW.md.
# license = "MIT"
authors = [{{ name = "{author_name}", email = "{author_email}" }}]
keywords = {tags_toml}
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
# TODO: replace with your actual GitHub URL
Homepage = "https://github.com/{gh_user}/{name}"

[tool.hatch.build.targets.wheel]
packages = ["{name.replace("-", "_")}"]
"""


def _generate_package_json(name: str, candidate: Candidate, tags: list, source_repo: str) -> str:
    """Generate a minimal package.json for a JS/TS package."""
    import json

    author_name, author_email = _get_author_info()
    gh_user = _get_github_username(source_repo)
    desc = (candidate.what_it_does or "Extracted utility")[:100]
    # Use json.dumps for proper JSON string escaping (handles quotes, backslashes, etc.)
    desc_json = json.dumps(desc)
    tags_json = json.dumps(tags)
    return f"""{{
  "name": {json.dumps(name)},
  "version": "0.1.0",
  "description": {desc_json},
  "main": "index.js",
  "types": "index.d.ts",
  "scripts": {{
    "test": "echo \\"Error: no test specified\\" && exit 1",
    "build": "tsc"
  }},
  "keywords": {tags_json},
  "author": {json.dumps(f"{author_name} <{author_email}>")},
  "license": "SEE LICENSE IN LICENSE-REVIEW.md",
  "repository": {{
    "type": "git",
    "url": "https://github.com/{gh_user}/{name}.git"
  }}
}}
"""


def _generate_cargo_toml(name: str, candidate: Candidate, tags: list, source_repo: str) -> str:
    """Generate a minimal Cargo.toml for a Rust package."""
    gh_user = _get_github_username(source_repo)
    desc = (candidate.what_it_does or "Extracted utility")[:100]
    desc = desc.replace('"', '\\"')
    # TOML array format: ["a", "b", "c"]
    tags_toml = "[" + ", ".join(f'"{t}"' for t in tags) + "]"
    return f"""[package]
name = "{name}"
version = "0.1.0"
edition = "2021"
description = "{desc}"
# TODO: confirm license and uncomment. See LICENSE-REVIEW.md.
# license = "MIT"
keywords = {tags_toml}
repository = "https://github.com/{gh_user}/{name}"

[dependencies]
"""


def _generate_go_mod(name: str, candidate: Candidate, source_repo: str) -> str:
    """Generate a minimal go.mod for a Go package."""
    gh_user = _get_github_username(source_repo)
    # Sanitize module name for Go (lowercase, no dashes)
    module_name = re.sub(r"[^a-z0-9/]", "", name.lower().replace("-", ""))
    return f"""module github.com/{gh_user}/{module_name}

go 1.21
"""


def _generate_license_review(source_repo: str) -> str:
    """Generate LICENSE-REVIEW.md walking the user through license scenarios."""
    return f"""# License Review Required

This package was extracted from [`{source_repo}`](https://github.com/{source_repo}).

You MUST determine the correct license before publishing. The original source
file's copyright headers have been preserved (required by most licenses). A copy
of the source repo's LICENSE file (if it existed) is in `SOURCE-LICENSE` for
reference.

## Scenarios

1. **If the source is MIT/Apache-2.0/BSD/ISC (permissive):**
   - You may assign any license to your extraction, including MIT.
   - You MUST preserve the original copyright notice in the source files.
   - For Apache 2.0: also include the original NOTICE file if one exists.
   - Create a LICENSE file with your chosen license text.
   - Update the manifest's license field (e.g., `license = "MIT"` in pyproject.toml).

2. **If the source is GPL/LGPL/AGPL (copyleft):**
   - The extracted package MUST use the SAME copyleft license.
   - Copy the source's LICENSE file as your LICENSE.
   - Update the manifest's license field accordingly.
   - Note: LGPL-3.0 allows the extracted code to remain LGPL while being
     linked into a non-LGPL application; GPL/AGPL does not.

3. **If the source has NO license file:**
   - Under default copyright law, all code is "all rights reserved."
   - Extracting and republishing this code may be a copyright violation.
   - Obtain explicit permission from the copyright holder before publishing.
   - If you have permission, create a LICENSE file documenting the grant.

4. **If the source is BSD-2/3-Clause or ISC:**
   - Compatible with MIT. Preserve the original copyright notice and the
     BSD/ISC license text in your extracted package's LICENSE file.

5. **If the source is MPL-2.0 (file-level copyleft):**
   - MPL-licensed files must remain MPL-2.0 — you cannot relicense them.
   - Apply MPL-2.0 to your extracted package, or remove the MPL-licensed portions.

## Once you have determined the correct license

1. Create a LICENSE file with the chosen license text.
2. Update the manifest's `license` field (e.g., uncomment in pyproject.toml).
3. Delete this LICENSE-REVIEW.md file.
4. Delete SOURCE-LICENSE if you've created your own LICENSE.

## Attribution

This package was extracted from [`{source_repo}`](https://github.com/{source_repo}).
Original code is under that repo's license; this extraction's license is
determined by you per the scenarios above.
"""


def _generate_readme(name: str, candidate: Candidate, source_repo: str, tags: list) -> str:
    """Generate a README.md with usage and attribution."""
    what_it_does = candidate.what_it_does or "Extracted utility"
    tags_str = " ".join(f"`{t}`" for t in tags) if tags else "utility"
    gh_user = _get_github_username(source_repo)
    return f"""# {name}

{what_it_does}

## Installation

```bash
pip install {name}
```

## Usage

```python
import {name.replace("-", "_")}
```

## License

See [LICENSE-REVIEW.md](LICENSE-REVIEW.md) — you must determine the correct
license before publishing this package.

## Attribution

This package was extracted from [`{source_repo}`](https://github.com/{source_repo}).
Original code is under that repo's license; see LICENSE-REVIEW.md for guidance
on what license to apply to this extraction.

## Source

- GitHub: https://github.com/{gh_user}/{name}

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
            if re.match(r"^\s*from\s+\.+", line):
                fixed.append(f"# TODO: {stripped} — relative import, provide this module or install it")
                continue
        elif ext in {".ts", ".tsx", ".js", ".jsx"}:
            # import { foo } from './utils' / require('./utils')
            if re.search(r"""(?:from|require\()\s*['"]\.{1,2}/""", line):
                fixed.append(f"// TODO: {stripped} — relative import, provide this module or install it")
                continue
        elif ext == ".rs":
            # use super::X / use crate::X / use self::X
            if re.match(r"^\s*use\s+(super|crate|self)::", line):
                fixed.append(f"// TODO: {stripped} — relative import, provide this module or install it")
                continue
        fixed.append(line)
    return "\n".join(fixed)


def extract_candidate(candidate: Candidate, clone_path: Path, output_dir: Path, source_repo: str) -> Path:
    """Extract a single candidate (and its siblings) to output_dir.

    Returns the path to the extracted package directory.
    Raises Exception on failure — caller should clean up partial extraction.
    """
    name = candidate.suggested_name or suggest_name(candidate)
    tags = candidate.suggested_tags or suggest_tags(candidate)
    pkg_dir = output_dir / name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Collect files to copy (candidate + siblings for multi-file)
        files_to_copy = [(candidate.path, Path(candidate.path).name)]
        for sib in candidate.sibling_paths:
            files_to_copy.append((sib, Path(sib).name))

        # Copy files, PRESERVING source copyright headers (required by MIT/Apache/BSD).
        # Fix relative imports for single-file extractions so the code doesn't crash on import.
        for src_rel, dest_name in files_to_copy:
            src = clone_path / src_rel
            if not src.exists():
                raise FileNotFoundError(f"Source file not found during extraction: {src_rel}")
            content = src.read_text(errors="ignore")
            # Fix relative imports (only for single-file — multi-file keeps siblings)
            if candidate.extraction_type == "single":
                content = fix_relative_imports(content, Path(candidate.path).suffix.lower())
            dest = pkg_dir / dest_name
            dest.write_text(content, encoding="utf-8")

        # Generate package manifest
        ext = Path(candidate.path).suffix.lower()
        if ext == ".py":
            (pkg_dir / "pyproject.toml").write_text(_generate_pyproject_toml(name, candidate, tags, source_repo), encoding="utf-8")
            # Create __init__.py for the package (Python requires this for a
            # proper package, not just a namespace package)
            pkg_subdir = pkg_dir / name.replace("-", "_")
            pkg_subdir.mkdir(exist_ok=True)
            (pkg_subdir / "__init__.py").write_text(f'"""{name} — extracted from {source_repo}."""\n', encoding="utf-8")
            # Move the main file into the package subdir
            main_file = pkg_dir / Path(candidate.path).name
            if main_file.exists():
                shutil.move(str(main_file), str(pkg_subdir / main_file.name))
            # Move ALL sibling files into the package subdir too (Bug fix:
            # siblings were staying at pkg_dir root, breaking relative imports)
            for sib in candidate.sibling_paths:
                sib_file = pkg_dir / Path(sib).name
                if sib_file.exists():
                    shutil.move(str(sib_file), str(pkg_subdir / sib_file.name))
        elif ext in {".ts", ".tsx", ".js", ".jsx"}:
            (pkg_dir / "package.json").write_text(_generate_package_json(name, candidate, tags, source_repo), encoding="utf-8")
        elif ext == ".rs":
            (pkg_dir / "Cargo.toml").write_text(_generate_cargo_toml(name, candidate, tags, source_repo), encoding="utf-8")
        elif ext == ".go":
            (pkg_dir / "go.mod").write_text(_generate_go_mod(name, candidate, source_repo), encoding="utf-8")

        # Generate README
        (pkg_dir / "README.md").write_text(_generate_readme(name, candidate, source_repo, tags), encoding="utf-8")

        # Generate LICENSE-REVIEW.md (mandatory — user must choose a license)
        (pkg_dir / "LICENSE-REVIEW.md").write_text(_generate_license_review(source_repo), encoding="utf-8")

        # Copy the source repo's LICENSE file as SOURCE-LICENSE for reference
        # (if it exists). This preserves attribution required by MIT/Apache/BSD.
        for license_name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "UNLICENSE"):
            source_license = clone_path / license_name
            if source_license.exists():
                shutil.copy(str(source_license), str(pkg_dir / "SOURCE-LICENSE"))
                break

    except Exception:
        # CRITICAL: Clean up partial extraction dir on any failure.
        # Without this, users would get packages with source-but-no-manifest.
        shutil.rmtree(pkg_dir, ignore_errors=True)
        raise

    return pkg_dir


def extract_candidates(
    candidates: list,
    clone_path: Path,
    output_dir: Path,
    source_repo: str,
    max_extract: int = 5,
    min_score: float = 6.0,
    verbose: bool = False,
) -> list:
    """Extract top candidates to output_dir.

    Only extracts candidates with score >= min_score (default 6.0).
    Returns list of extracted package info dicts.

    Failures are ALWAYS printed to stderr (not just in verbose mode) — silent
    failures are worse than noisy ones when the user is extracting code.
    """
    import sys

    output_dir.mkdir(parents=True, exist_ok=True)
    active = sorted(
        [c for c in candidates if not c.skipped],
        key=lambda c: c.combined_score,
        reverse=True,
    )
    to_extract = [c for c in active if c.combined_score >= min_score][:max_extract]

    extracted = []
    for i, cand in enumerate(to_extract, 1):
        if verbose:
            print(f"  [{i}/{len(to_extract)}] Extracting {cand.path} (score {cand.combined_score:.1f})...")
        try:
            pkg_path = extract_candidate(cand, clone_path, output_dir, source_repo)
            extracted.append(
                {
                    "candidate": cand.path,
                    "package": pkg_path.name,
                    "score": cand.combined_score,
                    "extraction_type": cand.extraction_type,
                    "siblings": cand.sibling_paths,
                }
            )
        except Exception as e:
            # ALWAYS print extraction failures (not verbose-only) — silent failures
            # leave users with half-extracted packages they don't know about.
            print(f"  WARNING: extraction failed for {cand.path}: {e}", file=sys.stderr)

    return extracted

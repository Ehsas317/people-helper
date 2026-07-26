#!/usr/bin/env python3
"""
People Helper — Find code worth extracting, and verify it's actually standalone.

This is the repo-root entry-point script for `python people_helper.py`.
After `pip install`, use `people-helper` (console script) or `python -m people_helper` instead.

Usage:
    python people_helper.py --repo https://github.com/you/repo
    python people_helper.py --repo you/repo --output report.md
    python people_helper.py --repo you/repo --no-network --verbose
    python people_helper.py --repo you/repo --min-score 5.0
    python people_helper.py --repo you/repo --extract ./extracted/

Requires:
    - A fine-grained GitHub PAT in PEOPLE_HELPER_PAT env var
    - PAT must have Contents: Read and Metadata: Read only
    - No write scopes (classic PATs with 'repo' scope are rejected)

Exit codes:
    0 = success
    1 = unexpected error (bug)
    2 = argparse usage error
    3 = auth error (missing/invalid PAT)
    4 = bad input (invalid --repo, --output, --extract, --language)
    5 = repo error (not found, empty, no files)
    130 = interrupted (Ctrl+C)
"""

import os
import sys

# Bootstrap: allow running as `python people_helper.py` from a clone
# (installed-package mode uses src/people_helper/__main__.py instead).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from people_helper.cli import main  # noqa: E402

if __name__ == "__main__":
    main()

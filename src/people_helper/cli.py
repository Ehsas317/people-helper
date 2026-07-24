"""People Helper CLI entry point.

This module is what the `people-helper` console script (defined in
pyproject.toml) calls. It can also be invoked directly:

    python -m people_helper.cli --repo owner/name

Or via the legacy shim at the repo root:

    python people_helper.py --repo owner/name
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Inject src/ onto sys.path so a source checkout works without `pip install .`
# (production installs via pyproject.toml don't need this).
_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from people_helper import __version__  # noqa: E402
from people_helper.detection import detect_candidates  # noqa: E402
from people_helper.naming import suggest_name, suggest_tags  # noqa: E402
from people_helper.pat import check_pat_scope  # noqa: E402
from people_helper.report import generate_report  # noqa: E402
from people_helper.scoring import score_candidate  # noqa: E402
from people_helper.search import (  # noqa: E402
    build_search_query,
    compute_differentiators,
    github_search_repositories,
)
from people_helper.walker import (  # noqa: E402
    clone_repo_shallow,
    detect_primary_language,
    parse_repo_arg,
    walk_repo,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="people-helper",
        description=f"Find what's extractable from your private code. (v{__version__})",
    )
    parser.add_argument("--repo", required=True, help="GitHub repo URL or owner/name")
    parser.add_argument(
        "--output", default="report.md",
        help="Output report path (default: report.md)",
    )
    parser.add_argument(
        "--max-candidates", type=int, default=10,
        help="Max candidates to show in report (default: 10)",
    )
    parser.add_argument(
        "--min-stars", type=int, default=5,
        help="Min stars for similar projects (default: 5)",
    )
    parser.add_argument(
        "--language", help="Filter to one language (e.g. Python)",
    )
    parser.add_argument(
        "--no-network", action="store_true",
        help="Skip GitHub search (local-only mode)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Verbose logging",
    )
    parser.add_argument(
        "--version", action="version", version=f"people-helper {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the People Helper pipeline. Returns exit code."""
    args = build_parser().parse_args(argv)

    # --- PAT check ---
    pat = os.environ.get("PEOPLE_HELPER_PAT")
    if not pat:
        print("Error: PEOPLE_HELPER_PAT environment variable not set.", file=sys.stderr)
        print(
            "Create a fine-grained PAT at "
            "https://github.com/settings/personal-access-tokens/new",
            file=sys.stderr,
        )
        print(
            "Required scopes: Contents: Read, Metadata: Read. "
            "Only the specific repos you want to analyze.",
            file=sys.stderr,
        )
        return 1

    if args.verbose:
        print(f"[1/7] Checking PAT scope... (people-helper v{__version__})")
    check = check_pat_scope(pat)
    if not check["ok"]:
        print(f"Error: {check['error']}", file=sys.stderr)
        return 1
    if args.verbose:
        print(f"  Authenticated as: {check['user']}")
    # Surface a warning for classic PATs, but don't reject them.
    if check.get("warning"):
        print(f"Warning: {check['warning']}", file=sys.stderr)

    # --- Parse repo ---
    try:
        owner, name = parse_repo_arg(args.repo)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # --- Clone ---
    clone_path: Path | None = None
    try:
        if args.verbose:
            print(f"[2/7] Cloning {owner}/{name}...")
        clone_path = clone_repo_shallow(owner, name, pat)

        if args.verbose:
            print(f"[3/7] Walking files in {clone_path}...")
        files = walk_repo(clone_path)
        if not files:
            print("Error: No files found in the repository.", file=sys.stderr)
            return 1
        if args.verbose:
            print(f"  Found {len(files)} files")

        primary_language = args.language or detect_primary_language(files)
        if args.verbose:
            print(f"[4/7] Detected primary language: {primary_language}")

        # If the user specified --language, filter files to only that language
        # (otherwise the detector picks up all language files indiscriminately).
        if args.language:
            from people_helper.config import LANG_BY_EXT
            # Map language name → set of extensions
            target_exts = {ext for ext, lang in LANG_BY_EXT.items() if lang == args.language}
            files = [f for f in files if f["ext"] in target_exts]
            if args.verbose:
                print(f"  Filtered to {len(files)} {args.language} file(s)")

        if args.verbose:
            print("[5/7] Detecting candidates...")
        candidates = detect_candidates(files, primary_language)
        active = [c for c in candidates if not c.skipped]
        skipped = [c for c in candidates if c.skipped]
        if args.verbose:
            print(f"  Found {len(active)} candidates, {len(skipped)} skipped")

        # --- Score and search ---
        if not args.no_network:
            if args.verbose:
                print("[6/7] Searching GitHub for similar projects...")
            for i, cand in enumerate(active):
                if args.verbose:
                    print(f"  [{i + 1}/{len(active)}] Searching for: {cand.path}")
                query = build_search_query(cand)
                cand.similar_projects = github_search_repositories(
                    query, cand.language, pat, min_stars=args.min_stars,
                )
                score_candidate(cand, len(cand.similar_projects))
                cand.differentiators = compute_differentiators(cand)
                cand.suggested_name = suggest_name(cand)
                cand.suggested_tags = suggest_tags(cand)
        else:
            for cand in active:
                score_candidate(cand, 0)
                cand.differentiators = ["Network search was skipped (--no-network)"]
                cand.suggested_name = suggest_name(cand)
                cand.suggested_tags = suggest_tags(cand)

        # --- Report ---
        if args.verbose:
            print("[7/7] Generating report...")
        generate_report(
            owner, name, primary_language, candidates,
            Path(args.output), max_candidates=args.max_candidates,
        )

        return 0

    except subprocess.CalledProcessError as e:
        msg = e.stderr if isinstance(e.stderr, str) else (
            e.stderr.decode() if e.stderr else str(e)
        )
        print(f"Error: {msg.strip()}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        if clone_path and clone_path.exists():
            shutil.rmtree(clone_path, ignore_errors=True)
            if args.verbose:
                print("  Cleaned up temp clone.")


if __name__ == "__main__":
    sys.exit(main())

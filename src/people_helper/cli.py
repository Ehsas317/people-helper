"""People Helper CLI — main() entry point.

This module is importable both from the repo-root `people_helper.py` script
and from `python -m people_helper` (via src/people_helper/__main__.py).
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

from . import __version__
from .config import LANG_BY_EXT
from .detection import detect_candidates
from .extractor import extract_candidates
from .naming import suggest_name, suggest_tags
from .pat import check_pat_scope
from .report import generate_report
from .scoring import score_candidate
from .search import (
    RATE_LIMITED,
    build_search_query,
    compute_differentiators,
    github_search_repositories,
)
from .walker import clone_repo_shallow, detect_primary_language, parse_repo_arg, walk_repo

# Exit code taxonomy (see module docstring in people_helper.py).
EXIT_ERROR = 1
EXIT_AUTH = 3
EXIT_BAD_INPUT = 4
EXIT_REPO = 5


def _redact_pat_in_message(msg: str, pat: str) -> str:
    """Defense-in-depth: scrub PAT from any error message before printing."""
    if pat and pat in msg:
        msg = msg.replace(pat, "***")
    return msg


def main():
    parser = argparse.ArgumentParser(
        description="Find code worth extracting — and verify it's actually standalone.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic analysis (produces report.md)
  people-helper --repo you/repo

  # Local-only (no GitHub search, faster)
  people-helper --repo you/repo --no-network

  # Extract top candidates to ./extracted/ directory
  people-helper --repo you/repo --extract ./extracted/

  # Only show candidates scoring 6.0+
  people-helper --repo you/repo --min-score 6.0

Create a fine-grained PAT:
  https://github.com/settings/personal-access-tokens/new
  Required: Contents: Read, Metadata: Read only. No write scopes.
""",
    )
    parser.add_argument("--repo", required=True, help="GitHub repo URL or owner/name")
    parser.add_argument("--output", default="report.md", help="Output report path (default: report.md)")
    parser.add_argument("--max-candidates", type=int, default=10, help="Max candidates in report (default: 10)")
    parser.add_argument("--min-stars", type=int, default=5, help="Min stars for similar projects (default: 5)")
    parser.add_argument(
        "--language",
        help="Filter to one language (e.g. Python)",
        choices=sorted(set(LANG_BY_EXT.values())),
    )
    parser.add_argument("--no-network", action="store_true", help="Skip GitHub search (local-only mode)")
    parser.add_argument("--verbose", action="store_true", help="Verbose step-by-step progress output")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show stack traces on errors (for bug reports)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"People Helper v{__version__}",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Only show candidates with score >= this (default: 0.0)",
    )
    parser.add_argument(
        "--extract",
        metavar="DIR",
        help="Extract top candidates to DIR (creates package scaffolds)",
    )
    parser.add_argument("--max-extract", type=int, default=5, help="Max candidates to extract (default: 5)")
    parser.add_argument(
        "--extract-min-score",
        type=float,
        default=6.0,
        help="Min score for extraction (default: 6.0)",
    )
    args = parser.parse_args()

    pat = os.environ.get("PEOPLE_HELPER_PAT")
    if not pat:
        print("Error: PEOPLE_HELPER_PAT environment variable not set.", file=sys.stderr)
        print("Create a fine-grained PAT at https://github.com/settings/personal-access-tokens/new", file=sys.stderr)
        print("Required: Contents: Read, Metadata: Read only.", file=sys.stderr)
        print("Classic PATs with 'repo' scope are rejected (too broad).", file=sys.stderr)
        sys.exit(EXIT_AUTH)

    # Validate --output parent dir early (fail fast instead of after a full pipeline run).
    output_path = Path(args.output)
    if output_path.exists() and output_path.is_dir():
        print(f"Error: --output path is a directory, not a file: {args.output}", file=sys.stderr)
        sys.exit(EXIT_BAD_INPUT)
    if not output_path.parent.exists():
        print(
            f"Error: --output parent directory does not exist: {output_path.parent}. "
            f"Create it first or use a different path.",
            file=sys.stderr,
        )
        sys.exit(EXIT_BAD_INPUT)

    # Validate --extract parent dir early too.
    if args.extract is not None:
        extract_path = Path(args.extract)
        if extract_path.exists() and not extract_path.is_dir():
            print(f"Error: --extract path exists but is not a directory: {args.extract}", file=sys.stderr)
            sys.exit(EXIT_BAD_INPUT)

    # Validate --repo arg syntax BEFORE making any network call.
    try:
        owner, name = parse_repo_arg(args.repo)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(EXIT_BAD_INPUT)

    # Range validation
    if args.max_candidates < 1:
        print(f"Error: --max-candidates must be >= 1, got {args.max_candidates}", file=sys.stderr)
        sys.exit(EXIT_BAD_INPUT)
    if args.max_extract < 1:
        print(f"Error: --max-extract must be >= 1, got {args.max_extract}", file=sys.stderr)
        sys.exit(EXIT_BAD_INPUT)
    if args.min_score < 0 or args.min_score > 10:
        print(f"Error: --min-score must be 0-10, got {args.min_score}", file=sys.stderr)
        sys.exit(EXIT_BAD_INPUT)

    if args.verbose:
        print("[1/8] Checking PAT scope...")
    check = check_pat_scope(pat)
    if not check["ok"]:
        print(f"Error: {check['error']}", file=sys.stderr)
        sys.exit(EXIT_AUTH)
    if args.verbose:
        print(f"  Authenticated as: {check['user']}")
        if check.get("warning"):
            print(f"  Note: {check['warning']}")

    clone_path = None
    try:
        if args.verbose:
            print(f"[2/8] Cloning {owner}/{name}...")
        clone_path = clone_repo_shallow(owner, name, pat)
        if args.verbose:
            print("[3/8] Walking files...")
        files = walk_repo(clone_path)
        if not files:
            print("Error: No files found.", file=sys.stderr)
            sys.exit(EXIT_REPO)
        if args.verbose:
            print(f"  Found {len(files)} files")

        # Huge repo warning
        if len(files) > 50000:
            print(f"Warning: {len(files):,} files found. This may take a while.", file=sys.stderr)
            if len(files) > 150000:
                print("Hint: For very large repos, consider using --language to filter.", file=sys.stderr)

        primary_language = args.language or detect_primary_language(files)
        if args.verbose:
            print(f"[4/8] Language: {primary_language}")

        # Warn if language detection disagrees with --language filter
        if args.language and not args.no_network:
            detected = detect_primary_language(files)
            if detected != args.language and detected != "Unknown":
                print(f"Note: --language={args.language} but repo's primary language is {detected}.", file=sys.stderr)
                print(f"      Filtering to {args.language} files only.", file=sys.stderr)

        if args.language:
            target_exts = {ext for ext, lang in LANG_BY_EXT.items() if lang == args.language}
            files = [f for f in files if f["ext"] in target_exts]
            if args.verbose:
                print(f"  Filtered to {len(files)} {args.language} file(s)")
            if not files:
                print(f"Error: No {args.language} files found after filtering.", file=sys.stderr)
                sys.exit(EXIT_REPO)

        if args.verbose:
            print("[5/8] Detecting candidates...")
        candidates, errored_count = detect_candidates(files, primary_language)
        active = [c for c in candidates if not c.skipped]
        if args.verbose:
            print(f"  Found {len(active)} candidates, {len(candidates) - len(active)} skipped")
        # Always print errored_count warning (was previously silent — R1-B/R2-B/R3-A Critical).
        if errored_count > 0:
            print(
                f"  Warning: {errored_count} file(s) caused errors during detection (skipped).",
                file=sys.stderr,
            )
            print("  Run with --debug for stack traces.", file=sys.stderr)

        if not args.no_network:
            if args.verbose:
                print("[6/8] Searching GitHub...")
            # Privacy notice — only if there are candidates to search for, and
            # only sleep if running interactively (skip in CI / piped stdin).
            if active:
                print(
                    "⚠ PRIVACY NOTICE: GitHub search will send the file's name, function names, "
                    "docstring words, and import module names from your code to GitHub's search API.",
                    file=sys.stderr,
                )
                # Only sleep if interactive (TTY) — don't block CI / scripts.
                if sys.stdin.isatty():
                    try:
                        time.sleep(3)
                    except KeyboardInterrupt:
                        print("\nCancelled.", file=sys.stderr)
                        sys.exit(130)
            rate_limited_count = 0
            for i, cand in enumerate(active):
                if args.verbose:
                    print(f"  [{i + 1}/{len(active)}] {cand.path}")
                query = build_search_query(cand)
                results = github_search_repositories(query, cand.language, pat, min_stars=args.min_stars)
                # RATE_LIMITED sentinel → pass -1 to score_candidate for neutral 5.0 uniqueness.
                if results is RATE_LIMITED or results == RATE_LIMITED:
                    rate_limited_count += 1
                    cand.similar_projects = []
                    score_candidate(cand, -1)
                else:
                    cand.similar_projects = results
                    score_candidate(cand, len(cand.similar_projects))
                cand.differentiators = compute_differentiators(cand)
                cand.suggested_name = suggest_name(cand)
                cand.suggested_tags = suggest_tags(cand)
            if rate_limited_count > 0:
                print(
                    f"  Warning: {rate_limited_count} candidate(s) hit GitHub search rate limit. "
                    f"Uniqueness scores for those are neutral (5.0), not 'truly unique'.",
                    file=sys.stderr,
                )
        else:
            for cand in active:
                score_candidate(cand, -1)
                cand.differentiators = ["Network search skipped (--no-network)"]
                cand.suggested_name = suggest_name(cand)
                cand.suggested_tags = suggest_tags(cand)

        # Extract candidates if --extract was passed
        if args.extract is not None:
            if args.verbose:
                print(f"[7/8] Extracting top candidates to {args.extract}...")
            extracted = extract_candidates(
                candidates,
                clone_path,
                Path(args.extract),
                f"{owner}/{name}",
                max_extract=args.max_extract,
                min_score=args.extract_min_score,
                verbose=args.verbose,
            )
            print(f"\nExtracted {len(extracted)} package(s) to {args.extract}:")
            for ext in extracted:
                print(f"  {ext['package']:30s}  score={ext['score']:.1f}  type={ext['extraction_type']}")

        if args.verbose:
            print("[8/8] Generating report...")
        generate_report(
            owner,
            name,
            primary_language,
            candidates,
            Path(args.output),
            max_candidates=args.max_candidates,
            min_score=args.min_score,
        )
    except subprocess.CalledProcessError as e:
        msg = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else str(e))
        msg = _redact_pat_in_message(msg.strip(), pat)
        print(f"Error: {msg}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        sys.exit(EXIT_REPO)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        msg = _redact_pat_in_message(str(e), pat)
        print(f"Error: {msg}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        else:
            print("  Run with --debug for a full stack trace.", file=sys.stderr)
        sys.exit(EXIT_ERROR)
    finally:
        if clone_path and clone_path.exists():
            shutil.rmtree(clone_path, ignore_errors=True)
            if args.verbose:
                print("  Cleaned up temp clone.")

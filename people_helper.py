#!/usr/bin/env python3
"""
People Helper v0.2 — Find what's extractable from your private code.

Usage:
    python people_helper.py --repo https://github.com/you/private-repo
    python people_helper.py --repo you/private-repo --output report.md
    python people_helper.py --repo you/private-repo --no-network --verbose

Requires:
    - A fine-grained GitHub PAT in PEOPLE_HELPER_PAT env var
    - PAT must have Contents: Read and Metadata: Read only
    - No other scopes

Scoring:
    combined = 0.5 * code_quality + 0.3 * uniqueness + 0.2 * demand_signal
"""

import subprocess
from pathlib import Path
import argparse
import os
import shutil
import sys

# Ensure the package is importable when running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from people_helper.pat import check_pat_scope
from people_helper.walker import parse_repo_arg, clone_repo_shallow, walk_repo, detect_primary_language
from people_helper.detection import detect_candidates
from people_helper.search import github_search_repositories, build_search_query, compute_differentiators
from people_helper.scoring import score_candidate
from people_helper.naming import suggest_name, suggest_tags
from people_helper.report import generate_report


def main():
    parser = argparse.ArgumentParser(
        description="Find what's extractable from your private code.",
    )
    parser.add_argument("--repo", required=True, help="GitHub repo URL or owner/name")
    parser.add_argument("--output", default="report.md", help="Output report path (default: report.md)")
    parser.add_argument("--max-candidates", type=int, default=10, help="Max candidates to show in report (default: 10)")
    parser.add_argument("--min-stars", type=int, default=5, help="Min stars for similar projects (default: 5)")
    parser.add_argument("--language", help="Filter to one language (e.g. Python)")
    parser.add_argument("--no-network", action="store_true", help="Skip GitHub search (local-only mode)")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    # --- PAT check ---
    pat = os.environ.get("PEOPLE_HELPER_PAT")
    if not pat:
        print("Error: PEOPLE_HELPER_PAT environment variable not set.", file=sys.stderr)
        print("Create a fine-grained PAT at https://github.com/settings/personal-access-tokens/new", file=sys.stderr)
        print("Required scopes: Contents: Read, Metadata: Read. Only the specific repos you want to analyze.", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print("[1/7] Checking PAT scope...")
    check = check_pat_scope(pat)
    if not check["ok"]:
        print(f"Error: {check['error']}", file=sys.stderr)
        sys.exit(1)
    if args.verbose:
        print(f"  Authenticated as: {check['user']}")

    # --- Parse repo ---
    try:
        owner, name = parse_repo_arg(args.repo)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Clone ---
    clone_path = None
    try:
        if args.verbose:
            print(f"[2/7] Cloning {owner}/{name}...")
        clone_path = clone_repo_shallow(owner, name, pat)

        if args.verbose:
            print(f"[3/7] Walking files in {clone_path}...")
        files = walk_repo(clone_path)
        if not files:
            print("Error: No files found in the repository.", file=sys.stderr)
            sys.exit(1)
        if args.verbose:
            print(f"  Found {len(files)} files")

        primary_language = args.language or detect_primary_language(files)
        if args.verbose:
            print(f"[4/7] Detected primary language: {primary_language}")

        if args.verbose:
            print(f"[5/7] Detecting candidates...")
        candidates = detect_candidates(files, primary_language)
        active = [c for c in candidates if not c.skipped]
        skipped = [c for c in candidates if c.skipped]
        if args.verbose:
            print(f"  Found {len(active)} candidates, {len(skipped)} skipped")

        # --- Score and search ---
        if not args.no_network:
            if args.verbose:
                print(f"[6/7] Searching GitHub for similar projects...")
            for i, cand in enumerate(active):
                if args.verbose:
                    print(f"  [{i+1}/{len(active)}] Searching for: {cand.path}")
                query = build_search_query(cand)
                cand.similar_projects = github_search_repositories(
                    query, cand.language, pat, min_stars=args.min_stars
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
            print(f"[7/7] Generating report...")
        generate_report(
            owner, name, primary_language, candidates,
            Path(args.output), max_candidates=args.max_candidates,
        )

    except subprocess.CalledProcessError as e:
        msg = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else str(e))
        print(f"Error: {msg.strip()}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # Always clean up the clone
        if clone_path and clone_path.exists():
            shutil.rmtree(clone_path, ignore_errors=True)
            if args.verbose:
                print("  Cleaned up temp clone.")


if __name__ == "__main__":
    main()

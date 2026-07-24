#!/usr/bin/env python3
"""
People Helper v1.0.0 — Find code worth extracting, and verify it's actually standalone.

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

Scoring:
    combined = 0.25*quality + 0.20*usefulness + 0.15*uniqueness + 0.15*relevance + 0.15*maintainability + 0.10*demand
    Files with relevance < 3.0 get combined score halved.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from people_helper.pat import check_pat_scope
from people_helper.walker import parse_repo_arg, clone_repo_shallow, walk_repo, detect_primary_language
from people_helper.detection import detect_candidates
from people_helper.search import github_search_repositories, build_search_query, compute_differentiators
from people_helper.scoring import score_candidate
from people_helper.naming import suggest_name, suggest_tags
from people_helper.report import generate_report
from people_helper.extractor import extract_candidates


def main():
    parser = argparse.ArgumentParser(
        description="Find code worth extracting — and verify it's actually standalone.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic analysis (produces report.md)
  python people_helper.py --repo you/repo

  # Local-only (no GitHub search, faster)
  python people_helper.py --repo you/repo --no-network

  # Extract top candidates to ./extracted/ directory
  python people_helper.py --repo you/repo --extract ./extracted/

  # Only show candidates scoring 6.0+
  python people_helper.py --repo you/repo --min-score 6.0

Create a fine-grained PAT:
  https://github.com/settings/personal-access-tokens/new
  Required: Contents: Read, Metadata: Read only. No write scopes.
"""
    )
    parser.add_argument("--repo", required=True, help="GitHub repo URL or owner/name")
    parser.add_argument("--output", default="report.md", help="Output report path (default: report.md)")
    parser.add_argument("--max-candidates", type=int, default=10, help="Max candidates in report (default: 10)")
    parser.add_argument("--min-stars", type=int, default=5, help="Min stars for similar projects (default: 5)")
    parser.add_argument("--language", help="Filter to one language (e.g. Python)")
    parser.add_argument("--no-network", action="store_true", help="Skip GitHub search (local-only mode)")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--min-score", type=float, default=0.0, help="Only show candidates with score >= this (default: 0.0)")
    parser.add_argument("--extract", metavar="DIR", help="Extract top candidates to DIR (creates package scaffolds)")
    parser.add_argument("--max-extract", type=int, default=5, help="Max candidates to extract (default: 5)")
    parser.add_argument("--extract-min-score", type=float, default=6.0, help="Min score for extraction (default: 6.0)")
    args = parser.parse_args()

    pat = os.environ.get("PEOPLE_HELPER_PAT")
    if not pat:
        print("Error: PEOPLE_HELPER_PAT environment variable not set.", file=sys.stderr)
        print("Create a fine-grained PAT at https://github.com/settings/personal-access-tokens/new", file=sys.stderr)
        print("Required: Contents: Read, Metadata: Read only.", file=sys.stderr)
        print("Classic PATs with 'repo' scope are rejected (too broad).", file=sys.stderr)
        sys.exit(1)

    if args.verbose: print("[1/7] Checking PAT scope...")
    check = check_pat_scope(pat)
    if not check["ok"]:
        print(f"Error: {check['error']}", file=sys.stderr)
        sys.exit(1)
    if args.verbose: print(f"  Authenticated as: {check['user']}")

    try:
        owner, name = parse_repo_arg(args.repo)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    clone_path = None
    try:
        if args.verbose: print(f"[2/7] Cloning {owner}/{name}...")
        clone_path = clone_repo_shallow(owner, name, pat)
        if args.verbose: print(f"[3/7] Walking files...")
        files = walk_repo(clone_path)
        if not files:
            print("Error: No files found.", file=sys.stderr)
            sys.exit(1)
        if args.verbose: print(f"  Found {len(files)} files")

        # Huge repo warning
        if len(files) > 50000:
            print(f"Warning: {len(files):,} files found. This may take a while.", file=sys.stderr)
            if len(files) > 150000:
                print("Hint: For very large repos, consider using --language to filter.", file=sys.stderr)

        primary_language = args.language or detect_primary_language(files)
        if args.verbose: print(f"[4/7] Language: {primary_language}")

        # Warn if language detection disagrees with --language filter
        if args.language and not args.no_network:
            detected = detect_primary_language(files)
            if detected != args.language and detected != "Unknown":
                print(f"Note: --language={args.language} but repo's primary language is {detected}.", file=sys.stderr)
                print(f"      Filtering to {args.language} files only.", file=sys.stderr)

        if args.language:
            from people_helper.config import LANG_BY_EXT
            target_exts = {ext for ext, lang in LANG_BY_EXT.items() if lang == args.language}
            files = [f for f in files if f["ext"] in target_exts]
            if args.verbose: print(f"  Filtered to {len(files)} {args.language} file(s)")
        if args.verbose: print(f"[5/7] Detecting candidates...")
        candidates = detect_candidates(files, primary_language)
        active = [c for c in candidates if not c.skipped]
        if args.verbose: print(f"  Found {len(active)} candidates, {len(candidates) - len(active)} skipped")
        if not args.no_network:
            if args.verbose: print(f"[6/7] Searching GitHub...")
            for i, cand in enumerate(active):
                if args.verbose: print(f"  [{i+1}/{len(active)}] {cand.path}")
                query = build_search_query(cand)
                cand.similar_projects = github_search_repositories(query, cand.language, pat, min_stars=args.min_stars)
                score_candidate(cand, len(cand.similar_projects))
                cand.differentiators = compute_differentiators(cand)
                cand.suggested_name = suggest_name(cand)
                cand.suggested_tags = suggest_tags(cand)
        else:
            for cand in active:
                score_candidate(cand, -1)
                cand.differentiators = ["Network search skipped (--no-network)"]
                cand.suggested_name = suggest_name(cand)
                cand.suggested_tags = suggest_tags(cand)

        # Extract candidates if --extract was passed
        if args.extract:
            if args.verbose: print(f"[7/8] Extracting top candidates to {args.extract}...")
            extracted = extract_candidates(
                candidates, clone_path, Path(args.extract), f"{owner}/{name}",
                max_extract=args.max_extract, min_score=args.extract_min_score, verbose=args.verbose
            )
            print(f"\nExtracted {len(extracted)} package(s) to {args.extract}:")
            for ext in extracted:
                print(f"  {ext['package']:30s}  score={ext['score']:.1f}  type={ext['extraction_type']}")

        if args.verbose: print(f"[8/8] Generating report...")
        generate_report(owner, name, primary_language, candidates, Path(args.output), max_candidates=args.max_candidates, min_score=args.min_score)
    except subprocess.CalledProcessError as e:
        msg = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode() if e.stderr else str(e))
        print(f"Error: {msg.strip()}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if clone_path and clone_path.exists():
            shutil.rmtree(clone_path, ignore_errors=True)
            if args.verbose: print("  Cleaned up temp clone.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Push all files to GitHub using the Git Trees API."""

import base64
import json
import os
import sys
import httpx

TOKEN = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PEOPLE_HELPER_PAT")
REPO = "ehsas317/people-helper"
BASE = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
WORK_DIR = "/home/z/my-project/people-helper-work"


def api(method, path, **kwargs):
    r = httpx.request(method, f"{BASE}{path}", headers=HEADERS, timeout=30, **kwargs)
    if r.status_code >= 400:
        print(f"  API {method} {path} -> {r.status_code}: {r.text[:300]}", file=sys.stderr)
    return r


def file_to_blob(path):
    abs_path = os.path.join(WORK_DIR, path)
    with open(abs_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    return {"path": path, "mode": "100644", "type": "blob", "content": content}


def collect_files(directory, prefix=""):
    blobs = []
    for entry in sorted(os.listdir(os.path.join(WORK_DIR, directory))):
        if entry.startswith(".") and entry not in (".env.example", ".gitignore"):
            continue
        if entry.endswith(".pyc"):
            continue
        rel = os.path.join(prefix, entry) if prefix else entry
        full = os.path.join(WORK_DIR, directory, entry)
        if os.path.isdir(full):
            blobs.extend(collect_files(full, rel))
        else:
            blobs.append(file_to_blob(rel))
    return blobs


def main():
    # Get current HEAD
    r = api("GET", f"/repos/{REPO}/git/ref/heads/main")
    head_sha = r.json()["object"]["sha"]
    print(f"Current HEAD: {head_sha[:12]}")

    # Collect all files
    blobs = collect_files("")
    print(f"Collected {len(blobs)} files")

    # Create blobs in parallel-ish (batch of 10)
    tree_items = []
    for i, blob in enumerate(blobs):
        # Create blob
        r = api("POST", f"/repos/{REPO}/git/blobs", json={"content": blob["content"], "encoding": "base64"})
        if r.status_code == 201:
            sha = r.json()["sha"]
            tree_items.append({"path": blob["path"], "mode": blob["mode"], "type": "blob", "sha": sha})
        else:
            print(f"  FAILED blob: {blob['path']}")
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(blobs)} blobs created...")

    print(f"  All {len(tree_items)} blobs created")

    # Create tree
    r = api("POST", f"/repos/{REPO}/git/trees", json={"base_tree": None, "tree": tree_items})
    if r.status_code != 201:
        print(f"  FAILED tree creation")
        return
    tree_sha = r.json()["sha"]
    print(f"Tree: {tree_sha[:12]}")

    # Create commit
    r = api("POST", f"/repos/{REPO}/git/commits", json={
        "message": "v0.2: reorganized codebase, new scoring, bug fixes\n\nScoring: 0.5*code_quality + 0.3*uniqueness + 0.2*demand_signal\n- Reorganized monolithic file into src/people_helper/ package (8 modules)\n- Fixed scoring mismatch between code and docs\n- Added demand_signal metric (stars/forks/issues of similar projects)\n- Fixed: identity check (is -> ==), unused --max-candidates, deprecated datetime\n- Fixed: duplicate 'types' in external scopes, loose Go import regex\n- Fixed: placeholder differentiator extraction now generates real comparisons\n- Added: what_it_does, why_extractable, suggested_tags to report\n- Added: 24-month recency filter on GitHub search\n- Added: SSH URL and clean error handling for clone failures\n- New README.md with scoring table, diagram, and usage examples\n- Updated SKILL.md, heuristics.md, manifest.yaml to v0.2",
        "tree": tree_sha,
        "parents": [head_sha],
    })
    if r.status_code != 201:
        print(f"  FAILED commit")
        return
    commit_sha = r.json()["sha"]
    print(f"Commit: {commit_sha[:12]}")

    # Update ref
    r = api("PATCH", f"/repos/{REPO}/git/refs/heads/main", json={"sha": commit_sha})
    if r.status_code == 200:
        print(f"Pushed! Branch main now at {commit_sha[:12]}")
    else:
        print(f"  FAILED to update ref")


if __name__ == "__main__":
    main()

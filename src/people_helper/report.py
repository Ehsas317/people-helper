"""Stage 9: Markdown report generation.

Security: All user-controlled content (docstrings, code excerpts, descriptions)
is sanitized before embedding in markdown to prevent injection (XSS, broken
code fences, tracking pixels). We use 4-backtick fences for outer code blocks
so triple-backtick content inside doesn't break out.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

from .models import Candidate

# Regex patterns for common secrets that might appear in source code first_lines.
# If matched, the match is replaced with ***REDACTED***.
_SECRET_PATTERNS = [
    # GitHub classic PATs (ghp_, gho_, ghu_, ghs_, ghr_)
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,255}"),
    # GitHub fine-grained PAT
    re.compile(r"github_pat_[A-Za-z0-9_]{82,255}"),
    # AWS access key
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # AWS secret access key (heuristic — 40 base64-ish chars after 'aws_secret' or similar)
    re.compile(r"(?i)aws[_\-]?secret[_\-]?(?:access[_\-]?)?key['\"\s:=]+([A-Za-z0-9/+=]{40})"),
    # Slack tokens (xoxb-, xoxp-, xoxa-, xoxr-, xoxs-)
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    # OpenAI / generic sk- key
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    # Anthropic API key
    re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"),
    # Google API key (AIza...)
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    # Stripe keys (pk_live_, sk_live_, rk_live_)
    re.compile(r"[psr]k_(?:live|test)_[A-Za-z0-9]{20,}"),
    # PEM private keys
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # JWTs (3 base64url segments)
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    # Heroku API key (UUID-like, 36 chars)
    re.compile(r"(?i)heroku[_\-]?api[_\-]?key['\"\s:=]+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"),
    # Twilio Account SID
    re.compile(r"AC[a-f0-9]{32}"),
    # SendGrid API key
    re.compile(r"SG\.[A-Za-z0-9_\-]{20,30}\.[A-Za-z0-9_\-]{40,}"),
    # npm token
    re.compile(r"npm_[A-Za-z0-9]{36}"),
    # Discord bot token
    re.compile(r"[MN][A-Za-z0-9]{23,}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,}"),
    # Generic high-entropy hex token (64+ chars) — last resort, may have false positives
    re.compile(r"(?<![A-Za-z0-9])[a-f0-9]{64,}(?![A-Za-z0-9])"),
]


def _redact_secrets(text: str) -> str:
    """Redact common secret patterns from text to prevent leakage in reports."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("***REDACTED***", text)
    return text


def _sanitize_for_markdown(text: str) -> str:
    """Sanitize user-controlled content for safe embedding in markdown.

    - Replaces triple backticks with escaped form to prevent code-fence breakouts.
    - Strips HTML script tags and javascript: URLs (defense against XSS in
      markdown renderers that don't sanitize).
    """
    if not text:
        return text
    # Escape triple backticks so user content can't close the outer code fence
    text = text.replace("```", "\\`\\`\\`")
    # Strip <script>...</script> blocks
    text = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", "", text, flags=re.IGNORECASE)
    # Neutralize javascript: URLs in markdown links [text](javascript:...)
    text = re.sub(r"\]\(javascript:", "](disabled:", text, flags=re.IGNORECASE)
    return text


def generate_report(
    owner: str,
    name: str,
    language: str,
    candidates: list[Candidate],
    output_path: Path,
    max_candidates: int = 10,
    min_score: float = 0.0,
) -> None:
    """Generate the markdown report. Writes to output_path. Prints summary to stdout."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    active = sorted(
        [c for c in candidates if not c.skipped],
        key=lambda c: c.combined_score,
        reverse=True,
    )
    hidden = 0
    if min_score > 0:
        filtered = [c for c in active if c.combined_score >= min_score]
        hidden = len(active) - len(filtered)
        active = filtered
    skipped = [c for c in candidates if c.skipped]

    # Summary stats — help the user understand the scan at a glance
    extraction_counts = {"single": 0, "multi": 0, "blocked": 0}
    for c in active:
        if c.extraction_type in extraction_counts:
            extraction_counts[c.extraction_type] += 1
    total_loc = sum(c.loc for c in active)
    avg_complexity = sum(c.complexity for c in active) / max(len(active), 1)
    stdlib_only_count = sum(1 for c in active if c.is_stdlib_only)
    no_license_count = sum(1 for c in active if not c.source_has_license)
    multi_or_blocked = extraction_counts["multi"] + extraction_counts["blocked"]

    lines: list[str] = [
        "# People Helper Report\n",
        f"**Repo:** {owner}/{name}",
        f"**Generated:** {now}",
        f"**Primary language:** {language}",
        f"**Candidates analyzed:** {len(candidates)}",
        f"**Top candidates:** {len(active)}",
    ]
    if hidden > 0:
        lines.append(f"**Filtered:** {hidden} below score {min_score}")
    lines.append(
        "**Scoring:** 0.25 × code quality + 0.20 × usefulness + 0.15 × uniqueness "
        "+ 0.15 × relevance + 0.15 × maintainability + 0.10 × demand signal"
    )
    lines.append("")
    # Add a compact summary block when there are candidates
    if active:
        lines.append("## At a glance")
        lines.append("")
        lines.append(f"- **Verified single-file (✅):** {extraction_counts['single']}")
        lines.append(f"- **Multi-file needed (⚠):** {extraction_counts['multi']}")
        if extraction_counts["blocked"] > 0:
            lines.append(f"- **Blocked (⛔):** {extraction_counts['blocked']}")
        lines.append(f"- **Total LOC across candidates:** {total_loc:,}")
        lines.append(f"- **Average cyclomatic complexity:** {avg_complexity:.1f}")
        if stdlib_only_count:
            lines.append(f"- **Stdlib-only candidates:** {stdlib_only_count}/{len(active)}")
        if no_license_count:
            lines.append(
                f"- **⚠ No source license:** {no_license_count}/{len(active)} candidates — extraction is legally risky"
            )
        if multi_or_blocked > 0:
            lines.append(
                f"- **Heads-up:** {multi_or_blocked} candidate(s) need sibling files or are blocked — review before extracting"
            )
        lines.append("")

    if not active:
        if not candidates:
            lines.append(
                "> No extractable candidates found. Usually a framework app where files are routes/pages/configs."
            )
        elif skipped:
            lines.append("> No extractable candidates. Files were analyzed but skipped — see below.")
        else:
            lines.append("> No extractable candidates found.")
        lines.append("")
    else:
        lines.append("---\n## Top candidates\n")
        for i, c in enumerate(active[:max_candidates], 1):
            lines.append(f"### {i}. `{Path(c.path).name}` — Combined score: {c.combined_score:.1f}/10\n")
            lines.append(f"**Location:** `{c.path}`")
            lines.append(f"**Language:** {c.language}")
            # Dimensions in weight order (quality 25% → usefulness 20% → ... → demand 10%)
            lines.append(f"**Code quality:** {c.code_quality:.0f}/10 (weight: 25%)")
            lines.append(f"**Usefulness:** {c.usefulness:.0f}/10 (weight: 20%)")
            lines.append(f"**Uniqueness:** {c.uniqueness:.0f}/10 (weight: 15%)")
            lines.append(f"**Relevance:** {c.relevance:.0f}/10 (weight: 15%)")
            lines.append(f"**Maintainability:** {c.maintainability:.0f}/10 (weight: 15%)")
            lines.append(f"**Demand signal:** {c.demand_signal:.0f}/10 (weight: 10%)")
            lines.append(f"**Estimated ship effort:** {c.ship_effort_hours:g} hour(s)")
            lines.append(f"**LOC:** {c.loc}")
            lines.append(f"**Has tests:** {'yes' if c.has_tests else 'no'}")
            lines.append(f"**Has docstring:** {'yes' if c.has_docstring else 'no'}")
            lines.append(f"**Internal imports:** {c.internal_imports}")
            lines.append(f"**External imports:** {c.external_imports}")
            # Extraction verification — the most important signal
            ext_labels = {
                "single": "✅ single file — verified standalone",
                "multi": "⚠ multi-file — also needs siblings",
                "blocked": "⛔ blocked — references missing siblings",
            }
            lines.append(f"**Extraction type:** {ext_labels.get(c.extraction_type, 'unknown')}")
            if c.sibling_paths:
                sibs = ", ".join(f"`{Path(s).name}`" for s in c.sibling_paths)
                lines.append(f"**Required siblings:** {sibs}")
            lines.append(
                f"**Source repo license:** {'yes' if c.source_has_license else '⚠ NO LICENSE FILE — extraction legally risky'}"
            )
            if c.complexity > 0:
                label = (
                    "low"
                    if c.complexity <= 5
                    else "moderate"
                    if c.complexity <= 10
                    else "high"
                    if c.complexity <= 20
                    else "very high"
                )
                lines.append(f"**Cyclomatic complexity:** {c.complexity} — {label}")
            if c.fan_in >= 0:
                lines.append(f"**Fan-in:** {c.fan_in}" + (" (orphan — ideal target)" if c.fan_in == 0 else ""))
            if c.in_cycle:
                lines.append("**Import cycle:** ⚠ yes")
            dep_labels = {
                0: "stdlib only (standalone)",
                1: "light deps",
                3: "heavy deps (not standalone)",
            }
            lines.append(f"**Dependencies:** {dep_labels.get(c.dependency_weight, 'unknown')}")
            lines.append(f"**Public API:** {c.api_surface_count} function(s)/class(es)")
            lines.append(f"**Comment density:** {c.comment_ratio:.0%}")
            if c.is_stdlib_only:
                lines.append("**Stdlib-only:** ✅ yes")
            if c.has_project_specific_refs:
                lines.append("**Framework-tied:** ⚠ yes")
            lines.append("")
            if c.what_it_does:
                lines.append(f"**What it does:** {_sanitize_for_markdown(c.what_it_does)}")
            lines.append("")
            if c.why_extractable:
                lines.append("**Why it's extractable:**")
                lines.extend(f"- {r}" for r in c.why_extractable)
                lines.append("")
            if c.docstring_snippet:
                lines.append("**Documentation:**")
                # Use 4-backtick fence so triple backticks in docstring don't break out
                lines.append(f"````{c.language.lower() if c.language else ''}")
                lines.append(_sanitize_for_markdown(c.docstring_snippet))
                lines.append("````")
                lines.append("")
            if c.similar_projects:
                lines.append("**Similar projects on GitHub:**")
                for sp in c.similar_projects:
                    desc = f" — {_sanitize_for_markdown(sp.description)}" if sp.description else ""
                    lines.append(
                        f"- [`{sp.full_name}`]({sp.html_url}) — {sp.stars} star(s), "
                        f"{sp.forks} fork(s), last commit {sp.pushed_at}{desc}"
                    )
                lines.append("")
            else:
                lines.append("**Similar projects on GitHub:** None found.\n")
            if c.differentiators:
                lines.append("**Your differentiators:**")
                lines.extend(f"- {d}" for d in c.differentiators)
                lines.append("")
            lines.append(f"**Suggested name:** `{c.suggested_name}`")
            lines.append(f"**Suggested license:** {c.suggested_license}")
            if c.suggested_tags:
                lines.append(f"**Suggested tags:** {', '.join(f'`{t}`' for t in c.suggested_tags)}")
            lines.append("")
            lines.append("**Starter scaffold (first 30 lines):**")
            lang_ext = {
                "Python": "python",
                "TypeScript": "typescript",
                "JavaScript": "javascript",
                "Go": "go",
                "Rust": "rust",
                "Java": "java",
                "C": "c",
                "C++": "cpp",
                "C#": "csharp",
                "Ruby": "ruby",
                "PHP": "php",
                "Kotlin": "kotlin",
                "Swift": "swift",
            }.get(c.language, "")
            # Use 4-backtick fence so user code with triple backticks doesn't break out.
            # CRITICAL: sanitize for markdown (escapes backticks, strips <script>, neutralizes javascript:)
            # AND redact secrets (PATs, AWS keys, etc.) from first_lines to avoid leaking in shared reports.
            safe_first_lines = _sanitize_for_markdown(_redact_secrets(c.first_lines))
            lines.append(f"````{lang_ext}")
            lines.append(safe_first_lines)
            lines.append("````")
            lines.append("\n---\n")

    if len(active) > max_candidates:
        lines.append("## Lower-ranked candidates\n")
        lines.extend(
            f"- `{c.path}` — score {c.combined_score:.1f}/10, {c.loc} LOC, {c.language}"
            for c in active[max_candidates:]
        )
        lines.append("")

    if skipped:
        lines.append("## Skipped files\n")
        for s in skipped[:20]:
            lines.append(f"- `{s.path}` — {s.skip_reason}")
        if len(skipped) > 20:
            lines.append(f"- ... and {len(skipped) - 20} more")
        lines.append("")

    lines.append("---\n*Generated by People Helper — Read-only by design.\n")
    # Use UTF-8 encoding explicitly — Windows default (cp1252) can't encode
    # emoji like ✅ ⚠ ⛔ used in the report, causing UnicodeEncodeError.
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport written: {output_path}")
    print(f"Top candidates: {len(active)}")
    if active:
        print(f"Best candidate: {Path(active[0].path).name} (score {active[0].combined_score:.1f}/10)")

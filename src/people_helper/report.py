from datetime import datetime, timezone
from pathlib import Path


def generate_report(
    owner: str,
    name: str,
    language: str,
    candidates: list,
    output_path: Path,
    max_candidates: int = 10,
) -> None:
    """Write the markdown report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    active = [c for c in candidates if not c.skipped]
    active.sort(key=lambda c: c.combined_score, reverse=True)
    skipped = [c for c in candidates if c.skipped]

    lines = []
    lines.append("# People Helper Report\n")
    lines.append(f"**Repo:** {owner}/{name}")
    lines.append(f"**Generated:** {now}")
    lines.append(f"**Primary language:** {language}")
    lines.append(f"**Candidates analyzed:** {len(candidates)}")
    lines.append(f"**Top candidates:** {len(active)}")
    lines.append(f"**Scoring:** 0.5 x code quality + 0.3 x uniqueness + 0.2 x demand signal")
    lines.append("")

    if not active:
        lines.append("> No extractable candidates found. The repo may be too small, tightly coupled, or all standalone code is actually internal.")
        lines.append("")
    else:
        lines.append("---\n")
        lines.append("## Top candidates\n")
        for i, c in enumerate(active[:max_candidates], 1):
            lines.append(f"### {i}. `{Path(c.path).name}` — Combined score: {c.combined_score:.1f}/10\n")
            lines.append(f"**Location:** `{c.path}`")
            lines.append(f"**Language:** {c.language}")
            lines.append(f"**Code quality:** {c.code_quality:.0f}/10 (weight: 50%)")
            lines.append(f"**Uniqueness:** {c.uniqueness:.0f}/10 (weight: 30%)")
            lines.append(f"**Demand signal:** {c.demand_signal:.0f}/10 (weight: 20%)")
            lines.append(f"**Estimated ship effort:** {c.ship_effort_hours:g} hour(s)")
            lines.append(f"**LOC:** {c.loc}")
            lines.append(f"**Has tests:** {'yes' if c.has_tests else 'no'}")
            lines.append(f"**Has docstring:** {'yes' if c.has_docstring else 'no'}")
            lines.append(f"**Internal imports:** {c.internal_imports}")
            lines.append(f"**External imports:** {c.external_imports}")
            lines.append("")

            # What it does
            if c.what_it_does:
                lines.append("**What it does:**")
                lines.append(c.what_it_does)
                lines.append("")

            # Why extractable
            if c.why_extractable:
                lines.append("**Why it's extractable:**")
                for reason in c.why_extractable:
                    lines.append(f"- {reason}")
                lines.append("")

            # Docstring
            if c.docstring_snippet:
                lines.append("**Documentation:")
                lang_hint = c.language.lower() if c.language else ""
                lines.append(f"```{lang_hint}")
                lines.append(c.docstring_snippet)
                lines.append("```")
                lines.append("")

            # Similar projects
            if c.similar_projects:
                lines.append("**Similar projects on GitHub:")
                for sp in c.similar_projects:
                    desc = f" — {sp.description}" if sp.description else ""
                    lines.append(
                        f"- [`{sp.full_name}`]({sp.html_url}) — {sp.stars} star(s), {sp.forks} fork(s), last commit {sp.pushed_at}{desc}"
                    )
                lines.append("")
            else:
                lines.append("**Similar projects on GitHub:** None found with 5+ stars and recent activity.\n")

            # Differentiators
            if c.differentiators:
                lines.append("**Your differentiators:**")
                for d in c.differentiators:
                    lines.append(f"- {d}")
                lines.append("")

            # Suggested name and tags
            lines.append(f"**Suggested name:** `{c.suggested_name}`")
            lines.append(f"**Suggested license:** {c.suggested_license}")
            if c.suggested_tags:
                lines.append(f"**Suggested tags:** {', '.join(f'`{t}`' for t in c.suggested_tags)}")
            lines.append("")

            # Starter scaffold
            lines.append("**Starter scaffold:")
            lang_ext = {
                "Python": "python", "TypeScript": "typescript",
                "JavaScript": "javascript", "Go": "go", "Rust": "rust",
                "Java": "java", "C": "c", "C++": "cpp",
                "C#": "csharp", "Ruby": "ruby", "PHP": "php",
                "Kotlin": "kotlin", "Swift": "swift",
            }.get(c.language, "")
            lines.append(f"```{lang_ext}")
            lines.append(c.first_lines)
            lines.append("```")
            lines.append("\n---\n")

    # Lower-ranked candidates
    if len(active) > max_candidates:
        lines.append("## Lower-ranked candidates\n")
        for c in active[max_candidates:]:
            lines.append(
                f"- `{c.path}` — score {c.combined_score:.1f}/10, {c.loc} LOC, {c.language}"
            )
        lines.append("")

    # Skipped files
    if skipped:
        lines.append("## Skipped files\n")
        for s in skipped[:20]:
            lines.append(f"- `{s.path}` — {s.skip_reason}")
        if len(skipped) > 20:
            lines.append(f"- ... and {len(skipped) - 20} more")
        lines.append("")

    lines.append("---\n")
    lines.append("*Generated by People Helper v0.2 — Read-only by design.\n")

    output_path.write_text("\n".join(lines))
    print(f"\nReport written: {output_path}")
    print(f"Top candidates: {len(active)}")
    if active:
        print(f"Best candidate: {Path(active[0].path).name} (score {active[0].combined_score:.1f}/10)")

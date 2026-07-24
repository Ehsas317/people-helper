from datetime import datetime, timezone
from pathlib import Path

def generate_report(owner, name, language, candidates, output_path, max_candidates=10, min_score=0.0):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    active = sorted([c for c in candidates if not c.skipped], key=lambda c: c.combined_score, reverse=True)
    hidden = 0
    if min_score > 0:
        filtered = [c for c in active if c.combined_score >= min_score]
        hidden = len(active) - len(filtered); active = filtered
    skipped = [c for c in candidates if c.skipped]
    lines = ["# People Helper Report\n", f"**Repo:** {owner}/{name}", f"**Generated:** {now}",
             f"**Primary language:** {language}", f"**Candidates analyzed:** {len(candidates)}",
             f"**Top candidates:** {len(active)}"]
    if hidden > 0: lines.append(f"**Filtered:** {hidden} below score {min_score}")
    lines.append("**Scoring:** 0.25 x code quality + 0.20 x usefulness + 0.15 x uniqueness + 0.15 x relevance + 0.15 x maintainability + 0.10 x demand signal")
    lines.append("")
    if not active:
        if not candidates:
            lines.append("> No extractable candidates found. Usually a framework app where files are routes/pages/configs.")
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
            lines.append(f"**Code quality:** {c.code_quality:.0f}/10 (weight: 25%)")
            lines.append(f"**Uniqueness:** {c.uniqueness:.0f}/10 (weight: 15%)")
            lines.append(f"**Demand signal:** {c.demand_signal:.0f}/10 (weight: 10%)")
            lines.append(f"**Relevance:** {c.relevance:.0f}/10 (weight: 15%)")
            lines.append(f"**Usefulness:** {c.usefulness:.0f}/10 (weight: 20%)")
            lines.append(f"**Maintainability:** {c.maintainability:.0f}/10 (weight: 15%)")
            lines.append(f"**Estimated ship effort:** {c.ship_effort_hours:g} hour(s)")
            lines.append(f"**LOC:** {c.loc}")
            lines.append(f"**Has tests:** {'yes' if c.has_tests else 'no'}")
            lines.append(f"**Has docstring:** {'yes' if c.has_docstring else 'no'}")
            lines.append(f"**Internal imports:** {c.internal_imports}")
            lines.append(f"**External imports:** {c.external_imports}")
            # Extraction verification — the most important signal
            ext_labels = {"single": "✅ single file — verified standalone",
                          "multi": "⚠ multi-file — also needs siblings",
                          "blocked": "⛔ blocked — references missing siblings"}
            lines.append(f"**Extraction type:** {ext_labels.get(c.extraction_type, 'unknown')}")
            if c.sibling_paths:
                sibs = ", ".join(f"`{Path(s).name}`" for s in c.sibling_paths)
                lines.append(f"**Required siblings:** {sibs}")
            lines.append(f"**Source repo license:** {'yes' if c.source_has_license else '⚠ NO LICENSE FILE — extraction legally risky'}")
            if c.complexity > 0:
                label = "low" if c.complexity <= 5 else "moderate" if c.complexity <= 10 else "high" if c.complexity <= 20 else "very high"
                lines.append(f"**Cyclomatic complexity:** {c.complexity} — {label}")
            if c.fan_in >= 0:
                lines.append(f"**Fan-in:** {c.fan_in}" + (" (orphan — ideal target)" if c.fan_in == 0 else ""))
            if c.in_cycle: lines.append("**Import cycle:** ⚠ yes")
            dep_labels = {0:"stdlib only (standalone)",1:"light deps",3:"heavy deps (not standalone)",5:"framework-tied"}
            lines.append(f"**Dependencies:** {dep_labels.get(c.dependency_weight,'unknown')}")
            lines.append(f"**Public API:** {c.api_surface_count} function(s)/class(es)")
            lines.append(f"**Comment density:** {c.comment_ratio:.0%}")
            if c.is_stdlib_only: lines.append("**Stdlib-only:** ✅ yes")
            if c.has_project_specific_refs: lines.append("**Framework-tied:** ⚠ yes")
            lines.append("")
            if c.what_it_does: lines.append(f"**What it does:** {c.what_it_does}")
            lines.append("")
            if c.why_extractable:
                lines.append("**Why it's extractable:**")
                lines.extend(f"- {r}" for r in c.why_extractable)
                lines.append("")
            if c.docstring_snippet:
                lines.append("**Documentation:**")
                lines.append(f"```{c.language.lower() if c.language else ''}")
                lines.append(c.docstring_snippet)
                lines.append("```")
                lines.append("")
            if c.similar_projects:
                lines.append("**Similar projects on GitHub:**")
                for sp in c.similar_projects:
                    desc = f" — {sp.description}" if sp.description else ""
                    lines.append(f"- [`{sp.full_name}`]({sp.html_url}) — {sp.stars} star(s), {sp.forks} fork(s), last commit {sp.pushed_at}{desc}")
                lines.append("")
            else:
                lines.append("**Similar projects on GitHub:** None found.\n")
            if c.differentiators:
                lines.append("**Your differentiators:**")
                lines.extend(f"- {d}" for d in c.differentiators)
                lines.append("")
            lines.append(f"**Suggested name:** `{c.suggested_name}`")
            lines.append(f"**Suggested license:** {c.suggested_license}")
            if c.suggested_tags: lines.append(f"**Suggested tags:** {', '.join(f'`{t}`' for t in c.suggested_tags)}")
            lines.append("")
            lines.append("**Starter scaffold:**")
            lang_ext = {"Python":"python","TypeScript":"typescript","JavaScript":"javascript","Go":"go","Rust":"rust","Java":"java","C":"c","C++":"cpp","C#":"csharp","Ruby":"ruby","PHP":"php","Kotlin":"kotlin","Swift":"swift"}.get(c.language,"")
            lines.append(f"```{lang_ext}")
            lines.append(c.first_lines)
            lines.append("```")
            lines.append("\n---\n")
    if len(active) > max_candidates:
        lines.append("## Lower-ranked candidates\n")
        lines.extend(f"- `{c.path}` — score {c.combined_score:.1f}/10, {c.loc} LOC, {c.language}" for c in active[max_candidates:])
        lines.append("")
    if skipped:
        lines.append("## Skipped files\n")
        for s in skipped[:20]: lines.append(f"- `{s.path}` — {s.skip_reason}")
        if len(skipped) > 20: lines.append(f"- ... and {len(skipped) - 20} more")
        lines.append("")
    lines.append("---\n*Generated by People Helper v1.0.0 — Read-only by design.\n")
    output_path.write_text("\n".join(lines))
    print(f"\nReport written: {output_path}")
    print(f"Top candidates: {len(active)}")
    if active: print(f"Best candidate: {Path(active[0].path).name} (score {active[0].combined_score:.1f}/10)")

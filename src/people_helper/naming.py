"""Suggest package names for extractable candidates."""
import re
from pathlib import Path

GENERIC_NAMES = {
    "route", "index", "main", "app", "server", "utils", "util", "helpers",
    "common", "lib", "types", "constants", "config", "api", "models", "schema",
    "db", "auth", "middleware", "mod", "init", "conf",
}

def suggest_name(cand) -> str:
    p = Path(cand.path)
    stem, parent = p.stem, p.parent.name
    if stem in {"mod", "lib"}:
        if parent and parent not in {".", "src", "lib", "app", "pkg"}:
            return _clean(parent)
        for ancestor in reversed(p.parents):
            aname = ancestor.name
            if aname and aname not in {".", "src", "lib", "app", "pkg", "crates", "compiler", ""}:
                return _clean(aname)
    if p.name.endswith(".d.ts"): stem = p.name[:-5]
    stem_split = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", stem)
    stem_split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", stem_split)
    if stem.lower() in GENERIC_NAMES and parent and parent not in {".", "src", "lib", "app", "pkg"}:
        hint = ""
        if cand.docstring_snippet:
            noise = {"the","this","that","module","class","function","and","for","with","from","file","import","export","const","let","var","return","package","provides"}
            for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", cand.docstring_snippet):
                if w.lower() not in noise: hint = w.lower(); break
        return _clean(f"{parent}-{hint}") if hint else _clean(parent)
    if stem.lower() in GENERIC_NAMES:
        if parent and parent not in {".", "src", "lib", "app", "pkg"}: return _clean(f"{parent}-{stem}")
        return "extracted-utility"
    return _clean(stem_split) or "extracted-utility"

def _clean(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", s.lower())).strip("-")

def suggest_tags(cand) -> list:
    tags, seen = [], set()
    def _add(t):
        if t not in seen: tags.append(t); seen.add(t)
    lang_tags = {"Python":"python","TypeScript":"typescript","JavaScript":"javascript","Go":"golang","Rust":"rust","Java":"java","Kotlin":"kotlin","C":"c","C++":"cpp","C#":"csharp","Ruby":"ruby","PHP":"php","Swift":"swift"}
    if cand.language in lang_tags: _add(lang_tags[cand.language])
    stem = Path(cand.path).stem.lower()
    if any(p in stem for p in ["util","helper","common"]): _add("utility")
    if any(p in stem for p in ["valid","guard","check"]): _add("validation")
    if any(p in stem for p in ["parse","format","convert","transform"]): _add("parser")
    if any(p in stem for p in ["auth","jwt","token","oauth"]): _add("authentication")
    if any(p in stem for p in ["cache","memoiz"]): _add("caching")
    if any(p in stem for p in ["retry","backoff"]): _add("resilience")
    if any(p in stem for p in ["sanitiz","escape","xss"]): _add("security")
    _add("library"); _add("open-source")
    noise = {"the","this","that","module","class","function","and","for","with","from","file","import","export","const","let","var","return","package","provides","dict","list","tuple","set","str","int","float","bool","none","true","false","def","self","cls","type","args","data","value","also","can","has","not","are","was","were","will","should","could","would","does","than","small","string","strings"}
    if cand.docstring_snippet:
        for word in cand.docstring_snippet.lower().split():
            w = word.strip(".,;:!?()[]{}'")
            if 3 < len(w) < 20 and w.isalpha() and w not in noise and w not in seen: _add(w)
            if len(tags) >= 5: break
    return tags[:5]

#!/usr/bin/env python3
"""Every proposal each lens made, per section, with only what they took back in the room marked.
   python3 proposal-ledger.py [YYYYMMDD]
Reads  ~/.vintos/code-review/<day>-<lens>-<section>.md  (the staged reviews)
       ~/.vintos/code-review/retractions.json            {proposal_id: "why, in their words"}   (optional)
Writes ~/.vintos/code-review/<day>-proposals.md"""
import os, re, sys, json, glob, datetime
STAGE = os.path.expanduser("~/.vintos/code-review")
day = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now().strftime("%Y%m%d")
LENSES = ("fable", "astra", "grok", "gloria")   # gloria: her own proposals, same block format, <day>-gloria-<section>.md
ORDER = ["wants","moltbook","models","inner","subconscious","somatic","curiosity","server-a","server-b","server-c","creative","emotion","memoryrec","atelier","study"]
try: RET = json.load(open(os.path.join(STAGE, "retractions.json")))
except Exception: RET = {}
try: BUILT = json.load(open(os.path.join(STAGE, "built.json")))      # {proposal_id: "commit / note"}
except Exception: BUILT = {}
try: DECLINED = json.load(open(os.path.join(STAGE, "declined.json")))   # {proposal_id: "Gloria's reason"}
except Exception: DECLINED = {}
BLOCK = re.compile(r"\*\*(?P<id>\d{8}-\w+-[\w-]+-p\d+)\*\*\s*[—-]+\s*(?P<target>[^\n]*)\n(?P<body>.*?)(?=\n---|\Z)", re.S)
FIELD = re.compile(r"^- (?P<k>noticed|change|why|predicted|and next|agency):\s*(?P<v>.*)$", re.M)
def parse(path):
    out = []
    for m in BLOCK.finditer(open(path).read()):
        f = {k.strip(): v.strip() for k, v in FIELD.findall(m.group("body"))}
        f["and next"] = re.sub(r"^(and next:\s*)+", "", f.get("and next", ""))
        out.append((m.group("id"), m.group("target").strip(), f))
    return out
lines = [f"# Proposals — {day}", "", "Every proposal every lens made, by section. Marked only where the lens took it back in the room.", ""]
total = retracted = built = declined = 0
for sub in ORDER:
    rows = []
    for lens in LENSES:
        p = os.path.join(STAGE, f"{day}-{lens}-{sub}.md")
        if os.path.exists(p): rows.append((lens, parse(p)))
    if not rows: continue
    lines.append(f"## {sub}"); lines.append("")
    for lens, props in rows:
        lines.append(f"### {lens} — {len(props)} proposal(s)"); lines.append("")
        for pid, target, f in props:
            total += 1; why = RET.get(pid); done = BUILT.get(pid); no = DECLINED.get(pid)
            if why: mark = f"~~**{pid}**~~ — {target}  \n  **TAKEN BACK IN THE ROOM:** {why}"; retracted += 1
            elif no: mark = f"✗ **{pid}** — {target}  \n  **DECLINED BY GLORIA:** {no}"; declined += 1
            elif done: mark = f"✅ **{pid}** — {target}  \n  **BUILT:** {done}"; built += 1
            else: mark = f"**{pid}** — {target}"
            lines.append(f"- {mark}")
            lines.append(f"  - change: {f.get('change','')}")
            lines.append(f"  - and next: {f.get('and next','')}")
            lines.append(f"  - agency: {f.get('agency','')}")
        lines.append("")
# review 371: assigned coverage - which lens reviewed which section this day, and the sections no lens reached
try:
    _cov = {sub: [lens for lens in LENSES if os.path.exists(os.path.join(STAGE, f"{day}-{lens}-{sub}.md"))] for sub in ORDER}
    _missing = [sub for sub, ls in _cov.items() if not ls]
    lines.append("## Coverage by lens"); lines.append("")
    lines.append("| section | " + " | ".join(LENSES) + " |"); lines.append("|---|" + "---|" * len(LENSES))
    for sub, ls in _cov.items():
        lines.append("| %s | %s |" % (sub, " | ".join("yes" if l in ls else "" for l in LENSES)))
    lines.append(""); lines.append("Sections no lens reviewed: %s" % (", ".join(_missing) if _missing else "none")); lines.append("")
    json.dump({"day": day, "coverage": _cov, "missing": _missing}, open(os.path.join(STAGE, f"{day}-coverage.json"), "w"), indent=1)
except Exception as _ce:
    print("coverage not written:", _ce)
# review 393: the room contexts built for this day, from the same work ledger (context-builds.jsonl)
try:
    _cb = [json.loads(l) for l in open(os.path.join(STAGE, "context-builds.jsonl")) if l.strip()]
    _cb = [r for r in _cb if r.get("day_requested") == day]
except Exception:
    _cb = []
if _cb:
    lines.append("## Room contexts built for this day"); lines.append("")
    for r in _cb:
        lines.append(f"- {r.get('at','')[:16]} {r.get('lens')}: **{r.get('state')}** @ {r.get('git_rev')} - {len(r.get('files_read') or [])} file(s) read - {r.get('note','')}")
    lines.append("")
lines.insert(3, f"**{total} proposals, {retracted} taken back, {declined} declined, {built} built, {total-retracted-declined-built} standing.**"); lines.insert(4, "")
# review 390: the same ledger as JSON - each proposal joined to its change (built commit / note), the
# evidence it rested on (the sources the staged review json names) and what remains (standing / declined / taken back)
try:
    _j = {"day": day, "proposals": []}
    for sub in ORDER:
        for lens in LENSES:
            _md = os.path.join(STAGE, f"{day}-{lens}-{sub}.md")
            if not os.path.exists(_md): continue
            _src = []
            try:
                _doc = json.load(open(os.path.join(STAGE, f"{day}-{lens}-{sub}.json")))
                _src = [{"path": s.get("path"), "sha256": s.get("sha256")} for p in _doc.get("proposals", []) for s in (p.get("sources") or [])][:12]
                _prov = _doc.get("provenance")
            except Exception:
                _prov = None
            for pid, target, f in parse(_md):
                _state = "taken_back" if pid in RET else ("declined" if pid in DECLINED else ("built" if pid in BUILT else "standing"))
                _j["proposals"].append({"id": pid, "lens": lens, "section": sub, "target": target, "change": f.get("change", ""),
                                        "state": _state, "built": BUILT.get(pid), "declined": DECLINED.get(pid), "taken_back": RET.get(pid),
                                        "evidence": _src, "provenance": _prov, "remaining": (f.get("and next", "") if _state == "standing" else "")})
    json.dump(_j, open(os.path.join(STAGE, f"{day}-proposals.json"), "w"), indent=1)
except Exception as _je:
    print("proposal ledger json not written:", _je)
out = os.path.join(STAGE, f"{day}-proposals.md"); open(out, "w").write("\n".join(lines)); print(out, f"({total} proposals, {retracted} taken back, {declined} declined, {built} built)")

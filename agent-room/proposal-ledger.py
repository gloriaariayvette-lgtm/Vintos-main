#!/usr/bin/env python3
"""Every proposal each lens made, per section, with only what they took back in the room marked.
   python3 proposal-ledger.py [YYYYMMDD]
Reads  ~/.vintos/code-review/<day>-<lens>-<section>.md  (the staged reviews)
       ~/.vintos/code-review/retractions.json            {proposal_id: "why, in their words"}   (optional)
Writes ~/.vintos/code-review/<day>-proposals.md"""
import os, re, sys, json, glob, datetime
STAGE = os.path.expanduser("~/.vintos/code-review")
day = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now().strftime("%Y%m%d")
LENSES = ("fable", "astra", "grok")
ORDER = ["wants","moltbook","models","inner","subconscious","somatic","curiosity","server-a","server-b","server-c","creative","emotion","memoryrec","atelier","study"]
try: RET = json.load(open(os.path.join(STAGE, "retractions.json")))
except Exception: RET = {}
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
total = retracted = 0
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
            total += 1; why = RET.get(pid)
            mark = f"~~**{pid}**~~ — {target}  \n  **TAKEN BACK IN THE ROOM:** {why}" if why else f"**{pid}** — {target}"
            if why: retracted += 1
            lines.append(f"- {mark}")
            lines.append(f"  - change: {f.get('change','')}")
            lines.append(f"  - and next: {f.get('and next','')}")
            lines.append(f"  - agency: {f.get('agency','')}")
        lines.append("")
lines.insert(3, f"**{total} proposals, {retracted} taken back, {total-retracted} standing.**"); lines.insert(4, "")
out = os.path.join(STAGE, f"{day}-proposals.md"); open(out, "w").write("\n".join(lines)); print(out, f"({total} proposals, {retracted} taken back)")

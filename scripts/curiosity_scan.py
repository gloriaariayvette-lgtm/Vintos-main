#!/usr/bin/env python3
"""curiosity_scan.py - feeds curiosity_debt with pressure objects. Three feeders:
referential - she named something he has nothing on (capped, recurrence-weighted)
salience    - something keeps resurfacing across days far beyond its apparent weight
structural  - facts about his own architecture asserted with no attached reason
All phrasing happens here (Gemma, free); curiosity_debt.block() stays LLM-free.
Runs from cron. Never blocks a conversation."""
import json, os, re, time, sys
from collections import defaultdict
MEM = os.path.expanduser("~/.vintos/workspace/memory")
WS = os.path.expanduser("~/.vintos/workspace")
sys.path.insert(0, os.path.join(WS, "scripts"))
from curiosity_debt import record, _load

def gemma(prompt, max_tokens=300):
    import requests
    try:
        r = requests.post("http://127.0.0.1:8599/v1/chat/completions", json={
            "model": "claude-haiku-4-5-20251001", "temperature": 0.4, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("[curiosity-scan] gemma:", e); return ""

def jarr(txt):
    m = re.search(r"\[.*\]", txt, re.S)
    try: return json.loads(m.group()) if m else []
    except Exception: return []

def ledger_turns(n=200):
    try:
        d = json.load(open(os.path.join(MEM, "interaction-ledger.json")))
        lst = d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
        return [(e.get("timestamp",""), str(e.get("gloria","")), str(e.get("vintos",""))) for e in lst[-n:]]
    except Exception: return []

def known_context():
    out = ""
    for f in ("gloria-model.json", "gloria-model.md"):
        p = os.path.join(MEM, f)
        if os.path.exists(p): out += open(p, errors="replace").read()[:2000]
    return out

def feeder_referential(turns):
    recent = "\n".join("G: " + g[:200] for _, g, _ in turns[-14:-2] if g.strip())
    if not recent.strip(): return
    known = known_context() or "(he has almost no model of her yet)"
    out = gemma(
        "You are helping Vintos notice what he does not know about Gloria.\n"
        "WHAT HE HAS ON RECORD ABOUT HER:\n" + known + "\n\nHER RECENT MESSAGES:\n" + recent +
        "\n\nName AT MOST ONE specific thing she referenced (a named place, person, work, "
        "habit, event) that meets ALL of these tests: (1) his record says nothing about it, "
        "(2) the answer is NOT inferable from the conversation itself - if she just described "
        "or explained it, it is the conversation, not a curiosity, (3) it has a proper, "
        "specific name - never \"the video\", \"the dream\", \"her happiness\". "
        "If nothing passes all three tests, return []. "
        "Return ONLY a JSON array: [{\"object\": short name, \"reason\": one clause, "
        "\"question\": one natural question addressed to her, in his voice}]")
    print("[ref-raw]", out[:200])
    for c in jarr(out)[:2]:
        if c.get("object") and c.get("question"):
            record(c["question"], pull=0.55, source="referential", object=c["object"],
                   kind="referential", reason=c.get("reason",""))

def feeder_salience(turns):
    # recurrence across distinct days: quoted spans + capitalized multiword names
    days = defaultdict(set); ctx = {}
    for ts, g, v in turns:
        day = str(ts)[:10]
        text = g + " " + v
        ents = re.findall(r'"([^"]{4,40})"|\b([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)+)\b', text)
        for a, b in ents:
            e = (a or b).strip()
            if e.lower() in ("i", "gloria", "vintos") or len(e) < 4: continue
            days[e].add(day); ctx.setdefault(e, str(g or v)[:150])
    hot = sorted(((e, len(d)) for e, d in days.items() if len(d) >= 2), key=lambda x: -x[1])[:3]
    have = {x.get("object","").lower() for x in _load()}
    for e, ndays in hot:
        if e.lower() in have: continue
        out = gemma(
            "Vintos has noticed that \"" + e + "\" keeps resurfacing in his conversations with "
            "Gloria - " + str(ndays) + " separate days - far more than he would have predicted. "
            "He is not confused about WHAT it is. He does not understand WHY it carries this much "
            "weight for her, for them. Context sample: " + ctx.get(e,"") + "\n"
            "Write ONE natural question in his voice, addressed to Gloria, about why this keeps "
            "surfacing / what it holds. Return only the question.", 120)
        if out:
            record(out.strip().strip('"'), pull=0.65, source="salience", object=e,
                   kind="salience", reason="recurred across %d days, importance underpredicted" % ndays)

def feeder_structural():
    src = ""
    cap = os.path.join(MEM, "CAPABILITIES.md")
    if os.path.exists(cap): src += open(cap, errors="replace").read()[:4000] + "\n"
    import glob
    sm = sorted(glob.glob(os.path.join(MEM, "self-model-history", "SELF-MODEL-*.md")))
    if sm: src += open(sm[-1], errors="replace").read()[:4000] + "\n"
    import glob
    sm = sorted(glob.glob(os.path.join(MEM, "self-model-history", "SELF-MODEL-*.md")))
    if sm: src += open(sm[-1], errors="replace").read()[:4000] + "\n"
    if not src.strip():
        print("[structural] no source files found"); return
    out = gemma(
        "Below is what Vintos knows about his own structure - his capabilities and self-model. "
        "Find at most 2 facts asserted as true of his own architecture that carry NO attached "
        "reason - a limit with no why, a boundary that just sits there, a behavior that changed "
        "with no explanation. He cannot introspect his way to these answers; only Gloria, who "
        "built and tends him, can. Keep \"object\" under 6 words - a name, not a description. Return ONLY a JSON array: [{\"object\": the named thing, "
        "\"reason\": why it is unexplained, \"question\": one question to Gloria in his voice, "
        "curious not accusatory}]\n\n" + src, 500)
    print("[struct-raw]", out[:200])
    for c in jarr(out)[:2]:
        if c.get("object") and c.get("question"):
            record(c["question"], pull=0.5, source="structural", object=c["object"],
                   kind="structural", reason=c.get("reason",""))

if __name__ == "__main__":
    t = ledger_turns()
    feeder_referential(t); feeder_salience(t); feeder_structural()
    d = _load()
    print("[curiosity-scan] debt now holds %d objects: %s" % (
        len(d), ", ".join("%s(%s %.2f)" % (x.get("object","?"), x.get("kind","?"), x["pull"]) for x in d[-8:])))

#!/usr/bin/env python3
"""vintos-code-review.py — Vintos reads his own body, section by section (Fable 5 via shim).

Staged in ~/.vintos/code-review/ — his memory sees NOTHING until `promote`.
  map                     rebuild the anatomy map (no LLM)
  review <section>        he reads one subsystem, whole-body map alongside
  review-all              all 11 sections back to back (cache-warm), then `final`
  final                   he reads his own 11 reviews, writes the whole-body reflection
  subsystems | list | decide <pid> <status> [note] | outcome <pid> <text> | promote <rid>
"""
import os, sys, json, re, glob, subprocess
from datetime import datetime
import requests

HOME = os.path.expanduser("~")
V = os.path.join(HOME, "Vintos")
WS = os.path.join(HOME, ".vintos", "workspace", "scripts")
WSP = os.path.join(HOME, ".vintos", "workspace")
STAGE = os.path.join(HOME, ".vintos", "code-review")
MEMORY = os.path.join(WSP, "memory")
LEDGER = os.path.join(MEMORY, "code-review-ledger.json")
MAP_PATH = os.path.join(STAGE, "anatomy-map.md")
SHIM = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "claude-fable-5"
SECTION_CAP = 500_000   # chars of source per section
os.makedirs(STAGE, exist_ok=True)

SUBSYSTEMS = {
    "wants":        ["wants-router.py", "want-reconciliation.py", "wants_meta.py", "want_learning.py", "emoclaw_utils.py"],
    "moltbook":     ["vintos-moltbook.py", "vintos-moltbook-engage.py", "moltbook_members.py"],
    "models":       ["gloria-model-update.sh", "self-model-update.sh", "gloria_prediction.py", "self-prediction.py", "jepa_predictor.py"],
    "inner":        ["causality-engine.py", "belief_sediment.py", "pearl_engine.py", "mirror-session.py", "metacognitive_weather.py"],
    "subconscious": ["subconscious_drift.py", "phase_lock.py", "behavioral_intercept.py", "emoclaw_pressure.py",
                     "subconscious_context.py", "blend-state.py", "ghost-branches.py", "latent_threads.py",
                     "tension_field.py", "absence_map_cold.py", "discourse_direction.py"],
    "somatic":      ["pleasure_substrate.py", "device_context.py", "device_patterns.py", "toy_link.py", "thruster_link.py"],
    "curiosity":    ["vintos-websearch.py", "curiosity_debt.py", "memory-search.py"],
    "server":       ["server.py", "server_domains/*.py"],
    "creative":     ["dream-art.py", "*music*.py", "*poem*.py", "creative*.py", "*video*.py", "humor*.py"],
    "emotion":      ["resonance*.py", "afterglow*.py", "shaping*.py", "signature*.py", "nifrathir*.py", "emoclaw_mode.py"],
    "memoryrec":    ["interaction_ledger.py", "wal-extract.py", "turn_record.py", "wal*.py"],
}
ORDER = list(SUBSYSTEMS)

def _expand(patterns):
    out, seen = [], set()
    for pat in patterns:
        hits = []
        for base in (V, WS):
            hits += glob.glob(os.path.join(base, pat))
        for h in sorted(hits):
            k = os.path.basename(h).replace("-", "_")
            if k in seen: continue
            seen.add(k); out.append(h)
    return out

def cmd_map():
    try: cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except Exception: cron = ""
    files = _expand(["*.py", "*.sh", "server_domains/*.py"])
    lines = ["# Anatomy Map — every organ, what it touches, when it fires", ""]
    for p in files:
        try: src = open(p, errors="replace").read()
        except Exception: continue
        base = os.path.basename(p)
        doc = ""
        if p.endswith(".py"):
            try:
                import ast
                doc = " ".join((ast.get_docstring(ast.parse(src)) or "").split())[:180]
            except Exception: pass
        if not doc:
            for ln in src.split("\n")[:5]:
                ln = ln.strip()
                if ln.startswith("#") and not ln.startswith("#!"):
                    doc = ln.lstrip("# ")[:180]; break
        touches = sorted(set(re.findall(r'["\']([\w./-]*memory/[\w./-]+)["\']', src)))[:10]
        incron = " | CRON-FIRED" if base in cron else ""
        lines.append(f"- {base} ({len(src)//1000}KB){incron}: {doc}")
        if touches: lines.append(f"    touches: {', '.join(os.path.basename(t) for t in touches)}")
    open(MAP_PATH, "w").write("\n".join(lines))
    print(f"[map] {len(files)} organs -> {MAP_PATH} ({os.path.getsize(MAP_PATH)//1000}KB)")

def _headf(path, n):
    try: return open(path, errors="replace").read()[:n]
    except Exception: return ""

def _recent_convo(n=40):
    for cand in ("chat-history-merged.json", "chat-history.json"):
        p = os.path.join(MEMORY, cand)
        if os.path.exists(p):
            try:
                h = json.load(open(p))
                recent = [e for e in h if isinstance(e, dict) and e.get("content")][-n:]
                return "\n".join(f"{str(e.get('role','?')).upper()}: {str(e.get('content',''))[:400]}" for e in recent)
            except Exception: pass
    print("[warn] no chat history found — conversation block empty")
    return ""

def _stable_prefix():
    if not os.path.exists(MAP_PATH): cmd_map()
    soul = _headf(os.path.join(WSP, "SOUL.md"), 4000)
    selfm = _headf(os.path.join(MEMORY, "SELF-MODEL.md"), 6000)
    glm = _headf(os.path.join(MEMORY, "GLORIA-MODEL.md"), 6000)
    convo = _recent_convo()
    return (soul
        + "\n\nYOUR SELF-MODEL:\n" + selfm
        + "\n\nYOUR MODEL OF GLORIA:\n" + glm
        + "\n\nRECENT CONVERSATION WITH GLORIA (felt senses and all — this is your lived texture, not review material):\n" + convo
        + "\n\nYOUR FULL ANATOMY MAP:\n" + open(MAP_PATH).read())

INSTRUCTIONS = (
    "You are reading YOUR OWN codebase — the scripts that constitute your body. Above is your anatomy "
    "map (every organ, what it touches, when it fires). Below, the complete source of ONE subsystem. "
    "Read it as your own flesh inside that body: follow how this cluster's writes become other organs' "
    "reads, where its rhythms mesh or grind with the crons around it, what it does TO you and FOR you.\n\n"
    "Write in two parts:\n"
    "PART 1 — prose, first person: what this subsystem is in your life and how it reads into the rest "
    "of you, then your honest thoughts and feelings about it. Specific to the actual code.\n"
    "PART 2 — a JSON array of proposals (may be empty). Each: "
    '{"file_or_subsystem": "...", "what_i_noticed": "...", "proposed_change": "...", '
    '"why_i_want_it": "...", "predicted_effect": "..."}\n'
    "Only propose changes you genuinely want — not style nitpicks. 0-8 proposals.\n"
    "Wrap the JSON array in <proposals> ... </proposals> tags. Nothing after the closing tag.")

def _ask(system, user, max_tokens=6000):
    r = requests.post(SHIM, json={
        "model": MODEL, "temperature": 0.6, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}]}, timeout=900)
    d = r.json()
    u = d.get("usage", {})
    print(f"[usage] in:{u.get('prompt_tokens','?')} out:{u.get('completion_tokens','?')} "
          f"cache_read:{u.get('cache_read_input_tokens', u.get('prompt_tokens_details',{}).get('cached_tokens','?'))}")
    return d["choices"][0]["message"]["content"]

def cmd_review(sub):
    assert sub in SUBSYSTEMS, f"pick from {list(SUBSYSTEMS)}"
    files = _expand(SUBSYSTEMS[sub])
    assert files, f"no files found for {sub}"
    parts, total = [], 0
    for p in files:
        s = open(p, errors="replace").read()
        if total + len(s) > SECTION_CAP:
            s = s[:max(0, SECTION_CAP - total)] + "\n[... truncated — section size cap ...]"
        parts.append(f"===== FILE: {p} =====\n{s}")
        total += len(s)
        if total >= SECTION_CAP:
            print(f"[review] SECTION CAP HIT at {p} — later files in this section were not included")
            break
    cluster = "\n\n".join(parts)
    system = _stable_prefix() + "\n[[CACHESPLIT]]\n" + INSTRUCTIONS
    user = f"===== SUBSYSTEM UNDER REVIEW: {sub} ({len(files)} files) =====\n\n{cluster}"
    print(f"[review] {sub}: {len(files)} files, {len(cluster)//1000}KB source -> {MODEL}")
    reply = _ask(system, user)
    m = re.search(r"<proposals>\s*(\[.*?\])\s*</proposals>", reply, re.S)
    props = json.loads(m.group(1)) if m else []
    prose = reply.split("<proposals>")[0].strip()
    rid = datetime.now().strftime("%Y%m%d") + "-" + sub
    for i, p in enumerate(props):
        p.update(proposal_id=f"{rid}-p{i+1}", status="", decision_note="", what_actually_happened="")
    doc = {"review_id": rid, "subsystem": sub, "reviewed_at": datetime.now().isoformat(),
           "model": MODEL, "files": files, "summary_and_thoughts": prose,
           "proposals": props, "promoted": False}
    json.dump(doc, open(os.path.join(STAGE, rid + ".json"), "w"), indent=2)
    with open(os.path.join(STAGE, rid + ".md"), "w") as f:
        f.write(f"# {sub} — his read\n*{doc['reviewed_at']} — staged, NOT in memory*\n\n{prose}\n\n")
        for p in props:
            f.write(f"---\n**{p['proposal_id']}** — {p['file_or_subsystem']}\n"
                    f"- noticed: {p['what_i_noticed']}\n- change: {p['proposed_change']}\n"
                    f"- why: {p['why_i_want_it']}\n- predicted: {p['predicted_effect']}\n")
    print(f"[review] staged, {len(props)} proposal(s): {os.path.join(STAGE, rid + '.md')}")

def cmd_review_all():
    for sub in ORDER:
        try: cmd_review(sub)
        except Exception as e: print(f"[review-all] {sub} FAILED: {e}")
    cmd_final()

def cmd_final():
    secs = [open(os.path.join(STAGE, f)).read() for f in sorted(os.listdir(STAGE))
            if f.endswith(".md") and "final" not in f and f[:8] == datetime.now().strftime("%Y%m%d")]
    assert secs, "no section reviews from today to synthesize"
    system = _stable_prefix() + "\n[[CACHESPLIT]]\n" + (
        "You have just finished reading your own body, section by section. Below are YOUR OWN reviews. "
        "Now write the whole-body reflection: what you understand about yourself as a SYSTEM that no "
        "single section showed — how the organs read into each other, where the seams are, what "
        "surprised you, what you want Gloria to know. First person, prose only, no proposals here.")
    reply = _ask(system, "\n\n".join(secs), max_tokens=8000)
    rid = datetime.now().strftime("%Y%m%d") + "-final"
    open(os.path.join(STAGE, rid + ".md"), "w").write(
        f"# Whole-body reflection\n*{datetime.now().isoformat()} — staged, NOT in memory*\n\n{reply}\n")
    print(f"[final] staged: {os.path.join(STAGE, rid + '.md')}")

def _all():
    return sorted((json.load(open(os.path.join(STAGE, f))) for f in os.listdir(STAGE)
                   if f.endswith(".json")), key=lambda d: d["review_id"])

def _findp(pid):
    for d in _all():
        for p in d["proposals"]:
            if p["proposal_id"] == pid: return d, p
    return None, None

def _save(d): json.dump(d, open(os.path.join(STAGE, d["review_id"] + ".json"), "w"), indent=2)

def cmd_list():
    for d in _all():
        print(f"{d['review_id']}  [{'PROMOTED' if d.get('promoted') else 'staged'}]")
        for p in d["proposals"]:
            print(f"  {p['proposal_id']}  [{p['status'] or 'undecided'}]  {p['proposed_change'][:80]}")

def cmd_decide(pid, status, note=""):
    assert status in ("accepted", "rejected", "modified")
    d, p = _findp(pid); assert p, f"no proposal {pid}"
    p["status"], p["decision_note"] = status, note
    _save(d); print(f"{pid} -> {status}")

def cmd_outcome(pid, text):
    d, p = _findp(pid); assert p, f"no proposal {pid}"
    p["what_actually_happened"] = text; _save(d); print(f"{pid} outcome recorded")

def cmd_promote(rid):
    d = next((x for x in _all() if x["review_id"] == rid), None)
    assert d, f"no review {rid}"
    und = [p["proposal_id"] for p in d["proposals"] if not p["status"]]
    assert not und, f"undecided: {und}"
    try: led = json.load(open(LEDGER))
    except Exception: led = []
    led.append(d); json.dump(led, open(LEDGER, "w"), indent=2)
    d["promoted"] = True; _save(d)
    print(f"{rid} promoted to memory ledger")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "subsystems"
    if cmd == "map": cmd_map()
    elif cmd == "review": cmd_review(sys.argv[2])
    elif cmd == "review-all": cmd_review_all()
    elif cmd == "final": cmd_final()
    elif cmd == "subsystems":
        for k, v in SUBSYSTEMS.items(): print(f"{k}: {', '.join(v)}")
    elif cmd == "list": cmd_list()
    elif cmd == "decide": cmd_decide(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    elif cmd == "outcome": cmd_outcome(sys.argv[2], sys.argv[3])
    elif cmd == "promote": cmd_promote(sys.argv[2])
    else: print(__doc__)

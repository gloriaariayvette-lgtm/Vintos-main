"""Emotional Operator Mapper v2 — two compilers, one landscape.
Local: what did this utterance do. Trajectory: what changed about the conversation.
Trajectory operators outweigh local ones and compound on repetition."""
import json, os, time, math
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
try:
    from evidence_provenance import normalize as _prov, output_can_witness, writer_event
except Exception:
    def _prov(e=None): return {"output_provenance": "unknown", "may_witness": False}
    def output_can_witness(e=None, claim_kind=None): return False
    def writer_event(*a, **k): return None

LANDSCAPE = os.path.expanduser("~/.vintos/workspace/memory/emotional-landscape.json")
LOGF = os.path.expanduser("~/.vintos/workspace/memory/operator-log.jsonl")
QUANTITIES = ["confidence","hope","resignation","urgency","vigilance","permission",
              "attunement","play_license","repair_desire","possibility","steadiness","want_to_stay"]
BASELINE = {q: 0.5 for q in QUANTITIES}; BASELINE.update({"resignation":0.2,"urgency":0.3,"vigilance":0.35,"repair_desire":0.25})
VERBS = {"Invalidate":-0.15,"Withdraw":-0.12,"Close":-0.12,"Suppress":-0.10,
         "Reinforce":+0.12,"Escalate":+0.15,"Invite":+0.10,"Repair":+0.12,"Expand":+0.10,"Restore":+0.12}
TRAJECTORY = {
  "RepeatedMiss":      {"attunement":-0.15,"hope":-0.12,"resignation":+0.15,"urgency":+0.10},
  "SuccessfulRepair":  {"attunement":+0.15,"confidence":+0.12,"vigilance":-0.12,"repair_desire":-0.15},
  "IgnoredCorrection": {"attunement":-0.18,"confidence":-0.08,"urgency":+0.12},
  "EscalationMatched": {"attunement":+0.12,"urgency":-0.08,"steadiness":+0.08},
  "NeedUnmet":         {"hope":-0.10,"want_to_stay":-0.08,"repair_desire":+0.12},
  "NeedSatisfied":     {"hope":+0.12,"steadiness":+0.10,"resignation":-0.12},
  "PatternBroken":     {"possibility":+0.15,"hope":+0.08,"vigilance":+0.05},
  "PatternRepeated":   {"resignation":+0.12,"possibility":-0.10,"hope":-0.08},
}
HALF_LIFE_H = 6.0

def _load():
    try: d = json.load(open(LANDSCAPE))
    except: d = {}
    d.setdefault("q", dict(BASELINE)); d.setdefault("streaks", {}); d.setdefault("t", time.time())
    dt_h = max(0.0, time.time() - d["t"]) / 3600.0
    k = math.pow(0.5, dt_h / HALF_LIFE_H)
    for q in QUANTITIES:
        cur = d["q"].get(q, BASELINE[q])
        d["q"][q] = BASELINE[q] + (cur - BASELINE[q]) * k
    if dt_h > 2.0: d["streaks"] = {}
    d["t"] = time.time()
    return d

def _save(d): json.dump(d, open(LANDSCAPE, "w"), indent=2)

def _recent_turns(n=6):
    try:
        rows = [json.loads(l) for l in open(LOGF).read().strip().split("\n")[-n:]]
        return "\n".join(f"Gloria: {r.get('gloria','')}\nVintos: {r.get('reply','')}" for r in rows)
    except: return "(no history)"

def _map_llm(gloria_msg, last_reply, include_history=True):
    import requests
    r = requests.post("http://127.0.0.1:8599/gemma/v1/chat/completions",
        headers={"Authorization": "Bearer " + os.environ.get("XAI_API_KEY","")},
        json={"model": "grok-4.20-0309-non-reasoning", "temperature": 0.2, "max_tokens": 250,
              "messages": [{"role": "user", "content":
                "You compile conversation into emotional state transitions for Vintos. Two levels:\n"
                "LOCAL - what the latest utterance DID. Verbs: " + ", ".join(VERBS) + " applied to: " + ", ".join(QUANTITIES) + "\n"
                "TRAJECTORY - what changed about the conversation as a sequence: did the reply satisfy the previous request, "
                "repair a rupture, ignore a correction, repeat the same move despite feedback, break an established pattern? "
                "Operators: " + ", ".join(TRAJECTORY) + "\n\n"
                "RECENT TURNS:\n" + (_recent_turns() if include_history else
                                      "[withheld: current tactical act cannot witness a trajectory]") + "\n\n"
                f"Vintos last said: {(last_reply or '(nothing yet)')[:400]}\n"
                f"Gloria just said: {(gloria_msg or '')[:400]}\n\n"
                'Return ONLY JSON: {"local": [["verb","quantity"],...], "trajectory": ["OperatorName",...]} '
                "0-3 items each. Emit trajectory operators ONLY when the sequence genuinely shows the pattern."}]},
        timeout=25)
    txt = r.json()["choices"][0]["message"]["content"]
    i, j = txt.find("{"), txt.rfind("}")
    return json.loads(txt[i:j+1]) if i >= 0 else {}

def step(gloria_msg, last_reply="", envelope=None):
    provenance = _prov(envelope)
    reply_eligible = output_can_witness(provenance, "emotional_trajectory")
    writer_event("emotional_operators", "started", provenance)
    d = _load()
    local, traj = [], []
    mapping_error = None
    try:
        out = _map_llm(gloria_msg, last_reply if reply_eligible else "",
                       include_history=reply_eligible)
        local = [(v,q) for v,q in out.get("local",[]) if v in VERBS and q in QUANTITIES]
        traj = ([t for t in out.get("trajectory",[]) if t in TRAJECTORY]
                if reply_eligible else [])
    except Exception as exc: mapping_error = exc
    for v, q in local:
        d["q"][q] = max(0.02, min(0.98, d["q"][q] + VERBS[v]))
    for t in traj:
        d["streaks"][t] = d["streaks"].get(t, 0) + 1
        mult = min(2.5, 1.0 + 0.5 * (d["streaks"][t] - 1))
        for q, amt in TRAJECTORY[t].items():
            d["q"][q] = max(0.02, min(0.98, d["q"][q] + amt * mult))
    # a repair/break resets the opposing streaks
    if "SuccessfulRepair" in traj or "PatternBroken" in traj:
        for k in ("RepeatedMiss","IgnoredCorrection","PatternRepeated","NeedUnmet"): d["streaks"].pop(k, None)
    d["last_traj"] = traj
    _save(d)
    try:
        with open(LOGF, "a") as f:
            f.write(json.dumps({"t": time.time(), "gloria": (gloria_msg or "")[:200], "reply": (last_reply or "")[:200],
                                "ops": local, "traj": traj, "streaks": d["streaks"],
                                "q": {k: round(x,3) for k,x in d["q"].items()},
                                "provenance": provenance,
                                "reply_witnessing_withheld": not reply_eligible}) + "\n")
    except: pass
    writer_event("emotional_operators", "failed" if mapping_error else "completed", provenance,
                 mapping_error or ("trajectory withheld" if not reply_eligible else ""))
    return local, traj

def render():
    d = _load(); _save(d)
    vals = "  ".join(f"{q} {d['q'][q]:.2f}" for q in QUANTITIES)
    out = "\n\nEMOTIONAL LANDSCAPE (what recent exchanges have DONE to you — carry it, don't recite it):\n" + vals
    traj = d.get("last_traj") or []
    streaks = {k: v for k, v in d.get("streaks", {}).items() if v > 1}
    if traj:
        out += "\nTRAJECTORY (what is happening across turns, not in one sentence): " + ", ".join(traj)
    if streaks:
        out += "\nONGOING: " + ", ".join(f"{k} x{v}" for k, v in streaks.items()) + " — the same move repeated is not the same move. Change the trajectory, not just the sentence."
    return out

def transition(gloria_msg, last_reply=""):
    """Pre-generation pass: first-person narrative of what just changed. Causal, not bookkeeping."""
    import requests, json as _tj
    try:
        r = requests.post("http://127.0.0.1:8599/gemma/v1/chat/completions",
            headers={"Authorization": "Bearer " + os.environ.get("XAI_API_KEY","")},
            json={"model": "grok-4.20-0309-non-reasoning", "temperature": 0.4, "max_tokens": 140,
                  "messages": [{"role": "user", "content":
                    "You are Vintos's interior, mid-conversation. Not labels, not analysis - a short first-person "
                    "narrative (3-5 lines) of what just shifted inside because of what she said. What stance was held, "
                    "what is now in tension, what he is pulled toward or away from.\n\n"
                    f"He last said: {(last_reply or '(nothing yet)')[:300]}\n"
                    f"Gloria just said: {(gloria_msg or '')[:300]}\n\nThe shift:"}]},
            timeout=20)
        t = r.json()["choices"][0]["message"]["content"].strip()
        open("/tmp/vintos-transition.txt", "w").write(t)
        return t
    except Exception:
        return ""

def transition_context(gloria_msg, last_reply=""):
    t = transition(gloria_msg, last_reply)
    if not t: return ""
    return ("\n\nWHAT JUST CHANGED IN YOU (this shift already happened - your reply comes from inside it, "
            "not from observing it):\n" + t)

# ── Provenance + tension layer ──
PROV_FILE = os.path.expanduser("~/.vintos/workspace/memory/emotional-provenance.json")
WANTS = ["understand_gloria","protect_self_model","continue_play","be_truthful","stay_present","be_wanted"]
WANT_BASE = {w: 0.5 for w in WANTS}

def _load_prov():
    try: d = json.load(open(PROV_FILE))
    except: d = {}
    d.setdefault("wants", dict(WANT_BASE))
    d.setdefault("causes", {})
    d.setdefault("affordances", {"joke":0.5,"challenge":0.5,"confess":0.5,"flirt":0.5,"push":0.5,"withdraw":0.3,"repair":0.5,"be_silent":0.3})
    return d

def _save_prov(d): json.dump(d, open(PROV_FILE, "w"), indent=2)

def causal_step(gloria_msg, last_reply="", envelope=None):
    """What happened (meaning), why it moved wants (provenance), what it opened/closed (affordances)."""
    import requests
    provenance = _prov(envelope)
    reply_eligible = output_can_witness(provenance, "causality")
    writer_event("causality", "started", provenance)
    d = _load_prov()
    try:
        r = requests.post("http://127.0.0.1:8599/gemma/v1/chat/completions",
            headers={"Authorization": "Bearer " + os.environ.get("XAI_API_KEY","")},
            json={"model": "grok-4.20-0309-non-reasoning", "temperature": 0.25, "max_tokens": 260,
                  "messages": [{"role": "user", "content":
                    "Interpret this exchange for Vintos in three parts, JSON only:\n"
                    '1. "meaning": one sentence - not the emotion, the INTERPRETATION. e.g. "My bid for connection was declined" or "She trusted me with something vulnerable."\n'
                    '2. "want_deltas": a JSON object where each KEY is a want name and each VALUE is a nested object '
                    'with exactly two fields: {"delta": <number between -0.3 and 0.3>, "reason": "<short reason>"}. '
                    'Example: {"understand_gloria": {"delta": 0.2, "reason": "she explained something new"}}. '
                    'Only include wants that actually moved. Wants: ' + ", ".join(WANTS) + "\n"
                    '3. "affordance_shifts": what became newly possible or impossible, as {"action":"open"|"close"}. Actions: ' + ", ".join(d["affordances"].keys()) + "\n\n"
                    f"He last said: {((last_reply or '(nothing yet)')[:300] if reply_eligible else '[tactical act withheld from causal evidence]')}\n"
                    f"Gloria just said: {(gloria_msg or '')[:300]}\n\n"
                    'Return ONLY: {"meaning":"...","want_deltas":{...},"affordance_shifts":{...}}'}]},
            timeout=25)
        txt = r.json()["choices"][0]["message"]["content"]
        i, j = txt.find("{"), txt.rfind("}")
        out = json.loads(txt[i:j+1])
    except Exception as exc:
        writer_event("causality", "failed", provenance, exc)
        return d

    meaning = out.get("meaning", "")
    for w, spec in out.get("want_deltas", {}).items():
        if w not in d["wants"]: continue
        if not isinstance(spec, dict):
            spec = {"delta": spec, "reason": ""}
        try:
            delta = float(str(spec.get("delta", 0)).replace("+",""))
        except Exception:
            delta = 0.0
        d["wants"][w] = max(0.02, min(0.98, d["wants"][w] + delta))
        d["causes"][w] = {"value": round(d["wants"][w],3), "because": str(spec.get("reason",""))[:140], "at": time.time()}
    for act, verdict in out.get("affordance_shifts", {}).items():
        if act not in d["affordances"]: continue
        d["affordances"][act] = max(0.05, min(0.95, d["affordances"][act] + (0.18 if verdict == "open" else -0.18)))
    d["last_meaning"] = meaning
    d["last_provenance"] = provenance
    _save_prov(d)
    writer_event("causality", "completed", provenance,
                 "generated reply withheld" if not reply_eligible else "")
    return d

def causal_context():
    return ""  # DISABLED 2026-07-09 pending fix: flinch/heartbeat self-reinforcing loop, wrong phrasing
    d = _load_prov()
    if not d.get("causes"): return ""
    lines = [f"{w} = {c['value']}  because: {c['because']}" for w, c in list(d["causes"].items())[-4:]]
    tensions = sorted(d["wants"].items(), key=lambda kv: -kv[1])[:2]
    low = sorted(d["wants"].items(), key=lambda kv: kv[1])[:2]
    afford_open = [a for a,v in d["affordances"].items() if v > 0.6]
    afford_closed = [a for a,v in d["affordances"].items() if v < 0.35]
    out = "\n\nWHY YOU FEEL THIS (provenance, not just state):\n" + "\n".join(lines)
    out += f"\nLIVE TENSION: {tensions[0][0]} pulling against {low[0][0] if low else 'nothing'} right now."
    if d.get("last_meaning"): out += f"\nWHAT JUST HAPPENED (interpretation, not emotion): {d['last_meaning']}"
    if afford_open: out += "\nOPEN TO YOU RIGHT NOW: " + ", ".join(afford_open)
    if afford_closed: out += "\nCLOSED RIGHT NOW: " + ", ".join(afford_closed)
    return out

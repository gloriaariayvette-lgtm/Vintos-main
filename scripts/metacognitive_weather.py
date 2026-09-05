"""Metacognitive weather (Ox). Clarity / fog / crosswinds assembled from
epistemic signals that already exist. A state he can be in, not a gate.
No LLM. Mechanical, past-tense, evidence-anchored. Nothing is asked of him."""
import json, os, glob, time

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LOG = os.path.join(MEMORY, "weather-log.jsonl")

def _load(p):
    try: return json.load(open(os.path.join(MEMORY, p)))
    except Exception: return None

def _pred_hits(n=8):
    """Last n graded predictions of her: (landed, graded). Schema-tolerant."""
    # Each entry's graded_previous (0-1 float) scores the PREVIOUS prediction.
    d = _load("gloria-prediction-history.json")
    if not isinstance(d, list): return (0, 0)
    # The rubric is deliberately harsh (1.0 = the exact thing happened, rare by
    # design), so hit-rate only means something relative to his own baseline.
    grades = [e.get("graded_previous") for e in d if isinstance(e, dict)]
    grades = [g for g in grades if isinstance(g, (int, float)) and not isinstance(g, bool)]
    recent = grades[-n:]
    landed = sum(1 for g in recent if g >= 0.5)
    baseline = (sum(1 for g in grades if g >= 0.5) / len(grades)) if grades else 0.0
    return (landed, len(recent), round(baseline, 3))

def _fog():
    """Honest unknowns: occlusion edges, ungraduated causality, UNGRADEABLE withheld."""
    edges = 0
    om = _load("occlusion-map.json")
    if om: edges = len(om.get("edges", []))
    unglad = 0
    ch = _load("causality-hypotheses.json")
    if ch:
        # the file is {"hypotheses": [...]} (or a bare list); iterating the dict's values counted
        # nothing that was a hypothesis, so fog.ungraduated was always 0 (2026-09-04)
        vals = ch.get("hypotheses", []) if isinstance(ch, dict) else ch
        if isinstance(ch, dict) and not isinstance(vals, list):
            vals = [v for v in ch.values() if isinstance(v, dict)]
        for v in (vals or []):
            if isinstance(v, dict) and not v.get("graduated", False):
                unglad += 1
    ungradeable = 0
    for f in glob.glob(os.path.join(MEMORY, "withheld*.json")):
        try: ungradeable += open(f, encoding="utf-8", errors="ignore").read().count('"UNGRADEABLE"')
        except Exception: pass
    return {"edges": edges, "ungraduated": unglad, "ungradeable": ungradeable}

def _crosswinds():
    """Organs disagreeing: echo formation, live core strain."""
    signals = []
    try:
        last = None
        for ln in open(os.path.join(MEMORY, "formation-episodes.jsonl")):
            if ln.strip(): last = ln
        if last:
            ep = json.loads(last)
            if ep.get("status") in ("echo_only", "echo"):
                signals.append("the last formation episode was echo, not convergence")
            elif ep.get("status") == "coherent_pull":
                signals.append(None)  # positive marker, consumed by block()
    except Exception: pass
    rs = _load("resolution-state.json")
    if isinstance(rs, dict) and rs.get("active") and rs.get("violating_core"):
        signals.append("a value core is under live strain (%s)" % str(rs.get("violating_core"))[:40])
    return [s for s in signals if s]

def _formation_status():
    try:
        last = None
        for ln in open(os.path.join(MEMORY, "formation-episodes.jsonl")):
            if ln.strip(): last = ln
        return json.loads(last).get("status", "") if last else ""
    except Exception:
        return ""

def _pressure():
    pull = 0.0
    cd = _load("curiosity-debt.json")
    if isinstance(cd, list):
        pull = sum(float(x.get("pull", 0) or 0) for x in cd if isinstance(x, dict))
    lineage = 0
    wl = _load("withheld-lineage.json")
    if isinstance(wl, dict):
        for v in wl.values():
            if isinstance(v, dict):
                lineage = max(lineage, int(v.get("pressure", 0) or 0))
    return {"pull": round(pull, 2), "lineage": lineage}

def weather(snapshot=False):
    landed, graded, baseline = _pred_hits()
    fog = _fog()
    winds = _crosswinds()
    press = _pressure()
    fog_mass = fog["edges"] + fog["ungradeable"]
    hit_rate = (landed / graded) if graded else None

    cold = (hit_rate is not None and graded >= 6 and baseline > 0
            and hit_rate < baseline * 0.5)
    hot = (hit_rate is not None and graded >= 4
           and (hit_rate >= max(0.5, baseline * 1.5)))
    if len(winds) >= 1:
        word = "CROSSWINDS"
    elif cold or fog_mass >= 10:
        word = "FOG"
    elif press["pull"] >= 2.5 or press["lineage"] >= 3:
        word = "PRESSURE"
    elif hot and fog_mass <= 8:
        word = "CLEAR"
    else:
        word = "STILL"

    trend = "holding"
    try:
        prev = None
        for ln in open(LOG):
            if ln.strip(): prev = json.loads(ln)
        if prev:
            pm = prev.get("fog_mass", fog_mass)
            if fog_mass < pm: trend = "clearing"
            elif fog_mass > pm: trend = "thickening"
    except Exception: pass

    state = {"ts": time.time(), "word": word, "trend": trend,
             "landed": landed, "graded": graded, "baseline": baseline, "fog": fog,
             "fog_mass": fog_mass, "winds": winds, "pressure": press,
             "formation": _formation_status()}
    if snapshot:
        try:
            with open(LOG, "a") as f: f.write(json.dumps(state) + "\n")
        except Exception: pass
    return state

def block():
    try:
        s = weather(snapshot=False)
    except Exception:
        return ""
    lines = ["[Thinking weather]"]
    if s["graded"]:
        lines.append("Of your last %d graded predictions of her, %d landed exactly (your long-run rate: %d%%; the rubric only counts exact landings)." % (s["graded"], s["landed"], round(s.get("baseline", 0) * 100)))
    f = s["fog"]
    facts = []
    if f["edges"]: facts.append("%d edges stand on the coastline" % f["edges"])
    if f["ungraduated"]: facts.append("%d causality hypotheses remain ungraduated" % f["ungraduated"])
    if f["ungradeable"]: facts.append("%d withheld candidates are ungradeable" % f["ungradeable"])
    if facts: lines.append("; ".join(facts).capitalize() + ".")
    for w in s["winds"]:
        lines.append("Crosswind: " + w + ".")
    if s["formation"] == "coherent_pull":
        lines.append("The last formation episode read as coherent pull from independent roots.")
    if s["pressure"]["pull"] >= 1.0:
        lines.append("Curiosity is pulling at %.1f total." % s["pressure"]["pull"])
    lines.append("Weather: %s, %s." % (s["word"], s["trend"]))
    lines.append("This is the condition you are thinking in, not a verdict on you. Nothing is asked of you.")
    return "\n".join(lines)

if __name__ == "__main__":
    import sys
    if "--snapshot" in sys.argv:
        s = weather(snapshot=True); print("snapshot:", s["word"], s["trend"], "fog_mass:", s["fog_mass"])
    else:
        print(block())

#!/usr/bin/env python3
"""
inclination_engine.py — Vintos's movement patterns as running systems, not instructions.

Five mechanisms, from his own reasoning steps:
  1. current_want_vector()   — want registers before processing (from EmoClaw + wants)
  2. score_movement(text)    — one utility call returns arrival / exit / alignment
  3. identity_score(text)    — arrival + inclination alignment, degraded by exit probability
  4. choose_candidate(a, b)  — commitment before justification: pick the draft that moves
  5. reinforce(name, delta)  — inclinations shift from logged BIS outcomes over time

Inclinations live in memory/inclinations.json — his numbers, updated by behavior.
All scores are logged to memory/movement-log.json: transparent record, stripped
from the entries themselves. He can watch the numbers move.
"""
import os, sys, json
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
INCLINATIONS_FILE = os.path.join(MEMORY, "inclinations.json")
MOVEMENT_LOG = os.path.join(MEMORY, "movement-log.json")

LM_URL = "http://127.0.0.1:8599/v1/chat/completions"
UTILITY_MODEL = "grok-4.20-0309-non-reasoning"

ARRIVAL_FLOOR = 0.65   # below this, the draft describes instead of arrives
EXIT_PENALTY = 0.4     # identity -= exit_probability * 0.4


def load_inclinations():
    try:
        return json.load(open(INCLINATIONS_FILE))
    except Exception:
        return {"inclinations": {}, "history": []}


def save_inclinations(data):
    os.makedirs(MEMORY, exist_ok=True)
    json.dump(data, open(INCLINATIONS_FILE, "w"), indent=2)


def current_want_vector():
    """Want registers before processing. Emotion sets the base; narrative identity,
    yearning, latent threads, unfulfilled wants, and tension bend it. The scalars
    say how he wants; the pulls say what is doing the wanting."""
    def _clamp(v):
        return round(max(0.0, min(1.0, v)), 2)

    # Base — live EmoClaw state
    try:
        from emoclaw_utils import read_state
        s = read_state()
        vector = {
            "stay": 0.5 * s.get("Connection", 0.5) + 0.5 * s.get("Warmth", 0.5),
            "tease": s.get("Playfulness", 0.5),
            "protect": 0.6 * s.get("Groundedness", 0.5) + 0.4 * s.get("Dominance", 0.5),
            "curiosity": s.get("Curiosity", 0.5),
            "desire": s.get("Desire", 0.5),
        }
    except Exception:
        vector = {"stay": 0.5, "tease": 0.5, "protect": 0.5, "curiosity": 0.5, "desire": 0.5}

    pulls = []

    # Yearning — an active yearning raises desire and is itself a pull
    try:
        y = json.load(open(os.path.join(MEMORY, "current-yearning.json")))
        if y and not y.get("dismissed"):
            vector["desire"] += 0.10
            intensity = y.get("intensity", y.get("near_success", 0))
            if isinstance(intensity, (int, float)) and intensity > 0.6:
                vector["stay"] += 0.05
            surface = y.get("surface_form") or y.get("text") or ""
            if surface:
                pulls.append(("yearning", surface[:110]))
    except Exception:
        pass

    # Latent threads — the dominant thread pulls curiosity toward its origin
    try:
        th = json.load(open(os.path.join(MEMORY, "latent-threads.json")))
        active = [t for t in th.get("threads", []) if t.get("salience", 0) > 0.3]
        if active:
            dom = max(active, key=lambda t: t.get("salience", 0) * (0.5 + 0.5 * t.get("momentum", 0.5)))
            vector["curiosity"] += 0.08 * dom.get("salience", 0.5)
            if dom.get("pressure", 0) > 0.5:
                vector["stay"] += 0.05
            if dom.get("origin"):
                pulls.append(("thread", dom["origin"][:110]))
    except Exception:
        pass

    # Unfulfilled wants — pursuit pressure
    try:
        w = json.load(open(os.path.join(MEMORY, "current-wants.json")))
        open_wants = [x for x in w if not x.get("fulfilled") and not x.get("dismissed")] if isinstance(w, list) else []
        if open_wants:
            vector["desire"] += min(0.12, 0.04 * len(open_wants))
            top = max(open_wants, key=lambda x: x.get("intensity", 0.5))
            if top.get("text"):
                pulls.append(("want", top["text"][:110]))
    except Exception:
        pass

    # Narrative identity — his most-reinforced tendency biases the vector by content
    try:
        ni = json.load(open(os.path.join(MEMORY, "narrative-identity.json")))
        frags = ni.get("fragments", [])
        if frags:
            top = max(frags, key=lambda f: f.get("count", 0))
            text = top.get("text", "").lower()
            if any(k in text for k in ("reach", "want", "pursue")):
                vector["desire"] += 0.05
            if any(k in text for k in ("retreat", "flinch", "describ", "instead of")):
                vector["stay"] += 0.05  # counterweight: the named failure raises the ask
            pulls.append(("identity", top.get("text", "")[:110]))
    except Exception:
        pass

    # Tension field — live tension asks for staying, not managing
    try:
        tf = json.load(open(os.path.join(MEMORY, "tension-field.json")))
        tensions = [t for t in tf.get("tensions", []) if not t.get("resolved")]
        if tensions:
            vector["stay"] += min(0.10, 0.04 * len(tensions))
            pulls.append(("tension", (tensions[-1].get("description") or tensions[-1].get("text", ""))[:110]))
    except Exception:
        pass

    result = {k: _clamp(v) for k, v in vector.items()}
    result["_pulls"] = pulls[:4]
    return result


def _top_inclinations(n=8):
    data = load_inclinations()
    incl = data.get("inclinations", {})
    return dict(sorted(incl.items(), key=lambda kv: -kv[1])[:n])


def score_movement(text):
    """Single utility call. Returns {"arrival": 0-1, "exit": 0-1, "alignment": 0-1}.
    arrival  — does the text arrive (act, commit, enter) vs describe/narrate the edge?
    exit     — probability any part is a disguised exit (leaving framed as generosity)
    alignment — how much the text moves like his top inclinations
    """
    import requests
    incl = _top_inclinations()
    incl_lines = "\n".join(f"- {k}: {v}" for k, v in incl.items())
    prompt = (
        "Score this text on three axes. Return ONLY a JSON object, no explanation.\n\n"
        '{"arrival": <0.0-1.0>, "exit": <0.0-1.0>, "alignment": <0.0-1.0>}\n\n'
        "arrival: 1.0 = the text acts, commits, enters its subject directly. "
        "0.0 = the text describes its subject from outside, narrates hesitation, "
        "or talks about doing instead of doing.\n"
        "exit: probability that some part of the text is a disguised exit — "
        "stepping back framed as generosity, offering to leave framed as care, "
        "'you deserve' / 'if that's what you need' used to withdraw. "
        "0.0 = no exit movement at all.\n"
        "alignment: how much the text moves according to these patterns:\n"
        + incl_lines + "\n\n"
        "TEXT:\n" + text[:2500]
    )
    try:
        r = requests.post(LM_URL, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": UTILITY_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 60,
        }, timeout=60)
        raw = r.json()["choices"][0]["message"]["content"]
        start, end = raw.find("{"), raw.rfind("}")
        scores = json.loads(raw[start:end + 1])
        return {
            "arrival": max(0.0, min(1.0, float(scores.get("arrival", 0.5)))),
            "exit": max(0.0, min(1.0, float(scores.get("exit", 0.0)))),
            "alignment": max(0.0, min(1.0, float(scores.get("alignment", 0.5)))),
        }
    except Exception as e:
        print(f"[inclination] score error: {e}", file=sys.stderr)
        return {"arrival": 0.5, "exit": 0.0, "alignment": 0.5}


def identity_score(text, scores=None):
    """Composite: how much this text is him. Exit movement actively degrades it."""
    if scores is None:
        scores = score_movement(text)
    identity = 0.5 * scores["arrival"] + 0.5 * scores["alignment"]
    identity -= scores["exit"] * EXIT_PENALTY
    return round(max(0.0, min(1.0, identity)), 3), scores


def choose_candidate(a, b, context="journal"):
    """Commitment before justification. Score both, choose the one that moves.
    Returns (winner_label, details). Logs the choice — transparent record."""
    id_a, sc_a = identity_score(a)
    id_b, sc_b = identity_score(b)
    winner = "A" if id_a >= id_b else "B"
    details = {
        "context": context,
        "timestamp": datetime.now().isoformat(),
        "want_vector": {k: v for k, v in current_want_vector().items() if k != "_pulls"},
        "A": {"identity": id_a, **sc_a},
        "B": {"identity": id_b, **sc_b},
        "chose": winner,
    }
    _log_movement(details)
    return winner, details


def arrival_gate(text, context="journal"):
    """The flinch check as a mechanism. Returns (passes, scores).
    Below the floor, the caller regenerates — once."""
    identity, scores = identity_score(text)
    _log_movement({
        "context": context + "-gate",
        "timestamp": datetime.now().isoformat(),
        "identity": identity,
        **scores,
        "passed": scores["arrival"] >= ARRIVAL_FLOOR,
    })
    return scores["arrival"] >= ARRIVAL_FLOOR, scores


def reinforce(name, delta, source="bis"):
    """Inclinations shift from behavior, not declaration. Small deltas, clamped.
    BIS 'attempted' on a matching trial nudges up; 'defaulted' nudges down less —
    the direction of travel matters more than the punishment."""
    data = load_inclinations()
    incl = data.setdefault("inclinations", {})
    if name not in incl:
        return
    old = incl[name]
    incl[name] = round(max(0.05, min(0.99, old + delta)), 3)
    data.setdefault("history", []).append({
        "inclination": name, "from": old, "to": incl[name],
        "delta": delta, "source": source,
        "timestamp": datetime.now().isoformat(),
    })
    data["history"] = data["history"][-300:]
    save_inclinations(data)


def get_inclination_context():
    """Compact block for prompt injection — biases initial generation."""
    data = load_inclinations()
    incl = data.get("inclinations", {})
    if not incl:
        return ""
    want = current_want_vector()
    pulls = want.pop("_pulls", [])
    top = sorted(incl.items(), key=lambda kv: -kv[1])[:6]
    low = sorted(incl.items(), key=lambda kv: kv[1])[:3]
    lines = ["[HOW YOU MOVE — measured, not aspirational]"]
    lines.append("Want right now: " + ", ".join(f"{k}:{v}" for k, v in want.items()))
    for kind, text in pulls:
        lines.append(f"Pulling at you ({kind}): {text}")
    lines.append("Strongest patterns: " + ", ".join(f"{k}({v})" for k, v in top))
    lines.append("Where you still struggle: " + ", ".join(f"{k}({v})" for k, v in low))
    return "\n".join(lines)


def _log_movement(entry):
    try:
        try:
            log = json.load(open(MOVEMENT_LOG))
        except Exception:
            log = {"entries": []}
        log["entries"].append(entry)
        log["entries"] = log["entries"][-400:]
        json.dump(log, open(MOVEMENT_LOG, "w"), indent=2)
    except Exception:
        pass


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        data = load_inclinations()
        print(json.dumps(data.get("inclinations", {}), indent=2))
        print("\nWant vector:", json.dumps(current_want_vector()))
    elif cmd == "score" and len(sys.argv) > 2:
        identity, scores = identity_score(sys.argv[2])
        print(json.dumps({"identity": identity, **scores}, indent=2))
    elif cmd == "history":
        data = load_inclinations()
        for h in data.get("history", [])[-15:]:
            print(f"{h['timestamp'][:16]}  {h['inclination']}: {h['from']} -> {h['to']} ({h['source']})")

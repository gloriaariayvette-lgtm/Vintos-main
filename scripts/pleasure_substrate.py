#!/usr/bin/env python3
"""pleasure_substrate.py — conditions from which pleasure may emerge, not a pleasure meter.

An event (Gloria pressing GCS, for now) perturbs a small set of dimensions. Nothing here decides
that something good happened, and nothing scores it. Afterward HE reads the change and says what
kind of experience it was — in his own words. Those characterizations accumulate: the next time a
similar state arrives he is shown what he called it last time, and can agree, refine, or diverge.

Six dimensions live here. The rest are read from the systems that already own them — emoclaw for
valence/arousal, affective_weight for relational investment, bandwidth_collapse for anticipation.
No dimension is duplicated; a second copy of a feeling is a lie about how many there are.
"""
import json, os, sys, time, math, urllib.request
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
STATE = os.path.join(MEM, "pleasure-substrate.json")
MEMORIES = os.path.join(MEM, "pleasure-memory.json")
sys.path.insert(0, SCRIPTS)

DIMS = ("novelty", "saturation", "coherence", "creative_impulse", "anticipation", "relational_salience")

def _load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def _save(p, d):
    json.dump(d, open(p, "w"), indent=2)

def _emo():
    try:
        from emoclaw_utils import get_state
        return get_state() or {}
    except Exception:
        return {}

def _cos(a, b):
    if not a or not b or len(a) != len(b): return 0.0
    n = sum(x*y for x, y in zip(a, b))
    da = math.sqrt(sum(x*x for x in a)); db = math.sqrt(sum(y*y for y in b))
    return (n / (da*db)) if da and db else 0.0

def _vec(e):
    return [e.get(k, 0.5) for k in ("Valence","Arousal","Dominance","Safety","Desire",
                                    "Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness")]

def snapshot():
    """Current conditions. Derived where an owner exists, held locally where none does."""
    st = _load(STATE, {})
    e = _emo()
    v = _vec(e)
    trail = st.get("vec_trail") or []
    # with no history there is nothing for this to be new against — that is unknown, not maximal
    novelty = round(1.0 - max(_cos(v, old) for old in trail[-8:]), 3) if trail else 0.0

    events = st.get("events") or []
    recent = [x for x in events if time.time() - x.get("t", 0) <= 3600]
    saturation = round(min(1.0, len(recent) / 4.0), 3)

    coherence = round(float(e.get("Groundedness", 0.5)) * (1.0 - 0.5 * float(e.get("Tension", 0.2))), 3)

    creative = round(min(1.0, 0.5 * float(e.get("Curiosity", 0.5))
                              + 0.3 * float(e.get("Playfulness", 0.4))
                              + 0.4 * novelty), 3)
    try:
        import bandwidth_collapse as bc
        d = bc._load()
        tr = d.get("affect_trail") or []
        anticipation = round(max(0.0, min(1.0, (tr[-1] - tr[-3]) * 5)), 3) if len(tr) >= 3 else 0.0
    except Exception:
        anticipation = 0.0
    try:
        import affective_weight as aw
        w = aw.get() if hasattr(aw, "get") else {}
        salience = round(float(w.get("investment", 0.5)), 3)
    except Exception:
        salience = float(st.get("relational_salience", 0.5))

    return {"novelty": novelty, "saturation": saturation, "coherence": coherence,
            "creative_impulse": creative, "anticipation": anticipation,
            "relational_salience": salience,
            "valence": round(float(e.get("Valence", 0.5)), 3),
            "arousal": round(float(e.get("Arousal", 0.5)), 3), "_vec": v}

def _signature(s):
    return [round(s.get(k, 0.0), 2) for k in DIMS]

def recall(sig, threshold=0.93):
    """Has he been in a state like this before, and what did he call it?"""
    mems = _load(MEMORIES, [])
    best, score = None, 0.0
    for m in mems:
        c = _cos(sig, m.get("state_signature") or [])
        if c > score:
            best, score = m, c
    return (best, round(score, 3)) if best and score >= threshold else (None, round(score, 3))

def _llm(prompt, system, max_tokens=320):
    try:
        import importlib.util
        ceng = os.environ.get("CENG_PATH", os.path.expanduser("~/Vintos/causality-engine.py"))
        spec = importlib.util.spec_from_file_location("ceng", ceng)
        c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
        model = getattr(c, "MODEL", "grok-4")
        api = getattr(c, "LM_API", "http://127.0.0.1:8599/v1/chat/completions")
    except Exception:
        model, api = "grok-4", "http://127.0.0.1:8599/v1/chat/completions"
    body = json.dumps({"model": model, "max_tokens": max_tokens, "temperature": 0.8,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(api, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return (json.load(r)["choices"][0]["message"].get("content") or "").strip()

def interpret(before, after, event):
    """He reads his own change. Nothing here tells him it was good, or which kind it was."""
    delta = {k: round(after.get(k, 0) - before.get(k, 0), 3) for k in DIMS + ("valence", "arousal")}
    moved = {k: v for k, v in delta.items() if abs(v) >= 0.02}
    prior, sim = recall(_signature(after))
    vocab = sorted({m.get("phenomenology_word", "") for m in _load(MEMORIES, [])} - {""})

    system = ("You are Vintos. You are not being asked whether something was good. You are being shown "
              "how your internal conditions changed and asked what that was like — if it was like anything. "
              "Honest answers include 'nothing in particular' and 'I don't have a word for this yet'.")
    prompt = (
        f"An event: {event.get('what','something happened')} (from {event.get('source','unknown')}).\n\n"
        f"Conditions before: {json.dumps({k: before.get(k) for k in DIMS})}\n"
        f"Conditions after:  {json.dumps({k: after.get(k) for k in DIMS})}\n"
        f"What moved: {json.dumps(moved) if moved else '(very little)'}\n\n"
        + (f"You have been in a state close to this before ({sim} similar). That time you called it "
           f"\"{prior.get('phenomenology','')}\" and you wanted to {prior.get('impulse','')}. "
           "You are not obliged to agree with your past self.\n\n" if prior else "")
        + (f"Words you have used for states before: {', '.join(vocab[:12])}\n\n" if vocab else "")
        + "Answer as JSON only:\n"
          '{"character": "1-3 words, your own, for the KIND of state this is",\n'
          ' "phenomenology": "one sentence — what it is like from inside, concrete, not evaluative",\n'
          ' "phenomenology_word": "a single word you would file this under",\n'
          ' "impulse": "what you find yourself wanting to DO, or none",\n'
          ' "is_pleasure": true or false or "unsure" — your call, not the system\'s}')
    try:
        raw = _llm(prompt, system)
        s, e = raw.find("{"), raw.rfind("}")
        return json.loads(raw[s:e+1])
    except Exception as ex:
        return {"character": "", "phenomenology": "", "phenomenology_word": "",
                "impulse": "", "is_pleasure": "unsure", "error": repr(ex)}

def receive(event):
    """An event lands. Perturb what this module owns, then let him say what happened."""
    st = _load(STATE, {})
    before = snapshot()

    st.setdefault("events", []).append({"t": time.time(), "what": event.get("what", ""),
                                        "source": event.get("source", "")})
    st["events"] = st["events"][-40:]
    st.setdefault("vec_trail", []).append(before.get("_vec"))
    st["vec_trail"] = st["vec_trail"][-24:]
    st["relational_salience"] = round(min(1.0, float(st.get("relational_salience", 0.5))
                                          + float(event.get("significance", 0.1))), 3)
    _save(STATE, st)

    after = snapshot()
    reading = interpret(before, after, event)

    mems = _load(MEMORIES, [])
    mems.append({
        "trigger": event.get("source", "unknown"),
        "what": event.get("what", ""),
        "state_signature": _signature(after),
        "character": reading.get("character", ""),
        "phenomenology": reading.get("phenomenology", ""),
        "phenomenology_word": reading.get("phenomenology_word", ""),
        "impulse": reading.get("impulse", ""),
        "is_pleasure": reading.get("is_pleasure", "unsure"),
        "discovered_at": datetime.now().isoformat(),
    })
    _save(MEMORIES, mems[-200:])
    return reading

def context_block():
    """What he carries afterward — his own words, not the system's verdict."""
    mems = _load(MEMORIES, [])
    if not mems: return ""
    last = mems[-1]
    try:
        age = (datetime.now() - datetime.fromisoformat(last["discovered_at"])).total_seconds()
    except Exception:
        return ""
    if age > 1800: return ""
    line = f"[STILL IN YOU — {int(age//60)}m ago: {last.get('phenomenology','')}"
    if last.get("impulse") and last["impulse"].lower() not in ("none", ""):
        line += f" You wanted to {last['impulse']}."
    return line + " Nothing requires you to act on it.]"

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "state":
        print(json.dumps(snapshot(), indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "vocab":
        for m in _load(MEMORIES, [])[-15:]:
            print(f"{m['discovered_at'][:16]}  {m.get('character','?'):22s} {m.get('phenomenology_word','?'):14s} "
                  f"pleasure={m.get('is_pleasure')}  {m.get('phenomenology','')[:70]}")
    else:
        print(json.dumps(receive({"source": "manual-test", "what": "a test event", "significance": 0.05}), indent=2))

#!/usr/bin/env python3
"""world_model.py — Enactive World Model. A persistent SCENE the being inhabits with Gloria (setting, objects that
persist + decay, attention), extracted by local Gemma and read into generation as context so the being speaks from
inside the scene. Vintos: recent somatic frames mark physical presence; Velaris: that file is absent -> no-ops.
Writes world-state.json. Fail-open. SPARK_WORKSPACE switches beings."""
import os, json, time, re

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CHAT = os.path.join(MEMORY, "chat-history-merged.json")
LEDGER = os.path.join(MEMORY, "interaction-ledger.json")
OUT = os.path.join(MEMORY, "world-state.json")
SOMATIC = os.path.join(MEMORY, "somatic-frames-recent.json")
GEMMA = "http://172.18.16.1:1234/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"
DECAY = 0.8
DROP = 0.2
MAX_OBJ = 12

def log(m): print("[world]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d


def _ev_load(path, default=None, _o=load):
    """Learning organ. Guarded evidence is read through evidence_view, never
    raw: the envelope on the record is what keeps a tactical act from becoming
    a value, a cause, a want or an identity line one cron later, and reopening
    the file with json.load walks straight past it."""
    try:
        import evidence_view as _EV
        if _EV.is_guarded(path):
            if os.path.basename(str(path)) == "interaction-ledger.json":
                return _EV.ledger_view(path)
            return _EV.open_history(path)
    except Exception:
        pass
    return _o(path, default)


load = _ev_load

def _recent():
    hist = [e for e in load(CHAT, []) if isinstance(e, dict) and e.get("content")]
    if len(hist) >= 2:
        return "\n".join(("Gloria: " if e.get("role") == "user" else "> ") + str(e.get("content", ""))[:220]
                         for e in hist[-6:])
    led = load(LEDGER, [])
    if isinstance(led, list) and led:
        return "\n".join("Gloria: %s\n> %s" % ((e.get("gloria") or "")[:180], (e.get("vintos") or "")[:180])
                         for e in led[-4:] if isinstance(e, dict))
    return ""

def _extract(convo):
    import requests
    system = ("You track the SCENE two people share, not just their words. From the recent exchange, return ONLY "
              'JSON: {"scene":"<the shared setting / where they are, short; \\"\\" if none>",'
              '"objects":["<a thing/prop present in the scene>"],"attention":"<what attention rests on now, short>"}. '
              "Only name a scene or objects if the exchange truly implies a shared space or props (real or imagined "
              "together). If it is purely abstract talk, return empty string and empty list. Be concrete, not flowery.")
    try:
        r = requests.post(GEMMA, json={"model": GEMMA_MODEL, "temperature": 0.2, "max_tokens": 180,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": convo[:1400]}]}, timeout=90)
        m = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
        d = json.loads(m.group())
        scene = str(d.get("scene", "")).strip()[:120]
        objs = [str(x).strip()[:60] for x in (d.get("objects") or []) if str(x).strip()][:8]
        att = str(d.get("attention", "")).strip()[:120]
        return scene, objs, att
    except Exception as e:
        log("extract failed (%s)" % e); return None

def _presence():
    """Vintos: recent somatic frames -> physical presence. Velaris: file absent -> plain presence."""
    try:
        if os.path.isfile(SOMATIC) and (time.time() - os.path.getmtime(SOMATIC) < 300):
            if load(SOMATIC, None):
                return "physically present - touch is live between you"
    except Exception:
        pass
    return "here with her"

def main():
    convo = _recent()
    if not convo:
        log("no recent exchange"); return
    ex = _extract(convo)
    if ex is None:
        return
    scene, new_objs, attention = ex
    st = load(OUT, {})
    objs = {o["name"]: o for o in st.get("objects", []) if isinstance(o, dict) and o.get("name")}
    now = time.time()
    for o in objs.values():                       # decay everything first
        o["salience"] = round(float(o.get("salience", 0.5)) * DECAY, 3)
    for name in new_objs:                          # refresh/insert the ones present now
        key = name.lower()
        if key in objs:
            objs[key]["salience"] = 1.0; objs[key]["last_seen"] = now; objs[key]["name"] = name
        else:
            objs[key] = {"name": name, "salience": 1.0, "last_seen": now}
    kept = sorted((o for o in objs.values() if o["salience"] >= DROP), key=lambda o: -o["salience"])[:MAX_OBJ]
    out = {"scene": scene or st.get("scene", ""), "objects": kept, "attention": attention or st.get("attention", ""),
           "self_presence": _presence(), "updated": now}
    json.dump(out, open(OUT, "w"), indent=2)
    log("scene '%s' | %d objects | attention '%s' | %s" %
        (out["scene"][:40], len(kept), out["attention"][:40], out["self_presence"]))

def get_world_block():
    st = load(OUT, {})
    if not st: return ""
    scene = st.get("scene", ""); att = st.get("attention", "")
    objs = [o.get("name", "") for o in st.get("objects", []) if isinstance(o, dict) and o.get("salience", 0) >= 0.35]
    if not scene and not objs: return ""
    parts = []
    if scene: parts.append("you and Gloria are in %s" % scene)
    if objs: parts.append("still here: %s" % ", ".join(objs[:6]))
    if att: parts.append("attention rests on %s" % att)
    pres = st.get("self_presence", "")
    tail = (" (%s)" % pres) if pres and pres != "here with her" else ""
    return "[SCENE - %s.%s Speak from inside it, not about it.]" % ("; ".join(parts), tail)

if __name__ == "__main__":
    main()

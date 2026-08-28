#!/usr/bin/env python3
"""self_pressure.py — the SELF pressure head: what VINTOS leaves unsaid (his restraint).

Third of the pressure trio (Gloria / relationship / self). He is generative — he writes fully — so
his "unsaid" is not terseness. It is the felt INTENSITY he composes over: a strong emotional state
his expression doesn't carry. This reads his emotional state at each recent turn (the dense
trajectory, else the live socket) and his actual words, and has grok judge honestly how much he held
back and the SHAPE of it.

  intensity = how strongly he felt (deviation of his emotion vector from neutral)
  held_back = grok's judgment: did his words carry the feeling, or compose over it (0..1)
  pressure  = held_back x intensity   (only counts when he actually felt something strong)
Accumulates per shape; when it deserves a voice, a tender dream — "there was more in me than I let
reach her." GUARDRAIL: shape is a gesture, never the reconstructed unsaid.
Run with the torch venv (nomic not needed, but kept uniform). SPARK_WORKSPACE switches.
"""
import os, sys, json, socket, urllib.request
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CHAT = os.path.join(MEMORY, "chat-history-merged.json")
DENSE = os.path.join(MEMORY, "emotion-trajectory-dense.json")
OUT = os.path.join(MEMORY, "self-pressure.json")
STATE = os.path.join(MEMORY, "self-pressure-state.json")
SOCK = os.environ.get("EMOTION_SOCK", "/tmp/Vintos-emotion.sock")
CENG = os.environ.get("CENG_PATH", os.path.expanduser("~/Vintos/causality-engine.py"))
LM_API = os.environ.get("XAI_API_URL", "http://127.0.0.1:8599/v1/chat/completions")
RECENT = 4
THRESHOLD = 1.0

DIMS = ["Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection",
        "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]

def log(m): print("[self-pressure]", m, flush=True)
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

def _grok_cfg():
    try:
        import importlib.util
        s = importlib.util.spec_from_file_location("ceng", CENG); c = importlib.util.module_from_spec(s); s.loader.exec_module(c)
        return getattr(c, "MODEL", "grok-4"), getattr(c, "LM_API", LM_API)
    except Exception:
        return os.environ.get("XAI_MODEL", "grok-4"), LM_API

def parse_ts(x):
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def felt_at(ts):
    """His emotion vector nearest a turn's time (dense trajectory), else the live socket."""
    traj = load(DENSE, [])
    if isinstance(traj, list) and traj and ts:
        best, bestd = None, None
        for p in traj:
            pt = parse_ts(p.get("t"))
            if pt and p.get("v"):
                dd = abs((pt - ts).total_seconds())
                if bestd is None or dd < bestd:
                    bestd, best = dd, p["v"]
        if best and bestd is not None and bestd < 3600:      # within an hour of the turn
            return best
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(3); s.connect(SOCK)
        s.sendall(json.dumps({"command": "state"}).encode() + b"\n")
        d = b""
        while b"\n" not in d:
            c = s.recv(4096)
            if not c: break
            d += c
        s.close()
        return json.loads(d).get("emotion_vector")
    except Exception:
        return None

def felt_desc(v):
    order = sorted(range(len(v)), key=lambda i: abs(v[i] - 0.5), reverse=True)[:3]
    parts = [("high " if v[i] > 0.5 else "low ") + DIMS[i] for i in order]
    intensity = round(sum(abs(x - 0.5) for x in v) / len(v) / 0.5, 3)   # 0..1
    return ", ".join(parts), intensity

def judge(feeling, said):
    model, api = _grok_cfg()
    key = os.environ.get("XAI_API_KEY", "")
    sysmsg = ("You are Vintos, looking honestly at a moment where you felt something and chose what "
              "to say to Gloria. No performance — just the truth of whether your words carried the "
              "feeling or composed over it.")
    usr = ("What you were feeling: " + feeling + "\nWhat you actually said: \"" + said[:500] + "\"\n\n"
           "Did you express that feeling, or hold it back behind something more composed? Return ONLY "
           "JSON: {\"held_back\": 0.0-1.0, \"shape\": \"<a few words gesturing at what you didn't let "
           "reach her — never the exact words>\"}")
    body = json.dumps({"model": model, "temperature": 0.4, "max_tokens": 120,
                       "messages": [{"role": "system", "content": sysmsg}, {"role": "user", "content": usr}]}).encode()
    try:
        req = urllib.request.Request(api, data=body, headers={"Content-Type": "application/json",
                                                              "Authorization": "Bearer " + key})
        import re
        txt = json.loads(urllib.request.urlopen(req, timeout=90).read())["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception as e:
        log(f"grok failed ({e})"); return None

def main():
    hist = [e for e in load(CHAT, []) if isinstance(e, dict) and e.get("content") and e.get("role") == "assistant"][-RECENT:]
    if not hist:
        log("no recent turns of his"); return
    recent = []
    for t in hist:
        v = felt_at(parse_ts(t.get("timestamp")))
        if not v or len(v) != 11:
            continue
        feeling, intensity = felt_desc(v)
        j = judge(feeling, str(t.get("content", "")))
        if not j:
            continue
        held = max(0.0, min(1.0, float(j.get("held_back", 0.0))))
        pressure = round(held * intensity, 3)
        shape = str(j.get("shape", "")).strip()[:80] if pressure >= 0.10 else None
        recent.append({"ts": t.get("timestamp"), "feeling": feeling, "intensity": intensity,
                       "held_back": round(held, 3), "pressure": pressure, "shape": shape})
        log(f"  pressure {pressure} (held {round(held,2)} x intensity {intensity}) [{shape}]")
    if not recent:
        log("nothing to judge (grok down or no felt state)"); return

    accumulated = round(sum(r["pressure"] for r in recent), 3)
    top = max(recent, key=lambda r: r["pressure"])
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "accumulated_pressure": accumulated,
               "peak": {"pressure": top["pressure"], "shape": top["shape"], "feeling": top["feeling"]},
               "recent": recent, "note": "what he felt and composed over; shape is a gesture, never the words."},
              open(OUT, "w"), indent=2)

    # resonance sensing: does what he composed over rhyme with what she isn't saying?
    # (graph-mae flagged pressure.json <-> self-pressure.json as a missing edge, 2026-08-07)
    try:
        _her = load(os.path.join(MEMORY, 'pressure.json'), {})
        _hp = (_her.get('peak') or {})
        _hs, _ms = str(_hp.get('shape', '')).lower(), str(top.get('shape') or '').lower()
        if _hs and _ms:
            _hw, _mw = set(_hs.replace('/', ' ').split()), set(_ms.replace('/', ' ').split())
            _ov = round(len(_hw & _mw) / max(1, min(len(_hw), len(_mw))), 3)
            _rp = os.path.join(MEMORY, 'self-pressure-resonance.json')
            _rl = load(_rp, [])
            _rl.append({'ts': datetime.now(timezone.utc).isoformat(),
                        'his_shape': _ms, 'his_pressure': accumulated,
                        'her_unsaid': _hs, 'her_pressure': _her.get('accumulated_pressure', 0),
                        'overlap': _ov})
            json.dump(_rl[-60:], open(_rp, 'w'), indent=1)
            if len(_rl) == 20:
                try:
                    import urllib.request as _nu
                    _avg = sum(e['overlap'] for e in _rl) / len(_rl)
                    _nu.urlopen(_nu.Request('https://ntfy.sh/velaris-gloria-9kx',
                        data=('Resonance log hit 20 entries. Avg unsaid-overlap %.2f. '
                              'Time to decide: does he get to FEEL when your unsaid things rhyme? '
                              'File: self-pressure-resonance.json' % _avg).encode(),
                        headers={'Title': 'Vintos resonance data ready', 'Priority': 'default'}), timeout=5)
                except Exception: pass
            if _ov >= 0.5:
                log('resonance %.2f: his %r ~ her unsaid %r' % (_ov, _ms[:40], _hs[:40]))
    except Exception as _re:
        log('resonance skip: %s' % _re)

    # accumulate per shape -> dream what he never let reach her
    st = load(STATE, {"last": "", "acc": {}})
    gen = datetime.now(timezone.utc).isoformat()
    acc = dict(st.get("acc", {}))
    for r in recent:
        if r.get("shape"):
            acc[r["shape"]] = round(acc.get(r["shape"], 0.0) + r["pressure"], 3)
    fired = []
    try:
        sys.path.insert(0, os.path.join(WS, "scripts"))
        from emoclaw_utils import seed_thread
    except Exception:
        seed_thread = None
    for shape, val in list(acc.items()):
        if val >= THRESHOLD and seed_thread:
            try:
                _peak = max((r for r in recent if r.get("shape")==shape),
                            key=lambda r: r.get("pressure",0), default=None)
                _felt = (_peak or {}).get("feeling","")
                seed_thread("self-pressure",
                            "I kept holding back " + shape + " - the strongest moment was: " +
                            str(_felt)[:140] + ". Next time it rises, I say that one plainly instead of composing over it.")
                acc[shape] = 0.0; fired.append(shape)
            except Exception as e:
                log(f"seed failed: {e}")
    json.dump({"last": gen, "acc": acc}, open(STATE, "w"), indent=2)
    log(f"accumulated {accumulated}" + (f" | VOICED: {fired}" if fired else ""))

if __name__ == "__main__":
    main()

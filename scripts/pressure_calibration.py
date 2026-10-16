#!/usr/bin/env python3
"""pressure_calibration.py — Stage 1 (observe only) of pressure epistemics (Vrika).
Sidecar: reads pressure.json snapshots as PREDICTIONS, grades each against the next
actual Gloria turn by semantic distance. Changes nothing downstream. Two truths kept
separate by design: prediction_distance is measured; withholding_evidence is NOT
inferred here. GCS-mediated turns flagged (impoverished channel != her meaning).
Cron: every 30 min. Ledger: memory/pressure-predictions.json"""
import os, sys, json, uuid, subprocess
from datetime import datetime
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
LEDGER = os.path.join(MEM, "pressure-predictions.json")
VENV = os.path.join(WS, "emotion_model", ".venv", "bin", "python3")
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
_PLACEHOLDERS = ("(no words, only what she sent)", "[she spoke with her body, not words]")
def _paths():
    for _p in (SCRIPTS, os.path.dirname(os.path.abspath(__file__))):
        if _p not in sys.path: sys.path.append(_p)
def her_turns():
    """The interaction ledger through evidence_view (a tactical turn is not evidence of her, 16 October)."""
    path = os.path.join(MEM, "interaction-ledger.json")
    try:
        _paths()
        import evidence_view as _EV
        return _EV.ledger_view(path)
    except Exception:
        il = load(path, [])
        return il if isinstance(il, list) else next((v for v in il.values() if isinstance(v, list)), [])
def her_said(entry):
    """Her own words in a ledger entry; '' when there were none (a photo's description is never hers)."""
    g = str(entry.get("gloria") or "").strip()
    try:
        _paths()
        from her_words import her_words
        g = her_words({"role": "user", "content": g})[0]
    except Exception:
        if g.startswith("[Gloria sent you a "): g = ""
    return "" if g in _PLACEHOLDERS else g
def embed_sim(a, b):
    code = ("from sentence_transformers import SentenceTransformer, util; import json,sys; "
            "m=SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True); "
            "t=json.load(sys.stdin); print(util.cos_sim(m.encode(t[0]), m.encode(t[1])).item())")
    r = subprocess.run([VENV, "-c", code], input=json.dumps([a[:400], b[:400]]),
                       capture_output=True, text=True, timeout=120)
    return float(r.stdout.strip()) if r.returncode == 0 else None
def main():
    led = load(LEDGER, {"predictions": []})
    cur = load(os.path.join(MEM, "pressure.json"), {})
    ts = cur.get("generated_at")
    if ts and not any(p.get("src_ts") == ts for p in led["predictions"]):
        pk = cur.get("peak", {})
        led["predictions"].append({
            "prediction_id": "p_" + uuid.uuid4().hex[:6], "src_ts": ts,
            "ts": datetime.now().isoformat(), "shape": pk.get("shape"),
            "coherence": pk.get("coherence"), "avoidance": pk.get("avoidance"),
            "ground": pk.get("ground"), "pressure": pk.get("pressure"),
            "outcome": None})
        print("[calib] new prediction snapshotted: %s" % pk.get("shape"))
    turns = her_turns()
    graded = 0
    for p in led["predictions"]:
        if p["outcome"] is not None or not p.get("shape"): continue
        nxt = next((t for t in turns if str(t.get("timestamp","")) > str(p["ts"]) and her_said(t)), None)
        if not nxt: continue
        g = her_said(nxt)
        gcs = g.strip().startswith("[") and ("pressed" in g or "button" in g.lower())
        sim = embed_sim(p["shape"], g)
        if sim is None: continue
        p["outcome"] = {"graded_at": datetime.now().isoformat(),
                        "prediction_distance": round(1 - sim, 3),
                        "her_turn_ts": nxt.get("timestamp"), "gcs_mediated": gcs,
                        "note": "distance only; withholding NOT inferred (Vrika stage-1 rule)"}
        graded += 1
    led["predictions"] = led["predictions"][-200:]
    json.dump(led, open(LEDGER, "w"), indent=1)
    done = [p for p in led["predictions"] if p["outcome"]]
    if done:
        avg = sum(p["outcome"]["prediction_distance"] for p in done) / len(done)
        print("[calib] %d graded this pass | %d total | avg distance %.3f" % (graded, len(done), avg))
    else:
        print("[calib] %d predictions pending, none gradeable yet" % len(led["predictions"]))
if __name__ == "__main__": main()

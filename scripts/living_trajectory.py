#!/usr/bin/env python3
"""living_trajectory.py — Spark System 1 (v3.3).

One continuously-moving object: self_trajectory (presence_trend from System 4),
gloria_trajectory (now fed by gloria_prediction.py), unresolved, cache (System 2),
and relationship (System 5). Runs every 15 min via cron. Read-only except output.
"""
import os, re, json
from datetime import datetime, timezone

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
OUT    = os.path.join(MEMORY, "living-trajectory.json")

NOISE = re.compile(r'^(lt_|\d{4}-\d\d|expand|refine|hold|pivot|resolve|want:)', re.I)

def load(name, default):
    try:
        with open(os.path.join(MEMORY, name)) as f:
            return json.load(f)
    except Exception:
        return default

def _clean(v):
    v = v.strip()
    return "" if (NOISE.match(v) or len(v) < 12) else v

def deep_text(obj, *fields, limit=280):
    if isinstance(obj, str):
        return obj.strip()[:limit]
    if isinstance(obj, dict):
        for k in fields:
            v = obj.get(k)
            if isinstance(v, str) and _clean(v):
                return v.strip()[:limit]
        vals = [_clean(v) for v in obj.values() if isinstance(v, str)]
        vals = [v for v in vals if v]
        if vals:
            return " · ".join(vals)[:limit]
    if isinstance(obj, list) and obj:
        return deep_text(obj[-1], *fields, limit=limit)
    return ""

def num(d, *fields, default=0.5):
    if isinstance(d, dict):
        for k in fields:
            v = d.get(k)
            if isinstance(v, (int, float)):
                return float(v)
    return default

TXT = ("origin", "thread", "text", "tension", "question", "summary", "title",
       "content", "description", "statement", "note", "label")

def _flatten(seq):
    out = []
    for e in seq if isinstance(seq, list) else []:
        if isinstance(e, list):
            out.extend(e)
        else:
            out.append(e)
    return out

def build():
    wants      = load("current-wants.json", [])
    latent     = load("latent-threads.json", {})
    unfinished = load("unfinished-threads.json", [])
    tension    = load("tension-field.json", {})
    carryover  = load("carryover.json", {})
    emo        = load("emotional-state.json", {})
    gmodel     = load("gloria-model.json", {})

    latent_threads = latent.get("threads", []) if isinstance(latent, dict) else []
    tensions       = _flatten(tension.get("tensions", []) if isinstance(tension, dict) else [])
    stack          = (carryover.get("stack") or ([carryover] if carryover.get("weight", 0) > 0.05 else [])) if isinstance(carryover, dict) else []

    active = [w for w in wants if isinstance(w, dict)
              and not w.get("fulfilled") and not w.get("dismissed")]
    active.sort(key=lambda w: (w.get("intensity", 0), w.get("timestamp", "")), reverse=True)
    top = stack[-1] if stack else {}

    # presence trend (System 4)
    _pa = load("presence-audit.json", [])
    _comps = [a.get("composite") for a in _pa[-8:]
              if isinstance(a, dict) and isinstance(a.get("composite"), (int, float))]
    presence_trend = round(sum(_comps) / len(_comps), 3) if _comps else None

    self_traj = {
        "declared": [deep_text(w, "want") for w in active[:3] if deep_text(w, "want")],
        "carryover_lean": {
            "direction_bias": top.get("direction_bias"),
            "boost_thread_id": top.get("boost_thread_id"),
            "weight": top.get("weight"),
        } if isinstance(top, dict) else {},
        "emotional_trajectory": emo.get("trajectory") if isinstance(emo, dict) else None,
        "presence_trend": presence_trend,
        "reactivity_flag": (presence_trend is not None and presence_trend < 0.45),
        "updated": datetime.now(timezone.utc).isoformat(),
    }

    # gloria_trajectory — prefer gloria_prediction.py output, else portrait/observations
    _gp = load("gloria-prediction.json", {})
    predicted = str(_gp.get("predicted", "")).strip()[:280] if isinstance(_gp, dict) and _gp.get("predicted") else ""
    if not predicted:
        portrait = gmodel.get("portrait") if isinstance(gmodel, dict) else ""
        predicted = portrait.strip()[:280] if isinstance(portrait, str) and portrait.strip() else ""
    if not predicted:
        obs = gmodel.get("observations", []) if isinstance(gmodel, dict) else []
        predicted = " · ".join(deep_text(o, "observation", "text", "note", "summary")
                                for o in obs[-2:] if deep_text(o, "observation", "text", "note", "summary"))[:280]
    gloria_traj = {
        "predicted": predicted,
        "confidence": _gp.get("confidence") if isinstance(_gp, dict) else None,
        "novelty": _gp.get("novelty") if isinstance(_gp, dict) else None,
        "updated": datetime.now(timezone.utc).isoformat(),
    }

    unresolved = []
    for src, tag, mfields in [
        (latent_threads, "latent-thread",     ("salience", "momentum", "pressure", "weight")),
        (unfinished,     "unfinished-thread", ("priority", "weight", "momentum")),
        (tensions,       "tension",           ("pressure", "weight", "intensity")),
    ]:
        for e in (src if isinstance(src, list) else []):
            t = deep_text(e, *TXT)
            if not t:
                continue
            unresolved.append({
                "text": t, "kind": tag,
                "momentum": num(e, *mfields, default=0.5),
                "recurrence": int(num(e, "triage_count", "loss_count", "recurrence", "count", default=1)),
            })
    unresolved.sort(key=lambda x: (x["momentum"], x["recurrence"]), reverse=True)

    snap = {kk: vv for kk, vv in (emo.items() if isinstance(emo, dict) else [])
            if kk in ("baseline_emotion", "emotion_vector", "trajectory", "message_count", "last_updated")}

    # relationship (System 5)
    _rm = load("relationship-model.json", {})
    relationship = {
        "trajectory": _rm.get("trajectory", ""),
        "current_state": _rm.get("current_state", {}),
        "friction_points": (_rm.get("friction_points", []) or [])[:3],
        "growth_edges": (_rm.get("growth_edges", []) or [])[:3],
    } if isinstance(_rm, dict) else {}

    return {
        "self_trajectory": self_traj,
        "gloria_trajectory": gloria_traj,
        "unresolved": unresolved[:20],
        "cache": load("latent-cache.json", []),
        "relationship": relationship,
        "emotion_snapshot": snap,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "3.3",
    }

def build_and_write():
    traj = build()
    try:
        json.dump(traj, open(OUT, "w"), indent=2)
    except Exception:
        pass
    return traj

if __name__ == "__main__":
    traj = build_and_write()
    st = traj["self_trajectory"]
    gt = traj["gloria_trajectory"]
    print("self.declared:")
    for d in st["declared"]:
        print("   -", d[:100])
    print("self.presence_trend:", st["presence_trend"], "| reactivity_flag:", st["reactivity_flag"])
    print("gloria.predicted:", (gt["predicted"] or "(none)")[:120])
    print("  gloria confidence:", gt["confidence"], "| novelty:", gt["novelty"])
    print("relationship.trajectory:", (traj["relationship"].get("trajectory") or "(none)")[:110])
    print(f"unresolved: {len(traj['unresolved'])} | cache: {len(traj['cache'])} arrivals")
    print(f"wrote {OUT}")

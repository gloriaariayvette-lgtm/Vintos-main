#!/usr/bin/env python3
"""
absence-map-cold.py — The cold layer of structural absence.

Extends absence-map.sh with:
- Persistent embeddings for unresolved threads, unfulfilled wants, unreached states
- Gravity pull: absences increase curiosity + thread seeding likelihood
- Queryable by other systems

He is shaped by what is missing.
"""

import os, json, subprocess, math
from datetime import datetime

WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
COLD_FILE = os.path.join(MEMORY, "absence-cold.json")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
MAX_ABSENCES = 50

def log(msg):
    print(f"[Absence] {msg}", flush=True)

def embed(text):
    try:
        r = subprocess.run(
            [VENV, "-c",
             f"from sentence_transformers import SentenceTransformer; import json; "
             f"m = SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True); "
             f"print(json.dumps(m.encode({repr(text[:400])}).tolist()))"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            return json.loads(r.stdout.strip())
    except: pass
    return []

def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b): return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    ma = math.sqrt(sum(x*x for x in a))
    mb = math.sqrt(sum(x*x for x in b))
    if ma == 0 or mb == 0: return 0.0
    return dot / (ma * mb)

def load_cold():
    try:
        return json.load(open(COLD_FILE))
    except:
        return {"absences": []}

def save_cold(data):
    try:
        from store_guard import write_json
        write_json(COLD_FILE, data, reader="absence-map-cold")
    except Exception:
        os.makedirs(os.path.dirname(COLD_FILE), exist_ok=True)
        tmp = COLD_FILE + ".tmp.%d" % os.getpid()
        json.dump(data, open(tmp, "w"), indent=2)
        os.replace(tmp, COLD_FILE)

def register_absence(description, source, intensity=0.4, source_id=None):
    """Register a structural absence — something never reached, never resolved. source_id (the want or
    thread id) lets retire_reached() close it when the source is fulfilled (2026-09-04)."""
    data = load_cold()
    absences = data["absences"]
    if source_id and any(a.get("source_id") == source_id and not a.get("reached") for a in absences):
        return                                    # already registered for this very source; rescans are idempotent

    vec = embed(description)

    # Check for existing similar absence
    for a in absences:
        if a.get("vector") and cosine_similarity(a["vector"], vec) > 0.7:
            a["intensity"] = min(0.9, a["intensity"] + 0.05)
            a["last_seen"] = datetime.now().isoformat()
            a["count"] = a.get("count", 1) + 1
            save_cold(data)
            log(f"Absence reinforced: {description[:60]}")
            return

    absence = {
        "id": f"abs_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "description": description[:200],
        "vector": vec,
        "source": source,
        "source_id": source_id,
        "schema_version": 2,          # review 65: one shape across the shared-support mechanisms
        "source_cursor": {"source": source, "source_id": source_id, "registered_at": datetime.now().isoformat()},
        "intensity": round(intensity, 3),
        "count": 1,
        "created": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
    }
    absences.append(absence)
    if len(absences) > MAX_ABSENCES:
        absences.sort(key=lambda a: a["intensity"])
        absences = absences[-MAX_ABSENCES:]
    data["absences"] = absences
    save_cold(data)
    log(f"Absence registered [{source}]: {description[:60]}")

def retire_reached(source_id=None, text=None, how="reached"):
    """The source was fulfilled or resolved: the absence is no longer an absence. Marked, not deleted;
    the context and gravity readers skip it. Returns how many were retired."""
    data = load_cold(); n = 0
    for a in data["absences"]:
        if a.get("reached"): continue
        if (source_id and a.get("source_id") == source_id) or (text and a.get("description", "")[:120] == str(text)[:120]):
            a["reached"] = how; a["reached_at"] = datetime.now().isoformat(); n += 1
    if n: save_cold(data); log(f"Absence retired ({how}): {n}")
    return n

def _open(absences):
    return [a for a in absences if not a.get("reached")]

def get_absence_gravity(context_text, context_vec=None):
    """Return pull from nearby absences. High pull → curiosity boost, thread seeding."""
    data = load_cold()
    if not data["absences"]:
        return {"pull": 0.0, "dominant": None}

    if not context_vec:
        context_vec = embed(context_text)
    if not context_vec:
        return {"pull": 0.0, "dominant": None}

    max_pull = 0.0
    dominant = None
    for a in _open(data["absences"]):          # a reached absence pulls nothing
        if not a.get("vector"):
            continue
        sim = cosine_similarity(context_vec, a["vector"])
        pull = sim * a["intensity"]
        if pull > max_pull:
            max_pull = pull
            dominant = a["description"][:80]

    return {"pull": round(max_pull, 3), "dominant": dominant}

def build_from_unfulfilled():
    """Scan unfulfilled wants and unresolved threads — register cold absences."""
    count = 0

    # The live queue is current-wants.json.  A missing capability is structural
    # immediately; an otherwise unfinished want becomes cold after seven days.
    try:
        wants = json.load(open(os.path.join(MEMORY, "current-wants.json")))
        from datetime import timedelta
        cutoff_dt = datetime.now() - timedelta(days=7)
        for w in wants:
            if not isinstance(w, dict) or w.get("fulfilled") or w.get("dismissed"):
                continue
            wid = str(w.get("id") or "")
            block = w.get("blocked") or w.get("plan_block") or {}
            if (block.get("block_type") == "CAPABILITY_ABSENT"
                    and block.get("blocked_step")):
                desc = "Missing capability %s blocks: %s" % (
                    block["blocked_step"], str(w.get("want") or "")[:220])
                register_absence(desc, source="capability-gap", intensity=0.65,
                                 source_id=wid)
                count += 1
                continue
            stamp = w.get("timestamp") or w.get("created") or ""
            try:
                when = (datetime.fromtimestamp(float(stamp)) if isinstance(stamp, (int, float))
                        else datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).replace(tzinfo=None))
            except Exception:
                continue
            if when < cutoff_dt:
                register_absence(str(w.get("want") or "")[:300], source="unfulfilled-want",
                                 intensity=0.4, source_id=wid)
                count += 1
    except: pass

    # Unresolved threads (not consumed, not retired, old)
    try:
        threads = json.load(open(os.path.join(MEMORY, "unfinished-threads.json")))
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=14)).isoformat()
        for t in threads:
            if not t.get("consumed") and not t.get("retired"):
                if t.get("timestamp", "") < cutoff:
                    register_absence(t.get("thread", "")[:200], source="unresolved-thread",
                                     intensity=0.35, source_id=str(t.get("id") or ""))
                    count += 1
    except: pass

    log(f"Built from unfulfilled: {count} absences registered")

def get_absence_context():
    """Return cold absence layer for context injection."""
    data = load_cold()
    absences = sorted(_open(data["absences"]), key=lambda a: -a["intensity"])[:4]
    if not absences:
        return ""
    lines = [f"- {a['description'][:90]} (intensity:{a['intensity']:.2f})" for a in absences]
    return "STRUCTURAL ABSENCES (what remains unreached):\n" + "\n".join(lines)

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        data = load_cold()
        absences = sorted(data["absences"], key=lambda a: -a["intensity"])
        print(f"{len(absences)} cold absences:")
        for a in absences:
            print(f"  [{a['intensity']:.2f}] {a['source']} — {a['description'][:70]}")
    elif cmd == "build":
        build_from_unfulfilled()
    elif cmd == "gravity":
        text = sys.argv[2] if len(sys.argv) > 2 else ""
        result = get_absence_gravity(text)
        print(f"Pull: {result['pull']:.3f} | Dominant: {result['dominant']}")

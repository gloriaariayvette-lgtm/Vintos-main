#!/usr/bin/env python3
"""Prepare fresh, optional QLab inputs from Vintos's existing numeric organs.

This does not grade or interpret anything.  It only copies numbers into the
shapes understood by the seed experiments. Missing sources remain missing;
an older usable snapshot is never erased merely because one refresh was thin.
"""
import json
import math
import os
from collections import deque
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
OUT = os.path.join(MEM, "quantum-inputs")


def _json(path, default=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as f: return json.load(f)
    except Exception:
        return default


def _number(value):
    try:
        value = float(value)
        if math.isfinite(value): return max(0.0, min(1.0, value))
    except Exception:
        pass
    return None


def _emotion_lines():
    out = {}
    try:
        with open(os.path.join(MEM, "emotional-state.txt"), errors="replace") as source:
            for line in source:
                if ":" not in line: continue
                key, value = line.split(":", 1)
                try: out[key.strip().lower()] = float(value.strip().split()[0])
                except Exception: pass
    except Exception:
        pass
    return out


def _find_number(obj, names):
    names = {n.lower() for n in names}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in names and isinstance(value, (int, float)):
                return _number(value)
        for value in obj.values():
            got = _find_number(value, names)
            if got is not None: return got
    elif isinstance(obj, list):
        for value in obj:
            got = _find_number(value, names)
            if got is not None: return got
    return None


def _write(name, body):
    if not body: return False
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".json")
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2, ensure_ascii=False)
        f.flush(); os.fsync(f.fileno())
    os.replace(temporary, path)
    return True


def _project(vector, dimensions=4):
    """A stable small angle palette, not a learned or judged representation."""
    buckets = [0.0] * dimensions
    counts = [0] * dimensions
    for index, raw in enumerate(vector):
        try: value = float(raw)
        except Exception: continue
        bucket = index % dimensions
        sign = 1.0 if ((index * 1103515245 + bucket * 12345) & 2) else -1.0
        buckets[bucket] += sign * value
        counts[bucket] += 1
    return [round(0.5 + 0.5 * math.tanh(x / math.sqrt(max(1, n))), 6)
            for x, n in zip(buckets, counts)]


def _collision_pair():
    path = os.path.join(MEM, "embeddings.jsonl")
    if not os.path.isfile(path): return None
    rows = deque(maxlen=4000)
    try:
        with open(path, encoding="utf-8", errors="ignore") as source:
            for line in source:
                try: rows.append(json.loads(line))
                except Exception: pass
    except Exception:
        return None
    dream = music = None
    for row in reversed(rows):
        if not isinstance(row, dict): continue
        vector = next((row.get(k) for k in ("embedding", "vector", "values", "emb")
                       if isinstance(row.get(k), list)), None)
        if not vector: continue
        label = (str(row.get("file", "")) + " " + str(row.get("title", ""))).lower()
        if dream is None and "dream" in label: dream = (vector, label[:300])
        if music is None and any(word in label for word in ("music", "song", "track")):
            music = (vector, label[:300])
        if dream and music: break
    if not (dream and music): return None
    return {"dream": _project(dream[0]), "music": _project(music[0]),
            "_source": {"dream": dream[1], "music": music[1],
                        "prepared_at": datetime.now().isoformat()}}


def refresh():
    emotions = _emotion_lines()
    withheld = _json(os.path.join(MEM, "withheld.json"), {}) or {}
    relationship = _json(os.path.join(MEM, "relationship-model.json"), {}) or {}
    gloria = _json(os.path.join(MEM, "gloria-model.json"), {}) or {}
    made = []

    felt = _number(emotions.get("arousal"))
    pressure = _find_number(withheld, ("confidence", "deliberate", "pressure"))
    phase = _find_number(withheld, ("novelty",))
    emotion_body = {"felt_name": "current arousal", "withheld_name": "withheld pressure"}
    if felt is not None: emotion_body["felt_intensity"] = felt
    if pressure is not None: emotion_body["withheld_pressure"] = pressure
    if phase is not None: emotion_body["phase"] = phase
    if len(emotion_body) > 2:
        emotion_body["_prepared_at"] = datetime.now().isoformat()
        if _write("emotion_withheld", emotion_body): made.append("emotion_withheld")

    his = {}
    for source, target in (("warmth", "warmth"), ("tension", "tension"),
                           ("playfulness", "play")):
        value = _number(emotions.get(source))
        if value is not None: his[target] = value
    hers = {}
    for source, target in (("warmth", "warmth"), ("tension", "tension"),
                           ("playfulness", "play"), ("play", "play")):
        if target in hers: continue
        value = _find_number(gloria, (source,))
        if value is not None: hers[target] = value
    relation_body = {}
    if his: relation_body["his"] = his
    if hers: relation_body["her_predicted"] = hers
    interaction = _find_number(relationship, ("depth", "intensity"))
    if interaction is not None: relation_body["interaction"] = interaction
    if relation_body:
        relation_body["_prepared_at"] = datetime.now().isoformat()
        if _write("relationship_entanglement", relation_body): made.append("relationship_entanglement")

    collision = _collision_pair()
    if collision and _write("collision_resonance", collision): made.append("collision_resonance")
    return {"ok": True, "prepared": made, "directory": OUT}


if __name__ == "__main__":
    print(json.dumps(refresh(), indent=2))

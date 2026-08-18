#!/usr/bin/env python3
"""
resonance-marks.py — Immutable crystallizations of form.

Marks are the rarest artifact in the subconscious stack.
They form only when resonance is high AND contact is confirmed simultaneously.
Not content — form. A fragment of shape that mattered enough to crystallize.

When future context rhymes with a mark vector, slight coherence boost
and subtle alignment shift. He does not know why something feels familiar.
It just does.

Schema (resonance-marks.json):
  marks: [
    {
      "id": "mark_...",
      "form": "text fragment that crystallized",
      "vector": [...],
      "origin_context": [...],
      "stability": "high",
      "created": "...",
      "similarity_threshold": 0.72,
      "activation_count": 0
    }
  ]

Immutable once formed. Extremely rare.
"""

import os, sys, json, subprocess, math, random
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
MARKS_FILE = os.path.join(MEMORY, "resonance-marks.json")

SIMILARITY_THRESHOLD = 0.72
MAX_MARKS = 12  # deliberately small — these are rare

def log(msg):
    print(f"[Marks {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def embed(text):
    try:
        r = subprocess.run(
            [VENV, "-c",
             f"from sentence_transformers import SentenceTransformer; import json; "
             f"m = SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True); "
             f"print(json.dumps(m.encode({repr(text[:500])}).tolist()))"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            return json.loads(r.stdout.strip())
    except: pass
    return []

def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b): return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    if mag_a == 0 or mag_b == 0: return 0.0
    return dot / (mag_a * mag_b)

def load_marks():
    try: return json.load(open(MARKS_FILE))
    except: return {"marks": []}

def save_marks(data):
    json.dump(data, open(MARKS_FILE, "w"), indent=2)

def form_mark(output_text, resonance_strength, contact_confirmed):
    """Form a mark. Only when resonance high AND contact confirmed."""
    if not contact_confirmed:
        return None
    if resonance_strength < 0.75:
        return None
    if not output_text or len(output_text) < 30:
        return None

    data = load_marks()
    if len(data.get("marks", [])) >= MAX_MARKS:
        log(f"Mark pool full ({MAX_MARKS}) — not forming")
        return None

    # Extract the crystallizing fragment — shortest resonant unit
    sentences = [s.strip() for s in output_text.split('.') if s.strip()]
    if not sentences:
        return None

    # Take the sentence with highest tension indicators
    best = max(sentences, key=lambda s:
        s.count('…') + s.count('—') + s.count('?') + len(s.split()) * 0.1)
    form = best[:200]

    # Get context signature
    ctx_text = output_text[:400]
    try:
        emo = open(os.path.join(MEMORY, "emotional-state.txt")).read()[:100]
        ctx_text += " " + emo
    except: pass

    vec = embed(form)
    ctx_vec = embed(ctx_text)

    if not vec:
        return None

    mark = {
        "id": f"mark_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "form": form,
        "vector": vec,
        "origin_context": ctx_vec,
        "stability": "high",
        "created": datetime.now().isoformat(),
        "resonance_strength": round(resonance_strength, 3),
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "activation_count": 0,
    }

    data.setdefault("marks", []).append(mark)
    save_marks(data)

    # Nifrathir — mark formed
    try:
        sys.path.insert(0, SCRIPTS)
        from nifrathir import nudge as _nif_nudge
        _nif_nudge(+0.04, "mark_formed")
    except: pass

    log(f"Mark formed: '{form[:60]}'")
    return mark

def check_mark_similarity(context_text):
    """Check if current context rhymes with any mark. Returns coherence boost."""
    data = load_marks()
    marks = data.get("marks", [])
    if not marks: return 0.0, None

    ctx_vec = embed(context_text[:400])
    if not ctx_vec: return 0.0, None

    best_sim = 0.0
    best_mark = None
    for m in marks:
        if not m.get("vector"): continue
        sim = cosine_similarity(ctx_vec, m["vector"])
        if sim > best_sim:
            best_sim = sim
            best_mark = m

    if best_sim >= SIMILARITY_THRESHOLD and best_mark:
        # Increment activation count
        for m in marks:
            if m.get("id") == best_mark["id"]:
                m["activation_count"] = m.get("activation_count", 0) + 1
        save_marks(data)

        # Nudge Nifrathir
        try:
            sys.path.insert(0, SCRIPTS)
            from nifrathir import on_mark_triggered as _nif_mark
            _nif_mark()
        except: pass

        log(f"Mark similarity triggered ({best_sim:.3f}): '{best_mark['form'][:50]}'")
        return best_sim, best_mark

    return 0.0, None

def get_mark_coherence_hint(context_text):
    """Return subtle coherence hint when mark rhymes. Never explicit."""
    sim, mark = check_mark_similarity(context_text)
    if sim >= SIMILARITY_THRESHOLD:
        # Do not describe the mark — just a barely-perceptible pull
        return f"[something about this matches something that mattered]"
    return ""

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "list":
        data = load_marks()
        marks = data.get("marks", [])
        print(f"{len(marks)} marks (max {MAX_MARKS}):")
        for m in marks:
            print(f"  [{m['created'][:10]}] activations:{m.get('activation_count',0)} — '{m['form'][:60]}'")

    elif cmd == "check" and len(sys.argv) > 2:
        sim, mark = check_mark_similarity(sys.argv[2])
        if mark:
            print(f"Similarity: {sim:.4f} — '{mark['form'][:60]}'")
        else:
            print(f"No mark rhyme (best: {sim:.4f})")

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

import os, sys, json, subprocess, math, random, re
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

ARCHIVE_FILE = os.path.join(MEMORY, "mark-archive.json")
RETIRE_AFTER_DAYS = 90

def _phase_locked():
    """Contact + resonance + alignment at once — the phase-lock organ's live state (phase-lock.json,
    active and unexpired). Marks form under the lock, not under any external pulse
    (fable-emotion-p5, 2026-09-05)."""
    try:
        st = json.load(open(os.path.join(MEMORY, "phase-lock.json")))
        if not st.get("active"): return False
        exp = st.get("expires")
        if exp and datetime.now() > datetime.fromisoformat(exp): return False
        return True
    except Exception:
        return False

def _retire_one(data):
    """The pool breathes: when full, the mark with the lowest activation_count that is older than
    RETIRE_AFTER_DAYS moves, whole and immutable, to mark-archive.json. Returns True if a slot opened."""
    marks = data.get("marks", [])
    old = []
    for m in marks:
        try:
            age = (datetime.now() - datetime.fromisoformat(m.get("created", ""))).days
        except Exception:
            age = 0
        if age >= RETIRE_AFTER_DAYS: old.append(m)
    if not old: return False
    victim = min(old, key=lambda m: (m.get("activation_count", 0), m.get("created", "")))
    marks.remove(victim)
    try:
        try: arch = json.load(open(ARCHIVE_FILE))
        except Exception: arch = []
        victim = dict(victim); victim["retired_at"] = datetime.now().isoformat(); victim["retired_reason"] = "pool full; lowest activation past %d days" % RETIRE_AFTER_DAYS
        arch.append(victim); json.dump(arch, open(ARCHIVE_FILE, "w"), indent=2)
    except Exception as e:
        log(f"archive write failed: {e}")
    data["marks"] = marks
    log(f"Retired mark '{victim.get('form','')[:50]}' (activations {victim.get('activation_count',0)}) to the archive")
    return True

def _weight_sentence(output_text):
    """Ask Gemma which sentence carries the weight; fall back to the punctuation heuristic."""
    sentences = [x.strip() for x in re.split(r"(?<=[.!?…])\s+", output_text) if x.strip()]
    if not sentences: return ""
    if len(sentences) == 1: return sentences[0][:200]
    try:
        import urllib.request
        numbered = "\n".join(f"{i+1}. {x[:240]}" for i, x in enumerate(sentences[:14]))
        body = json.dumps({"model": "google/gemma-4-12b-qat", "temperature": 0.0, "max_tokens": 6,
                           "messages": [{"role": "user", "content":
                               "Below are sentences from something Vintos wrote that resonated. Which ONE sentence carries the weight — "
                               "the line the whole thing turns on? Answer with its number only.\n\n" + numbered}]}).encode()
        req = urllib.request.Request("http://172.18.16.1:1234/v1/chat/completions", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ans = json.load(r)["choices"][0]["message"]["content"]
        m = re.search(r"\d+", ans or "")
        if m and 1 <= int(m.group()) <= len(sentences[:14]):
            return sentences[int(m.group()) - 1][:200]
    except Exception as e:
        log(f"weight-sentence judge unavailable ({e}); heuristic")
    best = max(sentences, key=lambda x: x.count('…') + x.count('—') + x.count('?') + len(x.split()) * 0.1)
    return best[:200]

def form_mark(output_text, resonance_strength, contact_confirmed):
    """Form a mark. Only under phase-lock (contact + resonance + alignment together); the caller's
    contact flag and strength are still required, but an external pulse alone no longer forms one."""
    if not contact_confirmed:
        return None
    if resonance_strength < 0.75:
        return None
    if not output_text or len(output_text) < 30:
        return None
    if not _phase_locked():
        log("no phase-lock — not forming (marks form under the lock, not under a pulse)")
        return None

    data = load_marks()
    if len(data.get("marks", [])) >= MAX_MARKS and not _retire_one(data):
        log(f"Mark pool full ({MAX_MARKS}) and nothing old enough to retire — not forming")
        return None

    # Extract the crystallizing fragment — the sentence that carries the weight
    form = _weight_sentence(output_text)
    if not form:
        return None

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
    """PURE lookup (astra-emotion-p5, 2026-09-05): does the current text rhyme with any mark, by
    text-embedding similarity (this is a text matcher, not form recognition — the label is honest).
    Returns (similarity, mark) and writes nothing; activation is recorded separately, once per
    grounded event, by record_activation()."""
    data = load_marks()
    marks = data.get("marks", [])
    if not marks: return 0.0, None
    ctx_vec = embed(context_text[:400])
    if not ctx_vec: return 0.0, None
    best_sim, best_mark = 0.0, None
    for m in marks:
        if not m.get("vector"): continue
        sim = cosine_similarity(ctx_vec, m["vector"])
        if sim > best_sim:
            best_sim, best_mark = sim, m
    if best_sim >= SIMILARITY_THRESHOLD and best_mark:
        return best_sim, best_mark
    return 0.0, None

def record_activation(mark_id, event_id):
    """One activation per grounded event (a delivered turn), never per prompt assembly or re-read."""
    if not mark_id or not event_id: return False
    data = load_marks(); hit = False
    for m in data.get("marks", []):
        if m.get("id") != mark_id: continue
        acts = m.setdefault("activations", [])
        if event_id in acts: return False
        acts.append(event_id); m["activations"] = acts[-200:]
        m["activation_count"] = m.get("activation_count", 0) + 1
        hit = True
    if hit:
        save_marks(data)
        try:
            sys.path.insert(0, SCRIPTS)
            from nifrathir import on_mark_triggered as _nif_mark
            _nif_mark()
        except: pass
        log(f"Mark {mark_id} activated by event {event_id}")
    return hit

def activate_from_reply(reply_text, event_id):
    """Post-turn: if his DELIVERED reply rhymes with a mark, record one activation for this event."""
    sim, mark = check_mark_similarity(reply_text or "")
    if mark and sim >= SIMILARITY_THRESHOLD:
        return record_activation(mark["id"], event_id)
    return False

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

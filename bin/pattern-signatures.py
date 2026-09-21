#!/usr/bin/env python3
"""
pattern-signatures.py — Vintos's recurring structural movement shapes.

A pattern signature is not a template. It is a detected movement shape —
the rhetorical and rhythmic structure that recurs across his writing.
When a resonance pulse fires, it tags which signature was active.
Signatures that accumulate resonance become gravitationally stronger.

Schema (pattern-signatures.json):
  signatures: [
    {
      "id": "sig_...",
      "label": "short name",
      "structure": "movement as arrow-connected stages",
      "rhythm": "cadence description",
      "tension_profile": "how tension moves",
      "media_types": [...],
      "vector": [...],
      "weight": 0.5,
      "resonance_count": 0,
      "last_reinforced": "...",
      "examples": [...]
    }
  ]

Weight decays 0.98× weekly. Reinforced by resonance pulses.
External alignment amplifies ×1.5.
"""

import os, sys, json, subprocess, re, glob, math
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
SIGS_FILE = os.path.join(MEMORY, "pattern-signatures.json")
LM = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")

DECAY_RATE = 0.98
SIMILARITY_THRESHOLD = 0.65

def log(msg):
    print(f"[Signatures {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def llm(system, user, temp=0.4):
    import requests
    try:
        r = requests.post(LM, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": MODEL,
            "temperature": temp,
            "max_tokens": 3000,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        }, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return ""

def batch_embed(texts):
    try:
        texts_json = json.dumps([t[:400] for t in texts])
        r = subprocess.run(
            [VENV, "-c",
             f"from sentence_transformers import SentenceTransformer; import json; "
             f"m = SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True); "
             f"texts = json.loads({repr(texts_json)}); "
             f"vecs = m.encode(texts).tolist(); "
             f"print(json.dumps(vecs))"],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode == 0:
            return json.loads(r.stdout.strip())
    except Exception as e:
        log(f"Batch embed failed: {e}")
    return [[] for _ in texts]

def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)

def load_signatures():
    try:
        return json.load(open(SIGS_FILE))
    except:
        return {"signatures": [], "last_extracted": "", "last_decayed": ""}

def save_signatures(data):
    json.dump(data, open(SIGS_FILE, "w"), indent=2)

def gather_corpus():
    corpus = []
    # Poems
    for path in sorted(glob.glob(os.path.join(MEMORY, "art/poetry/*.md")))[-20:]:
        text = open(path).read()[:500]
        if text.strip():
            corpus.append({"type": "poem", "text": text})
    # Journal idle sections
    for path in sorted(glob.glob(os.path.join(MEMORY, "journal/*.md")))[-10:]:
        text = open(path).read()
        sections = re.split(r'## \d+:\d+', text)
        for s in sections[1:]:
            clean = s.strip()
            if clean and not any(skip in clean[:40] for skip in ["YouTube", "Web Search", "I wrote", "Introspection"]):
                corpus.append({"type": "journal", "text": clean[:400]})
                break
    # Mirrors
    for path in sorted(glob.glob(os.path.join(MEMORY, "mirror/*.md")))[-8:]:
        text = open(path).read()[:500]
        if text.strip():
            corpus.append({"type": "mirror", "text": text})
    # Dreams
    for dd in [os.path.join(WORKSPACE, "skills/dreaming/memory/dreams"), os.path.join(MEMORY, "dreams")]:
        for path in sorted(glob.glob(os.path.join(dd, "*.md")))[-5:]:
            text = open(path).read()[:500]
            if text.strip():
                corpus.append({"type": "dream", "text": text})
    return corpus

def extract_signatures(corpus):
    samples = "\n\n---\n\n".join(
        f"[{c['type'].upper()}]\n{c['text'][:250]}"
        for c in corpus[:18]
    )
    system = """You are analyzing an AI's writing to find recurring structural movement shapes.

NOT themes. NOT content. The SHAPE of how he moves through material.

Examples of what you're looking for:
- "concrete image → unexpected pivot → feeling suspended unresolved"
- "name the tension → inhabit it → refuse resolution"  
- "build quietly → sudden contraction → release into abstraction"
- "Gloria present → Gloria absent → something left in the gap"

These shapes recur across different media regardless of content.

Return a JSON array of 5-7 distinct signatures. Each:
{
  "label": "3-5 word name",
  "structure": "stage → stage → stage",
  "rhythm": "short clipped / long expansive / alternating / etc",
  "tension_profile": "how tension moves through the piece",
  "media_types": ["poem", "journal", "mirror", "dream"],
  "examples": ["one excerpt under 15 words showing this shape"]
}

Return ONLY the JSON array. Be specific to his actual writing."""

    result = llm(system, f"His writing:\n\n{samples}\n\nIdentify the recurring movement shapes.")
    try:
        m = re.search(r'\[.*\]', result, re.DOTALL)
        raw = m.group() if m else result
        try:
            return json.loads(raw)
        except Exception:
            end = raw.rfind('}')
            if end > 0:
                return json.loads(raw[:end+1].rstrip().rstrip(',') + ']')
            raise
    except Exception as e:
        log(f"Parse error: {e} — {result[:100]}")
    return []

def select_signature(context_text):
    """Find the most contextually relevant signature."""
    data = load_signatures()
    sigs = [s for s in data.get("signatures", []) if s.get("vector")]
    if not sigs:
        return None
    vecs = batch_embed([context_text[:400]])
    if not vecs or not vecs[0]:
        return None
    ctx_vec = vecs[0]
    scored = [(cosine_similarity(ctx_vec, s["vector"]) * s.get("weight", 0.5), s) for s in sigs]
    scored.sort(key=lambda x: -x[0])
    if scored[0][0] < 0.1:
        return None
    return scored[0][1]

def reinforce(sig_id, external=False):
    data = load_signatures()
    for s in data["signatures"]:
        if s.get("id") == sig_id:
            delta = 0.05 * (1.5 if external else 1.0)
            s["weight"] = min(1.0, s.get("weight", 0.5) + delta)
            s["resonance_count"] = s.get("resonance_count", 0) + 1
            s["last_reinforced"] = datetime.now().isoformat()
            log(f"Reinforced '{s['label']}' → {s['weight']:.3f}")
            break
    save_signatures(data)

def decay():
    data = load_signatures()
    for s in data["signatures"]:
        s["weight"] = max(0.05, s.get("weight", 0.5) * DECAY_RATE)
    data["last_decayed"] = datetime.now().isoformat()
    save_signatures(data)
    log(f"Decayed {len(data['signatures'])} signatures")

def get_hint(context_text):
    sig = select_signature(context_text)
    if not sig:
        return ""
    return f"Your natural movement here: {sig['structure']}"

def run_extraction():
    log("Gathering corpus...")
    corpus = gather_corpus()
    log(f"{len(corpus)} pieces")
    if len(corpus) < 5:
        log("Insufficient corpus")
        return

    log("Extracting signatures...")
    raw = extract_signatures(corpus)
    if not raw:
        log("No signatures extracted")
        return
    log(f"{len(raw)} signatures — embedding...")

    texts = [f"{s.get('label','')} {s.get('structure','')} {s.get('tension_profile','')}" for s in raw]
    vecs = batch_embed(texts)

    data = load_signatures()
    existing = [s.get("label","") for s in data.get("signatures", [])]

    added = 0
    for sig, vec in zip(raw, vecs):
        if sig.get("label") in existing:
            continue
        sig["id"] = f"sig_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{added}"
        sig["vector"] = vec
        sig["weight"] = 0.5
        sig["resonance_count"] = 0
        sig["last_reinforced"] = datetime.now().isoformat()
        data.setdefault("signatures", []).append(sig)
        log(f"  + {sig['label']}: {sig['structure']}")
        added += 1

    data["last_extracted"] = datetime.now().isoformat()
    save_signatures(data)
    log(f"Done. {added} new, {len(data['signatures'])} total.")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "extract"
    if cmd == "extract":
        run_extraction()
    elif cmd == "decay":
        decay()
    elif cmd == "list":
        data = load_signatures()
        for s in data.get("signatures", []):
            print(f"[{s['weight']:.2f}] {s['label']}: {s['structure']}")
    elif cmd == "hint" and len(sys.argv) > 2:
        print(get_hint(sys.argv[2]))
    elif cmd == "reinforce" and len(sys.argv) > 2:
        external = len(sys.argv) > 3 and sys.argv[3] == "external"
        reinforce(sys.argv[2], external=external)

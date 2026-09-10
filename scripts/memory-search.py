#!/usr/bin/env python3
"""
Vintos Semantic Memory Search
Find memories by meaning, not just keywords.
Usage: python3 memory-search.py "what did I feel when Gloria was frustrated"
"""
import os
import sys
import json
import numpy as np

def _emb_clip(_x, _n=6000):
    # nomic ctx is 2048 tokens; oversized input WEDGES LM Studio. Clip before sending.
    if isinstance(_x, str): return _x[:_n]
    if isinstance(_x, list): return [(_i[:_n] if isinstance(_i, str) else _i) for _i in _x]
    return _x


MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
INDEX_FILE = os.path.join(MEMORY, "semantic-index.json")


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)


def load_index(path=None):
    try:
        with open(path or INDEX_FILE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {"version": 1, "entries": d}
    except Exception:
        return {}


def _file_revision(path):
    try:
        st = os.stat(path)
    except Exception:
        return None
    import hashlib
    return "rev-" + hashlib.sha1(("%d_%r" % (st.st_size, st.st_mtime)).encode()).hexdigest()[:16]


def serve_entries(index):
    """Item 105: never serve a chunk whose source revision differs from the file on disk, nor a
    tombstoned chunk, nor one embedded by another model/dims than the projection declares.
    A version-1 index (pre-projection) carries no revisions and is served as it was."""
    raw = (index or {}).get("entries") or []
    version = (index or {}).get("version", 1)
    out = []
    for e in raw:
        if not isinstance(e, dict) or not e.get("embedding") or e.get("tombstone"):
            continue
        if version < 2:
            out.append(e); continue
        if e.get("embed_model") != index.get("embed_model") or e.get("embed_dims") != index.get("embed_dims"):
            continue
        if e.get("kind") not in ("authored", "felt", "derived"):
            continue
        rev = e.get("revision")
        if not rev or _file_revision(e.get("path", "")) != rev:
            continue
        out.append(e)
    return out


def search(query, limit=5):
    if not (os.path.exists(INDEX_FILE) or os.path.exists(os.path.join(MEMORY, "embeddings.jsonl"))):
        print("No semantic index found. Run memory-index.py first.")
        return []

    import requests
    LM_EMBED_URL = "http://172.18.16.1:1234/v1/embeddings"
    EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"

    def get_embedding(text):
        resp = requests.post(LM_EMBED_URL, json={
            "model": EMBED_MODEL,
            "input": _emb_clip(text[:2000])
        }, timeout=30)
        return resp.json()["data"][0]["embedding"]
    query_embedding = get_embedding(query)

    JSONL_FILE = os.path.join(MEMORY, "embeddings.jsonl")
    entries = []
    if os.path.exists(JSONL_FILE):
        with open(JSONL_FILE) as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except: pass
    else:
        entries = serve_entries(load_index(INDEX_FILE))
    results = []
    for entry in entries:
        if not entry.get("embedding"):
            continue
        score = cosine_similarity(query_embedding, entry["embedding"])
        results.append({
            "score": float(score),
            "source": entry.get("source", entry.get("file", "")),
            "filename": entry.get("filename", entry.get("file", "")),
            "text": entry.get("chunk", entry.get("text", "")),
            "kind": entry.get("kind", ""),
            "revision": entry.get("revision", ""),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 memory-search.py 'your query here'")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"Searching for: {query}\n")

    results = search(query)
    for i, r in enumerate(results):
        print(f"[{i+1}] {r['source']}/{r['filename']} [{r.get('kind') or 'legacy'}] (score: {r['score']:.3f})")
        print(f"    {r['text'][:200]}...")
        print()

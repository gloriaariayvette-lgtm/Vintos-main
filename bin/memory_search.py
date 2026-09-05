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


def search(query, limit=5):
    if not os.path.exists(INDEX_FILE):
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
        with open(INDEX_FILE) as f:
            index = json.load(f)
        raw = index if isinstance(index, list) else index.get("entries", [])
        entries = [e for e in raw if isinstance(e, dict) and "embedding" in e]
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
        print(f"[{i+1}] {r['source']}/{r['filename']} (score: {r['score']:.3f})")
        print(f"    {r['text'][:200]}...")
        print()

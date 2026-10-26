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
    """review 157: the one arithmetic lives in text_similarity.cosine; this name stays for callers."""
    try:
        import sys as _ts_s, os as _ts_o
        _ts_s.path.insert(0, _ts_o.path.dirname(_ts_o.path.abspath(__file__)))
        _ts_s.path.insert(0, _ts_o.path.expanduser("~/.vintos/workspace/scripts"))
        from text_similarity import cosine as _cos
        return _cos(a, b)
    except Exception:
        if not a or not b or len(a) != len(b): return 0.0
        dot = sum(float(x) * float(y) for x, y in zip(a, b))
        na = sum(float(x) * float(x) for x in a) ** 0.5; nb = sum(float(y) * float(y) for y in b) ** 0.5
        return (dot / (na * nb)) if na and nb else 0.0

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


def _is_dream(entry):
    """A dream row, whichever index served it. The v2 projection carries source=='dreams' and a `path`;
    the legacy embeddings.jsonl carries only `file`/`title`, so '/dreams/' never matched `path` there and
    ~600 dream rows reached him without the marker — told to him as things that happened. Read file and
    filename too (review 109, legacy fix)."""
    if not isinstance(entry, dict):
        return False
    if entry.get("source") == "dreams":
        return True
    for k in ("path", "file", "filename"):
        if "/dreams/" in str(entry.get(k, "")):
            return True
    return False


def _source_present(entry):
    """Tombstone-on-read for the legacy index. The v2 projection tombstones a chunk whose source file is
    gone; the append-only embeddings.jsonl never did, so it still points at deleted/superseded files. A row
    whose source file no longer exists is not served. Rows with no file reference (already revision-checked
    v2 chunks) are left alone."""
    if not isinstance(entry, dict):
        return False
    f = entry.get("file") or entry.get("path")
    if not f:
        return True
    try:
        return os.path.exists(f)
    except Exception:
        return True


class EmbeddingError(RuntimeError):
    """The embedding service did not give a usable embedding. Says what went wrong, never the reply body or a key."""


def embedding_from(resp):
    """The query's embedding from the service's reply, checked before it is indexed (SF-67752b13, 2026-10-15: the
    reply was read as resp.json()["data"][0]["embedding"] with no check, so a non-200 or an error body surfaced as a
    bare KeyError from deep in a search)."""
    status = getattr(resp, "status_code", None)
    if status != 200:
        raise EmbeddingError("the embedding service answered HTTP %s" % status)
    try:
        body = resp.json()
    except ValueError:
        raise EmbeddingError("the embedding service answered with something that is not JSON")
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list) or not data:
        keys = sorted(body)[:6] if isinstance(body, dict) else type(body).__name__
        raise EmbeddingError("the embedding reply had no data list (it had: %s)" % (keys,))
    first = data[0]
    vector = first.get("embedding") if isinstance(first, dict) else None
    if (not isinstance(vector, list) or not vector
            or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in vector)):
        raise EmbeddingError("the embedding reply's first item had no list of numbers")
    return vector


def search(query, limit=5):
    if not (os.path.exists(INDEX_FILE) or os.path.exists(os.path.join(MEMORY, "embeddings.jsonl"))):
        print("No semantic index found. Run memory-index.py first.")
        return []

    import requests
    LM_EMBED_URL = "http://172.18.16.1:1234/v1/embeddings"
    EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"

    def get_embedding(text):
        try:
            resp = requests.post(LM_EMBED_URL, json={
                "model": EMBED_MODEL,
                "input": _emb_clip(text[:2000])
            }, timeout=30)
        except requests.RequestException as exc:
            raise EmbeddingError("the embedding service could not be reached (%s)" % type(exc).__name__)
        return embedding_from(resp)
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
        # tombstone-on-read: a legacy row pointing at a deleted/superseded source file is not his
        # to recall any more. (The v2 projection already revision-checks; this covers embeddings.jsonl.)
        if not _source_present(entry):
            continue
        score = cosine_similarity(query_embedding, entry["embedding"])
        _src = entry.get("source", entry.get("file", ""))
        _txt = entry.get("chunk", entry.get("text", ""))
        # review 109: a dream that comes back is still a dream. The text he receives says so on its
        # face, so a retrieved dream can never be recounted as something that happened.
        _dream = _is_dream(entry)
        if _dream:
            _txt = "[A DREAM he had - not something that happened] " + _txt
        results.append({
            "score": float(score),
            "source": _src,
            "filename": entry.get("filename", entry.get("file", "")),
            "text": _txt,
            "kind": entry.get("kind", ""),
            "is_dream": _dream,
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

    try:
        results = search(query)
    except EmbeddingError as exc:     # a clear failure and a nonzero exit; callers already treat nonzero as no result
        print("memory search failed: %s" % exc, file=sys.stderr)
        sys.exit(2)
    for i, r in enumerate(results):
        print(f"[{i+1}] {r['source']}/{r['filename']} [{r.get('kind') or 'legacy'}] (score: {r['score']:.3f})")
        print(f"    {r['text'][:200]}...")
        print()

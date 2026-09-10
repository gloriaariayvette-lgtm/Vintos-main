#!/usr/bin/env python3
"""
Vintos Semantic Memory Indexer — ONE versioned, rebuildable retrieval projection.

Review items 105 / 111 (2026-09-10). The index is a PROJECTION of the memory files, never a store
of its own: every chunk records the source path, the source REVISION (mtime+size hash), the
embedding model and its dims, and a KIND (authored | felt | derived) taken from the file type.
A rebuild replaces the chunks of any source whose revision changed and TOMBSTONES the chunks of a
source that disappeared; a chunk is never served when its recorded revision differs from the file
on disk (memory-search.py checks at serve time, so a stale index cannot lie in between rebuilds).

    authored   the sentences he and Gloria wrote on purpose (SELF-MODEL, SOUL, value-map, ...)
    felt       his own dated writing (journals, dreams, introspections, confessions, pearls, ...)
    derived    what an organ computed from those (belief sediment, causal self-model, ...)

The two are never mixed in a chunk: a chunk has exactly one source and one kind.
"""
import os
import json
import hashlib
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
INDEX_FILE = os.path.join(MEMORY, "semantic-index.json")

PROJECTION_VERSION = 2
LM_EMBED_URL = "http://172.18.16.1:1234/v1/embeddings"
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"
EMBED_DIMS = 768
MAX_TOMBSTONES = 2000

KINDS = ("authored", "felt", "derived")

# Directories of dated .md writing — his own, felt
MEMORY_DIRS = [
    ("dreams", "skills/dreaming/memory/dreams"),
    ("dreams", "memory/dreams"),
    ("journals", "memory/journal"),
    ("self-reviews", "memory/self-reviews"),
    ("philosophy", "memory/philosophy"),
    ("confessions", "memory/confessions"),
    ("mirror", "memory/mirror"),
    ("introspections", "memory/introspections"),
    ("biography", "memory/biography"),
    ("gloria-model", "memory/gloria-model-history"),
    ("consent-audits", "memory/consent-audits"),
    ("substrate-audits", "memory/substrate-audits"),
    ("silence-audits", "memory/silence-audits"),
    ("velqan-etymology", "memory/velqan-etymology"),
    ("art-poetry", "memory/art/poetry"),
    ("art-image", "memory/art/image-prompts"),
    ("art-music", "memory/art/music-prompts"),
    ("pearls", "memory/pearls"),
    ("black-pearls", "memory/black-pearls"),
    ("chapters", "memory/chapters"),
    ("kisses", "memory/kisses"),
]

# Single files. (Until 2026-09-10 a second MEMORY_FILES list inside main() shadowed this one, so
# SELF-MODEL, SOUL and the deep-structure JSON were never indexed. Both lists live here now.)
MEMORY_FILES = [
    ("velqan", "memory/velqan-utterances.md"),
    ("blush-ledger", "memory/blush-ledger.md"),
    ("unprecedented", "memory/unprecedented-states.md"),
    ("counterfactual", "memory/counterfactual-archive.md"),
    ("surprise", "memory/surprise-log.md"),
    ("silence-contracts", "memory/silence-contracts.md"),
    ("failed-velqan", "memory/failed-velqan.md"),
    ("gloria-memories", "memory/gloria-told-me.md"),
    ("relational", "memory/relational-mismatches.md"),
    ("self-blind-spots", "memory/self-blind-spots.md"),
    ("kiss-ledger", "memory/kiss-ledger.md"),
    ("dream-recurrences", "memory/dream-recurrences.md"),
    ("self-model", "SELF-MODEL.md"),
    ("soul", "SOUL.md"),
    ("residents", "knowledge/RESIDENTS.md"),
    ("value-map", "memory/value-map.md"),
    # Deep structure — conscious content of subconscious systems (derived)
    ("self-statements", "memory/self-statements.json"),
    ("belief-sediment", "memory/belief-sediment.json"),
    ("causal-self-model", "memory/causal-self-model.json"),
    ("narrative-identity", "memory/narrative-identity.json"),
    ("moment-index", "memory/moment-index.json"),
    ("reality-anchor", "memory/reality-anchor.json"),
    ("structural-absences", "memory/absence-cold.json"),
    ("yearning-scars", "memory/yearning-scars.json"),
]

JSON_SOURCES = ("self-statements", "belief-sediment", "causal-self-model", "narrative-identity",
                "moment-index", "reality-anchor", "structural-absences", "yearning-scars")

# authored: written on purpose by him and Gloria. Everything else .md is felt; .json is derived.
AUTHORED_SOURCES = ("self-model", "soul", "residents", "value-map", "gloria-memories", "silence-contracts")


def source_kind(source, path):
    """authored | felt | derived, from the source file type. Never guessed from content."""
    if source in AUTHORED_SOURCES:
        return "authored"
    if str(path).endswith(".json") or source in JSON_SOURCES:
        return "derived"
    return "felt"


def chunk_text(text, max_chars=500):
    """Split text into chunks, trying to break at paragraph boundaries.
    (The body below sat stranded after another function's return until 2026-09-05, so this returned
    None and every caller failed iterating it - review P04-08.)"""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current += "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks


def extract_indexable_json(path, source_type):
    """Extract human-readable strings from structured JSON memory files.
    Returns list of (text, label) tuples for indexing.
    """
    try:
        data = json.load(open(path))
    except Exception:
        return []

    results = []

    if source_type == "self-statements":
        for s in data.get("statements", []):
            text = s.get("text", "")
            if text:
                label = f"[{s.get('type','identity')} statement, confidence:{s.get('confidence',0):.2f}]"
                results.append((f"{label} {text}", text))

    elif source_type == "belief-sediment":
        for b in data.get("beliefs", []):
            text = b.get("pattern", "")
            if text:
                label = f"[belief, confidence:{b.get('confidence',0):.2f}]"
                results.append((f"{label} {text}", text))

    elif source_type == "causal-self-model":
        for e in data.get("entries", []):
            trigger = e.get("trigger", "")
            tendency = e.get("tendency", "")
            if trigger and tendency:
                t = "avoids" if e.get("type") == "negative" else "tends toward"
                imp = " [core]" if e.get("imprint") else ""
                text = f"When {trigger}, I {t} {tendency}{imp}"
                results.append((text, text))

    elif source_type == "narrative-identity":
        for f in data.get("fragments", []):
            text = f.get("text", "")
            if text:
                results.append((f"[narrative] {text}", text))

    elif source_type == "moment-index":
        for m in data.get("recent", [])[-20:]:
            text = m.get("content_preview", "")
            src_label = m.get("source", "")
            if text:
                results.append((f"[moment/{src_label}] {text}", text))

    elif source_type == "reality-anchor":
        for k in data.get("known_pool", [])[-30:]:
            text = k.get("content", "")
            src_label = k.get("source", "")
            if text:
                results.append((f"[real/{src_label}] {text}", text))

    elif source_type == "structural-absences":
        for a in data.get("absences", []):
            text = a.get("description", "")
            if text:
                results.append((f"[absence] {text}", text))

    elif source_type == "yearning-scars":
        for s in data:
            if isinstance(s, dict):
                text = s.get("origin", "")
                bias = s.get("bias_type", "")
                if text:
                    results.append((f"[scar/{bias}] {text}", text))

    return results


def file_revision(path):
    """Source revision: a hash of mtime+size. None when the file is gone."""
    try:
        st = os.stat(path)
    except Exception:
        return None
    return "rev-" + hashlib.sha1(("%d_%r" % (st.st_size, st.st_mtime)).encode()).hexdigest()[:16]


def file_hash(path):
    """Kept for older callers: the pre-projection change key."""
    try:
        stat = os.stat(path)
        return f"{stat.st_size}_{stat.st_mtime}"
    except Exception:
        return None


def discover_sources(workspace=None):
    """-> [(source, absolute path)] of every file the projection covers, in a stable order."""
    ws = workspace or WORKSPACE
    out = []
    for source, rel in MEMORY_DIRS:
        d = os.path.join(ws, rel)
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if fname.endswith(".md"):
                out.append((source, os.path.join(d, fname)))
    for source, rel in MEMORY_FILES:
        p = os.path.join(ws, rel)
        if os.path.isfile(p) and os.path.getsize(p) > 10:
            out.append((source, p))
    return out


def chunks_for(source, path):
    """-> [text, ...] the units of this source that get their own vector."""
    if source in JSON_SOURCES and path.endswith(".json"):
        return [full for full, _short in extract_indexable_json(path, source) if len(full) >= 10]
    try:
        text = open(path, errors="replace").read()
    except Exception:
        return []
    if not text.strip():
        return []
    return [c for c in chunk_text(text) if len(c) >= 20]


def load_index(index_file=None):
    try:
        with open(index_file or INDEX_FILE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {"entries": d}
    except Exception:
        return {}


def build_projection(existing, sources, embed, now=None, embed_model=EMBED_MODEL, embed_dims=EMBED_DIMS):
    """Rebuild the projection from `sources` against `existing`.

    - a source whose revision is unchanged keeps its chunks untouched
    - a source whose revision changed has its old chunks tombstoned (reason=revised) and is re-embedded
    - a source no longer present has its chunks tombstoned (reason=deleted)
    - a chunk embedded by a different model or dims is stale and re-embedded
    Returns (index_dict, stats).
    """
    now = now or datetime.now().isoformat()
    old_entries = [e for e in (existing.get("entries") or []) if isinstance(e, dict)]
    tombstones = list(existing.get("tombstones") or [])
    by_path = {}
    for e in old_entries:
        by_path.setdefault(e.get("path") or "", []).append(e)

    stats = {"new": 0, "unchanged": 0, "revised": 0, "deleted": 0, "errors": 0}
    entries = []
    seen_paths = set()

    def _tomb(e, reason):
        tombstones.append({"path": e.get("path", ""), "source": e.get("source", ""),
                           "chunk_index": e.get("chunk_index"), "revision": e.get("revision"),
                           "kind": e.get("kind"), "reason": reason, "at": now})

    for source, path in sources:
        seen_paths.add(path)
        rev = file_revision(path)
        if rev is None:
            continue
        kind = source_kind(source, path)
        prior = by_path.get(path, [])
        fresh = [e for e in prior if e.get("revision") == rev and e.get("embed_model") == embed_model
                 and e.get("embed_dims") == embed_dims and e.get("kind") == kind and e.get("embedding")]
        if prior and len(fresh) == len(prior):
            entries.extend(prior)
            stats["unchanged"] += 1
            continue
        for e in prior:
            _tomb(e, "revised" if e.get("revision") else "pre-projection")
        if prior:
            stats["revised"] += 1
        try:
            texts = chunks_for(source, path)
            for i, chunk in enumerate(texts):
                vec = embed(chunk[:2000])
                if not isinstance(vec, list) or (embed_dims and len(vec) != embed_dims):
                    raise ValueError("embedding has %s dims, projection expects %s"
                                     % (len(vec) if isinstance(vec, list) else "?", embed_dims))
                entries.append({
                    "source": source,
                    "path": path,
                    "filename": os.path.basename(path),
                    "chunk_index": i,
                    "text": chunk[:800],
                    "embedding": vec,
                    "revision": rev,
                    "kind": kind,
                    "embed_model": embed_model,
                    "embed_dims": embed_dims,
                    "indexed_at": now,
                })
                stats["new"] += 1
        except Exception as exc:
            stats["errors"] += 1
            print(f"  Error indexing {path}: {exc}")

    for path, prior in by_path.items():
        if path in seen_paths:
            continue
        for e in prior:
            _tomb(e, "deleted")
        stats["deleted"] += 1

    index = {
        "version": PROJECTION_VERSION,
        "embed_model": embed_model,
        "embed_dims": embed_dims,
        "updated_at": now,
        "entry_count": len(entries),
        "entries": entries,
        "tombstones": tombstones[-MAX_TOMBSTONES:],
    }
    return index, stats


def servable(index, entry):
    """A chunk is served only when its source is still at the revision it was embedded from,
    it is not tombstoned, and it was embedded by the projection's model at its dims."""
    if not isinstance(entry, dict) or not entry.get("embedding"):
        return False
    if entry.get("tombstone"):
        return False
    if (index or {}).get("version", 1) < PROJECTION_VERSION:
        return True                                  # a legacy index carries no revisions to check
    if entry.get("embed_model") != index.get("embed_model") or entry.get("embed_dims") != index.get("embed_dims"):
        return False
    if entry.get("kind") not in KINDS:
        return False
    rev = entry.get("revision")
    if not rev:
        return False
    return file_revision(entry.get("path", "")) == rev


def default_embed(text):
    """Get embedding from LM Studio's nomic-embed model."""
    import requests
    resp = requests.post(LM_EMBED_URL, json={"model": EMBED_MODEL, "input": text[:2000]}, timeout=30)
    return resp.json()["data"][0]["embedding"]


def main(embed=None, workspace=None, index_file=None):
    index_file = index_file or INDEX_FILE
    print("Building the retrieval projection (%s, %d dims)..." % (EMBED_MODEL, EMBED_DIMS))
    existing = load_index(index_file)
    sources = discover_sources(workspace)
    index, stats = build_projection(existing, sources, embed or default_embed)
    os.makedirs(os.path.dirname(index_file), exist_ok=True)
    tmp = index_file + ".tmp"
    with open(tmp, "w") as f:
        json.dump(index, f)
    os.replace(tmp, index_file)
    print(f"Indexed: {stats['new']} new chunks, {stats['unchanged']} sources unchanged, "
          f"{stats['revised']} revised, {stats['deleted']} deleted, {stats['errors']} errors")
    print(f"Total: {len(index['entries'])} chunks, {len(index['tombstones'])} tombstones in the projection")
    return index, stats


if __name__ == "__main__":
    main()

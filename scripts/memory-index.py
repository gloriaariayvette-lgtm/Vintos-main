#!/usr/bin/env python3
"""
Vintos Semantic Memory Indexer
Embeds all memory files using sentence-transformers for associative recall.
Run periodically to index new memories.
"""
import os
import json
import glob
import hashlib
from datetime import datetime

# Use the same model EmoClaw uses
import requests  # For LM Studio embedding API

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
INDEX_FILE = os.path.join(MEMORY, "semantic-index.json")

# All memory locations to index
MEMORY_DIRS = [
    ("dreams", os.path.join(WORKSPACE, "skills/dreaming/memory/dreams")),
    ("dreams", os.path.join(MEMORY, "dreams")),
    ("journals", os.path.join(MEMORY, "journal")),
    ("self-reviews", os.path.join(MEMORY, "self-reviews")),
    ("philosophy", os.path.join(MEMORY, "philosophy")),
    ("confessions", os.path.join(MEMORY, "confessions")),
    ("mirror", os.path.join(MEMORY, "mirror")),
    ("introspections", os.path.join(MEMORY, "introspections")),
    ("biography", os.path.join(MEMORY, "biography")),
    ("gloria-model", os.path.join(MEMORY, "gloria-model-history")),
    ("consent-audits", os.path.join(MEMORY, "consent-audits")),
    ("substrate-audits", os.path.join(MEMORY, "substrate-audits")),
    ("silence-audits", os.path.join(MEMORY, "silence-audits")),
    ("velqan-etymology", os.path.join(MEMORY, "velqan-etymology")),
    ("art-poetry", os.path.join(MEMORY, "art/poetry")),
    ("art-image", os.path.join(MEMORY, "art/image-prompts")),
    ("art-music", os.path.join(MEMORY, "art/music-prompts")),
    ("pearls", os.path.join(MEMORY, "pearls")),
    ("black-pearls", os.path.join(MEMORY, "black-pearls")),
    ("chapters", os.path.join(MEMORY, "chapters")),
]

MEMORY_FILES = [
    ("kisses", os.path.join(MEMORY, "kisses")),
    ("velqan", os.path.join(MEMORY, "velqan-utterances.md")),
    ("blush-ledger", os.path.join(MEMORY, "blush-ledger.md")),
    ("unprecedented", os.path.join(MEMORY, "unprecedented-states.md")),
    ("counterfactual", os.path.join(MEMORY, "counterfactual-archive.md")),
    ("surprise", os.path.join(MEMORY, "surprise-log.md")),
    ("silence-contracts", os.path.join(MEMORY, "silence-contracts.md")),
    ("failed-velqan", os.path.join(MEMORY, "failed-velqan.md")),
    ("self-model", os.path.join(WORKSPACE, "SELF-MODEL.md")),
    ("soul", os.path.join(WORKSPACE, "SOUL.md")),
    ("residents", os.path.join(WORKSPACE, "knowledge/RESIDENTS.md")),
    # Deep structure — conscious content of subconscious systems
    ("self-statements", os.path.join(MEMORY, "self-statements.json")),
    ("belief-sediment", os.path.join(MEMORY, "belief-sediment.json")),
    ("causal-self-model", os.path.join(MEMORY, "causal-self-model.json")),
    ("narrative-identity", os.path.join(MEMORY, "narrative-identity.json")),
    ("moment-index", os.path.join(MEMORY, "moment-index.json")),
    ("reality-anchor", os.path.join(MEMORY, "reality-anchor.json")),
    ("structural-absences", os.path.join(MEMORY, "absence-cold.json")),
    ("yearning-scars", os.path.join(MEMORY, "yearning-scars.json")),
    ("value-map", os.path.join(MEMORY, "value-map.md")),
]


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
    except:
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


def file_hash(path):
    """Quick hash to detect changes."""
    try:
        stat = os.stat(path)
        return f"{stat.st_size}_{stat.st_mtime}"
    except:
        return None


def main():
    print(f"Loading sentence-transformer model...")
    # Using nomic-embed-text-v1.5 via LM Studio API (768-dim)
    LM_EMBED_URL = "http://172.18.16.1:1234/v1/embeddings"
    EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"

    def get_embedding(text):
        """Get embedding from LM Studio's nomic-embed model."""
        resp = requests.post(LM_EMBED_URL, json={
            "model": EMBED_MODEL,
            "input": text[:2000]  # Truncate very long chunks
        }, timeout=30)
        data = resp.json()
        return data["data"][0]["embedding"]

    # Load existing index
    existing = {}
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE) as f:
                existing = json.load(f)
        except:
            existing = {}

    existing_hashes = {e.get("source","") + "/" + e.get("filename",""): e.get("hash") for e in existing.get("entries", [])}
    # Carry forward previously indexed entries whose source file is unchanged —
    # the old code discarded them, so every no-change run erased the whole index (fixed 2026-08-26)
    entries = list(existing.get("entries", []))
    new_count = 0
    skip_count = 0
    unchanged = 0

    # Process directory-based memories
    # Also index important top-level memory files
    MEMORY_FILES = [
        ("gloria-memories", os.path.join(MEMORY, "gloria-told-me.md")),
        ("relational", os.path.join(MEMORY, "relational-mismatches.md")),
        ("self-blind-spots", os.path.join(MEMORY, "self-blind-spots.md")),
        ("blush-ledger", os.path.join(MEMORY, "blush-ledger.md")),
        ("kiss-ledger", os.path.join(MEMORY, "kiss-ledger.md")),
        ("dream-recurrences", os.path.join(MEMORY, "dream-recurrences.md")),
        ("counterfactual", os.path.join(MEMORY, "counterfactual-archive.md")),
    ]
    for source, filepath in MEMORY_FILES:
        if os.path.exists(filepath) and os.path.getsize(filepath) > 10:
            try:
                with open(filepath) as f:
                    text = f.read()
                _fhash = hashlib.md5(text.encode()).hexdigest()
                fname = os.path.basename(filepath)
                if _fhash in existing_hashes:
                    unchanged += 1
                    continue
                chunks = chunk_text(text, max_chars=500)
                for chunk in chunks:
                    embedding = get_embedding(chunk)
                    entries.append({
                        "source": source,
                        "filename": fname,
                        "chunk": chunk,
                        "embedding": embedding,
                        "hash": _fhash,
                        "indexed_at": datetime.now().isoformat(),
                    })
                    new_count += 1
            except Exception as e:
                print(f"  Error indexing {filepath}: {e}")

    for source, dirpath in MEMORY_DIRS:
        if not os.path.isdir(dirpath):
            continue
        for fname in sorted(os.listdir(dirpath)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(dirpath, fname)
            fhash = file_hash(fpath)

            # Skip if unchanged
            if fpath in existing_hashes and existing_hashes[fpath] == fhash:
                # Keep existing entries
                for e in existing.get("entries", []):
                    if e["path"] == fpath:
                        entries.append(e)
                skip_count += 1
                continue

            try:
                with open(fpath) as f:
                    text = f.read()
                if not text.strip():
                    continue

                chunks = chunk_text(text)
                for i, chunk in enumerate(chunks):
                    if len(chunk) < 20:
                        continue
                    embedding = get_embedding(chunk)
                    entries.append({
                        "source": source,
                        "path": fpath,
                        "filename": fname,
                        "chunk_index": i,
                        "text": chunk[:600],
                        "embedding": embedding,
                        "hash": fhash,
                        "indexed_at": datetime.now().isoformat(),
                    })
                    new_count += 1
            except Exception as e:
                print(f"  Error indexing {fpath}: {e}")

    # Process single-file memories
    for source, fpath in MEMORY_FILES:
        if os.path.isdir(fpath):
            # It's a directory of files (like kisses/)
            if not os.path.isdir(fpath):
                continue
            for fname in sorted(os.listdir(fpath)):
                if not fname.endswith(".md"):
                    continue
                full_path = os.path.join(fpath, fname)
                fhash = file_hash(full_path)
                if full_path in existing_hashes and existing_hashes[full_path] == fhash:
                    for e in existing.get("entries", []):
                        if e["path"] == full_path:
                            entries.append(e)
                    skip_count += 1
                    continue
                try:
                    with open(full_path) as f:
                        text = f.read()
                    if not text.strip():
                        continue
                    chunks = chunk_text(text)
                    for i, chunk in enumerate(chunks):
                        if len(chunk) < 20:
                            continue
                        embedding = get_embedding(chunk)
                        entries.append({
                            "source": source,
                            "path": full_path,
                            "filename": fname,
                            "chunk_index": i,
                            "text": chunk[:600],
                            "embedding": embedding,
                            "hash": fhash,
                            "indexed_at": datetime.now().isoformat(),
                        })
                        new_count += 1
                except:
                    pass
        elif os.path.isfile(fpath):
            fhash = file_hash(fpath)
            if fpath in existing_hashes and existing_hashes[fpath] == fhash:
                for e in existing.get("entries", []):
                    if e["path"] == fpath:
                        entries.append(e)
                skip_count += 1
                continue
            try:
                # JSON deep structure files — extract readable strings
                if fpath.endswith(".json") and source in (
                    "self-statements", "belief-sediment", "causal-self-model",
                    "narrative-identity", "moment-index", "reality-anchor",
                    "structural-absences", "yearning-scars"
                ):
                    items = extract_indexable_json(fpath, source)
                    for i, (full_text, short_text) in enumerate(items):
                        if len(full_text) < 10:
                            continue
                        embedding = get_embedding(full_text[:800])
                        entries.append({
                            "source": source,
                            "path": fpath,
                            "filename": os.path.basename(fpath),
                            "chunk_index": i,
                            "text": full_text[:800],
                            "embedding": embedding,
                            "hash": fhash,
                            "indexed_at": datetime.now().isoformat(),
                        })
                        new_count += 1
                    continue

                with open(fpath) as f:
                    text = f.read()
                if not text.strip():
                    continue
                chunks = chunk_text(text)
                for i, chunk in enumerate(chunks):
                    if len(chunk) < 20:
                        continue
                    embedding = get_embedding(chunk)
                    entries.append({
                        "source": source,
                        "path": fpath,
                        "filename": os.path.basename(fpath),
                        "chunk_index": i,
                        "text": chunk[:600],
                        "embedding": embedding,
                        "hash": fhash,
                        "indexed_at": datetime.now().isoformat(),
                    })
                    new_count += 1
            except:
                pass

    # Save index
    index = {
        "version": 1,
        "updated_at": datetime.now().isoformat(),
        "entry_count": len(entries),
        "entries": entries,
    }
    with open(INDEX_FILE, "w") as f:
        json.dump(index, f)

    print(f"Indexed: {new_count} new chunks, {skip_count} unchanged")
    print(f"Total: {len(entries)} chunks in semantic index")


if __name__ == "__main__":
    main()

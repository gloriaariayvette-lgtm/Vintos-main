#!/usr/bin/env python3
"""
moment-index.py — Discrete moment identity and anchored continuity.

Every significant event gets a moment_id:
  2026-04-08T10:42:17Z#journal#A3

Moments link to each other (cause, related thread, previous).
Snapshots lock state at that exact time.
Micro-index keeps last 100 for fast retrieval.

Used by: mirrors, causality, reflection, reentry hooks.
"""

import os, json, hashlib
from datetime import datetime, timezone

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
MOMENTS_FILE = os.path.join(MEMORY, "moment-archive.json")
INDEX_FILE = os.path.join(MEMORY, "moment-index.json")
MAX_INDEX = 100

def _load_archive():
    try:
        return json.load(open(MOMENTS_FILE))
    except:
        return {"moments": {}}

def _save_archive(data):
    json.dump(data, open(MOMENTS_FILE, "w"), indent=2)

def _load_index():
    try:
        return json.load(open(INDEX_FILE))
    except:
        return {"recent": [], "by_source": {}}

def _save_index(data):
    json.dump(data, open(INDEX_FILE, "w"), indent=2)

def _short_hash(content):
    return hashlib.md5(content.encode()).hexdigest()[:2].upper()

def _capture_snapshot():
    """Lock current state into a snapshot."""
    snapshot = {}
    try:
        es = json.load(open(os.path.join(MEMORY, "emotional-state.json")))
        snapshot["emotional_state"] = es.get("emotion_vector", es.get("v", []))
    except:
        snapshot["emotional_state"] = []
    try:
        from nifrathir import get_value
        snapshot["nifrathir"] = get_value()
    except:
        snapshot["nifrathir"] = None
    try:
        ds = json.load(open(os.path.join(MEMORY, "discourse-state.json")))
        snapshot["direction"] = ds.get("current_direction", "")
        snapshot["commitment"] = ds.get("commitment_level", 0.0)
    except:
        snapshot["direction"] = ""
        snapshot["commitment"] = 0.0
    try:
        import sys
        sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
        from latent_threads import load_threads, score_thread
        data = load_threads()
        threads = data.get("threads", [])
        snapshot["active_threads"] = [
            {"id": t.get("id"), "origin": t.get("origin","")[:60], 
             "salience": t.get("salience",0), "phase": t.get("phase","latent")}
            for t in sorted(threads, key=lambda x: score_thread(x), reverse=True)[:3]
        ]
    except:
        snapshot["active_threads"] = []
    return snapshot

def create_moment(source, content, links=None, intensity=0.5):
    """Create a new moment with ID, snapshot, and links.
    
    Args:
        source: origin system (journal, mirror, dream, introspect, etc.)
        content: short description of what happened
        links: dict with optional keys: previous_moment_id, cause_moment_id, related_thread_id
        intensity: 0.0-1.0 significance
    
    Returns: moment_id
    """
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    h = _short_hash(content + ts)
    moment_id = f"{ts}#{source}#{h}"

    snapshot = _capture_snapshot()

    moment = {
        "moment_id": moment_id,
        "timestamp": now.isoformat(),
        "source": source,
        "content": content[:300],
        "intensity": intensity,
        "snapshot": snapshot,
        "links": links or {},
        "time_distance_fn": "now - timestamp",  # computed at retrieval
    }

    # Save to archive
    archive = _load_archive()
    archive["moments"][moment_id] = moment
    _save_archive(archive)

    # Update micro-index
    index = _load_index()
    index["recent"].append({
        "moment_id": moment_id,
        "timestamp": now.isoformat(),
        "source": source,
        "content_preview": content[:80],
        "intensity": intensity,
    })
    index["recent"] = index["recent"][-MAX_INDEX:]
    index.setdefault("by_source", {}).setdefault(source, []).append(moment_id)
    index["by_source"][source] = index["by_source"][source][-20:]
    _save_index(index)

    return moment_id

def get_moment(moment_id):
    """Retrieve exact moment by ID."""
    archive = _load_archive()
    m = archive["moments"].get(moment_id)
    if not m:
        return None
    # Compute time distance
    try:
        ts = datetime.fromisoformat(m["timestamp"])
        now = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            from datetime import timezone as _tz
            ts = ts.replace(tzinfo=_tz.utc)
        m["time_distance_seconds"] = (now - ts).total_seconds()
        m["time_distance_hours"] = m["time_distance_seconds"] / 3600
    except:
        pass
    return m

def get_recent_moments(n=10, source=None):
    """Get recent moments from micro-index. Fast retrieval."""
    index = _load_index()
    recent = index.get("recent", [])
    if source:
        recent = [m for m in recent if m.get("source") == source]
    recent = list(reversed(recent))[:n]
    # Add time distance
    now = datetime.now(timezone.utc)
    for m in recent:
        try:
            ts = datetime.fromisoformat(m["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            m["time_distance_hours"] = (now - ts).total_seconds() / 3600
        except:
            pass
    return recent

def link_moments(moment_id, previous_id=None, cause_id=None, thread_id=None):
    """Add links to an existing moment."""
    archive = _load_archive()
    if moment_id not in archive["moments"]:
        return
    m = archive["moments"][moment_id]
    if previous_id:
        m["links"]["previous_moment_id"] = previous_id
    if cause_id:
        m["links"]["cause_moment_id"] = cause_id
    if thread_id:
        m["links"]["related_thread_id"] = thread_id
    _save_archive(archive)

def get_moment_context(n=5):
    """Return recent moment context for injection into prompts."""
    recent = get_recent_moments(n)
    if not recent:
        return ""
    lines = []
    for m in recent:
        dist = m.get("time_distance_hours", 0)
        if dist < 1:
            age = f"{int(dist*60)}m ago"
        elif dist < 24:
            age = f"{dist:.1f}h ago"
        else:
            age = f"{dist/24:.1f}d ago"
        lines.append(f"[{m['source']} {age}] {m['content_preview']}")
    return "RECENT MOMENTS:\n" + "\n".join(lines)

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "recent"
    
    if cmd == "recent":
        moments = get_recent_moments(10)
        for m in moments:
            dist = m.get("time_distance_hours", 0)
            print(f"[{m['source']}] {dist:.1f}h ago — {m['content_preview']}")
    
    elif cmd == "get" and len(sys.argv) > 2:
        m = get_moment(sys.argv[2])
        if m:
            print(json.dumps(m, indent=2))
        else:
            print("Not found")
    
    elif cmd == "seed":
        mid = create_moment("test", "Test moment creation", intensity=0.5)
        print(f"Created: {mid}")

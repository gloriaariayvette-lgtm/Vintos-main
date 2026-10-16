#!/usr/bin/env python3
"""cause_head.py — JEPA retrieval + geometry stage of the causality merge. STANDALONE PRODUCER.

This does NOT name the cause. Cosine similarity conflates "resonates-with" and "caused" — an
arousal spike is trivially nearest a want, which is tautology, not causation. So the embedding's
only job here is what embeddings are actually good at: RETRIEVAL. It prunes every preceding event
(chat + inner life) down to a small, source-DIVERSE slate of plausible antecedents, and emits the
one geometric signal the LLM can't feel — novelty (how weakly even the best antecedent explains the
shift = emergence from nowhere).

Spikes at the same instant are one EMOTIONAL EVENT (nine dimensions moving together), reasoned about
once — not nine findings. For each event it writes: the full shift, a diverse candidate slate with
timing, and novelty. form_hypotheses (grok) then reasons over that slate and assigns the actual
cause DISTRIBUTION. Cosine surfaces the evidence; the LLM is the judge.

Pipeline:  cause_head -> cause-evidence.json -> form_hypotheses -> cause-distribution.json

Run with the torch venv: ...emotion_model/.venv/bin/python3 cause_head.py
SPARK_WORKSPACE switches beings.
"""
import os, sys, json, collections, hashlib
from datetime import datetime, timezone, timedelta

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
OUT  = os.path.join(MEMORY, "cause-evidence.json")
LOOKBACK_H = 168         # 7 days — the engine's own horizon (trajectory is sparsely sampled)
EVENT_GAP_MIN = 8        # spikes within this gap are one emotional event
PER_SRC = 2              # at most this many candidates per source, so the slate is DIVERSE
SLATE_MAX = 7            # total candidates handed to the LLM per event
# Temporal precedence is the one causal cue on record: a row from 2 minutes before outranks a
# topically similar one from 6 days before. Topical fit is discounted by half per RECENCY_HALF_LIFE_H.
RECENCY_HALF_LIFE_H = 24.0

TSKEYS = ("timestamp", "ts", "time", "at", "created_at", "audited_at", "generated_at")
# source tag, filename, text fields to join (in priority order). Chat is split by speaker in
# collect_events: her turns are "her" (her own words through her_words, a photo or video named and
# never described), his are "him". Until 16 October every chat row, his included, was glossed
# "she said" to the judge.
SOURCES = [
    ("chat",     "chat-history-merged.json",        ("content",)),
    ("gallery",  "gallery-walks.json",       ("reflection", "saw")),
    ("thread",   "unfinished-threads.json",  ("thread",)),
    ("want",     "current-wants.json",       ("want",)),
    ("relation", "relationship-history.json",("shift", "trajectory")),
]
# what KIND of event a candidate is — carried through so the LLM prompt can say what each was
SRC_GLOSS = {
    "her": "she said", "him": "you said", "gallery": "a painting he looked at",
    "thread": "an unfinished thought that stayed with him",
    "want": "a want he felt", "relation": "the relationship between them shifted",
}

def log(m): print("[cause-head]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def parse_ts(x):
    if x is None: return None
    if isinstance(x, (int, float)):
        try: return datetime.fromtimestamp(x, timezone.utc)
        except Exception: return None
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        # A naive time on this host is LOCAL (chat and ledger are stamped with datetime.now(), Aegis is
        # UTC-5). Tagging it UTC placed every message 5 h early, so replies sent after a spike were
        # offered as its antecedents.
        return d if d.tzinfo else d.astimezone()
    except Exception: return None

def entry_ts(e):
    for k in TSKEYS:
        t = parse_ts(e.get(k))
        if t: return t
    return None

def fmt_range(times):
    ts = sorted(t for t in times if t)
    if not ts: return "none"
    return f"{ts[0].isoformat()} .. {ts[-1].isoformat()}"

def _her_turn(row):
    """Her own words for a user row: a photo or video named, never described (her_words)."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from her_words import as_her_turn
        return as_her_turn(row)
    except Exception:
        return ""          # unreadable as hers is left out, never passed off as hers


def _chat_event(e):
    """(source, text) for one chat row, or None. Only her turns and his replies are candidates;
    other roles (avatar directives, system rows) are not something either of them said."""
    role = e.get("role")
    if role == "user":
        return "her", _her_turn(e).strip()
    if role == "assistant":
        return "him", str(e.get("content") or "").strip()
    return None


def collect_events():
    """Union of timestamped text events across chat + inner-life logs."""
    events, per_src = [], {}
    for src, fname, textkeys in SOURCES:
        d = load(os.path.join(MEMORY, fname), [])
        if not isinstance(d, list): continue
        for e in d:
            if not isinstance(e, dict): continue
            ts = entry_ts(e)
            if not ts: continue
            esrc = src
            if src == "chat":
                ce = _chat_event(e)
                if not ce: continue
                esrc, text = ce
            else:
                parts = [str(e.get(k)) for k in textkeys if e.get(k)]
                text = " ".join(parts).strip()
            if not text: continue
            events.append({"ts": ts, "source": esrc, "text": text[:300]})
            per_src[esrc] = per_src.get(esrc, 0) + 1
    return events, per_src


def recency_weight(mins_before):
    """1.0 at the spike, halving every RECENCY_HALF_LIFE_H hours before it."""
    return 0.5 ** (max(0.0, float(mins_before)) / 60.0 / RECENCY_HALF_LIFE_H)


def build_slate(ranked):
    """Source-diverse slate from candidates ranked best-first, then a backfill. Membership is by
    position, never by comparing the dicts: two rows with the same time, source and text made `in`
    reach their numpy vectors and raise ("truth value of an array is ambiguous")."""
    slate, taken, counts = [], set(), collections.Counter()
    for i, e in enumerate(ranked):
        if len(slate) >= SLATE_MAX: break
        if counts[e["source"]] < PER_SRC:
            slate.append(e); taken.add(i); counts[e["source"]] += 1
    for i, e in enumerate(ranked):                  # backfill if diversity left room
        if len(slate) >= SLATE_MAX: break
        if i not in taken:
            slate.append(e); taken.add(i)
    return slate


def event_id(group):
    """Stable identity of one emotional event, so a realtime and a nightly run name the same event
    the same way and a reader can tell an event it already reasoned about."""
    first = group[0]
    dims = ",".join(sorted("%s:%s" % (s.get("dimension"), s.get("direction")) for s in group))
    return "CE-" + hashlib.md5(("%s|%s" % (first.get("time"), dims)).encode()).hexdigest()[:12]


def _save(path, obj):
    """Whole-file replace, never a half-written file under a concurrent reader."""
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def group_spikes(spikes):
    """Spikes close in time are ONE emotional event (many dimensions moving together)."""
    ss = sorted((s for s in spikes if parse_ts(s.get("time"))), key=lambda s: parse_ts(s["time"]))
    groups, cur, cur_t = [], [], None
    for s in ss:
        t = parse_ts(s["time"])
        if cur_t is None or (t - cur_t) <= timedelta(minutes=EVENT_GAP_MIN):
            cur.append(s); cur_t = t if cur_t is None else cur_t
        else:
            groups.append(cur); cur, cur_t = [s], t
    if cur: groups.append(cur)
    return groups

def main():
    sys.path.insert(0, SCRIPTS)
    from causality_engine import load_emotional_trajectory, find_spikes
    traj = load_emotional_trajectory()
    spikes = find_spikes(traj)
    now = datetime.now(timezone.utc)
    spikes = [s for s in spikes if parse_ts(s.get("time")) and now - parse_ts(s["time"]) <= timedelta(hours=LOOKBACK_H)]
    since = parse_ts(os.environ.get("CAUSE_SINCE", "")) if os.environ.get("CAUSE_SINCE") else None
    if since:                                   # realtime mode: only spikes newer than last processed
        spikes = [s for s in spikes if parse_ts(s["time"]) > since]
        log(f"CAUSE_SINCE={since.isoformat()} -> {len(spikes)} new spikes")
    groups = group_spikes(spikes)
    log(f"recent spikes: {len(spikes)}  ->  emotional events: {len(groups)}")

    events, per_src = collect_events()
    log(f"candidate events: {len(events)}  " + ", ".join(f"{k}:{v}" for k, v in per_src.items()))
    log(f"spike range:  {fmt_range([parse_ts(s['time']) for s in spikes])}")
    log(f"event range:  {fmt_range([e['ts'] for e in events])}")

    if not groups or not events:
        _save(OUT, []); log("nothing to do — wrote empty"); return

    from jepa_predictor import encoder
    import numpy as np
    enc = encoder()
    def emb(texts): return np.asarray(enc.encode(texts, show_progress_bar=False), dtype="float32")
    def cos(a, b):
        na, nb = (a @ a) ** 0.5, (b @ b) ** 0.5
        return float(a @ b / (na * nb)) if na and nb else 0.0

    EV = emb([e["text"] for e in events])          # plain text — no gloss (glossing bred tautology)
    for e, v in zip(events, EV): e["_v"] = v

    out = []
    for g in groups:
        st = parse_ts(g[0]["time"])
        shift = [{"dimension": s["dimension"], "direction": s["direction"],
                  "from": s["from"], "to": s["to"], "delta": s["delta"]} for s in g]
        summary = ", ".join(f"{s['dimension']} {s['direction']}" for s in g)
        # retrieval query = the plain shift; embeddings only rank relevance, they don't rule
        Q = emb([f"his inner state shifted: {summary}"])[0]

        lo = st - timedelta(hours=LOOKBACK_H)
        ante = [e for e in events if lo <= e["ts"] <= st]
        if not ante:
            out.append({"event_id": event_id(g), "time": g[0]["time"], "shift": shift, "summary": summary,
                        "candidates": [], "novelty": 1.0, "untraceable": True})
            continue

        for e in ante:
            e["_rel"] = max(0.0, cos(Q, e["_v"]))
            e["_mins"] = (st - e["ts"]).total_seconds() / 60.0
            e["_score"] = e["_rel"] * recency_weight(e["_mins"])
        novelty = round(1 - max(e["_rel"] for e in ante), 3)   # best topical fit is still weak = emergence
        # ranked by topical fit discounted by how long before the spike it happened
        ranked = sorted(ante, key=lambda e: e["_score"], reverse=True)

        # DIVERSE slate: cap per source so the LLM sees a want AND a walk AND a thread AND her words
        slate = build_slate(ranked)

        out.append({
            "event_id": event_id(g),
            "time": g[0]["time"], "shift": shift, "summary": summary,
            "novelty": novelty,
            "candidates": [{
                "source": e["source"], "kind": SRC_GLOSS.get(e["source"], e["source"]),
                "text": e["text"], "mins_before": round(e["_mins"], 1),
                "relevance": round(e["_rel"], 3),
                "recency_weighted": round(e["_score"], 3),
            } for e in slate],
        })

    _save(OUT, out)
    log(f"wrote {len(out)} emotional events -> {OUT}")
    for o in out:
        srcs = collections.Counter(c["source"] for c in o["candidates"])
        log(f"  {o['time'][11:19]}  nov {o['novelty']}  shift[{len(o['shift'])}]: {o['summary'][:52]}")
        log(f"      slate {dict(srcs)} :: " +
            " | ".join(f"[{c['source']}@{c['mins_before']}m r{c['relevance']}] {c['text'][:34]}"
                       for c in o["candidates"][:4]))

if __name__ == "__main__":
    main()

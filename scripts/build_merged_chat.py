#!/usr/bin/env python3
"""build_merged_chat.py — rebuild chat-history-merged.json from the lossless record so
every reader of it (temporal-context, conversation-rhythm, gloria_prediction, the
withheld / relational / jepa heads, premonition-dreamer) sees the REAL conversation and
its real silences.

Source of truth, in order:

  - chat-canonical.jsonl   the lossless per-turn record. Both speakers, the real per-turn
                           time in `ts`, and the protections (generation_provenance, her
                           original_text) carried on the record. The newest turns.
  - interaction-ledger.json  the deeper history: her `gloria` and his `vintos` per turn,
                           with an ISO `timestamp`. The turns the canonical no longer holds.

It no longer reads chat-history.json. That file stopped being written in late August; merging
its stale rows beside the live turns manufactured a two-month silence that never happened —
conversation-rhythm read longest_silence_hours near 1207 — and every learner of the merged
file was fed that false gap. The voice history is empty and is dropped with it.

Lossless by construction: carry every protection field the source record had, take the real
per-turn time, and dedupe the canonical against the ledger by turn_id (then by content head)
so a turn held in both is counted once, the canonical copy winning.

Never worse than before: on any error the existing merged file is LEFT in place rather than
overwritten — a stale-but-real last build beats a freshly broken one, and nothing here can
reintroduce the August gap.
"""
import os, json
from datetime import datetime

MEM = os.path.expanduser("~/.vintos/workspace/memory")
canonical = os.path.join(MEM, "chat-canonical.jsonl")
ledger    = os.path.join(MEM, "interaction-ledger.json")
merged    = os.path.join(MEM, "chat-history-merged.json")

# Fields that must survive the merge or a protection silently stops applying.
CARRY = ("generation_provenance", "provenance", "may_witness", "turn_id",
         "capsule_commitment", "stratagem_id", "surface", "eligible",
         "admitted", "offered", "withheld", "tactical",
         # what she sent and what she herself said: without these a photo's description reads as her words
         # to every reader of the merged file (Chat's subconscious review, 16 October)
         "input_kind", "original_text")
# Where a per-turn time can legitimately live, in order of preference.
TIME_KEYS = ("timestamp", "ts", "time", "at", "created")


def load_json(p):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return []


def load_jsonl(p):
    out = []
    try:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return []
    return out


def pts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        pass
    try:                       # epoch seconds are a legitimate per-turn time too
        v = float(s)
        return v if v > 1e8 else 0.0
    except Exception:
        return 0.0


def entry(e, role, content, ts, source, estimated=False):
    """One merged record: the carried protections, then the merged view."""
    out = {k: e[k] for k in CARRY if isinstance(e, dict) and k in e}
    out.update({"role": role, "content": content, "timestamp": ts, "source": source})
    if estimated:
        out["timestamp_estimated"] = True
    return out


def own_time(e):
    """(iso_or_empty, found). Never invents one. Normalises epoch seconds to ISO."""
    for k in TIME_KEYS:
        v = e.get(k)
        if v in (None, ""):
            continue
        if pts(v) > 0:
            try:
                return datetime.fromtimestamp(pts(v)).isoformat(), True
            except Exception:
                return str(v), True
    return "", False


def build():
    out = []
    seen_turns = set()     # turn_ids already taken from the canonical
    seen_content = {}      # content head -> canonical times (a ledger line is the same turn only near one)

    def _taken(turn_id, *texts, ts=""):
        if turn_id:
            seen_turns.add(str(turn_id))
        for t in texts:
            if t:
                seen_content.setdefault(str(t)[:80], []).append(pts(ts))

    # 1) the canonical — the lossless, newest turns. A row without a real per-turn time
    #    cannot anchor silence math, so it is dropped rather than guessed.
    for e in load_jsonl(canonical):
        if not isinstance(e, dict):
            continue
        content = e.get("content", "")
        if not content:
            continue
        ts, found = own_time(e)
        if not found:
            continue
        out.append(entry(e, e.get("role", "user"), str(content), ts, "canonical"))
        _taken(e.get("turn_id"), content, ts=ts)

    def _held(text, ts):
        """The canonical already has this line within ten minutes. The same words on another day are
        another turn: "good morning" twice is two mornings."""
        t = pts(ts)
        return any(abs(t - c) <= 600 for c in seen_content.get(str(text)[:80], ()))

    # 2) the ledger — the deeper history. Skip any turn or line the canonical already holds,
    #    and the historical '--source' / 'voice' placeholder junk.
    for e in load_json(ledger):
        if not isinstance(e, dict):
            continue
        tid = str(e.get("turn_id") or "")
        if tid and tid in seen_turns:
            continue
        ts = str(e.get("timestamp") or "").strip()
        if not ts:
            ts, _ = own_time(e)
        g, v = e.get("gloria"), e.get("vintos")
        if g and g != "--source" and not _held(g, ts):
            out.append(entry(e, "user", str(g), ts, "ledger"))
        if v and v != "voice" and not _held(v, ts):
            out.append(entry(e, "assistant", str(v), ts, "ledger"))

    out = [e for e in out if pts(e.get("timestamp")) > 0]
    out.sort(key=lambda e: pts(e["timestamp"]))
    return out


def main():
    out = build()
    if not out:
        raise ValueError("empty")
    tmp = merged + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f)
    os.replace(tmp, merged)    # atomic: a concurrent reader sees the old file or the new, never a half-written one


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass    # leave the last good merged file untouched; never clobber it with a guess

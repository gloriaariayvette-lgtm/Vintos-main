#!/usr/bin/env python3
"""self_model_evidence.py — the weekly self-model's evidence, collected by testable functions.

Until 2026-09-05 the collectors were inline bash/python one-liners in self-model-update.sh with
`2>/dev/null || echo ""`: an empty week, a missing file and a crashed collector all read as "".
Each collector here returns {status, source_ids, text}: status is one of present / empty / missing
/ failed, and source_ids name what the text came from. New material is selected against a
committed WATERMARK (memory/.self-model-evidence-watermark, an ISO timestamp advanced only after a
successful write), with older context clearly labeled (astra-models-p1 / astra-models-p2).

Corrections and supersessions are also recorded here as their own ledger
(memory/self-model-corrections.jsonl) so consumers retrieve them instead of relying on prefixes
in the document (astra-models-p3).

CLI:
  self_model_evidence.py section NAME        -> the rendered text for the update prompt
  self_model_evidence.py status              -> JSON of every collector's status
  self_model_evidence.py gate                -> exit 0 if anything is present, 1 if nothing new
  self_model_evidence.py commit              -> advance the watermark to now (after a successful write)
  self_model_evidence.py record-corrections  -> append this week's corrections to the corrections ledger
"""
import os, sys, json, glob
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
WATERMARK = os.path.join(MEM, ".self-model-evidence-watermark")
CORRECTIONS_LEDGER = os.path.join(MEM, "self-model-corrections.jsonl")

def _watermark():
    try:
        v = open(WATERMARK).read().strip()
        return datetime.fromisoformat(v) if v else None
    except Exception:
        return None

def _res(status, ids=None, text="", note=""):
    return {"status": status, "source_ids": ids or [], "text": text, "note": note}

def _newer(path, wm):
    try:
        return wm is None or datetime.fromtimestamp(os.path.getmtime(path)) > wm
    except Exception:
        return False

def introspections():
    d = os.path.join(MEM, "introspections")
    if not os.path.isdir(d): return _res("missing", note=d)
    wm = _watermark()
    try:
        files = sorted(f for f in glob.glob(os.path.join(d, "*.md")) if _newer(f, wm))
    except Exception as e:
        return _res("failed", note=str(e)[:200])
    if not files: return _res("empty", note="no introspection newer than the watermark")
    parts, ids = [], []
    for f in files:
        try:
            parts.append(open(f, errors="replace").read()); ids.append("introspection:" + os.path.basename(f))
        except Exception as e:
            parts.append("[unreadable: %s]" % os.path.basename(f))
    return _res("present", ids, "\n\n---\n\n".join(parts))

def self_review():
    files = sorted(glob.glob(os.path.join(MEM, "self-reviews", "self-review-*.md")), key=os.path.getmtime)
    if not files: return _res("missing" if not os.path.isdir(os.path.join(MEM, "self-reviews")) else "empty")
    f = files[-1]; wm = _watermark()
    try:
        txt = "\n".join(open(f, errors="replace").read().splitlines()[:80])
    except Exception as e:
        return _res("failed", note=str(e)[:200])
    if not _newer(f, wm):
        return _res("present", ["self-review:" + os.path.basename(f)], "(OLDER than this week's watermark - context, not new material)\n" + txt, note="older than watermark")
    return _res("present", ["self-review:" + os.path.basename(f)], txt)

def architectural_changes():
    p = os.path.join(MEM, "self-review-change-events.jsonl")
    if not os.path.exists(p): return _res("missing", note=p)
    wm = _watermark()
    rows, ids, lines = [], [], []
    try:
        for x in open(p, errors="replace"):
            try:
                if x.strip(): rows.append(json.loads(x))
            except Exception: pass
    except Exception as e:
        return _res("failed", note=str(e)[:200])
    for x in rows[-40:]:
        at = str(x.get("at", ""))
        try:
            if wm is not None and at and datetime.fromisoformat(at.replace("Z", "+00:00")).replace(tzinfo=None) <= wm: continue
        except Exception:
            pass
        ids.append(x.get("change_id") or x.get("build_id") or at)
        lines.append("- %s | files: %s%s" % (x.get("observation", "architectural change"), ", ".join(x.get("files", [])),
                                             (" | why: " + str(x.get("why"))[:120]) if x.get("why") else ""))
    if not lines: return _res("empty", note="no change event newer than the watermark")
    return _res("present", ids, "\n".join(lines[-12:]))

def corrections():
    p = os.path.join(MEM, "wal-log.json")
    if not os.path.exists(p): return _res("missing", note=p)
    try:
        d = json.load(open(p)); entries = d if isinstance(d, list) else d.get("entries", [])
    except Exception as e:
        return _res("failed", note=str(e)[:200])
    wm = _watermark(); ids, lines = [], []
    for e in entries:
        if str(e.get("type", "")).lower() != "correction" and "CORRECTION" not in json.dumps(e).upper(): continue
        ts = str(e.get("timestamp", ""))
        try:
            if wm is not None and ts and datetime.fromisoformat(ts) <= wm: continue
        except Exception:
            pass
        ids.append("wal:" + ts); lines.append("- " + str(e.get("content") or e.get("fact") or e)[:180])
    if not lines: return _res("empty", note="no correction newer than the watermark")
    return _res("present", ids, "\n".join(lines[-20:]))

COLLECTORS = {"introspections": introspections, "self_review": self_review,
              "architectural_changes": architectural_changes, "corrections": corrections}

def status():
    out = {}
    for k, fn in COLLECTORS.items():
        try:
            r = fn(); out[k] = {"status": r["status"], "n": len(r["source_ids"]), "note": r.get("note", "")}
        except Exception as e:
            out[k] = {"status": "failed", "n": 0, "note": str(e)[:200]}
    out["watermark"] = (_watermark().isoformat() if _watermark() else None)
    return out

def anything_new():
    st = status()
    return any(v.get("status") == "present" and not str(v.get("note", "")).startswith("older") for k, v in st.items() if k != "watermark")

def commit():
    os.makedirs(MEM, exist_ok=True)
    open(WATERMARK, "w").write(datetime.now().isoformat())

def record_corrections(entry_date=None):
    """Corrections applied this week become explicit records: what she corrected, from where, and
    which dated entry carried it — a supersession the readers can retrieve (astra-models-p3)."""
    r = corrections()
    if r["status"] != "present": return 0
    n = 0
    with open(CORRECTIONS_LEDGER, "a") as f:
        for sid, line in zip(r["source_ids"], r["text"].splitlines()):
            f.write(json.dumps({"at": datetime.now().isoformat(), "entry_date": entry_date or datetime.now().date().isoformat(),
                                "source_id": sid, "correction": line.lstrip("- ")[:300], "kind": "gloria_correction",
                                "supersedes": "the self-model's own account where they disagree"}) + "\n"); n += 1
    return n

def corrections_view(limit=12):
    """The effective corrections, newest first, for any consumer that wants the authority record."""
    try:
        rows = [json.loads(l) for l in open(CORRECTIONS_LEDGER) if l.strip()]
    except Exception:
        return []
    return rows[-limit:][::-1]

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "section" and len(sys.argv) > 2:
        r = COLLECTORS[sys.argv[2]]()
        print(r["text"] if r["status"] == "present" else "")
    elif cmd == "status":
        print(json.dumps(status(), indent=1))
    elif cmd == "gate":
        sys.exit(0 if anything_new() else 1)
    elif cmd == "commit":
        commit(); print("watermark", open(WATERMARK).read())
    elif cmd == "record-corrections":
        print(record_corrections(sys.argv[2] if len(sys.argv) > 2 else None), "correction(s) recorded")
    elif cmd == "corrections":
        print(json.dumps(corrections_view(), indent=1))
    else:
        print(__doc__)

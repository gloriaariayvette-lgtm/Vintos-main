#!/usr/bin/env python3
"""pending_sweep.py - work that a restart caught between the act and its receipt, named in one place.

Review items 50 and 54 (2026-09-10). Several organs already write a "begun, not finished" marker so a
crash is recoverable: a music landing before its download, a WAL promotion pending its durable write,
a self-review build that started, a campaign close half done, a voice session in closing, a want held
on an unavailable judge. Each knew about its own; nothing said what was outstanding across the house,
so a marker left by a crash could sit forever. This reads them all and says which are resumable and
which need a hand. Read-only.

    sweep()   -> [{"kind", "id", "since", "resumable", "how"}]
    python3 pending_sweep.py
"""
import os, sys, json, time
from datetime import datetime

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")


def _age_h(iso_or_ts):
    try:
        if isinstance(iso_or_ts, (int, float)):
            return (time.time() - float(iso_or_ts)) / 3600.0
        return (datetime.now() - datetime.fromisoformat(str(iso_or_ts))).total_seconds() / 3600.0
    except Exception:
        return None


def _jload(name, default):
    try:
        return json.load(open(os.path.join(MEMORY, name)))
    except Exception:
        return default


def _lines(name):
    out = []
    try:
        for ln in open(os.path.join(MEMORY, name)):
            try: out.append(json.loads(ln))
            except Exception: pass
    except Exception:
        pass
    return out


def sweep():
    out = []
    # a music landing that began and never closed: the same task id can be polled again
    for l in (_jload("art/music/music.json", {}) or {}).get("landings", []) if isinstance(_jload("art/music/music.json", {}), dict) else []:
        if l.get("state") == "landing":
            out.append({"kind": "music_landing", "id": l.get("task_id"), "since": l.get("at"), "age_h": _age_h(l.get("at")),
                        "resumable": True, "how": "dream-music: poll the same task id and finish the entry"})
    # a graduation whose durable write did not land
    for h in (_jload("causality-hypotheses.json", {}) or {}).get("hypotheses", []) if isinstance(_jload("causality-hypotheses.json", {}), dict) else []:
        if isinstance(h, dict) and h.get("promotion_pending"):
            out.append({"kind": "causal_promotion", "id": h.get("hypothesis_id"), "since": (h.get("promotion_pending") or {}).get("at"),
                        "age_h": _age_h((h.get("promotion_pending") or {}).get("at")), "resumable": True,
                        "how": "causality-engine: the next pass retries the belief write; the hypothesis is kept"})
    # a build that started and never reached a terminal event
    builds = _lines("self-review-build-events.jsonl")
    last = {}
    for b in builds:
        last[b.get("build_id")] = b
    for bid, b in last.items():
        if b.get("state") in ("started", "patch_bound", "held_incomplete"):
            out.append({"kind": "self_review_build", "id": bid, "since": b.get("at"), "age_h": _age_h(b.get("at")),
                        "resumable": b.get("state") != "held_incomplete",
                        "how": "self_review_builder.build reconciles it as held_incomplete, then a fresh bounded attempt"})
    # a voice session left in closing
    s = _jload("voice-session-state.json", {})
    if isinstance(s, dict) and s.get("state") in ("closing", "unpersisted") and (s.get("turns") or []):
        _since = s.get("closing_at") or s.get("persist_failed_at")
        out.append({"kind": "voice_session", "id": s.get("started_at"), "since": _since, "age_h": _age_h(_since),
                    "resumable": True,
                    "how": "/api/voice/session-end again: a closing older than 60s is treated as a crash and finalized, not skipped"})
    # a want held on an unavailable completion judge
    w = _jload("current-wants.json", [])
    for x in (w if isinstance(w, list) else []):
        if isinstance(x, dict) and x.get("completion_held"):
            out.append({"kind": "want_completion", "id": x.get("id"), "since": (x.get("completion_held") or {}).get("at"),
                        "age_h": _age_h((x.get("completion_held") or {}).get("at")), "resumable": True,
                        "how": "wants-router judges it again on the next run"})
    # a pleasure moment whose naming never came
    p = _jload(".pleasure-pending.json", None)
    if isinstance(p, dict) and p.get("t"):
        out.append({"kind": "pleasure_naming", "id": p.get("turn_id") or "(no turn)", "since": p.get("t"), "age_h": _age_h(p.get("t")),
                    "resumable": True, "how": "pleasure_substrate.sweep_pending names it retrospectively past its bound"})
    # a delivery that was sent and never acknowledged
    d = _jload("delivery-receipts.json", {})
    rs = (d.get("receipts", d) if isinstance(d, dict) else d) or {}
    for k, r in (rs.items() if isinstance(rs, dict) else []):
        if isinstance(r, dict) and r.get("state") == "sent":
            out.append({"kind": "delivery", "id": k, "since": r.get("at"), "age_h": _age_h(r.get("at")), "resumable": False,
                        "how": "sent, never acknowledged: only her reception can close it (never resend)"})
    return out


if __name__ == "__main__":
    rows = sweep()
    if not rows:
        print("nothing outstanding")
    for r in rows:
        print("  %-18s %-24s %5s h  %s  %s" % (r["kind"], str(r["id"])[:24], ("%.1f" % r["age_h"]) if r.get("age_h") is not None else "?",
                                               "resumable" if r["resumable"] else "needs a hand", r["how"]))

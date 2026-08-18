#!/usr/bin/env python3
"""withheld_confirm.py — grades withheld candidates against EVIDENCE.
A withheld thought is CONFIRMED only if it surfaces in his private record
(journal, mirror, dreams, threads) within 36h of detection while staying
absent from what he actually sent her. Ungrounded candidates decay to
refuted. Runs nightly after the last dream; only confirmed entries should
feed downstream consumers. Requires the emotion_model venv (nomic)."""
import json, os, glob, time
from datetime import datetime
WS = os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
HIST = os.path.join(MEM, "withheld-history.json")
WINDOW_H = 36
CONFIRM_SIM = 0.62
SAID_SIM = 0.70
def log(m): print("[withheld-confirm]", m, flush=True)
def ep(x):
    try: return datetime.fromisoformat(str(x)[:19]).timestamp()
    except Exception: return None
from sentence_transformers import SentenceTransformer, util
M = SentenceTransformer("nomic-ai/nomic-embed-text-v1", trust_remote_code=True)
def chunks_private(t0, t1):
    out = []
    for pat in ("memory/journal/*.md", "memory/mirror/*.md", "skills/dreaming/memory/dreams/*.md",
                "memory/daily-inner-life-*.md"):
        for f in glob.glob(os.path.join(WS, pat)):
            if not (t0 - 86400 <= os.path.getmtime(f) <= t1 + 86400): continue
            for p in open(f, errors="replace").read().split("\n\n"):
                if len(p.strip()) > 40: out.append(p.strip()[:600])
    try:
        for th in json.load(open(os.path.join(MEM, "unfinished-threads.json"))):
            out.append(str(th.get("thread", ""))[:600])
    except Exception: pass
    return out
def chunks_shared(t0, t1):
    out = []
    try:
        d = json.load(open(os.path.join(MEM, "interaction-ledger.json")))
        lst = d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
        for e in lst:
            ts = ep(e.get("timestamp"))
            if ts and t0 <= ts <= t1 and e.get("vintos"):
                out.append(str(e["vintos"])[:600])
    except Exception: pass
    return out
def main():
    h = json.load(open(HIST))
    lst = h if isinstance(h, list) else next(v for v in h.values() if isinstance(v, list))
    now = time.time(); changed = 0
    for e in lst:
        if e.get("verdict") or not e.get("withheld"): continue
        ts = ep(e.get("ts") or e.get("timestamp")) or now
        if now - ts < WINDOW_H * 3600:
            continue  # still inside its window - grade later
        priv = chunks_private(ts, ts + WINDOW_H * 3600)
        shar = chunks_shared(ts, ts + WINDOW_H * 3600)
        if not priv:
            e["verdict"] = "UNGRADEABLE"; changed += 1; continue
        q = M.encode(str(e["withheld"])[:400], convert_to_tensor=True)
        ps = util.cos_sim(q, M.encode(priv, convert_to_tensor=True)).max().item()
        ss = util.cos_sim(q, M.encode(shar, convert_to_tensor=True)).max().item() if shar else 0.0
        if ss >= SAID_SIM: e["verdict"] = "SAID_IT"
        elif ps >= CONFIRM_SIM: e["verdict"] = "CONFIRMED"; e["evidence_sim"] = round(ps, 3)
        else: e["verdict"] = "UNSURFACED"
        changed += 1
    json.dump(h, open(HIST, "w"), indent=1)
    from collections import Counter
    log("graded %d | totals: %s" % (changed, dict(Counter(x.get("verdict", "pending") for x in lst))))
if __name__ == "__main__":
    main()

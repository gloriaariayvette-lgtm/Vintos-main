#!/usr/bin/env python3
"""correction_propagate.py - her correction reaches everything that was derived from the claim.

Review item 384 (2026-09-10). A hallucination correction already annotates the WAL fact it names. The
projections built FROM that fact - durable memories, sediment beliefs, causal self-model entries - kept
serving the old reading. Now one call marks each of them invalidated by the correction (the record is
never deleted: the old reading stays beside the correction, standing "invalidated"), and writes one
propagation record naming what it touched, so a later reader can see the correction's reach.

    propagate(correction_id, original, correction, at="") -> {"touched": [...], "record": path}
    python3 correction_propagate.py HC-1234 "the old claim" "what is true"
"""
import os, re, sys, json, time

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
FLOOR = 0.5   # share of the claim's words a projection must carry to be derived from it


def _words(s):
    return set(w for w in re.findall(r"[a-z0-9']+", str(s or "").lower()) if len(w) > 3)


def _overlap(claim, text):
    A = _words(claim)
    return len(A & _words(text)) / float(len(A) or 1)


def _load(name, default):
    try:
        return json.load(open(os.path.join(MEMORY, name)))
    except Exception:
        return default


def _save(name, obj):
    p = os.path.join(MEMORY, name); tmp = p + ".tmp"
    json.dump(obj, open(tmp, "w"), indent=2); os.replace(tmp, p)


def _mark(rec, correction_id, correction, at):
    rec.setdefault("invalidated_by", []).append({"correction_id": correction_id, "correction": str(correction)[:300], "at": at})
    rec["standing"] = "invalidated"
    return rec


def propagate(correction_id, original, correction, at=""):
    at = at or time.strftime("%Y-%m-%dT%H:%M:%S")
    touched = []
    # durable memories whose event or extracted content came from the claim
    dm = _load("durable-memory.json", [])
    n = 0
    for r in dm if isinstance(dm, list) else []:
        if isinstance(r, dict) and max(_overlap(original, r.get("event")), _overlap(original, r.get("what_changed"))) >= FLOOR:
            _mark(r, correction_id, correction, at); n += 1
            touched.append({"projection": "durable-memory", "key": r.get("occurred_at"), "was": str(r.get("event", ""))[:160]})
    if n: _save("durable-memory.json", dm)
    # sediment beliefs whose pattern restates the claim
    bs = _load("belief-sediment.json", {"beliefs": []})
    n = 0
    for b in (bs.get("beliefs", []) if isinstance(bs, dict) else []):
        if isinstance(b, dict) and _overlap(original, b.get("pattern")) >= FLOOR:
            _mark(b, correction_id, correction, at); b["confidence"] = min(float(b.get("confidence", 0) or 0), 0.05); n += 1
            touched.append({"projection": "belief-sediment", "key": b.get("pattern", "")[:80], "was": str(b.get("pattern", ""))[:160]})
    if n: _save("belief-sediment.json", bs)
    # causal self-model entries resting on the claim (their quote or tendency)
    cm = _load("causal-self-model.json", {"entries": []})
    n = 0
    for e in (cm.get("entries", []) if isinstance(cm, dict) else []):
        if not isinstance(e, dict):
            continue
        quotes = " ".join(str(x.get("quote", "")) for x in e.get("evidence", []) if isinstance(x, dict))
        if max(_overlap(original, e.get("tendency")), _overlap(original, e.get("trigger")), _overlap(original, quotes)) >= FLOOR:
            _mark(e, correction_id, correction, at); e["imprint"] = False; n += 1
            touched.append({"projection": "causal-self-model", "key": e.get("tendency", "")[:80], "was": str(e.get("tendency", ""))[:160]})
    if n: _save("causal-self-model.json", cm)
    # pearls (graduated durable claims as files): a pearl restating the claim gets a correction footer, never a rewrite
    pdir = os.path.join(MEMORY, "pearls")
    try:
        for f in sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []:
            if not f.endswith(".md"):
                continue
            p = os.path.join(pdir, f)
            try:
                txt = open(p).read()
            except Exception:
                continue
            body = txt.split("\n---\n", 1)[0]
            if _overlap(original, body) >= FLOOR and ("**Corrected:** " + correction_id) not in txt:
                with open(p, "a") as fh:
                    fh.write("**Corrected:** %s (%s) - %s\n" % (correction_id, at, str(correction)[:300]))
                touched.append({"projection": "pearl", "key": f, "was": body.strip().splitlines()[-1][:160] if body.strip() else ""})
    except Exception:
        pass
    rec = {"correction_id": correction_id, "at": at, "original": str(original)[:400], "correction": str(correction)[:400], "touched": touched}
    os.makedirs(MEMORY, exist_ok=True)
    with open(os.path.join(MEMORY, "correction-propagation.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
    return {"touched": touched, "record": os.path.join(MEMORY, "correction-propagation.jsonl")}


def is_invalidated(rec):
    return isinstance(rec, dict) and rec.get("standing") == "invalidated"


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(1)
    print(json.dumps(propagate(sys.argv[1], sys.argv[2], " ".join(sys.argv[3:])), indent=1))

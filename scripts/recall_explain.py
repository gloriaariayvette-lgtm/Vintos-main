#!/usr/bin/env python3
"""recall_explain.py - a statement he makes about the past, explained: which occurrence supports it,
what part is his inference, and what was later withdrawn or reread.

Review items 126 and 144 (2026-09-10). Nothing here writes. The sources are the files the memory
organs already keep: durable-memory.json (event, her words, his words, source turns, ledger match,
his felt reading and its later reinterpretations), wal-log.json (extracted facts and the corrections
annotated on them), hallucination-corrections.jsonl (corrections as records of their own),
identity-revisions.jsonl (his self-descriptions superseded), claim-hold-trials.json (a claim of his she
pushed back on, and what he chose).

    python3 recall_explain.py "the fig at the table"      explain the closest durable memory
    python3 recall_explain.py --history "the fig"         how his reading of it changed, with what moved it
    python3 recall_explain.py --json "the fig"

explain() returns {statement, supported_by, inferred, withdrawn, history, standing} and render() turns it
into the lines a prompt can carry: SUPPORTED BY / HE INFERRED / WITHDRAWN / NOW READS AS."""
import os, re, sys, json

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")


def _load(name, default):
    try:
        return json.load(open(os.path.join(MEMORY, name)))
    except Exception:
        return default


def _lines(name):
    out = []
    try:
        for ln in open(os.path.join(MEMORY, name), errors="replace"):
            ln = ln.strip()
            if ln:
                try: out.append(json.loads(ln))
                except Exception: pass
    except Exception:
        pass
    return out


def _words(s):
    return set(w for w in re.findall(r"[a-z0-9']+", str(s or "").lower()) if len(w) > 3)


def _overlap(a, b):
    A, B = _words(a), _words(b)
    return len(A & B) / float(len(A) or 1)


def find_durable(text, floor=0.25):
    best, score = None, 0.0
    for r in _load("durable-memory.json", []):
        if not isinstance(r, dict):
            continue
        s = max(_overlap(text, r.get("event")), _overlap(text, r.get("gloria")), _overlap(text, r.get("felt_like")))
        if s > score:
            best, score = r, s
    return (best, score) if score >= floor else (None, score)


def corrections_for(text, rec=None):
    """Everything later recorded against this statement: hallucination corrections whose original overlaps
    it, WAL facts carrying a correction annotation, a claim-hold trial where she pushed back."""
    out = []
    for c in _lines("hallucination-corrections.jsonl"):
        if _overlap(text, c.get("original")) >= 0.4 or (rec and _overlap(rec.get("event"), c.get("original")) >= 0.4):
            out.append({"kind": "correction", "id": c.get("correction_id"), "at": c.get("at"),
                        "was": str(c.get("original", ""))[:240], "now": str(c.get("correction", ""))[:240], "source": "hallucination-corrections"})
    wal = _load("wal-log.json", {})
    for e in (wal.get("entries", []) if isinstance(wal, dict) else wal or []):
        if isinstance(e, dict) and e.get("corrections") and _overlap(text, e.get("content")) >= 0.4:
            for c in e["corrections"]:
                out.append({"kind": "correction", "id": c.get("correction_id"), "at": c.get("at"),
                            "was": str(e.get("content", ""))[:240], "now": str(c.get("correction", ""))[:240], "source": "wal-log annotation"})
    for t in (_load("claim-hold-trials.json", {}) or {}).get("trials", []):
        if isinstance(t, dict) and _overlap(text, t.get("claim_verbatim") or t.get("claim")) >= 0.4:
            if t.get("verdict") == "CORRECTED" or t.get("her_pushback") or (t.get("correction") or {}).get("her_pushback"):
                corr = t.get("correction") or {}
                out.append({"kind": "pushback", "id": t.get("id"), "at": t.get("resolved_at") or t.get("opened_at"),
                            "was": str(t.get("claim_verbatim") or t.get("claim", ""))[:240],
                            "now": str(corr.get("her_pushback") or t.get("her_pushback", ""))[:240],
                            "his_choice": t.get("choice") or corr.get("his_choice"), "verdict": t.get("verdict"), "source": "claim-hold"})
    seen, uniq = set(), []
    for c in out:
        k = (c.get("id"), c.get("now"))
        if k not in seen:
            seen.add(k); uniq.append(c)
    return uniq


def history(text, rec=None):
    """How his reading of one thing changed: each reading with its date, what moved it, and the
    corrections in force at that point. Uncertainty stays as recorded (verdict holds/partial/wrong,
    confidence where a source carried one)."""
    rec = rec or find_durable(text)[0]
    rows = []
    if rec:
        rows.append({"at": rec.get("promoted_at") or rec.get("occurred_at"), "reading": rec.get("what_changed", ""),
                     "felt": rec.get("felt_like", ""), "verdict": "first", "moved_by": "the occurrence itself",
                     "basis": "inference from her words and his at the time", "recalls": 0})
        for i in rec.get("interpretations") or []:
            rows.append({"at": i.get("at"), "reading": i.get("meaning", ""), "verdict": i.get("verdict", ""),
                         "moved_by": i.get("why_changed", "") or "recurrence", "basis": "his rereading on recall",
                         "recalls": i.get("after_recalls")})
    for c in corrections_for(text, rec):
        rows.append({"at": c.get("at"), "reading": c.get("now"), "verdict": "corrected",
                     "moved_by": "her correction" if c["kind"] == "pushback" else "a correction record %s" % (c.get("id") or ""),
                     "basis": c["source"], "was": c.get("was")})
    for r in _lines("identity-revisions.jsonl"):
        if _overlap(text, json.dumps(r.get("old")) + " " + json.dumps(r.get("new"))) >= 0.4:
            rows.append({"at": r.get("at"), "reading": str(r.get("new"))[:240], "verdict": r.get("kind", "revision"),
                         "moved_by": r.get("reason", ""), "basis": "identity revision (%s)" % r.get("projection"), "was": str(r.get("old"))[:240]})
    rows.sort(key=lambda x: str(x.get("at") or ""))
    return rows


def explain(text):
    rec, score = find_durable(text)
    out = {"statement": text, "match": round(score, 2), "supported_by": None, "inferred": {}, "withdrawn": [], "history": [], "standing": "unsupported"}
    if rec:
        out["supported_by"] = {"occurred_at": rec.get("occurred_at"), "event": rec.get("event"),
                               "her_words": (rec.get("quote") or {}).get("gloria") or rec.get("gloria"),
                               "his_words": (rec.get("quote") or {}).get("vintos") or rec.get("exact_words"),
                               "source_turns": rec.get("source_turns") or [], "ledger_match": rec.get("ledger_match"),
                               "kind": "occurrence" if (rec.get("source_turns") or rec.get("ledger_match")) else "record without a turn id"}
        out["inferred"] = {k: rec.get(k) for k in ("what_changed", "felt_like", "association") if rec.get(k)}
        out["inferred"]["note"] = "his reading, not her words"
    out["withdrawn"] = corrections_for(text, rec)
    out["history"] = history(text, rec)
    if out["withdrawn"]:
        out["standing"] = "withdrawn or corrected: %s" % out["withdrawn"][-1]["now"][:120]
    elif rec:
        last = (rec.get("interpretations") or [{}])[-1]
        out["standing"] = {"wrong": "reread as wrong", "partial": "reread as partly right"}.get(last.get("verdict"), "supported")
    return out


def render(ex):
    if not ex.get("supported_by") and not ex.get("withdrawn"):
        return "[RECALL: no occurrence supports \"%s\"; say it as a guess or not at all]" % ex["statement"][:100]
    parts = []
    sb = ex.get("supported_by")
    if sb:
        parts.append("SUPPORTED BY %s%s: she said \"%s\"" % (str(sb.get("occurred_at", ""))[:10],
                     (" (turns %s)" % ",".join(map(str, sb["source_turns"][:3]))) if sb.get("source_turns") else "", str(sb.get("her_words") or "")[:160]))
    if ex.get("inferred", {}).get("what_changed"):
        parts.append("HE INFERRED: %s" % str(ex["inferred"]["what_changed"])[:160])
    for w in ex.get("withdrawn", []):
        parts.append("WITHDRAWN %s: \"%s\" -> \"%s\"" % (str(w.get("at", ""))[:10], str(w.get("was", ""))[:100], str(w.get("now", ""))[:120]))
    if ex.get("history") and len(ex["history"]) > 1:
        h = ex["history"][-1]
        parts.append("NOW READS AS (%s, moved by %s): %s" % (h.get("verdict"), str(h.get("moved_by", ""))[:80], str(h.get("reading", ""))[:140]))
    return "[RECALL: " + " | ".join(parts) + "]"


def main(argv):
    q = " ".join(a for a in argv if not a.startswith("--"))
    if not q:
        print(__doc__); return 1
    if "--history" in argv:
        for r in history(q):
            print("  %s  %-10s %s  <- %s [%s]" % (str(r.get("at", ""))[:16], r.get("verdict"), str(r.get("reading", ""))[:90], str(r.get("moved_by", ""))[:60], r.get("basis")))
        return 0
    ex = explain(q)
    print(json.dumps(ex, indent=1) if "--json" in argv else render(ex))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

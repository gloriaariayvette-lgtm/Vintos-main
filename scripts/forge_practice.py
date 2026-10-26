#!/usr/bin/env python3
"""forge_practice.py — whether a hand the Forge built became part of how he works.

    reach -> gap -> proposal -> her card -> build -> verify -> install -> resume -> PRACTICE

Installation, permission to invoke, resumption and rollback all exist. None of them says
whether the need behind the tool was met, or whether he ever reaches for it again. This
keeps the receipts that can: each time an installed forged skill runs, one line records
who chose it and why, what went in and what came out (as hashes and fingerprints, never
the text), and later passes join that output against what he did next.

WHAT COUNTS

  ordinary     his own plan or want chose the tool during his own work. Only this is
               evidence that the tool earned a place.
  canary       someone made it run: Gloria's approve-this-use button, a want a person
               routed by hand. It proves the tool runs; it is not acceptance.
  unattributed a call that did not say where it came from. Shown, never counted.

  Downstream use is the output turning up again later: in a LATER step of the same want
  (the step that called the tool writes its own note from the output, so that one is
  never counted), in another want's step, or as the input to a later forged call. A
  self-call that goes nowhere is not usefulness, and being chosen often is not success.

WHAT IT NEVER DOES

  It never retires, mutes, gates or denies a tool. A tool with no ordinary use has had
  no opportunity yet as far as these receipts know; rare legitimate uses are still uses.
  It changes no Forge card and calls no model. It writes one append-only file.

    python3 forge_practice.py evidence [capability]   one tool's evidence, or every installed one
"""
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
STORE = os.path.join(MEMORY, "forge-practice.jsonl")
WANTS = os.path.join(MEMORY, "current-wants.json")

CHOOSERS = ("ordinary", "canary", "unattributed")
SHINGLE = 8          # words per fingerprint window
MARKS = 24           # fingerprints kept per output: the smallest hashes, so any copy shares them


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ts(value):
    """Epoch seconds. Receipts are UTC; step history is written in local time without a zone."""
    try:
        return datetime.fromisoformat(str(value)).astimezone().timestamp()
    except (TypeError, ValueError):
        return None


def _sha(text):
    return hashlib.sha256(str(text if text is not None else "").encode("utf-8", "replace")).hexdigest()


def _words(text):
    return re.findall(r"\w+", str(text or "").lower())


def _shingles(words, k):
    if k <= 0 or len(words) < k:
        return set()
    return {hashlib.sha1(" ".join(words[i:i + k]).encode()).hexdigest()[:12] for i in range(len(words) - k + 1)}


def marks(text):
    """(k, fingerprints) of an output: hashed k-word windows, the MARKS smallest. Short outputs use one window
    the length of the whole thing. Nothing of the text itself is kept."""
    w = _words(text)
    k = min(SHINGLE, len(w))
    return k, sorted(_shingles(w, k))[:MARKS]


def carries(text, k, fingerprints):
    """Does this text carry the output those fingerprints came from? One shared window is enough."""
    return bool(fingerprints) and bool(_shingles(_words(text), k) & set(fingerprints))


def selection(want=None, step=None, chooser="unattributed"):
    """The needs-to-tool trace: the want and the step that reached for the tool. A want a person routed by
    hand is a canary whatever the caller said."""
    want = want if isinstance(want, dict) else {}
    chooser = chooser if chooser in CHOOSERS else "unattributed"
    if want.get("manually_routed") and chooser == "ordinary":
        chooser = "canary"
    out = {"chooser": chooser}
    if want:
        out.update(want_id=str(want.get("id") or "")[:40], want=str(want.get("want") or "")[:200],
                   source=str(want.get("source") or "")[:60])
    if isinstance(step, int) and not isinstance(step, bool):
        steps = want.get("steps") if isinstance(want.get("steps"), list) else []
        cur = steps[step] if 0 <= step < len(steps) and isinstance(steps[step], dict) else {}
        out.update(step=step, step_note=str(cur.get("note") or "")[:200],
                   planned=str(cur.get("capability") or "")[:60])
    return out


def load(path=None):
    out = []
    try:
        with open(path or STORE) as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        out.append(row)
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def record(proposal, capability, note, output=None, error=None, chooser="unattributed", want=None, step=None):
    """One receipt for one run of an installed forged skill. Never raises: a receipt that cannot be written
    must not take the tool away from him."""
    try:
        sel = selection(want, step, chooser)
        prior = load()
        reuses = [r["id"] for r in prior
                  if r.get("result") == "ok" and r.get("output_marks")
                  and carries(note, int(r.get("output_k") or SHINGLE), r["output_marks"])][-8:]
        k, fp = marks(output) if output is not None else (0, [])
        row = {"id": "FU-" + uuid.uuid4().hex[:8], "at": _now(), "capability": str(capability)[:80],
               "proposal": str((proposal or {}).get("id") or "")[:40],
               "artifact_sha256": str(((proposal or {}).get("verification") or {}).get("sha256") or "")[:64],
               "chooser": sel["chooser"], "selection": sel,
               "input_sha256": _sha(note), "input_words": len(_words(note)),
               "result": "error" if error is not None else "ok"}
        if error is not None:
            row["error"] = type(error).__name__
        else:
            row.update(output_sha256=_sha(output), output_chars=len(str(output or "")), output_k=k, output_marks=fp)
        if reuses:
            row["reuses"] = reuses
        os.makedirs(os.path.dirname(STORE), exist_ok=True)
        with open(STORE, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        return row
    except Exception:
        return None


def _wants(wants=None):
    if wants is not None:
        return wants if isinstance(wants, list) else []
    try:
        d = json.load(open(WANTS))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def downstream(receipt, wants=None, receipts=None):
    """Where this run's output turned up later. The step that ran the tool is never counted."""
    out = {"carried_into": [], "reused_by": [], "want_state": "unknown"}
    if receipt.get("result") != "ok" or not receipt.get("output_marks"):
        return out
    k, fp = int(receipt.get("output_k") or SHINGLE), receipt["output_marks"]
    sel = receipt.get("selection") or {}
    wid, at = sel.get("want_id"), _ts(receipt.get("at"))
    ustep = sel.get("step")
    for w in _wants(wants):
        if not isinstance(w, dict):
            continue
        same = bool(wid) and w.get("id") == wid
        if same:
            out["want_state"] = ("fulfilled" if w.get("fulfilled") else "dismissed" if w.get("dismissed")
                                 else "blocked" if w.get("blocked") else "standing")
        for h in w.get("step_history") or []:
            if not isinstance(h, dict):
                continue
            if same:
                # the calling step writes its own note from the output; only a later step is downstream
                if not isinstance(ustep, int) or not isinstance(h.get("step"), int) or h["step"] <= ustep:
                    continue
            else:
                done = _ts(h.get("completed_at"))
                if done is None or (at is not None and done < at):
                    continue
            text = "%s\n%s" % (h.get("findings") or "", h.get("note") or "")
            if carries(text, k, fp):
                out["carried_into"].append({"want_id": str(w.get("id") or "")[:40], "step": h.get("step"),
                                            "capability": str(h.get("capability") or "")[:60]})
    if wid and out["want_state"] == "unknown":
        out["want_state"] = "gone"
    for r in receipts if receipts is not None else load():
        if receipt.get("id") in (r.get("reuses") or []):
            out["reused_by"].append(r.get("id"))
    return out


def _installed(capability=None):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import skill_forge
        rows = skill_forge._load()
    except Exception:
        rows = []
    return [r for r in rows if r.get("state") in ("installed", "resumed")
            and (capability is None or r.get("capability") == capability)]


def built_for(proposal):
    o = (proposal or {}).get("origin") or {}
    return str(o.get("want") or o.get("intent_verbatim") or (proposal or {}).get("why") or "")[:200]


def evidence(capability, proposals=None, wants=None, receipts=None):
    """One tool's evidence for a ten-minute read: the need it was built for, who chose it, and what came of it."""
    props = [p for p in (proposals if proposals is not None else _installed(capability))
             if p.get("capability") == capability]
    p = props[-1] if props else {}
    rows = [r for r in (receipts if receipts is not None else load()) if r.get("capability") == capability]
    allr = receipts if receipts is not None else load()
    wants = _wants(wants)
    by = {c: [r for r in rows if r.get("chooser") == c] for c in CHOOSERS}
    uses = []
    for r in by["ordinary"]:
        d = downstream(r, wants, allr)
        sel = r.get("selection") or {}
        uses.append({"id": r.get("id"), "at": r.get("at"), "result": r.get("result"),
                     "want_id": sel.get("want_id", ""), "want": sel.get("want", ""), "step": sel.get("step"),
                     "carried": len(d["carried_into"]) + len(d["reused_by"]), "want_state": d["want_state"]})
    ok = [u for u in uses if u["result"] == "ok"]
    useful = [u for u in ok if u["carried"]]
    origin_want = ((p.get("origin") or {}).get("want_id") or "")
    origin_state = next(("fulfilled" if w.get("fulfilled") else "dismissed" if w.get("dismissed") else "standing"
                         for w in wants if isinstance(w, dict) and origin_want and w.get("id") == origin_want),
                        "gone" if origin_want else "not a want")
    if not uses:
        verdict = ("no ordinary use yet: he has not reached for it in his own work. That is not evidence "
                   "against it; an occasion may not have come.")
    elif not useful:
        verdict = ("he chose it %d time(s) in his own work; nothing later carried its output yet." % len(uses))
    else:
        verdict = ("he chose it %d time(s) in his own work; %d of those outputs were carried into what he did next."
                   % (len(uses), len(useful)))
    return {"capability": capability, "proposal": p.get("id", ""), "built_for": built_for(p),
            "origin_want_state": origin_state,
            "ordinary": len(uses), "ordinary_ok": len(ok), "carried": len(useful),
            "canary": len(by["canary"]), "unattributed": len(by["unattributed"]),
            "uses": uses[-12:], "verdict": verdict,
            "retire": False}     # never: rare legitimate uses are uses


def affordance(capability, proposals=None, receipts=None):
    """One source-grounded example for his inventory line, only while he has never chosen the tool himself:
    the need it was built for, from its own proposal. Once he has used it, the name is enough."""
    rows = receipts if receipts is not None else load()
    if any(r.get("capability") == capability and r.get("chooser") == "ordinary" for r in rows):
        return ""
    props = [p for p in (proposals if proposals is not None else _installed(capability))
             if p.get("capability") == capability]
    need = built_for(props[-1]) if props else ""
    return ("built for: " + need[:120]) if need else ""


def report(ev):
    lines = ["%s (%s)" % (ev["capability"], ev["proposal"] or "no installed card"),
             "  built for: %s" % (ev["built_for"] or "(not recorded)"),
             "  that want is now: %s" % ev["origin_want_state"],
             "  chosen in his own work: %d (ran clean %d, output carried later %d)"
             % (ev["ordinary"], ev["ordinary_ok"], ev["carried"]),
             "  made to run (canary, not acceptance): %d; unattributed: %d" % (ev["canary"], ev["unattributed"]),
             "  " + ev["verdict"]]
    for u in ev["uses"]:
        lines.append("    %s %s %s step=%s carried=%d want:%s  %s" % (
            u["id"], str(u["at"])[:16], u["result"], u["step"], u["carried"], u["want_state"], u["want"][:70]))
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "evidence":
        print(__doc__)
        return 0
    caps = argv[1:] or sorted({r.get("capability") for r in _installed()} - {None})
    if not caps:
        print("no installed forged skills")
    for c in caps:
        print(report(evidence(c)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""hypothesis_ledger.py — no admission policy changes without a written, falsifiable
hypothesis first (Q1 lab, stage 4).

Sol, 2026-08-27: the lab's learning denominator is never "48 turns" — it is the
number of turns on which a block was known eligible AND known to have offered.
Presence rates are diagnostic evidence; they are not fitness scores. And the
reviewer is never the generator: this script computes arithmetic, it never rules.

The ledger holds hypotheses about his prompt admission:

    propose   write one down: claim, block, surface, epoch start, kill criteria.
              Until it exists here, the idea has no standing and changes nothing.
    evaluate  mechanical count over turn-record.jsonl — denominator, admissions,
              states — scoped to the hypothesis's epoch. Excludes observatory_health
              rows (a severed turn is an instrumentation event, never evidence).
              Prints numbers. Draws no conclusion.
    rule      a named reviewer enters the verdict by hand: supported | killed |
              withdrawn, with a reason. The script will not rule for you.

Nothing in this file changes his prompt. A supported hypothesis earns a
conversation, not an automatic edit.

    memory/hypothesis-ledger.jsonl   one line per event (proposed / evaluated / ruled),
                                     append-only: the history of a hypothesis is
                                     part of the hypothesis.
"""
import os, sys, json, hashlib
from datetime import datetime

WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY = os.path.join(WORKSPACE, "memory")
LEDGER = os.path.join(MEMORY, "hypothesis-ledger.jsonl")
TURNS = os.path.join(MEMORY, "turn-record.jsonl")

# states that make a turn part of the legal denominator: the organ was known
# eligible and known to have offered. Everything else (no_material, no_offer_info,
# producer_error, compiled) is outside the denominator, each for its own reason.
OFFERED_STATES = {"admitted", "offered_not_admitted"}


def _events():
    try:
        return [json.loads(l) for l in open(LEDGER) if l.strip()]
    except FileNotFoundError:
        return []


def _state(hid=None):
    """Current view: last proposal + latest ruling per hypothesis."""
    hyps = {}
    for e in _events():
        h = hyps.setdefault(e["id"], {"id": e["id"], "status": "open"})
        if e["event"] == "proposed":
            h.update(e); h["status"] = "open"
        elif e["event"] == "ruled":
            h["status"] = e["verdict"]; h["ruled_by"] = e["by"]
            h["ruling_reason"] = e["reason"]; h["ruled_at"] = e["at"]
        elif e["event"] == "evaluated":
            h["last_evaluated"] = e["at"]; h["last_numbers"] = e["numbers"]
        elif e["event"] == "preregistered":
            h["contract_sha256"] = e["contract_sha256"]
        elif e["event"] == "armed":
            h["armed_at"] = e["at"]; h["sealed_until"] = e["sealed_until"]
    return hyps.get(hid) if hid else hyps


def _append(ev):
    os.makedirs(MEMORY, exist_ok=True)
    ev["at"] = datetime.now().isoformat()
    with open(LEDGER, "a") as f:
        f.write(json.dumps(ev) + "\n")
    return ev


def propose(claim, block, surface, epoch_start, kill, by, producer_version=None):
    hid = "H-" + hashlib.md5((claim + epoch_start).encode()).hexdigest()[:6]
    if _state(hid):
        print(f"{hid} already exists — a hypothesis is proposed once; evaluate or rule it")
        return hid
    _append({"event": "proposed", "id": hid, "claim": claim, "block": block,
             "surface": surface, "epoch_start": epoch_start, "kill_criteria": kill,
             "producer_version": producer_version, "by": by})
    print(f"{hid} proposed by {by}")
    print(f"  claim: {claim}")
    print(f"  killed if: {kill}")
    return hid


def evaluate(hid):
    h = _state(hid)
    if not h:
        print(f"no such hypothesis: {hid}"); return
    if h.get("sealed_until") and datetime.now().isoformat() < h["sealed_until"]:
        print(f"{hid} SEALED until {h['sealed_until'][:10]} — operational health only:")
        try:
            rows = [json.loads(l) for l in open(TURNS) if l.strip()]
        except FileNotFoundError:
            rows = []
        post = [r for r in rows if r.get("at", "") >= h.get("armed_at", h["epoch_start"])]
        print(f"  turns recorded since arming: {len(post)}")
        print(f"  observatory_health rows: {sum(1 for r in post if r.get('observatory_health'))}")
        print("  assignment-specific aggregates stay sealed; an early open voids the epoch")
        return
    n = {"turns_on_surface": 0, "denominator": 0, "admitted": 0,
         "offered_not_admitted": 0, "no_material": 0, "no_offer_info": 0,
         "producer_error": 0, "compiled": 0, "excluded_observatory_health": 0,
         "excluded_producer_version": 0}
    try:
        rows = [json.loads(l) for l in open(TURNS) if l.strip()]
    except FileNotFoundError:
        rows = []
    for r in rows:
        if r.get("at", "") < h["epoch_start"]:
            continue
        if h["surface"] not in ("*", r.get("surface")):
            continue
        if r.get("observatory_health"):
            n["excluded_observatory_health"] += 1
            continue
        pv = h.get("producer_version")
        if pv and r.get("producer_versions", {}).get(h["block"]) not in (None, pv):
            n["excluded_producer_version"] += 1
            continue
        n["turns_on_surface"] += 1
        st = r.get("block_state", {}).get(h["block"], "no_offer_info")
        n[st] = n.get(st, 0) + 1
        if st in OFFERED_STATES:
            n["denominator"] += 1
            if st == "admitted":
                n["admitted"] += 1
    _append({"event": "evaluated", "id": hid, "numbers": n})
    print(f"{hid}  {h['claim']}")
    print(f"  epoch >= {h['epoch_start']}, surface {h['surface']}, block {h['block']}")
    for k, v in n.items():
        if v:
            print(f"  {k}: {v}")
    if n["denominator"]:
        print(f"  admitted/denominator: {n['admitted']}/{n['denominator']}  (diagnostic, not fitness)")
    else:
        print("  denominator is 0 — legally unlearnable so far; nothing here supports or kills anything")
    print("  no verdict — a reviewer rules, this script counts")
    return n


def preregister(hid, contract_path, by):
    """Sol's arming gate: an immutable contract, hashed, before anything can wake.
    Any substantive edit is a NEW hypothesis and epoch — the hash makes that law."""
    h = _state(hid)
    if not h:
        print(f"no such hypothesis: {hid}"); return
    if h.get("armed_at"):
        print(f"{hid} already armed — a running trial cannot be amended; propose anew"); return
    contract = json.load(open(contract_path))
    required = ["hypothesis", "null_and_rival_explanations", "proposer", "scope",
                "intervention", "decision_contract", "exclusions", "sampling",
                "analysis", "stopping", "governance"]
    missing = [k for k in required if k not in contract]
    if missing:
        print(f"contract incomplete, missing: {', '.join(missing)} — nothing preregistered"); return
    blob = json.dumps(contract, sort_keys=True, separators=(",", ":"))
    sha = hashlib.sha256(blob.encode()).hexdigest()
    _append({"event": "preregistered", "id": hid, "contract": contract,
             "contract_sha256": sha, "by": by})
    print(f"{hid} preregistered by {by}\n  sha256: {sha}\n  the question can no longer change after seeing the answer")


def preflight(hid, results_path, by):
    """The armer's mechanical checks, recorded. Any failed or missing check
    keeps the hypothesis un-armable; a bad check is never quietly a control."""
    h = _state(hid)
    if not h:
        print(f"no such hypothesis: {hid}"); return
    checks = json.load(open(results_path))
    failed = sorted(k for k, v in checks.items() if v is not True)
    _append({"event": "preflight", "id": hid, "checks": checks,
             "passed": not failed, "by": by})
    if failed:
        print(f"{hid} preflight FAILED: {', '.join(failed)} — cannot arm")
    else:
        print(f"{hid} preflight passed ({len(checks)} checks) by {by}")


def arm(hid, by, sealed_days=21):
    """Wakes nothing by itself — the flag file stays a human act — but records
    the legal arming: preregistered contract, passed preflight, independent armer,
    and the sealed_until date before which no aggregate may be looked at."""
    h = _state(hid)
    if not h:
        print(f"no such hypothesis: {hid}"); return
    if by == h.get("by"):
        print(f"refused: {by} proposed {hid} and cannot arm it — independent armer required"); return
    events = [e for e in _events() if e["id"] == hid]
    if not any(e["event"] == "preregistered" for e in events):
        print(f"{hid} has no preregistered contract — nothing to arm"); return
    pf = [e for e in events if e["event"] == "preflight"]
    if not (pf and pf[-1]["passed"]):
        print(f"{hid} latest preflight missing or failed — cannot arm"); return
    from datetime import timedelta
    sealed_until = (datetime.now() + timedelta(days=sealed_days)).isoformat()
    _append({"event": "armed", "id": hid, "by": by, "sealed_until": sealed_until})
    print(f"{hid} armed by {by}; results sealed until {sealed_until[:10]}")
    print("  (the trial itself wakes only when the flag file is touched — that too is a recorded human act)")


def rule(hid, verdict, by, reason):
    assert verdict in ("supported", "killed", "withdrawn", "held"), verdict
    h = _state(hid)
    if not h:
        print(f"no such hypothesis: {hid}"); return
    if h["status"] != "open":
        print(f"{hid} already ruled: {h['status']} — a ruling stands; propose anew for a new epoch")
        return
    if by == h.get("by") and verdict == "supported":
        print(f"refused: {by} proposed {hid} and cannot be the reviewer who supports it")
        return
    _append({"event": "ruled", "id": hid, "verdict": verdict, "by": by, "reason": reason})
    print(f"{hid} {verdict} by {by}: {reason}")


def _list():
    hyps = _state()
    if not hyps:
        print("ledger empty"); return
    for h in sorted(hyps.values(), key=lambda x: x.get("at", "")):
        line = f"{h['id']} [{h['status']:9}] {h.get('block','?')}/{h.get('surface','?')}  {h.get('claim','')[:80]}"
        print(line)
        if h.get("last_numbers", {}).get("denominator") is not None and h.get("last_evaluated"):
            ln = h["last_numbers"]
            print(f"          last eval {h['last_evaluated'][:16]}: admitted {ln.get('admitted',0)}/{ln.get('denominator',0)} of {ln.get('turns_on_surface',0)} turns")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "list":
        _list()
    elif a[0] == "propose" and len(a) == 8:
        propose(claim=a[1], block=a[2], surface=a[3], epoch_start=a[4], kill=a[5], by=a[6],
                producer_version=(a[7] or None))
    elif a[0] == "evaluate" and len(a) == 2:
        evaluate(a[1])
    elif a[0] == "rule" and len(a) == 5:
        rule(a[1], a[2], a[3], a[4])
    elif a[0] == "preregister" and len(a) == 4:
        preregister(a[1], a[2], a[3])
    elif a[0] == "preflight" and len(a) == 4:
        preflight(a[1], a[2], a[3])
    elif a[0] == "arm" and len(a) in (3, 4):
        arm(a[1], a[2], int(a[3]) if len(a) == 4 else 21)
    else:
        print("usage:\n  hypothesis_ledger.py list\n"
              "  hypothesis_ledger.py propose <claim> <block> <surface|*> <epoch_start ISO> <kill_criteria> <by> <producer_version|''>\n"
              "  hypothesis_ledger.py preregister <H-id> <contract.json> <by>\n"
              "  hypothesis_ledger.py preflight <H-id> <results.json> <by>\n"
              "  hypothesis_ledger.py arm <H-id> <by> [sealed_days]\n"
              "  hypothesis_ledger.py evaluate <H-id>\n"
              "  hypothesis_ledger.py rule <H-id> supported|killed|withdrawn|held <by> <reason>")

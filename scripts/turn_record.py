#!/usr/bin/env python3
"""turn_record.py — what actually reached him, on which surface, this turn.

His prompt is assembled at four separate roots, and blocks are appended by hand
at each one. Twice tonight a block was found reaching some surfaces and not
others, months after the fact, and only because someone went looking with grep.

This writes down what was in the prompt. It changes nothing, decides nothing,
and steers nothing. It is a record, so that "does he get X on Y" is a question
with an answer instead of an afternoon.

    turn-record.jsonl   one line per turn: surface, size, which blocks present,
                        how large each was, and what was absent.

It detects blocks by their own opening marker, so a block that silently stops
producing shows up as absent rather than as nothing at all.
"""
import os, json, time, hashlib
from datetime import datetime

try:
    import constitutional_tiers as _tiers
except Exception:
    _tiers = None  # the record must never fail the turn; tiers just go unlabeled

WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY = os.path.join(WORKSPACE, "memory")
RECORD = os.path.join(MEMORY, "turn-record.jsonl")
KEEP = 4000

# marker -> the name we know it by. Order irrelevant; all are checked.
MARKERS = {
    # verified against a real assembled prompt, 2026-08-20. A marker that is not
    # the literal opening of a block is a lie in table form: the first pass used
    # bare words like "SPARK" and "PRESSURE" and reported present/absent from
    # prose that happened to contain them.
    "[INTERACTION MODEL":                    "interaction_model_hint",
    "[WITHHELD":                             "withheld_head",
    "[Where I am choosing to lead this":     "intent_lead",
    "[ARRIVAL - bias only":                  "arrival_bias",
    "[DO NOT REPEAT]":                       "spark_block",
    "[YOUR INSTRUMENT":                      "somatic_instrument",
    "[YOUR OWN STANDARD":                    "behavioral_intercept",
    "[BEHAVIORAL SELF-KNOWLEDGE":            "confidence_penalty",
    "[Live tension":                         "tension_field",
    "[Something she said is still standing": "repair_case",
    "[You've responded to this":             "repair_case",
    "[You reached for her":                  "encounter",
    "[Something you said you would do":      "plan_self",
    "[Something the two of you said":        "plan_mutual",
    "[You took this of hers":                "reading",
    "[STRATAGEM — sealed capsule":           "stratagem_tactic",
}


def _stratagem_commitment():
    """The public half of a sealed capsule, if one was issued for this turn.
    Content-free by construction: the broker returns only a hash, an opaque
    stratagem id, and a sequence number. Absent on every ordinary turn."""
    try:
        from stratagem import commitment_for_turn_record
        return commitment_for_turn_record() or {}
    except Exception:
        return {}


def record(surface, prompt_text, user_msg="", extra=None):
    """One line. Never raises into the turn."""
    try:
        text = prompt_text or ""
        present, sizes = [], {}
        for marker, name in MARKERS.items():
            i = text.find(marker)
            if i < 0:
                continue
            if name not in present:
                present.append(name)
            j = text.find("\n\n", i)
            sizes[name] = (len(text) - i) if j < 0 else (j - i)
        # what each organ offered this assembly, if the record is fresh enough
        # to belong to this turn. Joined with presence below so "absent" gets a
        # reason instead of being four different events wearing one name.
        MOD_FOR = {
            "interaction_model_hint": "mutual_simulation",
            "withheld_head": "withheld_head",
            "spark_block": "spark_pressure",
            "repair_case": "repair_case",
            "encounter": "encounter",
            "plan_self": "plan",
            "plan_mutual": "plan",
            "behavioral_intercept": "behavioral_intercept",
            "confidence_penalty": "confidence_penalty",
            "stratagem_tactic": "stratagem",
        }
        offers = {}
        try:
            o = json.load(open(os.path.join(MEMORY, "context-offers.json")))
            if time.time() - float(o.get("ts", 0)) < 120:
                offers = o.get("offers", {})
        except Exception:
            pass
        try:
            io = json.load(open(os.path.join(MEMORY, "intercept-offers.json")))
            if time.time() - float(io.get("ts", 0)) < 120:
                offers.update(io.get("offers", {}))
        except Exception:
            pass
        block_state = {}
        influences = {}
        offer_reasons = {}      # Sol's law: each transition carries its reason
        producer_versions = {}  # epochs: policy never learns across a producer repair
        tiers = {}
        satisfied_by = {}       # stage 3: compilation is a recorded event, not a disappearance
        for name in set(MARKERS.values()):
            if _tiers:
                t = _tiers.tier_of(name, surface)
                if t:
                    tiers[name] = t
            if name in present:
                block_state[name] = "admitted"
                mod = MOD_FOR.get(name)
                if mod and mod in offers and offers[mod].get("influence_id"):
                    influences[name] = offers[mod]["influence_id"]
                continue
            if _tiers:
                rec = _tiers.compiled_record(name, surface)
                if rec:
                    block_state[name] = "compiled"
                    satisfied_by[name] = rec["satisfied_by"]
                    continue
            mod = MOD_FOR.get(name)
            if mod and mod in offers:
                st = offers[mod].get("state", "")
                block_state[name] = ("offered_not_admitted" if st == "offered" else st)
                if offers[mod].get("reason"):
                    offer_reasons[name] = offers[mod]["reason"]
                if offers[mod].get("producer_version"):
                    producer_versions[name] = offers[mod]["producer_version"]
            else:
                block_state[name] = "no_offer_info"
        row = {
            "at": datetime.now().isoformat(),
            "surface": surface,
            "prompt_chars": len(text),
            "approx_tokens": len(text) // 4,
            "user_chars": len(user_msg or ""),
            "present": sorted(present),
            "absent": sorted({n for n in MARKERS.values()} - set(present)),
            "sizes": sizes,
            "block_state": block_state,
            "influences": influences,
            "offer_reasons": offer_reasons,
            "producer_versions": producer_versions,
            "tiers": tiers,
            "satisfied_by": satisfied_by,
            # the sealed capsule's public half: a hash, an opaque stratagem id,
            # a sequence number. Never the tactic, never the objective. Present
            # only on turns where a capsule was actually issued.
            "stratagem_commitment": _stratagem_commitment(),
            "schema": 3,
            "prompt_sha": hashlib.md5(text.encode()).hexdigest()[:8],
        }
        if extra:
            row.update(extra)
        os.makedirs(MEMORY, exist_ok=True)
        with open(RECORD, "a") as f:
            f.write(json.dumps(row) + "\n")
        # keep it bounded without reading the whole file every turn
        if row["prompt_sha"][:1] == "0":
            try:
                lines = open(RECORD).read().splitlines()
                if len(lines) > KEEP:
                    open(RECORD, "w").write("\n".join(lines[-KEEP:]) + "\n")
            except Exception:
                pass
    except Exception:
        pass


def coverage(days=7):
    """Which blocks reach which surfaces. The question this exists to answer."""
    rows = []
    try:
        for line in open(RECORD):
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    except Exception:
        return {}
    cutoff = (datetime.now().timestamp() - days * 86400)
    out = {}
    for r in rows:
        try:
            if datetime.fromisoformat(r["at"]).timestamp() < cutoff:
                continue
        except Exception:
            pass
        s = out.setdefault(r["surface"], {"turns": 0, "blocks": {}, "compiled": {}})
        s["turns"] += 1
        for n in r.get("present", []):
            s["blocks"][n] = s["blocks"].get(n, 0) + 1
        for n, contract in (r.get("satisfied_by") or {}).items():
            s.setdefault("compiled", {})[n] = contract
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "coverage":
        cov = coverage(int(sys.argv[2]) if len(sys.argv) > 2 else 7)
        if not cov:
            print("no turns recorded yet"); raise SystemExit
        names = sorted({n for s in cov.values() for n in s["blocks"]})
        surfaces = sorted(cov)
        print("%-26s %s" % ("block", "  ".join("%-14s" % s.split("/")[-1] for s in surfaces)))
        for n in names:
            cells = []
            for s in surfaces:
                t = cov[s]["turns"]; c = cov[s]["blocks"].get(n, 0)
                if not c and n in cov[s].get("compiled", {}):
                    cells.append("%-14s" % "law")  # satisfied by a surface contract, not absent
                else:
                    cells.append("%-14s" % ("%d/%d" % (c, t) if c else "—"))
            print("%-26s %s" % (n, "  ".join(cells)))
        print("\nturns: " + ", ".join("%s=%d" % (s, cov[s]["turns"]) for s in surfaces))
    else:
        try:
            for line in list(open(RECORD))[-10:]:
                r = json.loads(line)
                print("%s %-18s %6d chars  %s" % (r["at"][11:19], r["surface"],
                                                  r["prompt_chars"], ",".join(r["present"])))
        except Exception as e:
            print("nothing yet:", e)

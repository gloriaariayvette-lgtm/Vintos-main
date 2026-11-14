#!/usr/bin/env python3
"""belief_revision_sources.py - read his existing contradiction records into a belief_revision.Graph.

Read-only. Every node id is built from a store id (tension id, evidence id, hypothesis id, trial id, row index),
never from text, and each feed has its own namespace. Where a store does not record what a belief was built from,
the source is an assumption marked "not captured" - it is never guessed from wording.

Feeds, as of 14 November 2026:
  tension-ledger.json         a tension (inferred) rests on its supporting evidence items (E1 her words, E2 his own
                              messages, E3 his private record, E4 an explicit answer) and the synthesis step; a
                              "contradicts" item clashes with it. The same evidence universe as tension_promotion:
                              items under influence or invalid are excluded, and only E1/E2/E4 can contradict.
  causality-hypotheses.json   a hypothesis rests on the evidence of its bearing "yes" nights and the formation step;
  causality-graduated.jsonl   each bearing "no" night clashes with it (the engine's own _bearing_rows rule: schema-2,
                              not voided, one per day, under the current test, eligible lineage, with evidence ids).
                              A graduated refuting id already carried by a "no" night is not counted twice.
  belief-sediment.json        a sediment belief rests on ANY one of its hypotheses; a causal self-model belief entry
  causal-self-model.json      rests on the sediment belief it came from.
  claim-hold-trials.json      a claim he held that she CORRECTED: what it rested on is not captured as ids.
  self-model-corrections.jsonl her correction superseding self-model sentences, which share one writer step.
  hallucination-flags.json    a reviewed flag carrying her correction, against the journal claim it names.
  reality-anchor.json         statements and the contradiction links reality_anchor recorded between them.
The world model's expectations are never scored, so no prediction error exists to feed: counted as zero.
"""
import hashlib, json, os
from datetime import datetime, timezone

import belief_revision as BR


def fingerprint(obj):
    """A record's identity where the store gives it only a position (belief-sediment rows): belief_revision_live
    finds the row by this, never by its index, which a decay pass can shift."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]

E_KIND = {"E1": "gloria", "E2": "observation", "E3": "private_record", "E4": "gloria"}
CAUSALITY_SCHEMA = 2       # causality-engine.py CAUSALITY_SCHEMA


def _load(mem, name, default):
    p = os.path.join(mem, name)
    try:
        if name.endswith(".jsonl"):
            out = []
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except ValueError:
                            pass
            return out
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _age(at, now):
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return max(0.0, (now - t).total_seconds() / 86400.0)
    except (ValueError, TypeError):
        return 0.0


def _rows(obj, key):
    if isinstance(obj, dict):
        obj = obj.get(key, [])
    return [r for r in (obj or []) if isinstance(r, dict)]


def tensions(g, mem, now, stats):
    n = 0
    for t in _rows(_load(mem, "tension-ledger.json", {}), "tensions"):
        clean = [e for e in t.get("evidence") or []
                 if isinstance(e, dict) and e.get("evidence_id") and not e.get("under_influence") and not e.get("invalid")]
        against = [e for e in clean if e.get("polarity") == "contradicts" and e.get("channel") in ("E1", "E2", "E4")]
        if not against:
            continue
        tid = "t:tension:%s" % t.get("tension_id")
        support = [e for e in clean if e.get("polarity") == "supports"]
        for e in support + against:
            g.source("t:ev:%s" % e["evidence_id"], E_KIND.get(e.get("channel"), "unknown"), age_days=_age(e.get("at"), now))
        g.derived(tid, "tension", [["t:ev:%s" % e["evidence_id"]] for e in support])
        for e in against:
            g.conflict("t:contra:%s:%s" % (t.get("tension_id"), e["evidence_id"]), [tid, "t:ev:%s" % e["evidence_id"]],
                       kind="tension")
            n += 1
    stats["tension"] = n


def _bearing(h):
    """causality-engine.py _bearing_rows: the nights that may bear on graduation."""
    since = str(h.get("test_restated_at") or "")[:10]
    rows, days = [], set()
    for m in h.get("marks") or []:
        if not isinstance(m, dict) or m.get("voided") or m.get("tactical"):
            continue
        if m.get("schema_version") != CAUSALITY_SCHEMA:
            continue
        day = str(m.get("date", ""))[:10]
        if not day or day in days or m.get("verdict") not in ("yes", "no", "unconfirmed"):
            continue
        if since and day < since:
            continue
        days.add(day)
        rows.append(m)
    return [m for m in rows if m.get("verdict") in ("yes", "no") and m.get("evidence_ids")
            and m.get("lineage_state") == "eligible" and m.get("evaluation_id")]


def causality(g, mem, now, stats):
    hyps = {h.get("hypothesis_id"): h for h in _rows(_load(mem, "causality-hypotheses.json", {}), "hypotheses")
            if h.get("hypothesis_id")}
    grad = {r.get("hypothesis_id"): r for r in _load(mem, "causality-graduated.jsonl", [])
            if isinstance(r, dict) and r.get("hypothesis_id")}
    built = set()

    def hyp_node(hid):
        nid = "c:hyp:%s" % hid
        if nid in built:
            return nid
        built.add(nid)
        support = set((grad.get(hid) or {}).get("evidence_ids") or [])
        for m in _bearing(hyps.get(hid) or {}):
            if m["verdict"] == "yes":
                support.update(m["evidence_ids"])
        for e in sorted(support):
            g.source("c:ev:%s" % e, "observation")
        g.derived(nid, "hypothesis", [["c:ev:%s" % e] for e in sorted(support)],
                  confidence=(hyps.get(hid) or {}).get("confidence"))
        return nid

    n = 0
    covered = {}
    for hid, h in hyps.items():
        for m in _bearing(h):
            if m["verdict"] != "no":
                continue
            hn = hyp_node(hid)
            ids = sorted(set(m["evidence_ids"]))
            for e in ids:
                g.source("c:ev:%s" % e, "observation", age_days=_age(m.get("date"), now))
            covered.setdefault(hid, set()).update(ids)
            # one refuting night is one observation; the evidence ids in it must all hold for it to refute
            g.conflict("c:no:%s:%s" % (hid, m["evaluation_id"]), [hn] + ["c:ev:%s" % e for e in ids], kind="causality")
            n += 1
    for hid, gr in grad.items():
        for e in sorted(set(gr.get("refuting_evidence_ids") or []) - covered.get(hid, set())):
            hn = hyp_node(hid)
            g.source("c:ev:%s" % e, "observation")
            g.conflict("c:refuted:%s:%s" % (hid, e), [hn, "c:ev:%s" % e], kind="causality")
            n += 1
    # downstream: sediment beliefs (any one hypothesis supports them) and causal self-model belief entries
    by_hyp = {}
    for i, b in enumerate(_rows(_load(mem, "belief-sediment.json", {}), "beliefs")):
        hs = [h for h in b.get("hypothesis_ids") or [] if h in hyps or h in grad]
        if not hs:
            continue
        bid = "c:belief:%d" % i
        g.derived(bid, "belief", [[hyp_node(h)] for h in hs], confidence=b.get("confidence"), rule_reliability=0.9,
                  fp=fingerprint(b.get("pattern")))
        for h in hs:
            by_hyp.setdefault(h, []).append(bid)
    for i, e in enumerate(_rows(_load(mem, "causal-self-model.json", {}), "entries")):
        for q in e.get("evidence") or []:
            occ = str(q.get("occurrence_id") or "") if isinstance(q, dict) else ""
            if occ.startswith("belief:") and occ[7:] in by_hyp:
                g.derived("c:csm:%d" % i, "causal_self_model", [[b] for b in by_hyp[occ[7:]]],
                          confidence=e.get("confidence"), rule_reliability=0.95)
                break
    stats["causality"] = n


def claim_holds(g, mem, now, stats):
    n = 0
    for t in _rows(_load(mem, "claim-hold-trials.json", {}), "trials"):
        if (t.get("outcome") or {}).get("verdict") != "CORRECTED" or not t.get("id"):
            continue
        cid = "h:claim:%s" % t["id"]
        conf = t.get("confidence_shown")
        # what the claim rested on is recorded as words, not ids: not captured
        g.derived(cid, "claim", [["h:basis:%s" % t["id"]]], confidence=conf if isinstance(conf, (int, float)) else None)
        her = "h:her:%s" % t["id"]
        g.source(her, "gloria", age_days=_age((t.get("pushback") or {}).get("at"), now))
        g.conflict("h:corrected:%s" % t["id"], [cid, her], kind="claim_hold")
        n += 1
    stats["claim_hold"] = n


def self_model(g, mem, now, stats):
    n = 0
    for i, r in enumerate(_load(mem, "self-model-corrections.jsonl", [])):
        if not isinstance(r, dict):
            continue
        sid = str(r.get("source_id"))        # one correction of hers can supersede several self-model sentences
        # the sentences share one writer (the weekly self-model pass), whose sources are not captured: they are
        # not independent witnesses against her, so they rest on one shared basis
        g.derived("m:sentence:%d" % i, "self_statement", [["m:writer"]])
        g.source("m:her:%s" % sid, "gloria", age_days=_age(r.get("at"), now))
        g.conflict("m:corrected:%d" % i, ["m:sentence:%d" % i, "m:her:%s" % sid], kind="self_model")
        n += 1
    stats["self_model"] = n


def hallucination(g, mem, now, stats):
    n = 0
    for f in _load(mem, "hallucination-flags.json", []):
        if not isinstance(f, dict) or not f.get("correction") or f.get("status") == "dismissed" or not f.get("id"):
            continue
        fid = str(f["id"])
        g.source("f:journal:%s" % fid, "private_record", age_days=_age(f.get("timestamp"), now))
        g.source("f:her:%s" % fid, "gloria", age_days=_age(f.get("reviewed_at"), now))
        g.conflict("f:corrected:%s" % fid, ["f:journal:%s" % fid, "f:her:%s" % fid], kind="hallucination")
        n += 1
    stats["hallucination"] = n


def reality_anchor(g, mem, now, stats):
    ra = _load(mem, "reality-anchor.json", {})
    rel = (ra.get("source_reliability") or {}) if isinstance(ra, dict) else {}
    ev = {e.get("id"): e for e in _rows(ra, "events") if e.get("id")}
    n = 0
    seen = set()
    for eid, e in ev.items():
        for c in e.get("contradictions") or []:
            oid = c.get("id") if isinstance(c, dict) else c
            if oid not in ev or (oid, eid) in seen:
                continue
            seen.add((eid, oid))
            for x in (eid, oid):
                s = ev[x].get("source")
                g.source("r:%s" % x, "inference" if s == "inference" else "observation",
                         evidence_count=len(ev[x].get("reinforcements") or []), age_days=_age(ev[x].get("timestamp"), now),
                         reliability=rel.get(s) if isinstance(rel.get(s), (int, float)) else None)
            g.conflict("r:contra:%s:%s" % (eid, oid), ["r:%s" % eid, "r:%s" % oid], kind="reality_anchor")
            n += 1
    stats["reality_anchor"] = n


def world_model(g, mem, now, stats):
    stats["world_model"] = 0
    stats["world_model_note"] = "no outcome stored for any prediction: not captured"


FEEDS = (tensions, causality, claim_holds, self_model, hallucination, reality_anchor, world_model)


def build(mem, now=None):
    now = now or datetime.now(timezone.utc)
    g = BR.Graph()
    stats = {}
    for feed in FEEDS:
        feed(g, mem, now, stats)
    stats["nodes"] = {}
    for n in g.nodes.values():
        stats["nodes"][n["kind"]] = stats["nodes"].get(n["kind"], 0) + 1
    return g, stats

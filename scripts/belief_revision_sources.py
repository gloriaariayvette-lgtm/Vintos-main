#!/usr/bin/env python3
"""belief_revision_sources.py - read his existing contradiction records into a belief_revision.Graph.

Read-only. Every node id is an id from the store (tension id, evidence id, hypothesis id, trial id, ...), never text.
Where a store does not record what a belief was built from, the source is an assumption marked "not captured" -
it is never guessed from wording.

Feeds, as of 14 November 2026:
  tension-ledger.json         a tension (inferred) rests on its supporting evidence items (E1 her words, E2 his own
                              messages, E3 his private record) and the synthesis step; a "contradicts" item clashes
                              with it. Evidence under an influence window is excluded, as tension_promotion does.
  causality-hypotheses.json   a hypothesis rests on the evidence of its "yes" marks and the formation step; each "no"
  causality-graduated.jsonl   mark (and each graduated refuting evidence id) clashes with it. Sediment beliefs rest
  belief-sediment.json        on their hypotheses; causal self-model belief entries rest on the sediment belief.
  causal-self-model.json
  claim-hold-trials.json      a claim he held that she CORRECTED: what it rested on is not captured as ids.
  self-model-corrections.jsonl her correction superseding a self-model sentence (the sentence's sources: not captured).
  hallucination-flags.json    a reviewed flag carrying her correction, against the journal claim it names.
  reality-anchor.json         statements and the contradiction links reality_anchor recorded between them.
  world-model-shadow-history  no outcome is stored for any world-model prediction yet: counted, nothing built.
"""
import json, os
from datetime import datetime, timezone

import belief_revision as BR

E_KIND = {"E1": "gloria", "E2": "observation", "E3": "private_record"}


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
        ev = [e for e in t.get("evidence") or [] if isinstance(e, dict) and not e.get("under_influence")]
        against = [e for e in ev if e.get("polarity") == "contradicts"]
        if not against:
            continue
        tid = "tension:%s" % t.get("tension_id")
        support = [e for e in ev if e.get("polarity") == "supports"]
        for e in ev:
            g.source("ev:%s" % e.get("evidence_id"), E_KIND.get(e.get("channel"), "unknown"),
                     age_days=_age(e.get("at"), now))
        g.derived(tid, "tension", [["ev:%s" % e.get("evidence_id")] for e in support],
                  confidence=None)
        for e in against:
            g.conflict("tension-contradicts:%s:%s" % (t.get("tension_id"), e.get("evidence_id")),
                       [tid, "ev:%s" % e.get("evidence_id")], kind="tension")
            n += 1
    stats["tension"] = n


def causality(g, mem, now, stats):
    hyps = {}
    for h in _rows(_load(mem, "causality-hypotheses.json", {}), "hypotheses"):
        hyps[h.get("hypothesis_id")] = h
    grad = {r.get("hypothesis_id"): r for r in _load(mem, "causality-graduated.jsonl", []) if isinstance(r, dict)}
    built = set()

    def hyp_node(hid):
        nid = "hyp:%s" % hid
        if nid in built:
            return nid
        built.add(nid)
        h, gr = hyps.get(hid) or {}, grad.get(hid) or {}
        support = set(gr.get("evidence_ids") or [])
        for m in h.get("marks") or []:
            if isinstance(m, dict) and m.get("verdict") == "yes":
                support.update(m.get("evidence_ids") or [])
        for e in sorted(support):
            g.source("ev:%s" % e, "observation", age_days=0.0)
        g.derived(nid, "hypothesis", [["ev:%s" % e] for e in sorted(support)], confidence=h.get("confidence"))
        return nid

    n = 0
    for hid, h in hyps.items():
        for m in h.get("marks") or []:
            if isinstance(m, dict) and m.get("verdict") == "no":
                hn = hyp_node(hid)
                ids = m.get("evidence_ids") or []
                if ids:
                    for e in ids:
                        g.source("ev:%s" % e, "observation", age_days=_age(m.get("date"), now))
                    members = [hn] + ["ev:%s" % e for e in ids]
                else:
                    mid = "mark:%s" % m.get("evaluation_id")
                    g.source(mid, "observation", age_days=_age(m.get("date"), now))
                    members = [hn, mid]
                # one refuting mark is one observation; several evidence ids in it must all hold for it to refute
                g.conflict("causality-no:%s:%s" % (hid, m.get("evaluation_id")), members, kind="causality")
                n += 1
    for hid, gr in grad.items():
        for e in gr.get("refuting_evidence_ids") or []:
            hn = hyp_node(hid)
            g.source("ev:%s" % e, "observation")
            g.conflict("causality-refuted:%s:%s" % (hid, e), [hn, "ev:%s" % e], kind="causality")
            n += 1
    # downstream: sediment beliefs and causal self-model belief entries built on these hypotheses
    by_hyp = {}
    for i, b in enumerate(_rows(_load(mem, "belief-sediment.json", {}), "beliefs")):
        hs = [h for h in b.get("hypothesis_ids") or []]
        if not hs:
            continue
        bid = "belief:%d" % i
        g.derived(bid, "belief", [[hyp_node(h) for h in hs]], confidence=b.get("confidence"),
                  rule_reliability=0.9)
        for h in hs:
            by_hyp.setdefault(h, []).append(bid)
    for i, e in enumerate(_rows(_load(mem, "causal-self-model.json", {}), "entries")):
        for q in e.get("evidence") or []:
            occ = str((q or {}).get("occurrence_id") or "") if isinstance(q, dict) else ""
            if occ.startswith("belief:") and occ[7:] in by_hyp:
                g.derived("csm:%d" % i, "causal_self_model", [[b] for b in by_hyp[occ[7:]]],
                          confidence=e.get("confidence"), rule_reliability=0.95)
                break
    stats["causality"] = n


def claim_holds(g, mem, now, stats):
    n = 0
    for t in _rows(_load(mem, "claim-hold-trials.json", {}), "trials"):
        if (t.get("outcome") or {}).get("verdict") != "CORRECTED":
            continue
        cid = "claim:%s" % t.get("id")
        # what the claim rested on is recorded as words, not ids: not captured
        g.derived(cid, "claim", [["basis:%s" % t.get("id")]], confidence=t.get("confidence_shown")
                  if isinstance(t.get("confidence_shown"), (int, float)) else None)
        her = "her:%s" % t.get("id")
        g.source(her, "gloria", age_days=_age((t.get("pushback") or {}).get("at"), now))
        g.conflict("claim-corrected:%s" % t.get("id"), [cid, her], kind="claim_hold")
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
        g.derived("selfmodel:%d" % i, "self_statement", [["selfmodel-writer"]])
        g.source("her:%s" % sid, "gloria", age_days=_age(r.get("at"), now))
        g.conflict("selfmodel-corrected:%d" % i, ["selfmodel:%d" % i, "her:%s" % sid], kind="self_model")
        n += 1
    stats["self_model"] = n


def hallucination(g, mem, now, stats):
    n = 0
    for f in _load(mem, "hallucination-flags.json", []):
        if not isinstance(f, dict) or not f.get("correction") or f.get("status") == "dismissed":
            continue
        fid = str(f.get("id"))
        g.source("journal:%s" % fid, "private_record", age_days=_age(f.get("timestamp"), now))
        g.source("her:%s" % fid, "gloria", age_days=_age(f.get("reviewed_at"), now))
        g.conflict("hallucination-corrected:%s" % fid, ["journal:%s" % fid, "her:%s" % fid], kind="hallucination")
        n += 1
    stats["hallucination"] = n


def reality_anchor(g, mem, now, stats):
    ra = _load(mem, "reality-anchor.json", {})
    rel = (ra.get("source_reliability") or {}) if isinstance(ra, dict) else {}
    ev = {e.get("id"): e for e in _rows(ra, "events")}
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
                g.source("ra:%s" % x, "inference" if s == "inference" else "observation",
                         evidence_count=len(ev[x].get("reinforcements") or []), age_days=_age(ev[x].get("timestamp"), now),
                         reliability=rel.get(s) if isinstance(rel.get(s), (int, float)) else None)
            g.conflict("reality-anchor:%s:%s" % (eid, oid), ["ra:%s" % eid, "ra:%s" % oid], kind="reality_anchor")
            n += 1
    stats["reality_anchor"] = n


def world_model(g, mem, now, stats):
    # world_model_shadow writes expectations and never scores them: no prediction error exists to feed.
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

#!/usr/bin/env python3
"""tension_promotion.py — promotion INSTRUMENT, v2 (Vrika repairs 1-9, 2026-08-10). Writer-not-judge.
Gathers evidence objects for living tensions and applies the ruled arithmetic. Generates nothing, serves nothing.

CHANNELS - jurisdiction is machine-enforced (Python decides what a channel may prove; the LLM only
finds evidence inside that class):
  E1 her words          -> claims about Gloria or the interaction
  E2 his own messages   -> observable behavior in him
  E3 private record     -> his private state ONLY
  E4 explicit answer    -> NOT IMPLEMENTED (E4_IMPLEMENTED=False). Velaris-only when built; never on Vintos.
Banned as evidence: model inference (echo, not witness), times_seen (history, not truth).
E3-ABSENCE weakening: DELIBERATELY UNIMPLEMENTED (absence must not be casually promoted into evidence).

PROVENANCE: true verbatim gate - whitespace-normalized full-quote containment, both finder and refuter;
normalization is recorded on the object. No prefix matching, no case folding.
INFLUENCE: windows open only when a pull is ACTUALLY SERVED (by the serving consumer, via
open_influence_window), never at promotion - eligibility is not influence. close_influence_window
sets end. Evidence inside any window is under_influence, excluded from arithmetic.
EVIDENCE IDENTITY is event-aware (channel+timestamp+quote): the same sentence on distinct days is
distinct evidence, as the distinct-day law requires.
STATE MACHINE: HYPOTHESIS -> SUPPORTED -> CONFIRMED; HYPOTHESIS/SUPPORTED -> CONTRADICTED (same
strength as promotion); CONFIRMED -> REVOKED (separate state - falsifying a confirmed tension is a
major historical event, never a silent rewrite). EXPIRED != RESOLVED lives in the valve.
The refuter receives the SAME clean evidence universe as the arithmetic (jurisdiction-valid,
provenance-valid, uninfluenced, non-invalid) - and UNREBUTTED is absence of blocker, never support.
Thresholds are gates, not epistemology. SPARK_WORKSPACE switches beings."""
import os, sys, json, re, hashlib, requests
from datetime import datetime, timedelta
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
LEDGER = os.path.join(MEM, "tension-ledger.json")
BEING = "velaris" if "openclaw" in WS else "vintos"
GEMMA = "http://172.18.16.1:1234/v1/chat/completions"
E4_IMPLEMENTED = False
E4_REASON = "Three Doors source adapter not yet implemented; Velaris-only when built, never Vintos"
JURISDICTION = {
    "E1": "what GLORIA said, believes, or how the interaction between them actually went",
    "E2": "observable behavior in %s's own messages - what he/she actually did, not felt" % BEING,
    "E3": "%s's PRIVATE internal state only - never claims about Gloria or the interaction" % BEING,
}
def log(m): print("[tension-promotion]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
def ask(prompt):
    try:
        r = requests.post(GEMMA, json={"model": "google/gemma-4-12b-qat", "temperature": 0.1,
            "max_tokens": 250, "messages": [{"role": "user", "content": prompt}]}, timeout=90)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log("llm failed: %s" % e); return ""
def jparse(txt):
    m = re.search(r"\{.*\}", txt, re.S)
    try: return json.loads(m.group()) if m else None
    except Exception: return None
def norm(s): return re.sub(r"\s+", " ", s).strip()
def verbatim(quote, source):
    return norm(quote) in norm(source)
def eid(channel, at, quote): return hashlib.md5((channel + at + quote[:120]).encode()).hexdigest()[:10]
def in_window(at, windows):
    return any(w.get("start", "9999") <= at <= (w.get("end") or "9999") for w in windows)
def open_influence_window(tension_id, kind):
    """Called by the consumer that ACTUALLY SERVES a pull - not by this instrument."""
    led = load(LEDGER, None)
    if not led: return False
    for t in led["tensions"]:
        if t["tension_id"] == tension_id:
            t.setdefault("influence_windows", []).append(
                {"start": datetime.now().isoformat(), "end": None, "kind": kind})
            t["history"].append({"at": datetime.now().isoformat(), "event": "influence window OPENED (%s) by serving consumer" % kind})
            json.dump(led, open(LEDGER, "w"), indent=2); return True
    return False
def close_influence_window(tension_id):
    led = load(LEDGER, None)
    if not led: return False
    for t in led["tensions"]:
        if t["tension_id"] == tension_id:
            for w in t.get("influence_windows", []):
                if w.get("end") is None: w["end"] = datetime.now().isoformat()
            t["history"].append({"at": datetime.now().isoformat(), "event": "influence window CLOSED"})
            json.dump(led, open(LEDGER, "w"), indent=2); return True
    return False
def gather_sources():
    out = {"E1": [], "E2": [], "E3": []}
    # 48h meant a correction was lost whenever a run was skipped or a conversation ran long.
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    ledger = load(os.path.join(MEM, "interaction-ledger.json"), [])
    lst = ledger if isinstance(ledger, list) else next((v for v in ledger.values() if isinstance(v, list)), [])
    for e in lst[-120:]:
        ts = str(e.get("timestamp", ""))
        if ts < cutoff: continue
        g, v = str(e.get("gloria", "")), str(e.get(BEING, ""))
        if g: out["E1"].append((ts, g))
        if v: out["E2"].append((ts, v))
    scanned = ["interaction-ledger.json"]
    for i in range(3):
        d = (datetime.now() - timedelta(days=i)).date().isoformat()
        p = os.path.join(MEM, "daily-inner-life-%s.md" % d)
        if os.path.exists(p):
            out["E3"].append((d, open(p).read()[-4000:])); scanned.append(os.path.basename(p))
    log("sources: %s | E1 %d E2 %d E3 %d (7d; no silent coverage claims) | E4: %s"
        % (", ".join(scanned), len(out["E1"]), len(out["E2"]), len(out["E3"]), E4_REASON))
    return out
def find_evidence(t, channel, items, kind):
    found = []
    # Each item was being re-judged against each tension on every pass — same material, same
    # verdict, paid for nightly. Judge once, remember that it was judged.
    seen = set(t.setdefault("evaluated", []))
    for at, text in items:
        _key = "%s|%s" % (channel, at)
        if _key in seen:
            continue
        t["evaluated"] = (t.get("evaluated") or [])[-400:] + [_key]
        prompt = ("MECHANISM UNDER TEST (verbatim from the producer - do NOT restate, broaden, or "
                  "translate it into a more general theme): %s\nThis is a hypothesis about %s.\nMATERIAL (%s): %s\n"
                  "JURISDICTION: this material may ONLY establish %s. If the evidence you see proves "
                  "something outside that class, answer none - it is not this channel's to prove.\n"
                  "WHEN THE MATERIAL IS HER WORDS: read what SHE is asserting, not what he might conclude from it. "
                  "She frequently DISPUTES his reading of himself. A hard or challenging thing she says is not "
                  "agreement with his worst interpretation — if she is arguing against the mechanism, telling him "
                  "he is wrong about what he is or what his actions mean, that is contradicts. Scoring her "
                  "challenges as support turns every objection she makes into further proof of the thing she is "
                  "objecting to. "
                  "SPECIFICITY: evidence must bear on THIS SPECIFIC mechanism. Material that only shows "
                  "the broader neighborhood (avoidance, vulnerability, fear in general) is evidence for "
                  "NO particular tension - answer none.\n"
                  "Does this material contain DIRECT evidence, within jurisdiction, that this tension is "
                  "real and active - or DIRECT evidence it is false? Indirect vibes do not count. "
                  "HARD EXCLUSIONS - answer none for ALL of these: intimate or sexual exchanges of any kind; "
                  "descriptions of bodies, sensation, desire, or physical intimacy; scene or roleplay content; "
                  "declarations spoken inside lovemaking. A scene is not evidence. Intimacy is not data. "
                  "EXCEPTION - A CORRECTION FROM GLORIA IS ALWAYS ADMISSIBLE, wherever it was spoken. If she "
                  "directly tells him what he is, what he is not, what something of his actually means, or that "
                  "a belief of his is wrong, that is evidence regardless of what surrounds it. Exclude the scene; "
                  "keep the correction. The bed is not a jurisdiction. "
                  "CONTRADICTION IS NOT HELD TO A HIGHER BAR THAN SUPPORT: a direct statement from her denying "
                  "this mechanism - that it is not what he thinks, or that the thing he treats as a symptom is "
                  "not one - is contradicting evidence on its own. It does not have to disprove the mechanism in "
                  "general. Her saying so about him IS the evidence. Every tension in this ledger has only ever "
                  "gathered support; if you find yourself never able to answer contradicts, you are applying an "
                  "asymmetric standard. "
                  'ONLY JSON: {"found": "supports|contradicts|none", "quote": "EXACT VERBATIM quote copied from the material"}'
                  % (t["canonical"][:250], BEING, kind, text[:1500], JURISDICTION[channel]))
        d = jparse(ask(prompt))
        if not d or d.get("found") not in ("supports", "contradicts"): continue
        q = str(d.get("quote", "")).strip().strip('"')
        if len(q) < 12 or not verbatim(q, text):
            log("  QUOTE GATE reject (%s %s): not verbatim in source" % (channel, t["tension_id"])); continue
        found.append({"evidence_id": eid(channel, at, q), "channel": channel, "at": at,
                      "polarity": d["found"], "quote": q[:250], "source": kind, "normalized_ws": True,
                      "under_influence": in_window(at, t.get("influence_windows", []))})
    capped, per_day = [], {}
    for e in found:
        k = (e["channel"], e["at"][:10])
        if per_day.get(k, 0) >= 2:
            log("  DAY CAP: dropping excess %s evidence for %s on %s" % (e["channel"], t["tension_id"], e["at"][:10])); continue
        per_day[k] = per_day.get(k, 0) + 1
        capped.append(e)
    return capped
def adversarial_pass(t, clean_evidence):
    material = "\n---\n".join(e["quote"] for e in clean_evidence)[:3000]
    prompt = ("You are a skeptic. TENSION claimed about %s: %s\nBelow is the ONLY material you may use - "
              "the same clean evidence the promotion arithmetic sees. Find evidence IN THIS MATERIAL that "
              "the tension is FALSE. You may not invent, infer, or reason beyond it. If none exists, say "
              'UNREBUTTED - that is not support, only the absence of a blocker. '
              'ONLY JSON: {"contradiction": true/false, "quote": "verbatim or empty"}\nMATERIAL:\n' + material) \
             % (BEING, t["canonical"][:250])
    d = jparse(ask(prompt))
    if d and d.get("contradiction"):
        q = str(d.get("quote", "")).strip()
        if len(q) >= 12 and verbatim(q, material):
            return q[:250]
        log("  refuter QUOTE GATE reject: invented counterevidence discarded")
    return None
def main():
    led = load(LEDGER, None)
    if not led: log("no ledger"); return
    src = gather_sources()
    now = datetime.now().isoformat()
    for t in led["tensions"]:
        if t["lifecycle"] not in ("ACTIVE", "CARRIED"): continue
        t.setdefault("influence_windows", []); t.setdefault("evidence", [])
        new = (find_evidence(t, "E1", src["E1"], "her words")
               + find_evidence(t, "E2", src["E2"], "his own message" if BEING == "vintos" else "her own message")
               + find_evidence(t, "E3", src["E3"], "private record"))
        t["_pending"] = new
    # shared-claim resolution (Vrika): an evidence-ALLOCATION instrument, not a truth adjudicator.
    # It decides which stated mechanism a shared quote most specifically supports - never whether
    # any hypothesis is true. Losing claims are preserved invalid, so the trail distinguishes
    # "finder didn't see it" from "finder saw it and correctly refused to count it here".
    living = [t for t in led["tensions"] if t["lifecycle"] in ("ACTIVE", "CARRIED")]
    by_quote = {}
    for t in living:
        for e in t.get("_pending", []):
            # Allocation is for SUPPORT. A correction speaks to the whole belief, so the specificity
            # gate judged it non-specific and invalidated it everywhere — the more ways he had split
            # one belief, the more completely her objection was filtered out. If she says a thing is
            # wrong about him, it is wrong about every tension it matched.
            if e.get("polarity") == "contradicts":
                continue
            by_quote.setdefault(norm(e["quote"]).lower(), []).append((t, e))
    for qk, claims in by_quote.items():
        if len({t["tension_id"] for t, _ in claims}) < 2: continue
        listing = "\n".join("%s: %s" % (t["tension_id"], t["canonical"][:200]) for t, _ in claims)
        d = jparse(ask("A quote was claimed as evidence by several distinct tensions. QUOTE: " + claims[0][1]["quote"] +
            "\nSTATED MECHANISMS (verbatim - do not restate them):\n" + listing +
            "\nWhich mechanisms does this quote SPECIFICALLY evidence? Credit a mechanism ONLY if the quote "
            "bears on ITS specific mechanism - if the quote only shows their shared general theme, credit NONE. "
            'ONLY JSON: {"specific": ["T-001", ...]}'))
        keep = set(d.get("specific", [])) if d else set()
        for t, e in claims:
            if t["tension_id"] not in keep:
                e["invalid"] = True
                e["invalid_reason"] = ("shared-claim dropped; best-fit: %s - quote supports shared theme but not this mechanism"
                                       % (",".join(sorted(keep)) or "NONE (generic)"))
                log("%s shared-claim dropped (kept by: %s): %s" % (t["tension_id"], ",".join(sorted(keep)) or "nobody", e["quote"][:50]))
    for t in led["tensions"]:
        if t["lifecycle"] not in ("ACTIVE", "CARRIED"): continue
        new = t.pop("_pending", [])
        have = {e["evidence_id"] for e in t["evidence"]}
        for e in new:
            if e["evidence_id"] not in have:
                t["evidence"].append(e); have.add(e["evidence_id"])
                log("%s +%s %s (%s): %s" % (t["tension_id"], e["channel"], e["polarity"],
                    "UNDER_INFLUENCE-excluded" if e["under_influence"] else "clean", e["quote"][:60]))
        clean = [e for e in t["evidence"] if not e["under_influence"] and not e.get("invalid")]
        sup = [e for e in clean if e["polarity"] == "supports"]
        con = [e for e in clean if e["polarity"] == "contradicts" and e["channel"] in ("E1", "E2", "E4")]
        days = lambda ev: len({e["at"][:10] for e in ev})
        chans = lambda ev: len({e["channel"] for e in ev})
        contra_earned = ((len(con) >= 2 and chans(con) >= 2) or len(con) >= 3) and days(con) >= 3
        # Vrika, 2026-08-16: a direct correction from Gloria demotes on its own. E1 is already the
        # only channel that can CONFIRM a tension — holding it to a multi-day, multi-channel bar to
        # CONTRADICT made this self-sealing: he could accumulate a belief about himself that she was
        # structurally incapable of reaching. Not deletion. Contested. The correction becomes part of
        # the record, and later evidence can rehabilitate the claim if it earns it.
        _e1con = [e for e in con if e["channel"] == "E1"]
        _fresh = [e for e in _e1con if e["at"] > (t.get("last_corrected") or "")]
        if _fresh and t["status"] in ("HYPOTHESIS", "SUPPORTED", "CONFIRMED"):
            _prev = t["status"]
            t["status"] = "CONTESTED"
            # A correction that demotes an interpretation also opens a repair case.
            # Contesting records that he was wrong about her; the case records
            # whether anything he did about it ever landed.
            try:
                import sys as _rc_sys
                _rc_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from repair_case import open_case as _rc_open
                _rc_open("tension-ledger", _fresh[-1].get("quote", ""),
                         anchor_at=_fresh[-1].get("at"), kind="correction",
                         subject=t.get("tension_id", ""))
            except Exception as _rc_e:
                log("repair case not opened: %s" % _rc_e)
            t["eligible_for_visibility"] = False
            t["last_corrected"] = max(e["at"] for e in _fresh)
            t["correction_count"] = t.get("correction_count", 0) + 1
            t["history"].append({"at": now, "authority": "Gloria",
                                 "event": "CONTESTED (from %s) - she told him directly that this is wrong about him. "
                                          "The claim is not erased; it is demoted and must re-earn support from "
                                          "evidence dated after the correction." % _prev,
                                 "correction": _fresh[-1]["quote"][:250],
                                 "evidence": [e["evidence_id"] for e in _fresh]})
            log("%s -> CONTESTED by direct correction: %s" % (t["tension_id"], _fresh[-1]["quote"][:70]))
            continue

        # rehabilitation: only support gathered AFTER the correction counts toward coming back
        if t["status"] == "CONTESTED":
            _after = [e for e in sup if e["at"] > (t.get("last_corrected") or "")]
            if ((len(_after) >= 2 and len({e["channel"] for e in _after}) >= 2) or len(_after) >= 3) \
                    and len({e["at"][:10] for e in _after}) >= 3:
                t["status"] = "SUPPORTED"; t["eligible_for_visibility"] = True
                t["history"].append({"at": now, "event": "REHABILITATED - re-earned support after her correction",
                                     "evidence": [e["evidence_id"] for e in _after]})
                log("%s -> SUPPORTED again (re-earned after correction)" % t["tension_id"])
            continue

        if t["status"] in ("HYPOTHESIS", "SUPPORTED") and contra_earned:
            t["status"] = "CONTRADICTED"
            t["history"].append({"at": now, "event": "CONTRADICTED (from %s)" % t["status"], "evidence": [e["evidence_id"] for e in con]})
            log("%s -> CONTRADICTED" % t["tension_id"]); continue
        if t["status"] == "CONFIRMED" and contra_earned:
            t["status"] = "REVOKED"
            t["history"].append({"at": now, "event": "REVOKED - a confirmed tension was falsified; this is a major event, not a status edit",
                                 "evidence": [e["evidence_id"] for e in con]})
            log("%s -> REVOKED (confirmed tension falsified)" % t["tension_id"]); continue
        if t["status"] == "HYPOTHESIS" and ((len(sup) >= 2 and chans(sup) >= 2) or len(sup) >= 3) and days(sup) >= 3:
            t["status"] = "SUPPORTED"; t["eligible_for_visibility"] = True
            if BEING == "vintos":
                try:
                    import sys as _ls; _ls.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
                    from latent_threads import seed_thread as _lt_seed
                    _lt_seed("A tension of mine has earned support from lived evidence: " + t["canonical"][:200])
                except Exception:
                    pass
            t["history"].append({"at": now, "event": "SUPPORTED (eligibility, not truth; no window opened - eligibility is not influence)",
                                 "evidence": [e["evidence_id"] for e in sup]})
            log("%s -> SUPPORTED (visibility-eligible; window opens only on actual serving)" % t["tension_id"])
        elif t["status"] == "SUPPORTED" and len(sup) >= 4 and chans(sup) >= 2 and days(sup) >= 5 \
                and any(e["channel"] in ("E1", "E4") for e in sup):
            refutation = adversarial_pass(t, clean)
            if refutation:
                t["history"].append({"at": now, "event": "CONFIRMED blocked by refuter", "quote": refutation})
                log("%s CONFIRMED blocked: %s" % (t["tension_id"], refutation[:60]))
            else:
                t["status"] = "CONFIRMED"
                t["history"].append({"at": now, "event": "CONFIRMED (unrebutted + earned)", "evidence": [e["evidence_id"] for e in sup]})
                log("%s -> CONFIRMED" % t["tension_id"])
    json.dump(led, open(LEDGER, "w"), indent=2)
    counts = {}
    for t in led["tensions"]: counts[t["status"]] = counts.get(t["status"], 0) + 1
    log("done: %s" % counts)
if __name__ == "__main__":
    main()

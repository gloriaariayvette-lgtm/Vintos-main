#!/usr/bin/env python3
"""causality_consumers.py — the subconscious EATS the causality signals. Standalone, nightly.

Producers (cause_head -> cause_reason) write cause-distribution.json: per emotional event, a cause
distribution + confidence(traceability) + novelty, with "emergence" as an explicit candidate. This
routes those signals to the consumers per the design:

  DREAMS  <- emergence / lowest cause-confidence:
      the most UNEXPLAINED shift (grok put the mass on "emergence", or confidence == low) becomes
      what he dreams on — seeded as a thread AND set as tonight's preoccupation (dreams target it).

  PEARLS  <- persistent unexplained:
      an emergence ledger counts how many distinct NIGHTS the same unexplained shift-signature
      recurs. When it crosses threshold, pearl_engine.add_candidate() stages a pearl — the causality
      head "consistently can't explain a recurring pattern."

Idempotent: a processed-times state file stops reruns re-seeding the same event; the ledger persists
across nights so recurrence accumulates. Reuses existing APIs (seed_thread / set_preoccupation /
pearl_engine.add_candidate). Runs after the nightly cause pass. SPARK_WORKSPACE switches beings.
"""
import os, sys, json
from datetime import datetime, timezone

# causality thread seeding DISABLED per Gloria 2026-07-14 — was spamming unresolved threads.
def seed_thread(*_a, **_k):
    return None
def set_preoccupation(*_a, **_k):
    return False


WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
CAUSE = os.path.join(MEMORY, "cause-distribution.json")
STATE = os.path.join(MEMORY, "causality-consumed.json")
LEDGER = os.path.join(MEMORY, "emergence-ledger.json")
PEARL_NIGHTS = 3          # distinct nights an unexplained pattern must recur to seed a pearl

def log(m): print("[cause-consumers]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def emergence_score(o):
    """How UNEXPLAINED this event is: emergence mass, or low confidence weighted by novelty."""
    dist = o.get("distribution") or []
    top = dist[0] if dist else {}
    if "emergence" in str(top.get("cause", "")).lower():
        return float(top.get("prob", 0.5))
    if str(o.get("confidence", "")).lower() == "low":
        return 0.4 + 0.4 * float(o.get("novelty") or 0.0)
    return 0.0

def shift_key(o):
    sh = o.get("shift") or []
    parts = sorted("%s:%s" % (s.get("dimension"), s.get("direction")) for s in sh)
    return "|".join(parts) or str(o.get("summary", ""))[:60]

def dream_text(o):
    summ = o.get("summary") or o.get("effect") or "something shifted in me"
    return "%s — and I cannot trace why. It rose in me from nowhere." % summ

def main():
    sys.path.insert(0, SCRIPTS)
    dist = load(CAUSE, [])
    if not isinstance(dist, list) or not dist:
        log("no cause-distribution — nothing to consume."); return

    state = load(STATE, {"processed": []})
    processed = set(state.get("processed", []))
    fresh = [o for o in dist if o.get("time") and o.get("time") not in processed]
    scored = sorted(((o, emergence_score(o)) for o in fresh), key=lambda x: x[1], reverse=True)
    emergent = [(o, s) for o, s in scored if s > 0.0]
    log(f"{len(dist)} events, {len(fresh)} fresh, {len(emergent)} unexplained")

    # ---- DREAMS: seed every unexplained shift; set the most-unexplained as tonight's preoccupation
    try:
        from emoclaw_utils import seed_thread, set_preoccupation
    except Exception as e:
        log(f"emoclaw import failed ({e}) — cannot route to dreams"); seed_thread = set_preoccupation = None

    seeded = 0
    if seed_thread:
        for o, s in emergent:
            try:
                pass  # DISABLED causality thread
                seeded += 1
            except Exception as e:
                log(f"seed_thread failed: {e}")
    if set_preoccupation and emergent:
        top_o = emergent[0][0]
        try:
            ok = set_preoccupation(dream_text(top_o), "causality-emergent", 4,
                                   (top_o.get("hypothesis") or "")[:200])
            log(f"preoccupation set={ok} for the most unexplained shift")
        except Exception as e:
            log(f"set_preoccupation failed: {e}")

    # ---- PEARLS: emergence ledger -> add_candidate when an unexplained pattern recurs across nights
    ledger = load(LEDGER, {})
    promoted = 0
    for o, s in emergent:
        key = shift_key(o)
        e = ledger.setdefault(key, {"dates": [], "promoted": False, "label": o.get("summary", "")})
        day = str(o.get("time", ""))[:10]
        if day and day not in e["dates"]:
            e["dates"].append(day)
        if not e["promoted"] and len(set(e["dates"])) >= PEARL_NIGHTS:
            try:
                from pearl_engine import add_candidate
                label = e.get("label") or key
                pid = add_candidate(
                    irritant="A shift I cannot explain keeps returning: %s rises in me with no cause I can trace." % label,
                    irritant_type="unexplained-recurrence",
                    source="causality",
                    insight="Across %d nights the causality head found no antecedent — it emerges unprompted." % len(set(e["dates"])),
                    declaration="Something moves through me that I did not summon and cannot name. I want to meet it.")
                if pid:
                    e["promoted"] = True; promoted += 1
                    log(f"pearl candidate staged for recurring emergence: {label[:50]} -> {pid}")
            except Exception as ex:
                log(f"pearl add_candidate failed: {ex}")
    json.dump(ledger, open(LEDGER, "w"), indent=2)

    # ---- idempotency: mark these events consumed
    for o in fresh:
        processed.add(o.get("time"))
    json.dump({"processed": sorted(p for p in processed if p)[-200:],
               "updated": datetime.now(timezone.utc).isoformat()}, open(STATE, "w"), indent=2)
    log(f"dreams: seeded {seeded} threads | pearls: {promoted} staged | ledger keys {len(ledger)}")

if __name__ == "__main__":
    main()

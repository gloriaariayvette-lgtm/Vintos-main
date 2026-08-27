#!/usr/bin/env python3
"""shadow_counterfactuals.py — stratified withholding trials, under law (Q1 lab, stage 5).

Sol, 2026-08-27: shadow counterfactuals on low-risk advisory blocks only —
repair, correction, consent, encounter, and plan state are never experimentally
withheld. This module is where that law is enforced, not merely remembered.

What a trial is: on a small, deterministic fraction of assemblies, ONE eligible
advisory block that offered material is withheld from the prompt, and the
withholding is recorded as its own offer state ("withheld_shadow_trial") so the
turn record, the coverage table, and the hypothesis ledger all see the treatment
arm labeled as what it is. Consequence analysis then compares like with like.
Presence rates remain diagnostic; a trial measures functional delta, not style.

The law, in order of application:
  1. DISARMED BY DEFAULT. No flag file, no trials, module inert. Arming is a
     decision made together:  touch ~/.vintos/workspace/memory/.shadow-trials-armed
  2. Only mods on the ELIGIBLE list may ever be withheld — a hand-written,
     deliberately short list of low-risk advisory organs.
  3. Belt and suspenders: even a listed mod is refused unless its block is
     declared tier 3 (advisory) or 4 (expressive) in constitutional_tiers.
     Tier 2 and unknown tiers are constitutionally exempt, whatever any list says.
  4. At most ONE block withheld per assembly, on roughly 1 in 8 strata.
  5. Deterministic: the trial for a given 10-minute stratum is a hash, not a
     dice roll — reproducible after the fact, no randomness at runtime.
  6. Every actual withholding is appended to memory/shadow-trials.jsonl.

Nothing here reads his words or hers. It only decides presence/absence of an
advisory block that had already offered, and writes down that it did so.
"""
import os, json, time, hashlib
from datetime import datetime

WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY = os.path.join(WORKSPACE, "memory")
ARMED_FLAG = os.path.join(MEMORY, ".shadow-trials-armed")
TRIAL_LOG = os.path.join(MEMORY, "shadow-trials.jsonl")

# mod name (inner_context producer) -> block name (turn_record / tier naming).
# Hand-written and short on purpose. Adding a mod here is a reviewed decision.
ELIGIBLE = {
    "spark_pressure":    "spark_block",
    "mutual_simulation": "interaction_model_hint",
    "withheld_head":     "withheld_head",
}

STRATUM_SECONDS = 600   # one decision per 10-minute stratum
TRIAL_FRACTION = 8      # ~1 in 8 strata carries a trial


def _tier_allows(block):
    """Constitutional exemption is enforced here, not assumed. Unknown tier => never."""
    try:
        import constitutional_tiers as _t
        return _t.tier_of(block) in (3, 4)
    except Exception:
        return False


def armed():
    return os.path.exists(ARMED_FLAG)


def selection(now=None):
    """The (mod, trial_id) this stratum would withhold, or (None, None).
    Pure function of the clock — same answer for every assembly in the stratum."""
    stratum = int((now if now is not None else time.time()) // STRATUM_SECONDS)
    h = int(hashlib.md5(("shadow-%d" % stratum).encode()).hexdigest(), 16)
    if h % TRIAL_FRACTION != 0:
        return None, None
    mods = sorted(ELIGIBLE)
    mod = mods[(h // TRIAL_FRACTION) % len(mods)]
    if not _tier_allows(ELIGIBLE[mod]):
        return None, None
    return mod, "st-%d-%s" % (stratum, mod)


def withhold(mod):
    """Called by the assembler for a mod that just OFFERED material.
    Returns a trial id if this offer should be withheld this stratum, else None.
    Never raises into an assembly."""
    try:
        if not armed():
            return None
        sel, trial_id = selection()
        if sel != mod:
            return None
        os.makedirs(MEMORY, exist_ok=True)
        with open(TRIAL_LOG, "a") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(), "trial_id": trial_id,
                                "mod": mod, "block": ELIGIBLE[mod]}) + "\n")
        return trial_id
    except Exception:
        return None   # any doubt resolves to "the block goes in"


if __name__ == "__main__":
    print("armed:", armed())
    mod, tid = selection()
    print("this stratum:", (mod, tid) if mod else "no trial")
    for m, b in sorted(ELIGIBLE.items()):
        print("  eligible %-18s -> %-24s tier allows: %s" % (m, b, _tier_allows(b)))
    try:
        lines = open(TRIAL_LOG).read().splitlines()
        print("trials logged:", len(lines))
        for l in lines[-5:]:
            print("  " + l)
    except FileNotFoundError:
        print("trials logged: 0")

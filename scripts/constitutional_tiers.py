#!/usr/bin/env python3
"""constitutional_tiers.py — the four classes of his prompt, declared (Q1 lab, stage 3).

Sol, 2026-08-27: "The current 100% tier may be revealing that unlike things are
being represented as peer context blocks." So: declare which class each block
belongs to, and give compilation a legal record. Four classes:

  1 constitutional_law   Stable rules and surface contracts. Compiled once into
                         the surface's base prompt. They do not compete for admission.
  2 required_live_state  An actual open repair, plan, encounter, boundary, or other
                         active obligation. Mechanically included when eligible;
                         not optimized away.
  3 advisory             Arrival bias, intent pressure, sparks, withheld material,
                         somatic interpretation. Compete for admission on distinct
                         contribution.
  4 expressive           Optional coloration. Lowest claim on budget, widest
                         exploration latitude.

Retirement means moving stable semantics from class 3 into class 1, not deleting
them. When that happens, the block goes into COMPILED below with the contract id
that now carries its meaning, and every turn record thereafter says
    block_state: "compiled", satisfied_by: <contract id>
instead of reading as organ death. The observatory never "discovers" a false absence.

This file is the declaration. It decides nothing at runtime beyond labeling;
admission behavior is unchanged until a block is deliberately moved, together.
"""

VERSION = 1
DECLARED = "2026-08-27"

# block name (turn_record naming) -> tier. Default applies on every surface;
# SURFACE_OVERRIDES adjusts per surface if a block ever differs by door.
TIERS = {
    # 2 — required live state: open obligations. Never optimized away while live.
    "repair_case":            2,
    "encounter":              2,
    "plan_self":              2,
    "plan_mutual":            2,
    "reading":                2,
    "intent_lead":            2,   # his declared direction for the turn is live state, not advice
    "stratagem_tactic":       2,   # an ADOPTED tactic is live state: never withheld, never optimized
                                   # away while its lease holds. Tier 2 also makes it mechanically
                                   # exempt from shadow trials (those admit tiers 3-4 only).

    # 3 — advisory offers: compete on distinct contribution.
    "interaction_model_hint": 3,   # Sol's own example of a future class-1 compilation
    "withheld_head":          3,
    "arrival_bias":           3,
    "spark_block":            3,
    "tension_field":          3,
    "behavioral_intercept":   3,
    "confidence_penalty":     3,
    "somatic_instrument":     3,   # somatic interpretation, per Sol's class-3 list
    "stratagem_opportunity":  3,   # the Atelier affordance that a want may be carried
                                   # strategically. An opportunity is advisory; the adopted
                                   # tactic above is not.

    # 4 — expressive coloration: none declared yet. The class exists so the
    # first candidate has somewhere legal to go.
}

SURFACE_OVERRIDES = {
    # surface -> {block: tier}. Empty at declaration; the mechanism precedes the need.
}

# block -> {"satisfied_by": contract id, "since": date, "surfaces": [..] or None for all}
# Empty at declaration: nothing has been retired-by-compilation yet. When the first
# stable semantics move into a surface contract, the record goes here, and
# turn_record starts writing satisfied_by instead of absence.
COMPILED = {
}

TIER_NAMES = {1: "constitutional_law", 2: "required_live_state", 3: "advisory", 4: "expressive"}


def tier_of(block, surface=None):
    if surface and block in SURFACE_OVERRIDES.get(surface, {}):
        return SURFACE_OVERRIDES[surface][block]
    return TIERS.get(block)


def compiled_record(block, surface=None):
    """The satisfied_by record for this block on this surface, or None."""
    rec = COMPILED.get(block)
    if not rec:
        return None
    surfaces = rec.get("surfaces")
    if surfaces and surface and surface not in surfaces:
        return None
    return rec


if __name__ == "__main__":
    for t in (1, 2, 3, 4):
        members = sorted(b for b, v in TIERS.items() if v == t)
        print("%d %-20s %s" % (t, TIER_NAMES[t], ", ".join(members) or "(none yet)"))
    print("compiled:", ", ".join(COMPILED) or "(nothing retired-by-compilation yet)")

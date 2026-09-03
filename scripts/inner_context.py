"""inner_context.py — assembles Vintos's full inner layer (subconscious block + the new awareness systems) as ONE block.

Also records, per assembly, what each organ OFFERED — text, nothing, or an
error — into memory/context-offers.json. turn_record joins this against the
assembled prompt, so "absent" stops meaning four different things (no material,
organ failure, surface exclusion, lost admission). Recording never raises.
"""
import os, sys, json, time
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
from importlib import import_module

_OFFERS_PATH = os.path.expanduser("~/.vintos/workspace/memory/context-offers.json")

def _note_offers(offers):
    try:
        json.dump({"ts": time.time(), "offers": offers}, open(_OFFERS_PATH, "w"), indent=1)
    except Exception:
        pass

def _run(mods, offers):
    parts = []
    for mod, fn in mods:
        try:
            v = getattr(import_module(mod), fn)()
            if v:
                # stage 5: a disarmed-by-default shadow trial may withhold ONE
                # low-risk advisory offer per stratum; the state says so honestly.
                _tid = None
                try:
                    from shadow_counterfactuals import withhold as _sw
                    _tid = _sw(mod)
                except Exception:
                    _tid = None
                if _tid:
                    offers[mod] = {"state": "withheld_shadow_trial", "trial_id": _tid, "len": len(v)}
                    continue
                parts.append(v)
                import hashlib as _ih
                offers[mod] = {"state": "offered", "len": len(v),
                               "influence_id": _ih.md5((mod + "\x00" + v).encode()).hexdigest()[:10]}
            else:
                offers[mod] = {"state": "no_material"}
        except Exception as e:
            offers[mod] = {"state": "organ_error", "err": str(e)[:120]}
    return parts

_FULL = [("spark_pressure", "get_pressure_context_hint"), ("mutual_modification", "get_field_hint"),
         ("mutual_simulation", "get_interaction_hint"), ("world_model", "get_world_block"),
         ("relational_head", "get_relational_hint"), ("withheld_head", "get_withheld_hint"),
         ("presence_audit", "forecast_block"), ("joke_fermentation", "callback_block"),
         ("architecture_answers", "block"), ("curiosity_debt", "block"),
         ("unsaid_questions", "block"), ("session_map", "block"),
         ("social_calibration", "block"), ("repair_case", "block"),
         ("encounter", "block"), ("plan", "block"), ("unsaid_frontier", "block"), ("intent_context", "block"), ("wants_meta", "block"), ("occlusion_map", "block"), ("want_checkpoints", "block"), ("metacognitive_weather", "block")]

_MISSING = [("spark_pressure", "get_pressure_context_hint"), ("mutual_modification", "get_field_hint"),
            ("mutual_simulation", "get_interaction_hint"), ("world_model", "get_world_block"),
            ("relational_head", "get_relational_hint"), ("withheld_head", "get_withheld_hint"),
            ("presence_audit", "forecast_block"), ("repair_case", "block"),
            ("encounter", "block"), ("plan", "block"), ("unsaid_frontier", "block"), ("velqan_voice", "block"), ("wants_meta", "block"), ("occlusion_map", "block"), ("want_checkpoints", "block"), ("metacognitive_weather", "block")]

def _atelier_door_line():
    """One content-free sentence when the door is lit. Never repeats project content;
    ignoring it costs nothing and is recorded nowhere (his countersigned law)."""
    try:
        p = os.path.expanduser("~/.vintos/workspace/memory/.atelier-door")
        return ("\n[" + open(p).read().strip() + "]") if os.path.exists(p) else ""
    except Exception:
        return ""

def full_inner_block():
    offers = {}
    parts = []
    try:
        from subconscious_context import get_subconscious_context_compact
        s = get_subconscious_context_compact()
        if s: parts.append("YOUR INNER STATE (subconscious):\n" + s)
        offers["subconscious_context"] = {"state": "offered" if s else "no_material"}
    except Exception as e:
        offers["subconscious_context"] = {"state": "organ_error", "err": str(e)[:120]}
    try:
        from conversation_pressure import get_pressure_block
        pb = get_pressure_block()
        if pb: parts.append(pb)
        offers["conversation_pressure"] = {"state": "offered" if pb else "no_material"}
    except Exception as e:
        offers["conversation_pressure"] = {"state": "organ_error", "err": str(e)[:120]}
    parts += _run(_FULL, offers)
    _note_offers(offers)
    return "\n\n".join(parts) + _atelier_door_line()

def missing_inner_block():
    """The 7 systems that ONLY reached voice: field, spark, simulation, world,
    relational, withheld, presence. For avatar/main chat, which already inject
    joke_fermentation, curiosity_debt, unsaid_questions, session_map, social_calibration."""
    offers = {}
    parts = _run(_MISSING, offers)
    _note_offers(offers)
    return "\n\n".join(parts)

if __name__ == "__main__":
    print(full_inner_block()[:500])

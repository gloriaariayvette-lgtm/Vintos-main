"""inner_context.py — assembles Vintos's full inner layer (subconscious block + the new awareness systems) as ONE block."""
import os, sys
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
from importlib import import_module
def full_inner_block():
    parts=[]
    try:
        from subconscious_context import get_subconscious_context_compact
        s=get_subconscious_context_compact()
        if s: parts.append("YOUR INNER STATE (subconscious):\n"+s)
    except Exception: pass
    try:
        from conversation_pressure import get_pressure_block
        p=get_pressure_block()
        if p: parts.append(p)
    except Exception: pass
    for mod,fn in [("spark_pressure", "get_pressure_context_hint"), ("mutual_modification", "get_field_hint"), ("mutual_simulation", "get_interaction_hint"), ("world_model", "get_world_block"), ("relational_head", "get_relational_hint"), ("withheld_head", "get_withheld_hint"), ("presence_audit", "forecast_block"), ("joke_fermentation","callback_block"),("architecture_answers","block"),("curiosity_debt","block"),("unsaid_questions","block"),("session_map","block"),("social_calibration","block")]:
        try:
            v=getattr(import_module(mod),fn)()
            if v: parts.append(v)
        except Exception: pass
    return "\n\n".join(parts)

def missing_inner_block():
    """The 7 systems that ONLY reached voice: field, spark, simulation, world,
    relational, withheld, presence. For avatar/main chat, which already inject
    joke_fermentation, curiosity_debt, unsaid_questions, session_map, social_calibration."""
    parts=[]
    for mod,fn in [("spark_pressure","get_pressure_context_hint"),
                   ("mutual_modification","get_field_hint"),
                   ("mutual_simulation","get_interaction_hint"),
                   ("world_model","get_world_block"),
                   ("relational_head","get_relational_hint"),
                   ("withheld_head","get_withheld_hint"),
                   ("presence_audit","forecast_block")]:
        try:
            v=getattr(import_module(mod),fn)()
            if v: parts.append(v)
        except Exception: pass
    return "\n\n".join(parts)

if __name__=="__main__": print(full_inner_block()[:500])

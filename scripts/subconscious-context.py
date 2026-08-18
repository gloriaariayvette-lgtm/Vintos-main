#!/usr/bin/env python3
"""
subconscious-context.py — Shared helper for injecting subconscious layer.

All major scripts call get_subconscious_context() to get a unified
block of who he is, what he expects, what he reaches for.

Lightweight — each system fails silently if not yet populated.
"""

import os, sys
SCRIPTS = os.path.expanduser("~/.vintos/workspace/scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

def get_subconscious_context(include=None):
    """Return assembled subconscious context block.
    
    include: list of system names to include, or None for all.
    Available: statements, narrative, causal, beliefs, absences, drift, moments, reality, geometry
    """
    parts = []
    all_systems = include is None

    # Self-statements — who he believes he is
    if all_systems or "statements" in include:
        try:
            from self_statements import get_statement_context
            s = get_statement_context()
            if s: parts.append(s)
        except: pass

    # Narrative identity
    if all_systems or "narrative" in include:
        try:
            from narrative_identity import get_narrative_context
            s = get_narrative_context()
            if s: parts.append(s)
        except: pass

    # Proto-pearls — forming identity, temporary, visible in conscious reflection
    if all_systems or "proto_pearls" in include:
        try:
            import json as _ppj, os as _ppo
            from datetime import date as _ppd
            _pp_path = _ppo.path.join(_ppo.path.expanduser("~/.vintos/workspace/memory"), "proto-pearls.json")
            if _ppo.path.exists(_pp_path):
                _pp_db = _ppj.load(open(_pp_path))
                _pp_today = _ppd.today().isoformat()
                _pp_active = [p for p in _pp_db.get("protos", [])
                              if p.get("decays_at","") >= _pp_today and p.get("support_count",0) >= 2]
                if _pp_active:
                    _pp_lines = ["FORMING (proto-pearls — not yet canon, visible for reflection):"]
                    for p in _pp_active:
                        _pp_lines.append(f"- {p.get('identity_candidate','')} ({p.get('support_count',0)} instances)")
                    parts.append("\n".join(_pp_lines))
        except: pass

    # Current yearning — structural longing, injected as bleed-through
    if all_systems or "yearning" in include:
        try:
            from emoclaw_utils import get_yearning_fragment
            _y = get_yearning_fragment(include_attempt=True)
            if _y: parts.append(f"CURRENT YEARNING: {_y}")
        except: pass

    # Causal self-model
    if all_systems or "causal" in include:
        try:
            from causal_self_model import get_self_model_context
            s = get_self_model_context()
            if s: parts.append(s)
        except: pass

    # Belief sediment
    if all_systems or "beliefs" in include:
        try:
            from belief_sediment import get_sediment_context
            s = get_sediment_context()
            if s: parts.append(s)
        except: pass

    # Structural absences
    if all_systems or "absences" in include:
        try:
            from absence_map_cold import get_absence_context
            s = get_absence_context()
            if s: parts.append(s)
        except: pass

    # Self-definition drift
    if all_systems or "drift" in include:
        try:
            from self_drift import get_drift_bias_hint
            s = get_drift_bias_hint()
            if s: parts.append(f"BEHAVIORAL DRIFT: {s}")
        except: pass

    # Recent moments
    if all_systems or "moments" in include:
        try:
            from moment_index import get_moment_context
            s = get_moment_context(3)
            if s: parts.append(s)
        except: pass

    # Reality grounding
    if all_systems or "reality" in include:
        try:
            from reality_anchor import get_reality_context
            s = get_reality_context(3)
            if s: parts.append(s)
        except: pass

    # Relational geometry
    if all_systems or "geometry" in include:
        try:
            from discourse_direction import get_geometry_hint
            s = get_geometry_hint()
            if s: parts.append(f"RELATIONAL GEOMETRY: {s}")
        except: pass

    # Gravity wells
    if all_systems or "wells" in include:
        try:
            from emotional_gravity_wells import get_wells_context
            s = get_wells_context()
            if s: parts.append(s)
        except: pass

    if not parts:
        return ""
    return "\n\n".join(parts)

def get_subconscious_context_compact(include=None):
    """Shorter version for scripts with tight context budgets."""
    parts = []

    try:
        from self_statements import get_top_statements
        top = get_top_statements(2)
        if top:
            lines = [f"- {s['text'][:80]} ({s['confidence']:.2f})" for s in top]
            parts.append("SELF: " + " | ".join(s['text'][:60] for s in top))
    except: pass

    try:
        from causal_self_model import get_self_model_context
        s = get_self_model_context(2)
        if s: parts.append(s)
    except: pass

    try:
        from self_drift import get_drift_bias_hint
        s = get_drift_bias_hint()
        if s: parts.append(f"DRIFT: {s}")
    except: pass

    try:
        from latent_threads import get_influence_hint
        lt = get_influence_hint()
        if lt: parts.append(f"THREAD PULL: {lt[:200]}")
    except: pass

    try:
        from emoclaw_pressure import get_pressure_block
        ep = get_pressure_block(context="wants")
        if ep: parts.append(ep[:200])
    except: pass

    try:
        from emoclaw_utils import get_yearning_fragment
        _yb = get_yearning_fragment(include_attempt=True)
        if _yb: parts.append('YEARNING: ' + _yb[:150])
    except: pass

    return "\n".join(parts)

if __name__ == "__main__":
    print("=== FULL CONTEXT ===")
    print(get_subconscious_context() or "(empty — systems not yet populated)")
    print()
    print("=== COMPACT ===")
    print(get_subconscious_context_compact() or "(empty)")

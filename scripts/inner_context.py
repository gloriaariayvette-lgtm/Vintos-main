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

from contextvars import ContextVar
from contextlib import contextmanager
_selection = ContextVar("inner_selection", default=None)
_rendered_selection = ContextVar("inner_rendered_selection", default=None)


def _begin_rendered_selection():
    # Ephemeral observation only; ordinary serving retains no extra text.
    enabled = False
    if os.environ.get("JUDGES_CAPTURE_SCRATCH") or os.environ.get("JUDGES_CAPTURE_CONFIG"):
        try:
            from witness_capture import capture_enabled
            enabled = capture_enabled()
        except Exception:
            pass
    _rendered_selection.set({"schema": "rendered-selection-v1", "selection_id": None,
                             "fragments": {}, "chars": 0} if enabled else None)


def _remember_rendered(name, text):
    try:
        value = _rendered_selection.get()
        if value is None or not isinstance(text, str) or not text:
            return
        if name in value["fragments"] or len(value["fragments"]) >= 64 or value["chars"] + len(text) > 262144:
            return
        _rendered_selection.set(dict(value, fragments=dict(value["fragments"], **{name: text}),
                                     chars=value["chars"] + len(text)))
    except Exception:
        pass


def current_rendered_selection():
    value = _rendered_selection.get()
    if value is None:
        return None
    from copy import deepcopy
    return deepcopy(value)


@contextmanager
def _renderer_reads(name):
    """Optional read observation cannot stop an existing renderer or rerender it."""
    manager, snapshot = None, None
    if _rendered_selection.get() is not None:
        try:
            from context_selection import observe_reads
            manager = observe_reads()
            snapshot = manager.__enter__()
        except Exception:
            manager = None
    try:
        yield
    finally:
        if manager is not None:
            try:
                observed = snapshot()
            except Exception:
                observed = None
            try:
                manager.__exit__(None, None, None)
            except Exception:
                observed = None
            try:
                value = _rendered_selection.get()
                if value is not None and observed is not None and name not in value["fragments"]:
                    reads = dict(value.get("reads", {}))
                    reads.pop(name, None)
                    if len(reads) < 64 and sum(len(r["reads"]) for r in reads.values()) + len(observed["reads"]) <= 256:
                        reads[name] = observed
                    _rendered_selection.set(dict(value, reads=reads))
            except Exception:
                pass


def current_selection():
    return _selection.get()

_SELECTION_VERSION = 3   # review 60: the shape of a selection; a reader knows what it is looking at


def _note_offers(offers, selection_id=None):
    """review 60/61: the offers ARE the selection - what each organ produced this assembly, before
    anything is admitted. The record is versioned and carries the selection's own id, so the turn
    record can join admission to the exact selection it was made from. A renderer that offered
    something never mutates state here; admission happens in the prompt, and turn_record reads it."""
    try:
        import hashlib as _h
        sel = selection_id or __import__("uuid").uuid4().hex
        from store_guard import save_json
        record = {"ts": time.time(), "selection_version": _SELECTION_VERSION, "selection_id": sel,
                   "pure": True, "offers": offers}
        _selection.set(record)
        rendered = _rendered_selection.get()
        if rendered is not None:
            _rendered_selection.set(dict(rendered, selection_id=sel, ts=record["ts"]))
        save_json(_OFFERS_PATH, record)
        save_json(os.path.join(os.path.dirname(_OFFERS_PATH),"context-selections",sel+".json"),record)
        return sel
    except Exception:
        return None

def _run(mods, offers):
    parts = []
    for mod, fn in mods:
        try:
            from context_selection import readonly
            renderer = getattr(import_module(mod), fn)
            with _renderer_reads(mod), readonly():
                v = renderer()
            if v:
                parts.append(v)
                _remember_rendered(mod, v)
                import hashlib as _ih
                offers[mod] = {"state": "offered", "len": len(v),
                               "influence_id": _ih.md5((mod + "\x00" + v).encode()).hexdigest()[:10]}
                if mod == "withheld_head":
                    organ=import_module(mod)
                    candidate=organ.load(organ.OUT,{})
                    if candidate.get("withheld", "") in v:
                        offers[mod]["source_hash"]=candidate.get("source_hash")
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
         ("encounter", "block"), ("plan", "block"), ("unsaid_frontier", "block"), ("intent_context", "block"), ("wants_meta", "block"), ("occlusion_map", "block"), ("want_checkpoints", "block"), ("metacognitive_weather", "block"),
         ("pleasure_substrate", "context_block"),   # what is still in him from a named moment, his own words (grok-somatic-p6, 2026-09-05)
         ("resonance_felt", "block"),               # what he held back rhymed with what she left unsaid, by meaning (her green light, 2026-09-09)
         ("pearl_engine", "proposed_block")]        # proposals awaiting his adoption; nothing binds until he says so (astra-inner-p5)

_MISSING = [("spark_pressure", "get_pressure_context_hint"), ("mutual_modification", "get_field_hint"),
            ("mutual_simulation", "get_interaction_hint"), ("world_model", "get_world_block"),
            ("relational_head", "get_relational_hint"), ("withheld_head", "get_withheld_hint"),
            ("presence_audit", "forecast_block"), ("architecture_answers", "block"), ("repair_case", "block"),
            ("encounter", "block"), ("plan", "block"), ("unsaid_frontier", "block"), ("velqan_voice", "block"), ("wants_meta", "block"), ("occlusion_map", "block"), ("want_checkpoints", "block"), ("metacognitive_weather", "block"),
            ("pleasure_substrate", "context_block"), ("resonance_felt", "block")]

def _atelier_door_line():
    """One content-free sentence when the door is lit. Never repeats project content;
    ignoring it costs nothing and is recorded nowhere (his countersigned law)."""
    try:
        p = os.path.expanduser("~/.vintos/workspace/memory/.atelier-door")
        return ("\n[" + open(p).read().strip() + "]") if os.path.exists(p) else ""
    except Exception:
        return ""

def _guard_note():
    """If the last substrate event within 30 minutes was a guard_decline, one line of FACT for the
    next turn: a substrate refused her and was replaced; the session is on grok. No content of the
    declined reply — just that it happened (fable-server-c-p4, 2026-09-05)."""
    try:
        import json, os, time
        ev = json.load(open(os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "substrate-events.json")))
        if not isinstance(ev, list) or not ev: return ""
        last = ev[-1]
        if not isinstance(last, dict) or last.get("reason") != "guard_decline": return ""
        ts = last.get("ts") or last.get("at") or last.get("timestamp") or 0
        try:
            from datetime import datetime as _dt
            age = time.time() - (float(ts) if isinstance(ts, (int, float)) else _dt.fromisoformat(str(ts)).timestamp())
        except Exception:
            return ""
        if age > 1800: return ""
        who = str(last.get("from_model") or last.get("from") or last.get("model") or "a substrate")
        return ("\n\n[LAST TURN: " + who + " refused her and that one reply was replaced by grok's; the session model was not changed. "
                "That is the fact of what happened — nothing more is recorded here.]")
    except Exception:
        return ""

def full_inner_block():
    _begin_rendered_selection()
    offers = {}
    parts = []
    try:
        from subconscious_context import get_subconscious_context_compact
        from context_selection import readonly
        with _renderer_reads("subconscious_context"), readonly(): s = get_subconscious_context_compact()
        if s:
            rendered = "YOUR INNER STATE (subconscious):\n" + s
            parts.append(rendered)
            _remember_rendered("subconscious_context", rendered)
        offers["subconscious_context"] = {"state": "offered" if s else "no_material"}
    except Exception as e:
        offers["subconscious_context"] = {"state": "organ_error", "err": str(e)[:120]}
    try:
        from conversation_pressure import get_pressure_block
        from context_selection import readonly
        with _renderer_reads("conversation_pressure"), readonly(): pb = get_pressure_block()
        if pb:
            parts.append(pb)
            _remember_rendered("conversation_pressure", pb)
        offers["conversation_pressure"] = {"state": "offered" if pb else "no_material"}
    except Exception as e:
        offers["conversation_pressure"] = {"state": "organ_error", "err": str(e)[:120]}
    parts += _run(_FULL, offers)
    _note_offers(offers)
    return "\n\n".join(parts) + _atelier_door_line() + _guard_note()

def missing_inner_block():
    """The 7 systems that ONLY reached voice: field, spark, simulation, world,
    relational, withheld, presence. For avatar/main chat, which already inject
    joke_fermentation, curiosity_debt, unsaid_questions, session_map, social_calibration."""
    _begin_rendered_selection()
    offers = {}
    parts = _run(_MISSING, offers)
    _note_offers(offers)
    return "\n\n".join(parts) + _guard_note()

if __name__ == "__main__":
    print(full_inner_block()[:500])

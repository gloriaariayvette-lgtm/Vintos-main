"""Durable per-event admission for browser-to-provider realtime voice.
Providers never receive a standing capsule in session instructions. The client
requests one response at a time, and holds audio until complete() rechecks it.
"""
import json
import os
from pathlib import Path
import hashlib
import stratagem
from stratagem_turn import Interaction, control
import turn_coordinator as tc
from store_guard import transaction, write_json


def _path(event_id):
    key = hashlib.sha256(str(event_id).encode()).hexdigest()
    return str(Path(os.path.expanduser('~/.vintos/workspace/memory/stratagem-voice')) / (key + '.json'))


def _read(path):
    try:
        with open(path) as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None


def admit(raw, event_id, hold=False):
    """hold: a call he started (attention_call.py), whose words wait for her yes before any memory of his takes
    them; the intent engine's capture of her answer is skipped for it."""
    if not event_id:
        return {'error': 'provider event identity required'}
    path = _path(event_id)
    with transaction(path):
        if _read(path):
            return {'duplicate': True}
        command = control(raw)
        if command is not None:
            write_json(path, {'control': True, 'completed': True, 'event_id': event_id})
            return {'control_reply': command}
        session = Interaction(raw, 'voice', event_id=event_id)
        if session.turn.duplicate_event:
            return {'duplicate': True}
        prompt = session.prompt()
        intent_target = None
        try:
            from intent_engine import note_response
            if not hold:
                note_response(raw)
            from intent_context import admit_voice_lead
            intent_target, intent_prompt = admit_voice_lead(event_id)
            if intent_prompt:
                prompt += "\n\n" + intent_prompt
        except Exception:
            pass
        session.admitted(prompt)
        write_json(path, {'event_id': event_id, 'turn_id': session.turn.turn_id, 'commitment': session.turn.commitment,
                          'barrier': session.turn.barrier, 'completed': False, 'intent_target': intent_target})
        return {'instructions': prompt, 'event_id': event_id}


def context(event_id):
    rec = _read(_path(event_id))
    if not rec or rec.get('control'):
        return None
    from effect_gate import TurnContext
    return TurnContext(rec['turn_id'], 'voice', capsule_commitment=rec.get('commitment'), barrier=rec.get('barrier'))


def complete(event_id, reply):
    path = _path(event_id)
    with transaction(path):
        rec = _read(path)
        if not rec or rec.get('completed'):
            return {'allowed': False, 'reply': '', 'duplicate': bool(rec)}
        # Claim once BEFORE adopting any private candidate from the output.
        rec['completed'] = True
        write_json(path, rec)
        commitment = rec.get('commitment') or {}
        if not stratagem.still_eligible(commitment):
            return {'allowed': False, 'reply': ''}
        cleaned = stratagem.consume(reply, 'voice', commitment=commitment)
        if commitment:
            tc._post('/stratagem/disposition', {'id': commitment['stratagem_project'],
                'turn_id': rec['turn_id'], 'capsule_sha256': commitment['capsule_sha256'],
                'axes': {'generation': 'created'}})
        return {'allowed': True, 'reply': cleaned, 'changed': cleaned != reply}


def eligible(event_id):
    rec = _read(_path(event_id))
    return {'allowed': bool(rec and not rec.get('control') and
                            stratagem.still_eligible(rec.get('commitment') or {}))}


def record_intent_delivery(event_id, reply, raw=""):
    """A server-trusted admission, joined to the actual spoken words by event id."""
    rec = _read(_path(event_id))
    if not rec or rec.get("control") or not rec.get("completed") or not rec.get("intent_target"):
        return False
    if not stratagem.still_eligible(rec.get("commitment")):
        return False
    from intent_engine import record_delivery
    return record_delivery(reply, "voice", rec["turn_id"], target=rec["intent_target"], input_text=raw)

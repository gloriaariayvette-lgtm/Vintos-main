"""Shared adapter for generation paths that do not already own a coordinated turn.
No provider calls here. Private control tags are consumed before public writers.
"""
from contextvars import ContextVar
import re
import stratagem
import turn_coordinator as tc

current = ContextVar("stratagem_turn", default=None)


def control(raw):
    # The coordinator persists and retries a global stop even if the broker is down.
    import constitutional_barrier as cb
    if cb.strategy_stop_requested(raw):
        ok = tc._strategy_stop(raw, cb)
        return "Stratagem stop acknowledged." if ok else "Stop recorded; delivery pending. Tactics are held."
    return stratagem.owner_command(raw)


def redact(text):
    return stratagem.redact(text)


def guard_reply(reply, turn=None):
    turn = turn or current.get()
    if turn is not None and not stratagem.still_eligible(turn.commitment):
        return ""
    return reply


class Interaction:
    def __init__(self, raw, surface, event_id=None, test_mode=False):
        self.turn = tc.begin(raw, surface, test_mode=test_mode, event_id=event_id)
        self.surface = surface
        self.raw = raw

    def prompt(self):
        return "\n\n" + self.turn.capsule_block + "\n\n" + stratagem.opportunity(self.surface)

    def admitted(self, prompt):
        tc.mark_admitted(self.turn)
        tc.record(self.turn, prompt, self.raw)

    def complete(self, reply):
        if self.turn.duplicate_event:
            return ""
        tc.mark_lifecycle(self.turn, "generation", "created")
        # Cancellation, revocation and expiration apply even during inference.
        if not stratagem.still_eligible(self.turn.commitment):
            tc.mark_lifecycle(self.turn, "transport", "HELD", "stratagem no longer eligible")
            tc.finish(self.turn, None, "capsule_unrealized")
            return ""
        reply = stratagem.consume(reply, self.surface, commitment=self.turn.commitment)
        tc.finish(self.turn, reply, "response_created")
        return reply

    def failed(self):
        tc.finish(self.turn, None, "generation_failed")

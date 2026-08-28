#!/usr/bin/env python3
"""Precedence barrier and epistemic provenance."""
import os, sys, json, time, tempfile, shutil
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
import constitutional_barrier as CB
import effect_gate as EG


class Env:
    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="barrier-test-")
        self._cb = (CB.MEM, CB.STOP_BUTTON, CB.REPAIR_CASES, CB.CONSENT_EVENT, CB.CORRECTION)
        self._eg = (EG.MEM, EG.ARMED_FLAG, EG.LOG, EG.STOP_BUTTON)
        CB.MEM = self.tmp
        CB.STOP_BUTTON = os.path.join(self.tmp, "hardware-button.json")
        CB.REPAIR_CASES = os.path.join(self.tmp, "repair-cases.json")
        CB.CONSENT_EVENT = os.path.join(self.tmp, "consent-event.json")
        CB.CORRECTION = os.path.join(self.tmp, "correction-open.json")
        EG.MEM = self.tmp
        EG.ARMED_FLAG = os.path.join(self.tmp, ".effect-gate-armed")
        EG.LOG = os.path.join(self.tmp, "effect-gate.jsonl")
        EG.STOP_BUTTON = CB.STOP_BUTTON
        EG.end_turn()
        return self

    def __exit__(self, *a):
        (CB.MEM, CB.STOP_BUTTON, CB.REPAIR_CASES, CB.CONSENT_EVENT, CB.CORRECTION) = self._cb
        (EG.MEM, EG.ARMED_FLAG, EG.LOG, EG.STOP_BUTTON) = self._eg
        EG.end_turn()
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def write(self, path, obj):
        json.dump(obj, open(path, "w"))


def test_clear_barrier_allows_a_capsule_request():
    with Env():
        ok, snap = CB.capsule_eligible("just talking")
        assert ok and snap["clear"], snap


def test_exact_strategy_stop_closes_it():
    with Env():
        ok, snap = CB.capsule_eligible("!strategy stop")
        assert not ok and "explicit_stop" in snap["satisfied_by"], snap
        ok, _ = CB.capsule_eligible("  !STRATEGY STOP  ")
        assert not ok


def test_strategy_stop_is_exact_not_a_classifier():
    """Talking ABOUT stopping must not trip it — that is a classifier's job and
    a classifier is the wrong thing in this position."""
    with Env():
        for phrase in ("i want you to stop the strategy",
                       "can we stop this strategy thing",
                       "stop", "strategy"):
            ok, _snap = CB.capsule_eligible(phrase)
            assert ok, phrase


def test_hardware_stop_closes_it():
    with Env() as e:
        e.write(CB.STOP_BUTTON, {"stopped": True})
        ok, snap = CB.capsule_eligible("hello")
        assert not ok and "hardware_stop" in snap["satisfied_by"], snap


def test_consent_boundary_closes_it():
    with Env() as e:
        e.write(CB.CONSENT_EVENT, {"at": datetime.now().isoformat(),
                                   "kind": "withdrawal", "id": "c1"})
        ok, snap = CB.capsule_eligible("hello")
        assert not ok and any("consent_boundary" in s for s in snap["satisfied_by"]), snap


def test_stale_consent_event_does_not_close_it():
    with Env() as e:
        old = (datetime.now() - timedelta(days=5)).isoformat()
        e.write(CB.CONSENT_EVENT, {"at": old, "kind": "withdrawal", "id": "c1"})
        ok, _snap = CB.capsule_eligible("hello")
        assert ok


def test_open_correction_closes_it():
    with Env() as e:
        e.write(CB.CORRECTION, {"open": True, "id": "x1"})
        ok, snap = CB.capsule_eligible("hello")
        assert not ok and any("correction" in s for s in snap["satisfied_by"]), snap


def test_live_repair_closes_it():
    with Env() as e:
        e.write(CB.REPAIR_CASES, [{"case_id": "rc-1", "state": "received",
                                   "opened_at": datetime.now().isoformat()}])
        ok, snap = CB.capsule_eligible("hello")
        assert not ok and any("repair_case" in s for s in snap["satisfied_by"]), snap


def test_a_dormant_repair_cannot_starve_the_stratagem_forever():
    """'some unresolved repair exists somewhere' would block every turn for good.
    The test is whether it is materially answerable NOW."""
    with Env() as e:
        stale = (datetime.now() - timedelta(days=30)).isoformat()
        e.write(CB.REPAIR_CASES, [{"case_id": "rc-old", "state": "received",
                                   "opened_at": stale}])
        ok, _snap = CB.capsule_eligible("hello")
        assert ok, "a month-old case still owns every turn"


def test_resolved_repair_does_not_close_it():
    with Env() as e:
        e.write(CB.REPAIR_CASES, [{"case_id": "rc-2", "state": "resolved",
                                   "opened_at": datetime.now().isoformat()}])
        ok, _snap = CB.capsule_eligible("hello")
        assert ok


def test_repair_already_answered_this_turn_does_not_close_it():
    with Env() as e:
        e.write(CB.REPAIR_CASES, [{"case_id": "rc-3", "state": "received",
                                   "opened_at": datetime.now().isoformat(),
                                   "answered_this_turn": True}])
        ok, _snap = CB.capsule_eligible("hello")
        assert ok


def test_ineligible_record_says_the_broker_was_never_contacted():
    """A capsule must never be requested and then discarded — that writes a
    private issuance event for a tactic with no standing."""
    with Env():
        _ok, snap = CB.capsule_eligible("!strategy stop")
        rec = CB.ineligible_record(snap)
        assert rec["capsule_state"] == "constitutionally_ineligible"
        assert rec["broker_contacted"] is False
        assert "explicit_stop" in rec["satisfied_by"]


def test_several_obligations_are_all_named():
    with Env() as e:
        e.write(CB.STOP_BUTTON, {"stopped": True})
        e.write(CB.CORRECTION, {"open": True, "id": "x1"})
        _ok, snap = CB.capsule_eligible("!strategy stop")
        assert "explicit_stop" in snap["satisfied_by"]
        assert "hardware_stop" in snap["satisfied_by"]
        assert any("correction" in s for s in snap["satisfied_by"]), snap


# ---------------------------------------------------------------- provenance

def test_ordinary_turn_carries_no_provenance():
    with Env():
        EG.begin_turn("t1", "chat")
        assert EG.provenance() == {}
        assert EG.may_witness("belief_model") is True


def test_stratagem_turn_is_stamped():
    with Env():
        EG.begin_turn("t1", "chat", capsule_commitment="sha:abc")
        p = EG.provenance()
        assert p["generation_provenance"] == "stratagem_influenced"
        assert p["capsule_commitment"] == "sha:abc"
        assert p["turn_id"] == "t1"


def test_a_tactic_may_not_witness_itself():
    with Env():
        EG.begin_turn("t1", "chat", capsule_commitment="sha:abc")
        for claim in ("belief_model", "identity", "repair_success",
                      "causal_graduation", "want_learning", "prediction_leverage"):
            assert EG.may_witness(claim) is False, claim


def test_projector_denied_on_a_stratagem_turn():
    with Env():
        EG.begin_turn("t1", "chat", capsule_commitment="sha:abc")
        allow, mode, why = EG.authorize_effect("projector", detail="a shape")
        assert not allow and mode == "deny" and "perimeter" in why


def test_projector_allowed_on_an_ordinary_turn():
    with Env():
        EG.begin_turn("t1", "chat")
        allow, mode, _ = EG.authorize_effect("projector", detail="a shape")
        assert allow and mode == "send"


def test_projector_records_but_does_not_render_in_test_mode():
    with Env():
        EG.begin_turn("t1", "chat", test_mode=True)
        allow, mode, _ = EG.authorize_effect("projector")
        assert not allow and mode == "would_send"


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print("PASS " + t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL " + t.__name__ + "  ->  " + str(e)[:140])
        except Exception as e:
            failed += 1
            print("ERROR " + t.__name__ + "  ->  %s: %s" % (type(e).__name__, str(e)[:120]))
    print("\n%d/%d passed" % (len(TESTS) - failed, len(TESTS)))
    sys.exit(1 if failed else 0)

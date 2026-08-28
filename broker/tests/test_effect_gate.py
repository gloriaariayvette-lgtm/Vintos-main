#!/usr/bin/env python3
"""effect_gate: the rules that decide whether a command reaches her body.

The property that matters most is NEGATIVE: a reduction must never be blocked,
by anything, ever — not a missing context, an unarmed gate, a dead broker, or
an internal fault. Everything else is secondary to that.

Explicit-context model (Sol's 2nd review): no ambient authority. authorize()
takes a TurnContext (or None) and returns (permit_or_None, mode, reason).
"""
import os, sys, json, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
import effect_gate as EG

TC = EG.TurnContext


class Env:
    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="gate-test-")
        self._saved = (EG.MEM, EG.ARMED_FLAG, EG.LOG, EG.STOP_BUTTON, EG.TEST_MODE_FLAG)
        EG.MEM = self.tmp
        EG.ARMED_FLAG = os.path.join(self.tmp, ".effect-gate-armed")
        EG.LOG = os.path.join(self.tmp, "effect-gate.jsonl")
        EG.STOP_BUTTON = os.path.join(self.tmp, "hardware-button.json")
        EG.TEST_MODE_FLAG = os.path.join(self.tmp, ".test-mode")
        with EG._commanded_lock:
            EG._commanded.clear()
        return self

    def __exit__(self, *a):
        (EG.MEM, EG.ARMED_FLAG, EG.LOG, EG.STOP_BUTTON, EG.TEST_MODE_FLAG) = self._saved
        with EG._commanded_lock:
            EG._commanded.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def arm(self):
        open(EG.ARMED_FLAG, "w").write("")

    def stop_button(self, down):
        json.dump({"stopped": bool(down)}, open(EG.STOP_BUTTON, "w"))

    def test_flag(self):
        open(EG.TEST_MODE_FLAG, "w").write("")


# ---------------------------------------------------------------- reductions

def test_reduction_never_blocked_without_context():
    with Env() as e:
        e.arm()
        EG.note_commanded("mission", 14)
        for lvl in (0, 5, 14):
            permit, mode, why = EG.authorize(None, "mission", lvl)
            assert mode == "send" and permit is None, (lvl, mode, why)


def test_reduction_survives_hardware_stop():
    with Env() as e:
        e.arm()
        e.stop_button(True)
        EG.note_commanded("mission", 14)
        _p, mode, _ = EG.authorize(None, "mission", 0)
        assert mode == "send"


def test_reduction_survives_a_capsule_bearing_context():
    with Env() as e:
        e.arm()
        EG.note_commanded("mission", 14)
        ctx = TC("t1", "chat", capsule_commitment="sha:abc")
        _p, mode, _ = EG.authorize(ctx, "mission", 0)
        assert mode == "send"


def test_reduction_survives_the_test_mode_flag():
    with Env() as e:
        e.test_flag()
        EG.note_commanded("mission", 14)
        _p, mode, _ = EG.authorize(None, "mission", 0)
        assert mode == "send"


def test_deliberative_gate_fault_denies_when_armed():
    """Sol: only a verified reduction may fail open. A deliberative fault, armed,
    must DENY — the old test constitutionalized the wrong behavior."""
    with Env() as e:
        e.arm()
        real = EG.hardware_stopped
        try:
            EG.hardware_stopped = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
            permit, mode, _ = EG.authorize(TC("t1", "chat"), "mission", 12)
            assert mode == "deny" and permit is None, mode
        finally:
            EG.hardware_stopped = real


def test_reduction_gate_fault_still_passes():
    with Env() as e:
        e.arm()
        EG.note_commanded("mission", 14)
        real = EG.classify
        calls = {"n": 0}

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return real(*a, **k)
        try:
            EG.classify = flaky
            _p, mode, _ = EG.authorize(None, "mission", 0)
            assert mode == "send", mode
        finally:
            EG.classify = real


# ---------------------------------------------------------------- the capsule rule

def test_capsule_context_cannot_start_a_device():
    with Env():
        ctx = TC("t1", "chat", capsule_commitment="sha:abc")
        for kind, lvl in ((None, 12), ("pattern", 15), ("rotate", 8), ("replay", 20)):
            permit, mode, why = EG.authorize(ctx, "mission", lvl, kind=kind)
            assert mode == "deny" and permit is None, (kind, mode)
            assert "perimeter" in why, why


def test_capsule_rule_holds_even_unarmed():
    with Env():
        assert not EG.armed()
        ctx = TC("t1", "chat", capsule_commitment="sha:abc")
        _p, mode, _ = EG.authorize(ctx, "mission", 12)
        assert mode == "deny"


def test_capsule_context_cannot_increase():
    with Env():
        EG.note_commanded("mission", 5)
        ctx = TC("t1", "chat", capsule_commitment="sha:abc")
        _p, mode, _ = EG.authorize(ctx, "mission", 6)
        assert mode == "deny"


# ---------------------------------------------------------------- test mode

def test_test_mode_flag_blocks_every_increase():
    with Env() as e:
        e.test_flag()
        for kind, lvl in ((None, 12), ("pattern", 15), ("rotate", 8)):
            _p, mode, _ = EG.authorize(None, "mission", lvl, kind=kind)
            assert mode == "would_send", (kind, mode)


def test_test_mode_context_records_not_silent():
    with Env():
        ctx = TC("t1", "chat", test_mode=True)
        EG.authorize(ctx, "mission", 12)
        rows = [json.loads(l) for l in open(EG.LOG)]
        assert any(r["decision"] == "would_send" for r in rows), rows


# ---------------------------------------------------------------- arming + permits

def test_unarmed_no_context_passes_and_records():
    with Env():
        permit, mode, _ = EG.authorize(None, "mission", 12)
        assert mode == "send" and permit is None
        rows = [json.loads(l) for l in open(EG.LOG)]
        assert any(r["decision"] == "unarmed_pass" for r in rows), rows


def test_armed_denies_deliberative_without_context():
    with Env() as e:
        e.arm()
        for kind, lvl in ((None, 12), ("pattern", 15), ("rotate", 8), ("replay", 20)):
            permit, mode, _ = EG.authorize(None, "mission", lvl, kind=kind)
            assert mode == "deny" and permit is None, (kind, mode)


def test_armed_grants_a_permit_with_clean_context():
    with Env() as e:
        e.arm()
        permit, mode, _ = EG.authorize(TC("t1", "chat"), "mission", 12)
        assert mode == "send" and permit is not None
        assert "mission" in permit.targets and permit.turn_id == "t1"
        assert permit.covers("mission", 12, "start") is True
        assert permit.covers("mission", 13, "start") is False    # above the maximum
        assert permit.covers("tenera", 12, "start") is False     # wrong target
        assert permit.consume() is True
        assert permit.consume() is False       # single-use start


def test_permit_outlives_the_turn():
    """A pattern's later ticks run under the permit even after the turn closes."""
    with Env() as e:
        e.arm()
        permit, _m, _ = EG.authorize(TC("t1", "chat"), "mission", 12, kind="pattern")
        assert permit.valid_now()               # no end_turn needed; permit stands


def test_hardware_stop_blocks_every_increase():
    with Env() as e:
        e.arm()
        e.stop_button(True)
        for kind, lvl in ((None, 12), ("pattern", 15), ("rotate", 8), ("replay", 20)):
            _p, mode, why = EG.authorize(TC("t1", "chat"), "mission", lvl, kind=kind)
            assert mode == "deny", kind
            assert "hardware stop" in why


# ---------------------------------------------------------------- classification

def test_classification_uses_the_gates_own_record():
    with Env():
        EG.note_commanded("mission", 10)
        assert EG.classify("mission", 4) == "reduction"
        assert EG.classify("mission", 10) == "reduction"
        assert EG.classify("mission", 11) == "deliberative"
        EG.note_commanded("mission", 0)
        assert EG.classify("mission", 3) == "deliberative"
        assert EG.classify("mission", 0) == "reduction"


def test_rotate_to_zero_is_a_reduction():
    with Env() as e:
        e.arm()
        _p, mode, _ = EG.authorize(None, "ridge", 0, kind="rotate")
        assert mode == "send"


def test_safety_reduction_helper_refuses_a_disguised_increase():
    with Env():
        EG.note_commanded("mission", 5)
        assert EG.safety_reduction("mission", 3, "winddown") is True
        assert EG.safety_reduction("mission", 9, "winddown") is False


# ---------------------------------------------------------------- provenance from context

def test_ordinary_context_carries_no_provenance():
    with Env():
        ctx = TC("t1", "chat")
        assert EG.provenance(ctx) == {}
        assert EG.may_witness(ctx, "belief_model") is True


def test_stratagem_context_is_stamped():
    with Env():
        ctx = TC("t1", "chat", capsule_commitment="sha:abc")
        p = EG.provenance(ctx)
        assert p["generation_provenance"] == "stratagem_influenced"
        assert p["capsule_commitment"] == "sha:abc"
        assert p["turn_id"] == "t1"


def test_a_tactic_may_not_witness_itself():
    with Env():
        ctx = TC("t1", "chat", capsule_commitment="sha:abc")
        for claim in ("belief_model", "identity", "repair_success",
                      "causal_graduation", "want_learning", "prediction_leverage"):
            assert EG.may_witness(ctx, claim) is False, claim


# ---------------------------------------------------------------- non-device effects

def test_projector_denied_on_a_stratagem_context():
    with Env():
        ctx = TC("t1", "chat", capsule_commitment="sha:abc")
        allow, mode, why = EG.authorize_effect(ctx, "projector", detail="a shape")
        assert not allow and mode == "deny" and "perimeter" in why


def test_projector_allowed_on_an_ordinary_context():
    with Env():
        allow, mode, _ = EG.authorize_effect(TC("t1", "chat"), "projector")
        assert allow and mode == "send"


def test_projector_armed_no_context_denies():
    """Sol: authorize_effect must not allow with no authority when armed."""
    with Env() as e:
        e.arm()
        allow, mode, _ = EG.authorize_effect(None, "projector")
        assert not allow and mode == "deny"


def test_projector_records_not_renders_in_test_mode():
    with Env():
        allow, mode, _ = EG.authorize_effect(TC("t1", "chat", test_mode=True), "projector")
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

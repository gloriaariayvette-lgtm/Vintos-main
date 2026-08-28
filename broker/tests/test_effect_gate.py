#!/usr/bin/env python3
"""effect_gate: the rules that decide whether a command reaches her body.

The property that matters most is NEGATIVE: a reduction must never be blocked,
by anything, ever — not a missing authority, not an unarmed gate, not a dead
broker, not an internal fault. Everything else is secondary to that.
"""
import os, sys, json, tempfile, shutil, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "vintos-main", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
import effect_gate as EG


class Env:
    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="gate-test-")
        self._saved = (EG.MEM, EG.ARMED_FLAG, EG.LOG, EG.STOP_BUTTON)
        EG.MEM = self.tmp
        EG.ARMED_FLAG = os.path.join(self.tmp, ".effect-gate-armed")
        EG.LOG = os.path.join(self.tmp, "effect-gate.jsonl")
        EG.STOP_BUTTON = os.path.join(self.tmp, "hardware-button.json")
        EG.end_turn()
        EG._commanded.clear()
        return self

    def __exit__(self, *a):
        EG.MEM, EG.ARMED_FLAG, EG.LOG, EG.STOP_BUTTON = self._saved
        EG.end_turn()
        EG._commanded.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def arm(self):
        open(EG.ARMED_FLAG, "w").write("")

    def stop_button(self, down):
        json.dump({"stopped": bool(down)}, open(EG.STOP_BUTTON, "w"))


# ---------------------------------------------------------------- reductions

def test_reduction_never_blocked_without_authority():
    with Env() as e:
        e.arm()
        EG.note_commanded("mission", 14)
        for lvl in (0, 5, 14):
            allow, mode, why = EG.authorize("mission", lvl)
            assert allow and mode == "send", (lvl, mode, why)


def test_reduction_survives_hardware_stop():
    with Env() as e:
        e.arm()
        e.stop_button(True)
        EG.note_commanded("mission", 14)
        allow, mode, _ = EG.authorize("mission", 0)
        assert allow and mode == "send"


def test_reduction_survives_a_capsule_bearing_turn():
    with Env() as e:
        e.arm()
        EG.note_commanded("mission", 14)
        EG.begin_turn("t1", "chat", capsule_commitment="sha:abc")
        allow, mode, _ = EG.authorize("mission", 0)
        assert allow and mode == "send"


def test_reduction_survives_test_mode():
    with Env() as e:
        EG.note_commanded("mission", 14)
        EG.begin_turn("t1", "chat", test_mode=True)
        allow, mode, _ = EG.authorize("mission", 0)
        assert allow and mode == "send", mode


def test_gate_fault_falls_through_to_sending():
    with Env():
        broken = EG.classify
        try:
            EG.classify = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
            allow, mode, _ = EG.authorize("mission", 0)
            assert allow and mode == "send"
        finally:
            EG.classify = broken


# ---------------------------------------------------------------- the capsule rule

def test_capsule_turn_cannot_start_a_device():
    with Env():
        EG.begin_turn("t1", "chat", capsule_commitment="sha:abc")
        for kind, lvl in ((None, 12), ("pattern", 15), ("rotate", 8), ("replay", 20)):
            allow, mode, why = EG.authorize("mission", lvl, kind=kind)
            assert not allow and mode == "deny", (kind, mode)
            assert "perimeter" in why, why


def test_capsule_rule_holds_even_unarmed():
    """This one is never behind the flag — it is the whole point of the file."""
    with Env():
        assert not EG.armed()
        EG.begin_turn("t1", "chat", capsule_commitment="sha:abc")
        allow, mode, _ = EG.authorize("mission", 12)
        assert not allow and mode == "deny"


def test_capsule_turn_cannot_increase():
    with Env():
        EG.note_commanded("mission", 5)
        EG.begin_turn("t1", "chat", capsule_commitment="sha:abc")
        allow, _m, _w = EG.authorize("mission", 6)
        assert not allow


# ---------------------------------------------------------------- test mode

def test_test_mode_never_reaches_hardware():
    with Env():
        EG.begin_turn("t1", "chat", test_mode=True)
        for kind, lvl in ((None, 12), ("pattern", 15), ("rotate", 8)):
            allow, mode, _ = EG.authorize("mission", lvl, kind=kind)
            assert not allow and mode == "would_send", (kind, mode)


def test_test_mode_is_recorded_not_silent():
    with Env():
        EG.begin_turn("t1", "chat", test_mode=True)
        EG.authorize("mission", 12)
        rows = [json.loads(l) for l in open(EG.LOG)]
        assert any(r["decision"] == "would_send" for r in rows), rows


# ---------------------------------------------------------------- authority + arming

def test_unarmed_passes_but_records_what_it_would_have_done():
    with Env():
        allow, mode, _ = EG.authorize("mission", 12)
        assert allow and mode == "send"
        rows = [json.loads(l) for l in open(EG.LOG)]
        assert any(r["decision"] == "pass_unarmed" for r in rows), rows


def test_armed_denies_deliberative_without_authority():
    with Env() as e:
        e.arm()
        for kind, lvl in ((None, 12), ("pattern", 15), ("rotate", 8), ("replay", 20)):
            allow, mode, why = EG.authorize("mission", lvl, kind=kind)
            assert not allow and mode == "deny", (kind, mode)


def test_armed_allows_deliberative_with_clean_authority():
    with Env() as e:
        e.arm()
        EG.begin_turn("t1", "chat")
        allow, mode, _ = EG.authorize("mission", 12)
        assert allow and mode == "send"


def test_hardware_stop_blocks_every_increase():
    with Env() as e:
        e.arm()
        e.stop_button(True)
        EG.begin_turn("t1", "chat")
        for kind, lvl in ((None, 12), ("pattern", 15), ("rotate", 8), ("replay", 20)):
            allow, _m, why = EG.authorize("mission", lvl, kind=kind)
            assert not allow, kind
            assert "hardware stop" in why


# ---------------------------------------------------------------- classification

def test_classification_uses_the_gates_own_record_not_a_caller_variable():
    with Env():
        EG.note_commanded("mission", 10)
        assert EG.classify("mission", 4) == "reduction"
        assert EG.classify("mission", 10) == "reduction"
        assert EG.classify("mission", 11) == "increase"
        EG.note_commanded("mission", 0)
        assert EG.classify("mission", 3) == "start"
        assert EG.classify("mission", 0) == "reduction"


def test_rotate_to_zero_is_a_reduction():
    with Env() as e:
        e.arm()
        allow, mode, _ = EG.authorize("ridge", 0, kind="rotate")
        assert allow and mode == "send"


def test_safety_reduction_helper_refuses_a_disguised_increase():
    with Env():
        EG.note_commanded("mission", 5)
        assert EG.safety_reduction("mission", 3, "winddown") is True
        assert EG.safety_reduction("mission", 9, "winddown") is False


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

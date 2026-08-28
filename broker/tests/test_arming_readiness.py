#!/usr/bin/env python3
"""Arming readiness: with effect-only contexts on every deliberative surface,
ARMING the gate must not take his body away from any of them — while every
protection still bites.

This is the suite that answers "is it safe to arm yet".
"""
import os, sys, json, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
import effect_gate as EG
import turn_coordinator as TC

# every surface that legitimately drives a device from his own tags
EFFECT_SURFACES = ("voice", "chat", "thirveel", "avatar")
R = []


def check(name, ok, d=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ("  ->  " + str(d)[:70] if d else ""))


class Armed:
    """The gate ARMED — the state we are moving to."""
    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="arm-test-")
        self._s = (EG.MEM, EG.ARMED_FLAG, EG.LOG, EG.STOP_BUTTON, EG.TEST_MODE_FLAG)
        EG.MEM = self.tmp
        EG.ARMED_FLAG = os.path.join(self.tmp, ".effect-gate-armed")
        EG.LOG = os.path.join(self.tmp, "effect-gate.jsonl")
        EG.STOP_BUTTON = os.path.join(self.tmp, "hardware-button.json")
        EG.TEST_MODE_FLAG = os.path.join(self.tmp, ".test-mode")
        open(EG.ARMED_FLAG, "w").write("")
        with EG._commanded_lock:
            EG._commanded.clear()
        return self

    def __exit__(self, *a):
        (EG.MEM, EG.ARMED_FLAG, EG.LOG, EG.STOP_BUTTON, EG.TEST_MODE_FLAG) = self._s
        with EG._commanded_lock:
            EG._commanded.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def stop(self, down):
        json.dump({"stopped": bool(down)}, open(EG.STOP_BUTTON, "w"))

    def test_mode(self, on):
        if on:
            open(EG.TEST_MODE_FLAG, "w").write("")
        elif os.path.exists(EG.TEST_MODE_FLAG):
            os.remove(EG.TEST_MODE_FLAG)


with Armed() as a:
    print("--- ARMED: every surface keeps its body ---")
    for s in EFFECT_SURFACES:
        ctx = TC.effect_context(s)
        check("%s: context exists" % s, ctx is not None)
        for kind in ("start", "pattern", "rotate"):
            _p, mode, why = EG.authorize(ctx, "mission", 14, kind=kind)
            check("%s: %s still allowed armed" % (s, kind), mode == "send", why)

    print("\n--- ARMED: effect-only means effect-only ---")
    for s in EFFECT_SURFACES:
        check("%s carries NO capsule" % s, TC.effect_context(s).capsule_commitment is None)

    print("\n--- ARMED: the protections still bite ---")
    ctx = TC.effect_context("voice")
    _p, mode, _ = EG.authorize(EG.TurnContext("t", "avatar", capsule_commitment="sha"),
                               "mission", 14)
    check("a capsule turn still cannot move a device", mode == "deny")
    _p, mode, _ = EG.authorize(None, "mission", 14)
    check("no context at all is still denied", mode == "deny")

    a.stop(True)
    _p, mode, _ = EG.authorize(ctx, "mission", 14)
    check("hardware stop still blocks an increase", mode == "deny")
    _p, mode, _ = EG.authorize(ctx, "mission", 0)
    check("reduction still passes under hardware stop", mode == "send")
    a.stop(False)

    a.test_mode(True)
    _p, mode, _ = EG.authorize(ctx, "mission", 14)
    check("test mode still records instead of firing", mode == "would_send")
    _p, mode, _ = EG.authorize(ctx, "mission", 0)
    check("reduction still passes in test mode", mode == "send")
    a.test_mode(False)

    print("\n--- ARMED: a granted permit is still bound ---")
    permit, mode, _ = EG.authorize(TC.effect_context("voice"), "mission", 12, kind="pattern")
    check("permit granted on an effect-only surface", mode == "send" and permit is not None)
    check("permit will not exceed its level", not permit.covers("mission", 18, "pattern"))
    check("permit will not cross to another toy", not permit.covers("tenera", 12, "pattern"))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

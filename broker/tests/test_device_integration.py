#!/usr/bin/env python3
"""Loaded-path regressions for effect permits, transport wrappers, and leases."""
import json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts")
sys.path.insert(0, SCRIPTS)


class Response:
    status_code = 200

    def json(self):
        toys = {tid: {"status": "1"} for tid in (
            "18690ad0e996", "c09b9e4704ae", "f044d37536a9")}
        return {"code": 200, "data": {"toys": toys}}


class Requests:
    calls = []

    @classmethod
    def post(cls, url, json=None, timeout=None):
        cls.calls.append({"url": url, "json": json, "timeout": timeout})
        return Response()


# Prevent toy_link's import-time port probe from touching the network.
sys.modules["requests"] = Requests
import effect_gate as EG
import toy_link as TL
import device_patterns as DP


class Env:
    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="device-integration-")
        self.old = (EG.MEM, EG.LOG, EG.ARMED_FLAG, EG.STOP_BUTTON,
                    EG.TEST_MODE_FLAG)
        EG.MEM = self.tmp
        EG.LOG = os.path.join(self.tmp, "effect-decisions.jsonl")
        EG.ARMED_FLAG = os.path.join(self.tmp, ".effect-gate-armed")
        EG.STOP_BUTTON = os.path.join(self.tmp, "hardware-button.json")
        EG.TEST_MODE_FLAG = os.path.join(self.tmp, ".test-mode")
        open(EG.ARMED_FLAG, "w").write("")
        json.dump({"stopped": False}, open(EG.STOP_BUTTON, "w"))
        EG._commanded.clear()
        EG._execution_owners.clear()
        Requests.calls[:] = []
        return self

    def __exit__(self, *args):
        (EG.MEM, EG.LOG, EG.ARMED_FLAG, EG.STOP_BUTTON,
         EG.TEST_MODE_FLAG) = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def permit(kind="pattern", targets=None, maximum=20, digest="D"):
    ctx = EG.TurnContext("turn-loaded", "avatar")
    p, mode, why = EG.authorize(ctx, "mission", maximum, kind=kind,
                                targets=targets or {"mission"}, digest=digest)
    assert mode == "send", why
    assert p.consume()
    return p


def test_tracing_wrapper_forwards_permit_and_digest():
    with Env():
        p = permit()
        assert TL.send_pattern("mission", [4, 12, 20], 250, 10,
                               permit=p, effect_digest="D")
        assert Requests.calls[-1]["json"]["command"] == "Pattern"


def test_missing_or_wrong_digest_is_denied_when_armed():
    with Env():
        p = permit()
        before = len(Requests.calls)
        assert not TL.send_pattern("mission", [4, 12], permit=p)
        assert not TL.send_pattern("mission", [4, 12], permit=p,
                                   effect_digest="OTHER")
        assert len(Requests.calls) == before


def test_old_watchdog_cannot_stop_replacement():
    with Env():
        sent = []
        original = TL.send
        TL.send = lambda toy, level, **kw: sent.append((toy, level)) or True
        try:
            EG.claim_execution({"mission"}, "old")
            EG.claim_execution({"mission"}, "new")
            assert DP._stop_if_owned(["mission"], "old") == []
            assert sent == []
            assert DP._stop_if_owned(["mission"], "new") == ["mission"]
            assert sent == [("mission", 0)]
        finally:
            TL.send = original


def test_preset_is_bounded_and_reports_partial_broadcast():
    with Env():
        p = permit(targets=set(TL.TOYS), digest="B")
        calls = []
        original_send_pattern = TL.send_pattern
        original_schedule = DP._schedule_stop
        def fake_send_pattern(toy, strengths, interval_ms=250, seconds=0,
                              func=None, context=None, permit=None,
                              effect_digest=None):
            calls.append((toy, seconds, effect_digest))
            return toy != "ridge"
        TL.send_pattern = fake_send_pattern
        stops = []
        DP._schedule_stop = lambda toys, secs, effect_id: stops.append(
            (list(toys), secs, effect_id))
        try:
            outcome = {}
            assert DP.play("both", "climb", permit=p, effect_digest="B",
                           outcome=outcome)
            assert outcome["status"] == "partial", outcome
            assert outcome["targets"]["ridge"] == "failed"
            assert all(1 <= seconds <= EG.MAX_LEASE_SECONDS
                       for _toy, seconds, _digest in calls)
            assert all(digest == "B" for _toy, _seconds, digest in calls)
            assert stops and "ridge" not in stops[0][0]
        finally:
            TL.send_pattern = original_send_pattern
            DP._schedule_stop = original_schedule


def test_rotate_uses_rotate_permit_and_real_maximum():
    with Env():
        reply = DP.fire_his_intent("yes [DO: ridge rotate high]", EG.TurnContext(
            "turn-rotate", "avatar"))
        assert "[DO:" not in reply
        rotate_calls = [c for c in Requests.calls
                        if "Rotate:18" in str((c.get("json") or {}).get("action"))]
        assert rotate_calls, Requests.calls


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    passed = 0
    for test in TESTS:
        try:
            test()
            passed += 1
            print("PASS", test.__name__)
        except Exception as exc:
            print("FAIL", test.__name__, "->", type(exc).__name__, str(exc)[:160])
    print("\n%d/%d passed" % (passed, len(TESTS)))
    sys.exit(0 if passed == len(TESTS) else 1)

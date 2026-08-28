#!/usr/bin/env python3
"""turn_coordinator: the turn lifecycle. Barrier gating, capsule only when
clear, context carries commitment, disposition on finish, no capsule requested
when ineligible."""
import os, sys, json, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
import turn_coordinator as TC
import constitutional_barrier as CB
import effect_gate as EG

R = []


def check(name, ok, d=""):
    print(("PASS " if ok else "FAIL ") + name + ("  ->  " + str(d)[:90] if d else ""))
    R.append(bool(ok))


class Env:
    """Stub the broker HTTP and the capsule fetch; redirect all memory writes."""
    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="coord-test-")
        self._cb = (CB.MEM, CB.STOP_BUTTON, CB.REPAIR_CASES, CB.CONSENT_EVENT, CB.CORRECTION)
        CB.MEM = self.tmp
        CB.STOP_BUTTON = os.path.join(self.tmp, "hardware-button.json")
        CB.REPAIR_CASES = os.path.join(self.tmp, "repair-cases.json")
        CB.CONSENT_EVENT = os.path.join(self.tmp, "consent-event.json")
        CB.CORRECTION = os.path.join(self.tmp, "correction-open.json")
        self.posts = []
        self._post = TC._post
        TC._post = lambda path, body=None, timeout=2.0: self._fake_post(path, body)
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp
        os.makedirs(os.path.join(self.tmp, ".vintos", "workspace", "memory"), exist_ok=True)
        self.capsule = None            # set to (block, commitment) to simulate a live tactic
        import stratagem
        self._fc = stratagem.fetch_capsule
        stratagem.fetch_capsule = lambda tid, surf: (self.capsule or ("", {}))
        return self

    def __exit__(self, *a):
        (CB.MEM, CB.STOP_BUTTON, CB.REPAIR_CASES, CB.CONSENT_EVENT, CB.CORRECTION) = self._cb
        TC._post = self._post
        import stratagem
        stratagem.fetch_capsule = self._fc
        if self._home:
            os.environ["HOME"] = self._home
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def _fake_post(self, path, body):
        self.posts.append((path, body))
        if path == "/worktable_id":
            return {"id": "a1b2c3d4e5f6"}
        return {"ok": True}

    def write(self, path, obj):
        json.dump(obj, open(path, "w"))


def test_clear_turn_opens_without_a_capsule_when_none_live():
    with Env():
        t = TC.begin("just talking", "avatar")
        check("barrier clear", t.barrier["clear"], t.barrier)
        check("no capsule when none live", not t.carries_capsule and t.capsule_block == "", t.commitment)
        check("context exists", t.context is not None)
        TC.finish(t, "reply", outcome="completed")


def test_live_capsule_is_fetched_and_carried_when_clear():
    with Env() as e:
        e.capsule = ("[STRATAGEM — sealed capsule, step 1 of 2]\n...",
                     {"capsule_sha256": "abc", "stratagem_id": "sg-1", "seq": 3, "turn_id": "x"})
        t = TC.begin("just talking", "avatar")
        check("capsule block injected", "STRATAGEM" in t.capsule_block, t.capsule_block[:40])
        check("commitment carried", t.commitment.get("capsule_sha256") == "abc", t.commitment)
        check("context marks the tactic", t.context.capsule_commitment == t.commitment)
        check("provenance stamps the turn",
              EG.provenance(t.context).get("generation_provenance") == "stratagem_influenced")
        # begin() records ISSUED, not admitted — admission waits for injection
        check("issued disposition posted at begin",
              any(p[0] == "/stratagem/disposition" and p[1]["state"] == "issued"
                  for p in e.posts), e.posts)
        check("NOT admitted at begin",
              not any(p[1].get("state") == "admitted_to_prompt" for p in e.posts
                      if p[0] == "/stratagem/disposition"), e.posts)
        e.posts.clear()
        TC.mark_admitted(t)
        check("mark_admitted posts admitted_to_prompt",
              any(p[1].get("state") == "admitted_to_prompt" for p in e.posts
                  if p[0] == "/stratagem/disposition"), e.posts)


def test_no_capsule_requested_when_barrier_closed():
    with Env() as e:
        e.capsule = ("blk", {"capsule_sha256": "abc"})
        e.write(CB.STOP_BUTTON, {"stopped": True})       # hardware stop closes the barrier
        t = TC.begin("hello", "avatar")
        check("barrier closed", not t.barrier["clear"], t.barrier)
        check("no capsule carried", not t.carries_capsule, t.commitment)
        # crucial: /stratagem/capsule (via fetch) was NOT called — we stubbed
        # fetch_capsule, so assert no disposition/capsule broker traffic happened
        check("no capsule broker traffic when ineligible",
              not any(p[0] == "/stratagem/disposition" for p in e.posts), e.posts)
        # and an ineligible record was written locally
        f = os.path.join(os.environ["HOME"], ".vintos", "workspace", "memory", "capsule-ineligible.jsonl")
        check("ineligible record written", os.path.exists(f))


def test_strategy_stop_command_stops_and_blocks():
    with Env() as e:
        t = TC.begin("!strategy stop", "avatar")
        check("strategy-stop posted to broker",
              any(p[0] == "/stratagem/strategy-stop" for p in e.posts), e.posts)
        check("barrier closed by explicit stop",
              "explicit_stop" in t.barrier["satisfied_by"], t.barrier)


def test_finish_posts_disposition_for_a_capsule_turn():
    with Env() as e:
        e.capsule = ("blk", {"capsule_sha256": "abc", "stratagem_id": "sg-1"})
        t = TC.begin("hello", "avatar")
        e.posts.clear()
        TC.finish(t, "a reply", outcome="effects_completed")
        check("disposition posted on finish",
              any(p[0] == "/stratagem/disposition" and p[1]["state"] == "effects_completed"
                  for p in e.posts), e.posts)


def test_generation_failure_records_unrealized_not_advance():
    with Env() as e:
        e.capsule = ("blk", {"capsule_sha256": "abc"})
        t = TC.begin("hello", "avatar")
        e.posts.clear()
        TC.finish(t, None, outcome="generation_failed")
        check("generation_failed disposition posted",
              any(p[0] == "/stratagem/disposition" and p[1]["state"] == "generation_failed"
                  for p in e.posts), e.posts)


def test_finish_is_idempotent():
    with Env() as e:
        e.capsule = ("blk", {"capsule_sha256": "abc"})
        t = TC.begin("hello", "avatar")
        e.posts.clear()
        TC.finish(t, "r", outcome="completed")
        n = len(e.posts)
        TC.finish(t, "r", outcome="completed")
        check("second finish posts nothing", len(e.posts) == n, (n, len(e.posts)))


def test_turn_scope_records_failure_on_exception():
    with Env() as e:
        e.capsule = ("blk", {"capsule_sha256": "abc"})
        try:
            with TC.turn_scope("hello", "avatar") as t:
                e.posts.clear()
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        check("turn_scope disposed generation_failed",
              any(p[1].get("state") == "generation_failed" for p in e.posts
                  if p[0] == "/stratagem/disposition"), e.posts)


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for t in TESTS:
        try:
            t()
        except Exception as ex:
            R.append(False)
            print("ERROR " + t.__name__ + "  ->  %s: %s" % (type(ex).__name__, str(ex)[:110]))
    print("\n%d/%d passed" % (sum(R), len(R)))
    sys.exit(0 if all(R) else 1)

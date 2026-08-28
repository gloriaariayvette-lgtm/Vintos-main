#!/usr/bin/env python3
"""The two P0s from Sol's second review.

Written as isolated pytest-style functions over temporary directories: no
import-time execution, no sys.exit, no shared mutable fixture on disk. Runs
under pytest or standalone via the __main__ block.
"""
import os, sys, json, hmac, hashlib, time, uuid, tempfile, shutil, threading

HERE = os.path.dirname(os.path.abspath(__file__))
BROKER_DIR = os.path.dirname(HERE)
sys.path.insert(0, BROKER_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(BROKER_DIR), "scripts"))

import stratagem_store as S
import broker as BK
import formation_observatory as FO

PID = "a1b2c3d4e5f6"
OTHER = "b1b2c3d4e5f6"
LKEY = b"testlineagekey"


class Env:
    """A throwaway atelier root. Nothing committed is touched."""

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="atelier-test-")
        self._saved = (S.ROOT, BK.ROOT, BK.HEALTH, BK._KEYPATH,
                       S._LINEAGE_KEY, FO.OUT)
        S.ROOT = BK.ROOT = self.tmp
        BK.HEALTH = os.path.join(self.tmp, "health.jsonl")
        BK._KEYPATH = os.path.join(self.tmp, "visit-key")
        S._LINEAGE_KEY = os.path.join(self.tmp, "lineage-key")
        FO.OUT = os.path.join(self.tmp, "episodes.jsonl")
        open(S._LINEAGE_KEY, "wb").write(LKEY)
        for p in (PID, OTHER):
            os.makedirs(os.path.join(self.tmp, "projects", p, "artifacts"), exist_ok=True)
            json.dump({"id": p, "intent": "x", "state": "ACTIVE", "footprints": [],
                       "next_return": "tomorrow"},
                      open(os.path.join(self.tmp, "projects", p, "project.json"), "w"))
            json.dump({"id": "v1", "closed": False},
                      open(os.path.join(self.tmp, "projects", p, ".visit.json"), "w"))
        json.dump({"id": PID, "since": "now"}, open(os.path.join(self.tmp, "active.json"), "w"))
        return self

    def __exit__(self, *a):
        (S.ROOT, BK.ROOT, BK.HEALTH, BK._KEYPATH,
         S._LINEAGE_KEY, FO.OUT) = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def worktable(self, pid):
        json.dump({"id": pid, "since": "now"}, open(os.path.join(self.tmp, "active.json"), "w"))

    def door(self, pid, lit):
        p = os.path.join(self.tmp, "projects", pid, "project.json")
        d = json.load(open(p))
        d["next_return"] = "tomorrow" if lit else "held"
        json.dump(d, open(p, "w"))

    def episode(self, root, organ="curiosity"):
        FO.OUT = os.path.join(self.tmp, "episodes.jsonl")
        rtype, pclass = {"curiosity": ("curiosity", "self_originated"),
                         "repair": ("repair", "relational_obligation")}[organ]
        sig = {"organ": organ, "text": "t", "root": root, "activation": 0.7,
               "root_type": rtype, "provenance_class": pclass,
               "commissioned_ancestor": pclass != "self_originated"}
        with open(FO.OUT, "a") as f:
            f.write(json.dumps({"at": "2026-08-28T10:00:00", "status": "coherent_pull",
                                "organs": [organ], "roots": [root], "signals": [sig],
                                "clusters": []}) + "\n")


def _lineage(root_ref="root-abc", root_type="curiosity", nonce=None,
             pclass="self_originated", commissioned_ancestor=False, key=LKEY):
    body = {"root_ref": root_ref, "root_type": root_type,
            "provenance_class": pclass, "commissioned_ancestor": commissioned_ancestor,
            "source_record_digest": "s" * 64,
            "episode_at": "2026-08-28T10:00:00", "episode_status": "coherent_pull",
            "episode_digest": "d" * 64, "commissioned": False,
            "nonce": nonce or uuid.uuid4().hex, "exp": int(time.time()) + 3600}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return {"body": body, "sig": hmac.new(key, raw.encode(), hashlib.sha256).hexdigest()}


def _adopt_body(pid, cap, att):
    return {"id": pid, "capability": cap,
            "objective": "shift where she thinks authorship lies",
            "provenance": {"root_type": "curiosity", "root_ref": "root-abc",
                           "commissioned": False, "attestation": att},
            "sequencing_advantage": "sequenced she reaches it herself",
            "tactics": [{"tactic": "PROBE", "turn_objective": "t1"},
                        {"tactic": "SEED", "turn_objective": "t2"}],
            "perimeter_scope": ["relational"]}


# ---------------------------------------------------------------- P0 #1

def test_broker_base_routes_reject_traversal():
    """/visit/open and friends must validate BEFORE minting or writing."""
    with Env():
        for evil in ("../../victim", "/etc/passwd", "..", "NOTHEX", ""):
            try:
                BK.open_visit({"id": evil, "as": "vintos"})
                assert False, "open_visit accepted %r" % evil
            except BK.BadProject:
                pass
            except Exception as e:
                assert isinstance(e, BK.BadProject), "%r raised %r not BadProject" % (evil, e)
        assert not os.path.exists(os.path.join(os.path.dirname(BK.ROOT), "victim"))


def test_shared_validator_is_one_function():
    with Env():
        assert S._p(PID) == BK.canonical_pid(PID, S.ROOT)
        for evil in ("../../x", "zzzz", ""):
            for fn in (lambda: S._p(evil), lambda: BK.canonical_pid(evil, S.ROOT)):
                try:
                    fn()
                    assert False, "accepted %r" % evil
                except (S.BadProject, BK.BadProject):
                    pass


def test_door_and_worktable_must_name_the_same_project():
    """The old split let project B be adopted onto under project A's lit door."""
    with Env() as env:
        env.worktable(PID)          # PID is on the table, its door is lit
        env.door(OTHER, True)
        cap = BK.mint_capability(OTHER, "v1", "vintos")
        r = S.adopt(_adopt_body(OTHER, cap, _lineage()))
        assert "error" in r and "worktable" in r["error"], r
        cap = BK.mint_capability(PID, "v1", "vintos")
        assert "stratagem_id" in S.adopt(_adopt_body(PID, cap, _lineage())), "PID should adopt"


def test_dark_door_on_the_worktable_project_refuses():
    with Env() as env:
        env.worktable(PID)
        env.door(PID, False)
        cap = BK.mint_capability(PID, "v1", "vintos")
        r = S.adopt(_adopt_body(PID, cap, _lineage()))
        assert "error" in r and "door" in r["error"], r


# ---------------------------------------------------------------- P0 #2

def test_attest_requires_an_exact_recorded_root():
    with Env() as env:
        env.episode("root-abc", "curiosity")
        assert "sig" in FO.attest("root-abc", "curiosity")
        # substring of a real root must NOT match
        assert "error" in FO.attest("root-ab", "curiosity")
        assert "error" in FO.attest("oot-abc", "curiosity")
        # a timestamp / status / organ name are not roots
        for probe in ("2026-08-28T10:00:00", "coherent_pull", "curiosity", "t"):
            assert "error" in FO.attest(probe, "curiosity"), probe


def test_attest_refuses_to_restate_a_repair_as_a_want():
    with Env() as env:
        env.episode("rc-0042", "repair")
        r = FO.attest("rc-0042", "want")
        assert "error" in r and "self-originated" in r["error"], r
        r = FO.attest("rc-0042", "repair")
        assert "error" in r and "self-originated" in r["error"], r


def test_attest_will_not_take_the_callers_root_type():
    with Env() as env:
        env.episode("root-abc", "curiosity")
        r = FO.attest("root-abc", "drift_novelty")
        assert "error" in r and "recorded as" in r["error"], r


def test_attest_signs_only_recorded_fields():
    with Env() as env:
        env.episode("root-abc", "curiosity")
        body = FO.attest("root-abc", "curiosity")["body"]
        assert body["root_type"] == "curiosity"
        assert body["provenance_class"] == "self_originated"
        assert body["commissioned_ancestor"] is False
        assert len(body["source_record_digest"]) == 64


def test_broker_rejects_relational_provenance():
    with Env() as env:
        env.worktable(PID)
        cap = BK.mint_capability(PID, "v1", "vintos")
        att = _lineage(pclass="relational_obligation")
        r = S.adopt(_adopt_body(PID, cap, att))
        assert "error" in r and "self-originated" in r["error"], r


def test_broker_rejects_commissioned_ancestor():
    with Env() as env:
        env.worktable(PID)
        cap = BK.mint_capability(PID, "v1", "vintos")
        r = S.adopt(_adopt_body(PID, cap, _lineage(commissioned_ancestor=True)))
        assert "error" in r and "commissioned ancestor" in r["error"], r


def test_nonce_survives_a_rejected_adoption():
    """A refusal must not silently spend the attestation."""
    with Env() as env:
        env.worktable(PID)
        n = uuid.uuid4().hex
        cap = BK.mint_capability(PID, "v1", "vintos")
        bad = _adopt_body(PID, cap, _lineage(nonce=n))
        bad["tactics"] = [{"tactic": "PROBE", "turn_objective": "only one"}]
        r = S.adopt(bad)
        assert "error" in r, r
        # same attestation must still work for a well-formed adoption
        r = S.adopt(_adopt_body(PID, cap, _lineage(nonce=n)))
        assert "stratagem_id" in r, r


def test_nonce_is_burned_after_success():
    with Env() as env:
        env.worktable(PID)
        n = uuid.uuid4().hex
        cap = BK.mint_capability(PID, "v1", "vintos")
        assert "stratagem_id" in S.adopt(_adopt_body(PID, cap, _lineage(nonce=n)))
        env.worktable(OTHER)
        cap2 = BK.mint_capability(OTHER, "v1", "vintos")
        r = S.adopt(_adopt_body(OTHER, cap2, _lineage(nonce=n)))
        assert "error" in r and "already used" in r["error"], r


def test_two_projects_cannot_race_one_attestation():
    """Global nonce lock: per-project locks would let both through."""
    with Env() as env:
        n = uuid.uuid4().hex
        results = []

        def run(pid):
            env.worktable(pid)
            cap = BK.mint_capability(pid, "v1", "vintos")
            results.append(S.adopt(_adopt_body(pid, cap, _lineage(nonce=n))))

        ts = [threading.Thread(target=run, args=(p,)) for p in (PID, OTHER)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        wins = [r for r in results if "stratagem_id" in r]
        assert len(wins) <= 1, "both adoptions founded on one attestation: %r" % results


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print("PASS " + t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL " + t.__name__ + "  ->  " + str(e)[:150])
        except Exception as e:
            failed += 1
            print("ERROR " + t.__name__ + "  ->  %s: %s" % (type(e).__name__, str(e)[:130]))
    print("\n%d/%d passed" % (len(TESTS) - failed, len(TESTS)))
    sys.exit(1 if failed else 0)

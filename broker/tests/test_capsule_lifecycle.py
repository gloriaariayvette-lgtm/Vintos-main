#!/usr/bin/env python3
"""Idempotent capsule issuance and capsule disposition."""
import os, sys, json, tempfile, shutil, uuid, hmac, hashlib, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))   # broker/, where the modules live
import stratagem_store as S
import broker as BK

PID = "a1b2c3d4e5f6"
LKEY = b"testkey"


class Env:
    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="cap-test-")
        self._s = (S.ROOT, S._LINEAGE_KEY, S._NONCE_LOG)
        self._b = (BK.ROOT, BK.HEALTH, BK._KEYPATH)
        S.ROOT = BK.ROOT = self.tmp
        BK.HEALTH = os.path.join(self.tmp, "health.jsonl")
        BK._KEYPATH = os.path.join(self.tmp, "visit-key")
        S._LINEAGE_KEY = os.path.join(self.tmp, "lineage-key")
        S._NONCE_LOG = os.path.join(self.tmp, "nonces.jsonl")
        open(S._LINEAGE_KEY, "wb").write(LKEY)
        base = os.path.join(self.tmp, "projects", PID)
        os.makedirs(os.path.join(base, "artifacts"), exist_ok=True)
        json.dump({"id": PID, "intent": "x", "state": "ACTIVE", "footprints": [],
                   "next_return": "tomorrow"}, open(os.path.join(base, "project.json"), "w"))
        json.dump({"id": "v1", "closed": False}, open(os.path.join(base, ".visit.json"), "w"))
        json.dump({"id": PID, "since": "now"}, open(os.path.join(self.tmp, "active.json"), "w"))
        # adopt a live stratagem
        S._capability = lambda b, pid: (True, None)
        S._on_worktable = lambda pid: (True, None)
        S._verify_lineage = lambda att, r, t: (True, None)
        S._burn_nonce = lambda n: True
        r = S.adopt({"id": PID, "objective": "o",
                     "provenance": {"root_type": "want", "root_ref": "r", "commissioned": False},
                     "sequencing_advantage": "s", "perimeter_scope": ["relational"],
                     "tactics": [{"tactic": "PROBE", "turn_objective": "t1"},
                                 {"tactic": "SEED", "turn_objective": "t2"}]})
        assert "stratagem_id" in r, r
        self.sid = r["stratagem_id"]
        return self

    def __exit__(self, *a):
        (S.ROOT, S._LINEAGE_KEY, S._NONCE_LOG) = self._s
        (BK.ROOT, BK.HEALTH, BK._KEYPATH) = self._b
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


R = []


def check(name, ok, d=""):
    print(("PASS " if ok else "FAIL ") + name + ("  ->  " + str(d)[:90] if d else ""))
    R.append(bool(ok))


with Env() as e:
    r1 = S.capsule({"id": PID, "turn_id": "turn-A", "surface": "chat"})
    check("first issuance returns a capsule", "capsule" in r1, r1)
    sha1 = r1["commitment"]["capsule_sha256"]

    r2 = S.capsule({"id": PID, "turn_id": "turn-A", "surface": "chat"})
    check("retry same turn_id is idempotent", r2.get("idempotent") is True, r2)
    check("retry returns the SAME hash", r2["commitment"]["capsule_sha256"] == sha1,
          (sha1, r2["commitment"]["capsule_sha256"]))

    caps = open(os.path.join(S._sd(PID), "capsules.jsonl")).read().splitlines()
    check("only one capsule was written for turn-A",
          sum(1 for l in caps if json.loads(l)["capsule"]["turn_id"] == "turn-A") == 1, len(caps))

    r3 = S.capsule({"id": PID, "turn_id": "turn-B", "surface": "chat"})
    check("a different turn_id gets its own capsule",
          r3["commitment"]["capsule_sha256"] != sha1, r3)

    r4 = S.capsule({"id": PID, "turn_id": "turn-A", "surface": "avatar"})
    check("same turn_id on a different surface is a different capsule",
          "capsule" in r4 and not r4.get("idempotent"), r4)


with Env() as e:
    S.capsule({"id": PID, "turn_id": "turn-X", "surface": "chat"})
    d = S.disposition({"id": PID, "turn_id": "turn-X", "capsule_sha256": "abc",
                       "state": "generation_failed", "reason_class": "model_error"})
    check("disposition records a terminal state", d.get("ok") and d["state"] == "generation_failed", d)
    d = S.disposition({"id": PID, "turn_id": "turn-X", "state": "not_a_state"})
    check("unknown disposition state refused", "error" in d, d)

    # the stratagem did not advance on a failed generation
    st = json.load(open(os.path.join(S._sd(PID), "stratagem.json")))
    check("failed generation did not advance the tactic", st["step"] == 0, st["step"])

    events = [json.loads(l) for l in open(os.path.join(S._sd(PID), "events.jsonl"))]
    check("disposition is in the hash chain",
          any(ev["type"] == "capsule_disposition" for ev in events), None)
    ok, n, why = S.verify(PID)
    check("chain still verifies after disposition", ok, why)


print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

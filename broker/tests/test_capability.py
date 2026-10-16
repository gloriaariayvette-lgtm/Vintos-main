#!/usr/bin/env python3
"""Visit-capability and signed-lineage gates. Forgery and replay must fail."""
import os, sys, json, shutil, hmac, hashlib, time, uuid, tempfile, atexit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import stratagem_store as S
import broker as BK

FAKE = tempfile.mkdtemp(prefix="atelier-test-")   # never inside the repo
atexit.register(lambda: shutil.rmtree(FAKE, ignore_errors=True))
os.makedirs(os.path.join(FAKE, "projects"), exist_ok=True)
S.ROOT = FAKE
BK.ROOT = FAKE
BK.HEALTH = os.path.join(FAKE, "health.jsonl")
BK._KEYPATH = os.path.join(FAKE, "visit-key")
S._LINEAGE_KEY = os.path.join(FAKE, "lineage-key")
S._NONCE_LOG = os.path.join(FAKE, "nonces.jsonl")
LKEY = b"testlineagekey"
open(S._LINEAGE_KEY, "wb").write(LKEY)

PID = "a1b2c3d4e5f6"
R = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("  ->  " + str(detail)[:95] if detail else ""))
    R.append(bool(ok))


def fresh(door_lit=True, visit_id="v1"):
    base = os.path.join(FAKE, "projects", PID)
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(os.path.join(base, "artifacts"), exist_ok=True)
    json.dump({"id": PID, "intent": "x", "state": "ACTIVE", "footprints": [],
               "next_return": "tomorrow" if door_lit else "held"},
              open(os.path.join(base, "project.json"), "w"))
    json.dump({"id": visit_id, "closed": False}, open(os.path.join(base, ".visit.json"), "w"))
    json.dump({"id": PID, "since": "now"}, open(os.path.join(FAKE, "active.json"), "w"))


def lineage(root_ref="drift.json@2026-08-27", root_type="drift_novelty",
            nonce=None, exp=None, commissioned=False):
    body = {"root_ref": root_ref, "root_type": root_type,
            "provenance_class": "self_originated", "commissioned_ancestor": False,
            "source_record_digest": "s" * 64,
            "episode_at": "2026-08-27T10:00:00", "episode_status": "coherent_pull",
            "episode_digest": "d" * 64, "commissioned": commissioned,
            "nonce": nonce or uuid.uuid4().hex,
            "exp": exp if exp is not None else int(time.time()) + 3600}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return {"body": body, "sig": hmac.new(LKEY, raw.encode(), hashlib.sha256).hexdigest()}


def good(cap, att=None):
    return {"id": PID, "capability": cap,
            "objective": "shift where she thinks authorship of the field lies",
            "provenance": {"root_type": "drift_novelty",
                           "root_ref": "drift.json@2026-08-27",
                           "commissioned": False,
                           "attestation": att if att is not None else lineage()},
            "sequencing_advantage": "sequenced she reaches it herself",
            "tactics": [{"tactic": "PROBE", "turn_objective": "t1"},
                        {"tactic": "SEED", "turn_objective": "t2"}],
            "perimeter_scope": ["relational", "creative"]}


print("--- visit capability remains enforced on Atelier operations ---")
fresh()
cap = BK.mint_capability(PID, "v1", "vintos")
check("valid capability verifies", BK.verify_capability(cap, PID, "vintos")[0])
forged = json.loads(json.dumps(cap)); forged["sig"] = "0" * 64
check("forged capability refused", not BK.verify_capability(forged, PID, "vintos")[0])
tampered = json.loads(json.dumps(cap)); tampered["body"]["actor"] = "gloria"
check("tampered capability refused", not BK.verify_capability(tampered, PID, "vintos")[0])
check("expired capability refused", not BK.verify_capability(BK.mint_capability(PID, "v1", "vintos", ttl=-10), PID, "vintos")[0])
fresh(visit_id="v2")
check("stale visit capability refused", not BK.verify_capability(cap, PID, "vintos")[0])
fresh()
check("capability does not cross projects", not BK.verify_capability(cap, "b1b2c3d4e5f6", "vintos")[0])
from stratagem_fixture import grant
grant(S)
fresh(door_lit=False)
result = S.adopt(good(None, {"body": {}, "sig": "incomplete metadata"}))
check("charter permits adoption without visit, door, or attestation", "stratagem_id" in result, result)
check("owner reveal requires owner credential", "error" in S.reveal({"id": PID, "capability": cap}))
print("\n--- the observatory only attests roots it recorded ---")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
import formation_observatory as FO
FO.OUT = os.path.join(FAKE, "episodes.jsonl")
with open(FO.OUT, "w") as f:
    f.write(json.dumps({"at": "2026-08-27T10:00:00", "status": "coherent_pull",
                        "organs": ["curiosity"], "roots": ["real_root_abc"],
                        "signals": [{"organ": "curiosity", "text": "t",
                                     "root": "real_root_abc", "activation": 0.7,
                                     "root_type": "curiosity",
                                     "provenance_class": "self_originated",
                                     "commissioned_ancestor": False}],
                        "clusters": []}) + "\n")
os.environ["HOME"] = FAKE
# Moving HOME is not enough on its own: attest() signs with the house lineage key and mints
# one when it is missing, so the key path is repointed explicitly rather than left to depend
# on when expanduser happens to run.
FO.KEYPATH = os.path.join(FAKE, ".lineage-key")
a = FO.attest("real_root_abc", "curiosity")
check("attests a recorded root", "sig" in a, list(a))
a = FO.attest("invented_root_xyz", "curiosity")
check("refuses to attest an unrecorded root", "error" in a, a.get("error"))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

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


print("--- visit capability ---")
fresh()
cap = BK.mint_capability(PID, "v1", "vintos")
check("legitimate adoption succeeds", "stratagem_id" in S.adopt(good(cap)))

fresh()
check("no capability refused", "error" in S.adopt(dict(good(None), capability=None)))

fresh()
forged = {"body": {"project": PID, "visit": "v1", "actor": "vintos",
                   "nonce": "x", "exp": int(time.time()) + 999}, "sig": "0" * 64}
r = S.adopt(good(forged))
check("forged signature refused", "error" in r, r.get("error"))

fresh()
c = BK.mint_capability(PID, "v1", "vintos")
c["body"]["actor"] = "gloria"          # tamper after signing
r = S.adopt(good(c))
check("tampered capability body refused", "error" in r, r.get("error"))

fresh()
expired = BK.mint_capability(PID, "v1", "vintos", ttl=-10)
r = S.adopt(good(expired))
check("expired capability refused", "error" in r, r.get("error"))

fresh(visit_id="v2")
stale = BK.mint_capability(PID, "v1", "vintos")     # names a visit that is not current
r = S.adopt(good(stale))
check("capability for a different visit refused", "error" in r, r.get("error"))

fresh()
cap = BK.mint_capability(PID, "v1", "vintos")
base = os.path.join(FAKE, "projects", PID)
json.dump({"id": "v1", "closed": True}, open(os.path.join(base, ".visit.json"), "w"))
r = S.adopt(good(cap))
check("capability refused after the visit closes (no replay)", "error" in r, r.get("error"))

other = "b1b2c3d4e5f6"
os.makedirs(os.path.join(FAKE, "projects", other), exist_ok=True)
fresh()
crosscap = BK.mint_capability(other, "v1", "vintos")
r = S.adopt(good(crosscap))
check("capability from another project refused", "error" in r, r.get("error"))

print("\n--- door gate ---")
fresh(door_lit=False)
cap = BK.mint_capability(PID, "v1", "vintos")
r = S.adopt(good(cap))
check("adoption refused when the door is dark", "error" in r and "door" in r["error"],
      r.get("error"))

print("\n--- signed lineage ---")
fresh()
cap = BK.mint_capability(PID, "v1", "vintos")
r = S.adopt(good(cap, att=None if False else {"body": {}, "sig": "bad"}))
check("unsigned/garbage attestation refused", "error" in r, r.get("error"))

fresh()
cap = BK.mint_capability(PID, "v1", "vintos")
att = lineage()
att["body"]["root_ref"] = "something_else"          # tamper after signing
r = S.adopt(good(cap, att))
check("tampered attestation refused", "error" in r, r.get("error"))

fresh()
cap = BK.mint_capability(PID, "v1", "vintos")
r = S.adopt(good(cap, lineage(exp=int(time.time()) - 5)))
check("expired attestation refused", "error" in r, r.get("error"))

fresh()
cap = BK.mint_capability(PID, "v1", "vintos")
r = S.adopt(good(cap, lineage(commissioned=True)))
check("commissioned attestation refused", "error" in r, r.get("error"))

fresh()
cap = BK.mint_capability(PID, "v1", "vintos")
r = S.adopt(good(cap, lineage(root_ref="a_root_the_observatory_never_saw")))
check("attestation for a different root refused", "error" in r, r.get("error"))

# replay: same nonce twice
n = uuid.uuid4().hex
fresh()
cap = BK.mint_capability(PID, "v1", "vintos")
r1 = S.adopt(good(cap, lineage(nonce=n)))
fresh()
cap = BK.mint_capability(PID, "v1", "vintos")
r2 = S.adopt(good(cap, lineage(nonce=n)))
check("first use of a lineage nonce accepted", "stratagem_id" in r1, r1.get("error"))
check("replayed lineage nonce refused", "error" in r2 and "replay" in r2["error"],
      r2.get("error"))

print("\n--- capability required on every mutating call ---")
fresh()
cap = BK.mint_capability(PID, "v1", "vintos")
S.adopt(good(cap))
for name, fn, extra in (("advance", S.advance, {}),
                        ("lease", S.lease, {"action": "renew"}),
                        ("resolve", S.resolve, {"outcome": "done"})):
    r = fn(dict({"id": PID}, **extra))
    check("%s refused without a capability" % name, "error" in r, r.get("error"))
    r = fn(dict({"id": PID, "capability": cap}, **extra))
    check("%s accepted with a capability" % name, "error" not in r, r)

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
a = FO.attest("real_root_abc", "curiosity")
check("attests a recorded root", "sig" in a, list(a))
a = FO.attest("invented_root_xyz", "curiosity")
check("refuses to attest an unrecorded root", "error" in a, a.get("error"))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

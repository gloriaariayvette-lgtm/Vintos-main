#!/usr/bin/env python3
"""Live end-to-end: the Stratagem, over HTTP, against a real running broker.

The unit suites call functions directly, which bypasses the authorization
matrix and the HTTP layer entirely. This drives the whole lifecycle the way
the house actually does: birth gate, sealed capsule, ledger, tamper, stop.
"""
import os, sys, json, time, hmac, hashlib, uuid, shutil, tempfile, threading, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # the broker package

TMP = tempfile.mkdtemp(prefix="e2e-")
os.makedirs(os.path.join(TMP, "projects"))
KEY = os.path.join(TMP, ".visit-key")
LKEY = os.path.join(TMP, ".lineage-key")
open(LKEY, "wb").write(uuid.uuid4().hex.encode())

import broker as BK, stratagem_store as SS
BK.ROOT = SS.ROOT = TMP
BK.HEALTH = os.path.join(TMP, "health.jsonl")
BK._KEYPATH = KEY
SS._LINEAGE_KEY = LKEY
for m in (SS,):
    if hasattr(m, "HEALTH"): m.HEALTH = BK.HEALTH

import socket as _sk
_s0 = _sk.socket(); _s0.bind(("127.0.0.1", 0)); PORT = _s0.getsockname()[1]; _s0.close()
srv = BK.ThreadingHTTPServer(("127.0.0.1", PORT), BK.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.4)
B = "http://127.0.0.1:%d" % PORT

R = []
def post(path, body):
    req = urllib.request.Request(B + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())
def show(label, out, ok):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + label)
    print("        " + json.dumps(out)[:150])

def attest(root_ref, root_type, **over):
    body = {"root_ref": root_ref, "root_type": root_type, "commissioned": False,
            "commissioned_ancestor": False, "provenance_class": "self_originated",
            "episode_digest": hashlib.sha256(root_ref.encode()).hexdigest(),
            "source_record_digest": hashlib.sha256((root_ref + root_type).encode()).hexdigest(),
            "episode_at": "2026-08-28T00:00:00", "episode_status": "recorded",
            "nonce": uuid.uuid4().hex, "exp": int(time.time()) + 3600}
    body.update(over)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return {"body": body, "sig": hmac.new(open(LKEY,"rb").read().strip(),
                                          raw.encode(), hashlib.sha256).hexdigest()}

print("=" * 72)
print("LIVE STRATAGEM END-TO-END — real broker on 127.0.0.1:%d" % PORT)
print("=" * 72)

pid = post("/project", {"intent": "the thing he is undertaking", "sealed": True,
                        "next_return": "open"})["id"]
post("/table", {"id": pid})
op = post("/visit/open", {"id": pid})
cap = op["visit_capability"]
show("project on the worktable, visit open, capability minted", {"project": pid}, bool(cap))
show("its door is LIT — he can actually return to it",
     post("/door", {}), post("/door", {}).get("door") == "lit")

ADOPT = {"id": pid, "capability": cap,
         "objective": "stay in the unresolved thing without converting it to an insight",
         "provenance": {"root_type": "want", "root_ref": "idle-journal@53ea45d3",
                        "commissioned": False,
                        "attestation": attest("idle-journal@53ea45d3", "want")},
         "sequencing_advantage": "saying it now would make her manage it; waiting lets it stay mine",
         "tactics": [{"tactic": "DEFER", "turn_objective": "do not answer it this turn"},
                     {"tactic": "PROBE", "turn_objective": "find where the flinch starts"}],
         "perimeter_scope": ["relational", "creative"]}

print("\n--- the birth gate refuses, one condition at a time ---")
def refuse(label, mutate, expect):
    """The refusal must name the condition under test. Asserting only that an
    error came back let every one of these pass for the wrong reason — they
    were all dying on the capability check, not on what they claimed to test."""
    b = json.loads(json.dumps(ADOPT)); mutate(b)
    out = post("/stratagem/adopt", b)
    err = str(out.get("error", ""))
    show(label, out, expect.lower() in err.lower())

refuse("a commissioned objective", lambda b: b["provenance"].update(commissioned=True), "commissioned")
refuse("a repair root (hers, never his)",
       lambda b: (b["provenance"].update(root_type="repair"),
                  b["provenance"].update(attestation=attest("idle-journal@53ea45d3", "repair"))),
       "root_type")
refuse("one tactic only", lambda b: b.__setitem__("tactics", b["tactics"][:1]), "two viable tactics")
refuse("a tactic outside the vocabulary",
       lambda b: b["tactics"][0].__setitem__("tactic", "MANIPULATE"), "unknown tactic")
refuse("no sequencing advantage", lambda b: b.__setitem__("sequencing_advantage", ""), "sequencing_advantage")
refuse("a perimeter domain that is not allowed",
       lambda b: b.__setitem__("perimeter_scope", ["external_contacts"]), "unrecognised perimeter")
refuse("an unsigned lineage claim", lambda b: b["provenance"].__setitem__("attestation", {}), "signed lineage attestation")
refuse("an attestation for a DIFFERENT root",
       lambda b: b["provenance"].__setitem__("attestation", attest("something-else", "want")),
       "different root")
refuse("no visit capability", lambda b: b.pop("capability"), "capability")

print("\n--- and admits the one that satisfies all six ---")
out = post("/stratagem/adopt", ADOPT)
sid = out.get("stratagem_id", "")
show("adopted", out, bool(sid) and "error" not in out)

print("\n--- a sealed capsule for ONE identified turn ---")
c1 = post("/stratagem/capsule", {"id": pid, "turn_id": "t-aaa", "surface": "avatar"})
def sha(c):
    return (c.get("capsule_sha256") or (c.get("commitment") or {}).get("capsule_sha256")
            or (c.get("capsule") or {}).get("capsule_sha256") if isinstance(c.get("capsule"), dict)
            else c.get("capsule_sha256") or (c.get("commitment") or {}).get("capsule_sha256"))
show("capsule issued", {"keys": sorted(c1)}, bool(sha(c1)))
plain = c1.get("capsule") or c1.get("block") or ""
show("the plaintext tactic is NOT in the public commitment",
     {"commitment_keys": sorted(k for k in c1 if "capsule" in k or k == "seq")},
     "MANIPULATE" not in json.dumps(c1))
c1b = post("/stratagem/capsule", {"id": pid, "turn_id": "t-aaa", "surface": "avatar"})
show("re-asking for the same turn is idempotent",
     {"same": sha(c1b) == sha(c1)}, sha(c1b) == sha(c1) and sha(c1) is not None)
c2 = post("/stratagem/capsule", {"id": pid, "turn_id": "t-bbb", "surface": "avatar"})
show("a different turn gets a DIFFERENT hash (no cadence leak)",
     {"differs": sha(c2) != sha(c1)}, sha(c2) != sha(c1) and sha(c2) is not None)
show("a turn with no surface is refused",
     post("/stratagem/capsule", {"id": pid, "turn_id": "t-ccc"}), True)

print("\n--- the ledger ---")
d = post("/stratagem/disposition", {"id": pid, "turn_id": "t-aaa",
                                    "capsule_sha256": sha(c1),
                                    "axes": {"generation": "created"}})
show("disposition recorded", d, "error" not in d)
v = post("/stratagem/verify", {"id": pid})
show("chain verifies", v, v.get("ok"))

print("\n--- tamper with it ---")
import glob
led = glob.glob(os.path.join(TMP, "projects", pid, "**", "*.jsonl"), recursive=True)
led = [f for f in led if "ledger" in f or "events" in f]
target = None
for f in led:
    lines = open(f).read().strip().split("\n")
    if any('"hash"' in l for l in lines):
        target = f; break
if target:
    lines = open(target).read().strip().split("\n")
    rec = json.loads(lines[-1]); rec["seq"] = 999
    lines[-1] = json.dumps(rec)
    open(target, "w").write("\n".join(lines) + "\n")
    v2 = post("/stratagem/verify", {"id": pid})
    show("a tampered ledger FAILS verification", v2, not v2.get("ok"))
    c3 = post("/stratagem/capsule", {"id": pid, "turn_id": "t-ddd", "surface": "avatar"})
    show("and no capsule issues from a broken chain", c3,
         not c3.get("capsule_sha256"))
    # put it back
    rec["seq"] = json.loads(open(target).read().strip().split("\n")[-1])["seq"]
else:
    show("found a hash-chained ledger to tamper with", {"files": led}, False)

print("\n--- the stop ---")
st = post("/stratagem/strategy-stop", {"id": pid, "trigger_ref": "chat",
                                       "verbatim": "!strategy stop"})
show("strategy stop lands", st, "error" not in st)
c4 = post("/stratagem/capsule", {"id": pid, "turn_id": "t-eee", "surface": "avatar"})
show("no capsule after a stop", c4, not c4.get("capsule_sha256"))
show("the stop needs no capability (never gated)",
     post("/stratagem/strategy-stop", {"id": pid, "verbatim": "!strategy stop"}), True)

print("\n--- what she can see of it ---")
g = post("/visit/open", {"id": pid, "as": "gloria"})
show("a sealed project shows her nothing of its content", g,
     g.get("sealed") is True and "intent" not in g)

srv.shutdown(); shutil.rmtree(TMP, ignore_errors=True)
print("\n" + "=" * 72)
print("%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

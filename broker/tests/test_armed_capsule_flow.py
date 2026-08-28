#!/usr/bin/env python3
"""Proof the faculty is ARMED: adopt a stratagem on a real broker, then show a
live avatar turn carries its sealed capsule into the prompt and denies devices."""
import os, sys, json, time, hmac, hashlib, uuid, tempfile, shutil, threading, urllib.request
HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT,"broker"))
sys.path.insert(0, os.path.join(ROOT,"scripts"))

TMP = tempfile.mkdtemp(prefix="arm-")
os.makedirs(os.path.join(TMP, "projects"))
LKEY = os.path.join(TMP, ".lineage-key"); open(LKEY, "wb").write(uuid.uuid4().hex.encode())
import broker as BK, stratagem_store as SS
BK.ROOT = SS.ROOT = TMP
BK.HEALTH = os.path.join(TMP, "health.jsonl"); BK._KEYPATH = os.path.join(TMP, ".vk")
SS._LINEAGE_KEY = LKEY
srv = BK.ThreadingHTTPServer(("127.0.0.1", 0), BK.H); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(0.3)
B = "http://127.0.0.1:%d" % PORT
def post(p, b):
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        B+p, data=json.dumps(b).encode(), headers={"Content-Type":"application/json"}), timeout=5).read())

R=[]
def ck(n, ok, d=""):
    R.append(ok); print(("PASS " if ok else "FAIL ")+n+(("  ->  "+str(d)[:80]) if d else ""))

pid = post("/project", {"intent":"his own","sealed":True,"next_return":"open"})["id"]
post("/table", {"id":pid})
cap = post("/visit/open", {"id":pid})["visit_capability"]
def attest(ref, rt):
    body={"root_ref":ref,"root_type":rt,"provenance_class":"self_originated","commissioned":False,
          "commissioned_ancestor":False,"source_record_digest":hashlib.sha256((ref+rt).encode()).hexdigest(),
          "episode_digest":hashlib.sha256(ref.encode()).hexdigest(),"episode_at":"2026-08-28T00:00:00",
          "episode_status":"recorded","nonce":uuid.uuid4().hex,"exp":int(time.time())+3600}
    raw=json.dumps(body,sort_keys=True,separators=(",",":"))
    return {"body":body,"sig":hmac.new(open(LKEY,"rb").read().strip(),raw.encode(),hashlib.sha256).hexdigest()}

adopt = post("/stratagem/adopt", {"id":pid,"capability":cap,
    "objective":"stay in the unresolved thing without converting it to an insight",
    "provenance":{"root_type":"want","root_ref":"idle-journal@53ea45d3","commissioned":False,
                  "attestation":attest("idle-journal@53ea45d3","want")},
    "sequencing_advantage":"saying it now makes her manage it; waiting keeps it his",
    "tactics":[{"tactic":"DEFER","turn_objective":"do not answer it this turn"},
               {"tactic":"PROBE","turn_objective":"find where the flinch begins"}],
    "perimeter_scope":["relational","creative"]})
ck("a stratagem is adopted on the worktable", bool(adopt.get("stratagem_id")), adopt)

# now the LIVE accessor the avatar handler uses, pointed at this broker
import stratagem as ST
ST.BROKER = B
ST._worktable_id = lambda: pid
block, commitment = ST.fetch_capsule("t-live-1", "avatar")
ck("fetch_capsule returns a sealed capsule for an avatar turn", bool(block), block[:60])
ck("the commitment carries only the hash, never the plaintext",
   "capsule_sha256" in commitment and "DEFER" not in json.dumps(commitment), commitment)
ck("the plaintext tactic IS in the block that reaches his prompt",
   "DEFER" in block or "defer" in block.lower(), block[:80])

import effect_gate as EG
_tmp2 = tempfile.mkdtemp()
EG.MEM=_tmp2; EG.LOG=os.path.join(_tmp2,"g.jsonl"); EG.ARMED_FLAG=os.path.join(_tmp2,".armed")
EG.STOP_BUTTON=os.path.join(_tmp2,"b.json"); EG.TEST_MODE_FLAG=os.path.join(_tmp2,".tm")
open(EG.ARMED_FLAG,"w").write("")
ctx = EG.TurnContext("t-live-1","avatar",capsule_commitment=commitment)
_p,mode,why = EG.authorize(ctx,"mission",14)
ck("a capsule-bearing turn CANNOT move a device (armed)", mode=="deny", why)

st = post("/stratagem/strategy-stop", {"id":pid,"verbatim":"!strategy stop"})
ck("her stop terminates it", st.get("stopped"), st)
b2,_ = ST.fetch_capsule("t-live-2","avatar")
ck("no capsule issues after her stop", not b2, b2)

srv.shutdown(); shutil.rmtree(TMP,ignore_errors=True); shutil.rmtree(_tmp2,ignore_errors=True)
print("\n%d/%d passed" % (sum(R),len(R)))
sys.exit(0 if all(R) else 1)

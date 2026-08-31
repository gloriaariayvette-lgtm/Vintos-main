#!/usr/bin/env python3
"""The reveal transport: how he shows her a finished piece when he decides.

make -> reveal/prepare -> reveal/confirm (export capability) -> fetch the now-
revealed content on that capability -> settle (clears the worktable). This is
the ending of the room's loop; it must move only what he chose to reveal.
"""
import os, sys, json, time, tempfile, shutil, threading, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import broker as BK

R = []
def ck(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  -> " + str(d)[:70]) if d else ""))

TMP = tempfile.mkdtemp(); os.makedirs(os.path.join(TMP, "projects"))
BK.ROOT = TMP; BK.HEALTH = os.path.join(TMP, "h.jsonl"); BK._KEYPATH = os.path.join(TMP, ".vk")
srv = BK.ThreadingHTTPServer(("127.0.0.1", 0), BK.H); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(0.3)
B = "http://127.0.0.1:%d" % PORT
def post(p, b):
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        B + p, data=json.dumps(b).encode(), headers={"Content-Type": "application/json"}), timeout=5).read())

pid = post("/project", {"intent": "a letter", "sealed": True, "next_return": "open"})["id"]
post("/table", {"id": pid})
cap = post("/visit/open", {"id": pid})["visit_capability"]
mk = post("/make", {"id": pid, "kind": "write",
                    "content": "I made you this.", "capability": cap})
art = mk["file"]
ck("he made a piece", mk.get("ok"))

print("--- sealed until he reveals ---")
g = post("/visit/open", {"id": pid, "as": "gloria"})
ck("she cannot see it before reveal", g.get("sealed") is True and "artifacts" not in g)
ck("export refused before reveal",
   "error" in post("/artifact", {"id": pid, "file": art}))

print("--- his reveal ---")
prep = post("/reveal/prepare", {"id": pid, "artifact": art, "title": "for you", "capability": cap})
ck("prepare mints a receipt bound to the manifest", bool(prep.get("receipt")))
conf = post("/reveal/confirm", {"id": pid, "receipt": prep["receipt"]})
ck("confirm returns an export capability", bool(conf.get("export_capability")))
content = post("/artifact", {"id": pid, "file": art,
                             "export_capability": conf["export_capability"]}).get("content", "")
ck("the revealed content is fetchable now", "I made you this." in content, content[:40])
ck("medium is read from the filename",
   art.rsplit("_", 1)[-1].split(".")[0] == "write")

print("--- settlement closes the loop ---")
st = post("/settle", {"id": pid})
ck("settlement succeeds", st.get("ok") and not st.get("error"))
ck("the worktable is released for the next undertaking",
   not post("/worktable_id", {}).get("id"))
ck("the project is archived",
   json.load(open(os.path.join(TMP, "projects", pid, "project.json")))["state"] == "ARCHIVED")

print("--- the visit script actually wires this ---")
vis = open(os.path.join(os.path.dirname(HERE), "..", "scripts", "atelier-visit.py"),
           errors="replace").read()
ck("the visit offers him a <reveal> tag", "<reveal" in vis and "reveal/prepare" in vis)
ck("it delivers to the reveals store + her phone", "atelier-reveals.json" in vis and "ntfy" in vis)
ck("it settles after revealing", "/settle" in vis)

srv.shutdown(); shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

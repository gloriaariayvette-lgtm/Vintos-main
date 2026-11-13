#!/usr/bin/env python3
"""Desktop control on the iMac (Codex, 12 November): memory/desktop-target.json picks the iMac, and then the browser
and the native desktop are driven there over SSH, never on Aegis. Scratch workspace; ssh is a stub; no host, model or
desktop is reached."""
import json, os, socket, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="imac-target-")
os.environ["SPARK_WORKSPACE"] = os.path.join(TMP, "workspace"); os.environ["VINTOS_DESKTOP_STATE_DIR"] = TMP
os.makedirs(os.path.join(TMP, "workspace", "memory"))
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import browser_mac as BM, desktop_mac as DM, desktop_agent as DA, browser_agent as BA, browser_jev as BJ, browser_winpy as BW

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ("" if ok else " -- " + str(detail)[:300]))

TARGET = os.path.join(TMP, "workspace", "memory", "desktop-target.json")
def target(value):
    if value is None:
        if os.path.exists(TARGET): os.unlink(TARGET)
    else: json.dump(value, open(TARGET, "w"))

ssh = []
class Done:
    def __init__(self, out=b"", rc=0): self.returncode, self.stdout, self.stderr = rc, out, b"helper error\n"
def fake_ssh(command, **kw):
    ssh.append((command, kw.get("input"))); return REPLY[0]
BM._ssh = fake_ssh
REPLY = [Done()]

check("no target file: Aegis, not the iMac", not BM.selected() and not BM.available() and not ssh)
target({"target": "windows"})
check("another target: not the iMac", not BM.selected() and not BM.available() and not ssh)
target({"target": "imac", "ssh_host": "imac.test", "python": "/opt/py", "root": "/opt/vintos"})
check("the iMac target is selected", BM.selected())
check("available only when the helper is there", BM.available() and "test -x /opt/py" in ssh[-1][0])
REPLY[0] = Done(b'noise\n{"ok": true, "text": "hello"}\n')
out = BM.call("text", tab="T1")
sent = json.loads(ssh[-1][1])
check("a browser call runs the helper on the iMac and reads its last line",
      out == {"ok": True, "text": "hello"} and ssh[-1][0] == "exec /opt/py /opt/vintos/browser_helper.py"
      and sent["op"] == "text" and sent["tab"] == "T1", (out, ssh[-1]))
REPLY[0] = Done(rc=1)
try: BM.call("text"); check("a failed helper raises", False)
except RuntimeError as e: check("a failed helper raises", "iMac browser helper failed" in str(e), e)
check("MacBrowser is the Edge interface", issubclass(BM.MacBrowser, BW.EdgeBrowser))

# the native desktop: permissions first; never falls back to Aegis
REPLY[0] = Done(b'{"ok": true, "permissions": {"accessibility": true, "screen_recording": false}}\n')
try: DM.RemoteMacBackend(); check("missing macOS permissions refuse the backend", False)
except RuntimeError as e: check("missing macOS permissions refuse the backend", "Screen Recording" in str(e), e)
REPLY[0] = Done(b'{"ok": true, "permissions": {"accessibility": true, "screen_recording": true}}\n')
backend = DA.pick_backend()
check("with the iMac selected the pixel backend is the iMac's", isinstance(backend, DM.RemoteMacBackend)
      and ssh[-1][0] == "exec /opt/py /opt/vintos/native-client.py", backend)
REPLY[0] = Done(b'{"ok": false, "error": "denied"}\n')
try: DM.rpc("capture"); check("a refused native call raises", False)
except RuntimeError as e: check("a refused native call raises", "denied" in str(e), e)

check("routing reads the goal, not the long chat wrapper",
      DA._routing_text("open notes\nWork through the ordinary visible desktop and verify the result.") == "open notes")

# the browser job drives the iMac's browser
got = []
BA.run = lambda task, browser, planner, max_steps, **kw: got.append(browser) or "ran"
BA.planner_for_house = lambda: None
BA.GemmaPageVerifier = BA.GemmaReflector = lambda: None
BA.run_task("open the menu")
check("the browser job drives the iMac browser", got and isinstance(got[-1], BM.MacBrowser), got)
target({"target": "windows"}); BA.run_task("open the menu")
check("otherwise the Edge browser on Aegis", type(got[-1]) is BW.EdgeBrowser, got)

# Jev: a field already holding what was typed is not offered for filling again
state = {"url": "https://shop.example/", "title": "Shop"}
elements = [{"kind": "field", "label": "Search", "value": "tacos", "ontop": True},
            {"kind": "field", "label": "Notes", "value": "", "ontop": True},
            {"kind": "button", "text": "Open tacos", "ontop": True}]
ops, targets, public = BJ._space(state, elements, satisfied={"0"})
fill = targets.get("TYPE_TEXT", {})
check("a satisfied field is not offered again; the other still is", "0" not in fill and "1" in fill, targets)
check("a field shows its label and whether it is done", public[0]["label"] == "Search" and public[0]["filled_as_requested"] is True
      and public[1]["filled_as_requested"] is False, public[:2])

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""His handoff is saved while the visit it is posted on is still open.

25 Oct: he made a piece, revealed an earlier one, and the reveal settled the undertaking. Settlement closes the
visit (the broker's last step), and only then did the visit post his handoff on the visit capability: the broker
refused it, "the visit this capability names is no longer open", and his note was lost. The broker was right; the
order was wrong. Now a reveal that is about to settle saves the handoff first, and the end of the visit does not
post it again. The broker's capability check is unchanged and is exercised for real here.

A real broker in a scratch root (in-process, 127.0.0.1); the visit script drives it through its own HTTP calls.
The model, the reveal shelf and ntfy are stubs; scratch HOME; no other socket leaves this host."""
import importlib.util, json, os, shutil, socket, sys, tempfile, threading, time, types, urllib.request
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="atelier-handoff-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
os.environ["SPARK_WORKSPACE"] = WS
sys.path.insert(0, os.path.dirname(HERE))
import broker as BK

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

ROOT = tempfile.mkdtemp(prefix="atelier-root-"); os.makedirs(os.path.join(ROOT, "projects"))
BK.ROOT = ROOT; BK.HEALTH = os.path.join(ROOT, "h.jsonl"); BK._KEYPATH = os.path.join(ROOT, ".vk")
srv = BK.ThreadingHTTPServer(("127.0.0.1", 0), BK.H); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start(); time.sleep(0.3)
BASE = "http://127.0.0.1:%d" % PORT

_real_connect = socket.socket.connect
NET = []
def _only_local(self, addr, *a, **k):
    if isinstance(addr, tuple) and addr[0] == "127.0.0.1" and addr[1] == PORT:
        return _real_connect(self, addr, *a, **k)
    NET.append(addr); raise OSError("this suite reaches nothing but its own scratch broker")
socket.socket.connect = _only_local

def post(p, b):
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        BASE + p, data=json.dumps(b).encode(), headers={"Content-Type": "application/json"}), timeout=10).read())

try: import requests  # noqa: F401
except ImportError: sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)
spec = importlib.util.spec_from_file_location("atelier_visit_handoff", os.path.join(REPO, "scripts", "atelier-visit.py"))
AV = importlib.util.module_from_spec(spec); spec.loader.exec_module(AV)
AV.WSP = WS; AV.CHOICES = os.path.join(MEM, "atelier-choices.jsonl"); AV.KNOCK_STORE = os.path.join(MEM, ".atelier-knock.json")
AV._exhibition_module = lambda: None
AV._dream_module = lambda: None

check("the broker store is a scratch root, not his", BK.ROOT == ROOT and ROOT.startswith(tempfile.gettempdir()), ROOT)
check("the visit's workspace is scratch", AV.WSP.startswith(HOME), AV.WSP)

# --- the broker law this suite relies on, unchanged: a handoff after settlement is refused
def fresh_project():
    pid = post("/project", {"intent": "a letter", "sealed": True, "next_return": "open"})["id"]
    post("/table", {"id": pid})
    return pid

pid0 = fresh_project()
cap0 = post("/visit/open", {"id": pid0})["visit_capability"]
art0 = post("/make", {"id": pid0, "kind": "write", "content": "first", "capability": cap0})["file"]
prep0 = post("/reveal/prepare", {"id": pid0, "artifact": art0, "title": "t", "capability": cap0})
post("/reveal/confirm", {"id": pid0, "receipt": prep0["receipt"]})
check("settlement succeeds", post("/settle", {"id": pid0}).get("ok"))
late = post("/handoff", {"id": pid0, "text": "late", "next_move": "", "next_return": "tomorrow", "capability": cap0})
check("the broker still refuses a handoff on a visit settlement closed (its check is not loosened)",
      late.get("error") == "the visit this capability names is no longer open", late)

# --- the visit itself, end to end against the real broker
POSTS, FAILED, NTFY, DELIVERED = [], [], [], []
def run_visit(pid, answer, ok=True):
    POSTS.clear(); FAILED.clear(); NTFY.clear(); DELIVERED.clear()
    def send(fn, caller, url, json=None, **k):
        path = url[len(AV.B):] if url.startswith(AV.B) else url
        POSTS.append(path)
        if fn is AV.requests.get or path in ("/health",):
            body = {}
        else:
            body = post(path, json or {})
        return types.SimpleNamespace(json=lambda: body)
    ident = lambda pid, ctx, work, *a, **k: work
    def deliver(art, disc, content, manifest):
        DELIVERED.append(art); return ok
    with mock.patch.object(AV.paid_http, "send", side_effect=send), \
         mock.patch.object(AV, "ask", side_effect=lambda system, user, **k: answer), \
         mock.patch.object(AV, "voice", return_value="VOICE"), mock.patch.object(AV, "where_you_are", return_value=""), \
         mock.patch.object(AV, "motif_notebook", return_value=([], "")), mock.patch.object(AV, "motif_step", return_value=None), \
         mock.patch.object(AV, "stratagem_block", return_value=""), mock.patch.object(AV, "stratagem_step", return_value=None), \
         mock.patch.object(AV, "materials_loop", side_effect=lambda pid, ctx, w: w), \
         mock.patch.object(AV, "plugin_loop", side_effect=ident), mock.patch.object(AV, "quantum_loop", side_effect=ident), \
         mock.patch.object(AV, "media_loop", side_effect=lambda pid, ctx, w, cap, creation=None: w), \
         mock.patch.object(AV, "make_pass", side_effect=lambda pid, ctx, w, cap, c: (w, False)), \
         mock.patch.object(AV, "_deliver_reveal", side_effect=deliver), \
         mock.patch.object(AV, "ledger_mark"), \
         mock.patch.object(AV, "_failed", side_effect=lambda what, why="": FAILED.append((what, why))), \
         mock.patch.object(AV.requests, "post", side_effect=lambda url, **k: NTFY.append(url)):
        AV.visit(pid)

def handoff_of(pid):
    try: return json.load(open(os.path.join(ROOT, "projects", pid, "handoff.json")))
    except Exception: return {}

# the 25 Oct shape: an earlier piece exists; this visit makes a new one and reveals the earlier one
pid = fresh_project()
c = post("/visit/open", {"id": pid})["visit_capability"]
earlier = post("/make", {"id": pid, "kind": "write", "content": "an earlier page", "capability": c})["file"]
post("/handoff", {"id": pid, "text": "first visit", "next_move": "", "next_return": "tomorrow", "capability": c})
run_visit(pid, '<piece kind="write">a new page</piece><look>I looked</look>'
               '<reveal artifact="%s">for you</reveal>'
               '<handoff>HANDOFF-AFTER-REVEAL</handoff><next_move>begin again</next_move>'
               '<next_return>tomorrow</next_return>' % earlier)
proj = json.load(open(os.path.join(ROOT, "projects", pid, "project.json")))
check("the reveal was delivered and the undertaking settled", DELIVERED == [earlier] and proj.get("state") == "ARCHIVED",
      (DELIVERED, proj.get("state")))
check("no 'his handoff was refused' fault", not any(w == "his handoff was refused" for w, _ in FAILED), FAILED)
ho = handoff_of(pid)
check("his handoff note was saved", ho.get("text") == "HANDOFF-AFTER-REVEAL" and ho.get("next_move") == "begin again", ho)
order = [p for p in POSTS if p in ("/handoff", "/settle")]
check("the handoff is posted once, before settlement", order == ["/handoff", "/settle"], order)
st = json.load(open(os.path.join(ROOT, "projects", pid, "reveal", "settlement.json")))
check("settlement still issues its signed receipt", bool(st.get("sig")) and st.get("worktable_released") is True, st)

# an ordinary visit (no reveal): the handoff is posted once at the end and closes the visit
pid2 = fresh_project()
run_visit(pid2, '<piece kind="write">a page</piece><handoff>ORDINARY</handoff><next_return>tomorrow</next_return>')
check("an ordinary visit saves its handoff once", handoff_of(pid2).get("text") == "ORDINARY"
      and POSTS.count("/handoff") == 1 and not FAILED, (POSTS, FAILED))
v2 = json.load(open(os.path.join(ROOT, "projects", pid2, ".visit.json")))
check("and the handoff closed that visit", v2.get("closed") is True, v2)

# a reveal that fails to deliver: nothing settles, the handoff is still saved once at the end
pid3 = fresh_project()
c3 = post("/visit/open", {"id": pid3})["visit_capability"]
e3 = post("/make", {"id": pid3, "kind": "write", "content": "older", "capability": c3})["file"]
post("/handoff", {"id": pid3, "text": "x", "next_move": "", "next_return": "tomorrow", "capability": c3})
run_visit(pid3, ok=False, answer='<piece kind="write">p</piece><reveal artifact="%s">x</reveal><handoff>KEPT-OPEN</handoff>' % e3)
check("a reveal that did not deliver does not settle; the handoff is saved once at the end",
      "/settle" not in POSTS and POSTS.count("/handoff") == 1 and handoff_of(pid3).get("text") == "KEPT-OPEN"
      and not FAILED, (POSTS, FAILED))

check("nothing left this host", NET == [] and NTFY == [], (NET, NTFY))
srv.shutdown(); shutil.rmtree(ROOT, ignore_errors=True); shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

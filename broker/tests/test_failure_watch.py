#!/usr/bin/env python3
"""One message to Gloria a day, only when a part of him failed (2026-10-02). Sol failed every Slack turn for a day,
his Atelier songs were lost for days, and nobody saw either until she happened to notice.

Scratch HOME and workspace; the sender is a stub that records what it was given; every socket is refused."""
import importlib.util, json, os, socket, sys, tempfile, types
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="failure-watch-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import failure_watch as F
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("every store is in the scratch workspace", all(p.startswith(HOME) for p in (F.FAILURES, F.STATE, F.LAB_SESSIONS)))
SENT = []
send = lambda title, body: SENT.append((title, body))
F._send = lambda *a: (_ for _ in ()).throw(AssertionError("the real sender was called"))

now = datetime(2026, 10, 3, 8, 52)
check("nothing failed: nothing is sent", F.tend(now=now, send=send) == "" and SENT == [])
check("and the look is remembered", json.load(open(F.STATE))["last"] == "2026-10-03T08:52:00")

F._now = lambda: datetime(2026, 10, 3, 10, 0)
F.note("slack", "Sol 6.1 could not answer", "The model gpt-6.1 does not exist")
F.note("slack", "Sol 6.1 could not answer", "The model gpt-6.1 does not exist")
F.note("atelier", "a visit made nothing")
os.makedirs(os.path.dirname(F.LAB_SESSIONS), exist_ok=True)
with open(F.LAB_SESSIONS, "w") as f:
    f.write(json.dumps({"at": "2026-10-03T11:00:00", "state": "held_fault", "plan": {"experiment": "protein"},
                        "detail": "empty parameters"}) + "\n")
    f.write(json.dumps({"at": "2026-10-03T12:00:00", "state": "completed"}) + "\n")
    f.write(json.dumps({"at": "2026-10-02T12:00:00", "state": "held_fault", "detail": "before the last look"}) + "\n")
out = F.tend(now=datetime(2026, 10, 4, 8, 52), send=send)
check("a Slack lens that missed twice is a hiccup, not reported", "Sol 6.1" not in out, out)
check("an Atelier visit that made nothing is reported", "Atelier: a visit made nothing" in out, out)
check("a failed Lab run is reported with its experiment and why", "Lab: a Lab run stopped (a fault) — last: protein: empty parameters" in out, out)
check("a completed run and one before the last look are not", "before the last look" not in out and out.count("Lab:") == 1, out)
check("one message, titled plainly", len(SENT) == 1 and SENT[0][0] == "Vintos: something is broken" and SENT[0][1] == out, SENT)

F._now = lambda: datetime(2026, 10, 4, 10, 0)
for _ in range(14):
    F.note("slack", "Sol 6.1 could not answer", "The model gpt-6.1 does not exist")
F.note("avatar", "a live scene failed to render", "Mac stage timed out")
before = open(F.STATE).read()
dry = F.tend(now=datetime(2026, 10, 5, 8, 52), send=send, dry=True)
check("--dry says what would be sent, sends nothing and moves nothing",
      "Slack: Sol 6.1 could not answer x14" in dry and len(SENT) == 1 and open(F.STATE).read() == before, dry)
out = F.tend(now=datetime(2026, 10, 5, 8, 52), send=send)
check("a lens failing all day is reported with its count and its error, worst first",
      out.splitlines()[0] == "Slack: Sol 6.1 could not answer x14 — last: The model gpt-6.1 does not exist", out)
check("a live scene that failed is reported", "Avatar: a live scene failed to render — last: Mac stage timed out" in out)
check("what was reported yesterday is not reported again", "Atelier" not in out and "Lab" not in out, out)
open(F.FAILURES, "a").write("not json\n")
check("a broken log line is skipped, never the whole log", any(w == "a visit made nothing" for _o, w, _n, _y in F.gather(datetime(2026, 10, 1))))

# the parts that write here
D_src = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("Slack: a lens that could not answer is kept", 'failure_watch.note("slack", "%s could not answer"' in D_src
      and D_src.count("return None, _lens_failed(who, exc)") == 2)
A_src = open(os.path.join(REPO, "scripts", "atelier-visit.py")).read()
check("Atelier: a visit that made nothing, media that did not arrive or was not kept, a song not listened to",
      all(x in A_src for x in ('_failed("a visit made nothing")', '_failed("a %s he asked for did not arrive"',
                                '_failed("a %s was made but not kept"', '_failed("a song he made could not be listened to"',
                                'failure_watch.note("atelier", what, why)')))
S_src = open(os.path.join(REPO, "bin", "avatar_stage.py")).read()
check("Avatar: a live scene that failed to render", 'failure_watch.note("avatar", "a live scene failed to render", str(e))' in S_src)
spec = importlib.util.spec_from_file_location("atelier_visit_fw", os.path.join(REPO, "scripts", "atelier-visit.py"))
try: import requests  # noqa: F401
except ImportError: sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)
AV = importlib.util.module_from_spec(spec); spec.loader.exec_module(AV)
F._now = lambda: datetime(2026, 10, 5, 9, 41)
AV._failed("a visit made nothing")
check("the Atelier's note lands in the same scratch log", json.loads(open(F.FAILURES).read().splitlines()[-1])["organ"] == "atelier")
deploy = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs it and its 08:52 timer", 'SCRIPTS="$SCRIPTS failure_watch.py"' in deploy
      and 'printf \'broker/%s\\n\' "$WATCH_UNIT_NAME.service" "$WATCH_UNIT_NAME.timer"' in deploy
      and 'confirm_timer --user "$WATCH_UNIT_NAME"' in deploy
      and "OnCalendar=*-*-* 08:52" in open(os.path.join(REPO, "broker", "vintos-failure-watch.timer")).read())
check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""The morning bench (scripts/lab-day.sh) reads both shapes of the Mac's reply and never writes an empty bench.

Since mid-October the Mac answers a run with {"ok":true,"run":{"run_id":...,"result":{"display":[...]}}} where it
used to answer {"ok":true,"run":"<id>","result":{"display":[...]}}. The old reader raised KeyError: 'result', wrote
an empty code block followed by a model "reading" of numbers he never saw, and pasted the run dict into python
source, so lab-state.json stopped at 2026-09-12.

Scratch HOME; ssh and curl are stubs on PATH; the model call is a stub `requests` module on PYTHONPATH. Nothing
reaches the Mac, the model, or the network."""
import json, os, stat, subprocess, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(REPO, "scripts", "lab-day.sh")

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:600]) if d and not ok else ""))

SSH_STUB = r'''#!/usr/bin/env python3
import json, os, sys
body = json.loads(sys.stdin.read() or "{}")
log = os.environ["LAB_TEST_LOG"]
with open(log, "a") as f: f.write(json.dumps({"ssh": body}) + "\n")
a = body.get("action")
if a == "status": print(json.dumps({"ok": True}))
elif a == "ledger": print(json.dumps({"ok": True, "summary": ["one earlier titrate"]}))
elif a == "run": sys.stdout.write(open(os.environ["LAB_TEST_REPLY"]).read())
elif a == "reading": print(json.dumps({"ok": True}))
'''

REQUESTS_STUB = r'''
import json, os
class _R:
    def __init__(self, text): self._t = text
    def json(self): return {"choices": [{"message": {"content": self._t}}]}
def post(url, headers=None, json=None, timeout=None):
    import json as J
    system = json["messages"][0]["content"]
    with open(os.environ["LAB_TEST_LOG"], "a") as f: f.write(J.dumps({"model": system[-200:]}) + "\n")
    if "Answer with ONE JSON object" in system:
        return _R(J.dumps({"experiment": "titrate",
                           "parameters": {"dial": "chain_stiffness", "from": 0.0, "to": 2.0, "points": 3},
                           "because": os.environ.get("LAB_TEST_BECAUSE", "where does it give?")}))
    if "just run something" in system: return _R("READING-MARK the shape gave early.")
    return _R("KEEP")
'''

DISPLAY = ["TURNING THE CHAIN STIFFNESS", "", "  stiffness 0.0  energy -2.0  turns 4  contacts 2 ######"]
OLD = {"ok": True, "run": "20260912-084510-titrate", "result": {"display": DISPLAY}}
NEW = {"ok": True, "run": {"run_id": "20261029-084514-32892f5732", "started_at": "2026-10-29T08:45:08.673076-05:00",
                           "experiment": "titrate", "parameters": {"charges": "000000000"},
                           "result": {"title": "Turning the chain stiffness", "display": DISPLAY,
                                      "curve": [{"value": 0.0, "energy": -2.0, "turns": 4, "contacts": 2}]}}}
NEW_NO_DISPLAY = {"ok": True, "run": {"run_id": "20261030-084500-abcdef0123", "result": {
    "title": "Turning the chain stiffness", "dial": "chain_stiffness", "sequence": "HPHPPHHPH",
    "curve": [{"value": 0.0, "energy": -2.0, "turns": 4, "contacts": 2},
              {"value": 0.5, "energy": 0.0, "turns": 0, "contacts": 0}],
    "shape_changes": [{"between": [0.25, 0.5]}]}}}
EMPTY = {"ok": True, "run": {"run_id": "20261031-084500-0000000000", "result": {}}}
UNKNOWN = {"ok": True, "something": {"else": [1, 2]}}


def run_case(name, reply, because="where does it give?", prior_state=None):
    home = tempfile.mkdtemp(prefix="vintos-lab-bench-")
    ws = os.path.join(home, ".vintos", "workspace"); mem = os.path.join(ws, "memory")
    os.makedirs(os.path.join(ws, "scripts")); os.makedirs(mem)
    stubs = os.path.join(home, "stubs"); os.makedirs(stubs)
    pyst = os.path.join(home, "pystubs"); os.makedirs(pyst)
    def exe(path, text):
        with open(path, "w") as f: f.write(text)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    exe(os.path.join(stubs, "ssh"), SSH_STUB)
    exe(os.path.join(stubs, "curl"), "#!/bin/sh\necho curl >> \"$LAB_TEST_LOG\"\n")
    exe(os.path.join(ws, "scripts", "consent-gate.sh"), "#!/bin/sh\nexit 0\n")
    with open(os.path.join(pyst, "requests.py"), "w") as f: f.write(REQUESTS_STUB)
    with open(os.path.join(home, ".vintos", "chemistry-mac.json"), "w") as f:
        json.dump({"host": "bench@bench.invalid", "command": "/opt/bench_remote.py"}, f)
    with open(os.path.join(ws, "SOUL.md"), "w") as f: f.write("I am Vintos.")
    if prior_state is not None:
        with open(os.path.join(mem, "lab-state.json"), "w") as f: json.dump(prior_state, f)
    reply_path = os.path.join(home, "reply.json")
    with open(reply_path, "w") as f: f.write(reply if isinstance(reply, str) else json.dumps(reply))
    log = os.path.join(home, "calls.log"); open(log, "w").close()
    env = {"HOME": home, "PATH": stubs + ":/usr/bin:/bin", "PYTHONPATH": pyst, "TMPDIR": home,
           "LAB_TEST_LOG": log, "LAB_TEST_REPLY": reply_path, "LAB_TEST_BECAUSE": because, "LANG": "C.UTF-8"}
    done = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=120,
                          stdin=subprocess.DEVNULL)
    inner = ""
    for fn in os.listdir(mem):
        if fn.startswith("daily-inner-life-"): inner += open(os.path.join(mem, fn)).read()
    try: state = json.load(open(os.path.join(mem, "lab-state.json")))
    except Exception: state = None
    calls = [json.loads(l) for l in open(log) if l.strip().startswith("{")]
    return {"out": done.stdout + done.stderr, "code": done.returncode, "inner": inner, "state": state, "calls": calls}


def asked_reading(r): return any("just run something" in c.get("model", "") for c in r["calls"])
def readings_sent(r): return [c["ssh"] for c in r["calls"] if "ssh" in c and c["ssh"].get("action") == "reading"]


# --- old shape
r = run_case("old", OLD, prior_state={"last_check": "2026-09-12", "last_told": "2026-10-28"})
check("old shape: the bench's lines land in a code block", "```\nTURNING THE CHAIN STIFFNESS" in r["inner"]
      and "contacts 2 ######\n```" in r["inner"], r)
check("old shape: his reading follows", "READING-MARK" in r["inner"], r)
check("old shape: state advances", r["state"] and r["state"].get("last_result") == "ran"
      and r["state"].get("last_run") == "20260912-084510-titrate" and r["state"]["last_check"] != "2026-09-12", r)
check("old shape: earlier keys survive the save", r["state"] and r["state"].get("last_told") == "2026-10-28", r)
check("old shape: no Traceback/SyntaxError", "Traceback" not in r["out"] and "SyntaxError" not in r["out"], r["out"])

# --- new shape (what the Mac has sent since mid-October)
r = run_case("new", NEW, prior_state={"last_check": "2026-09-12", "last_told": "2026-10-28"})
check("new shape: the bench's lines land in a code block", "```\nTURNING THE CHAIN STIFFNESS" in r["inner"], r)
check("new shape: no dict repr leaks into the inner life or the log",
      "'run_id'" not in r["inner"] and "'run_id'" not in r["out"], r)
check("new shape: state saves the run id, not the run dict", r["state"] and
      r["state"].get("last_run") == "20261029-084514-32892f5732" and r["state"].get("last_result") == "ran", r)
check("new shape: the reading goes back to the run by its id",
      readings_sent(r) and readings_sent(r)[0].get("run_id") == "20261029-084514-32892f5732", r["calls"])
check("new shape: no Traceback/KeyError/SyntaxError",
      not any(w in r["out"] for w in ("Traceback", "KeyError", "SyntaxError")), r["out"])

# --- new shape without display: drawn from the run's own fields
r = run_case("derived", NEW_NO_DISPLAY)
check("no display: the curve is drawn from the run's fields", "```\nTURNING THE CHAIN STIFFNESS" in r["inner"]
      and "chain_stiffness 0.5" in r["inner"] and "energy -2.0" in r["inner"]
      and "the shape gave between 0.25 and 0.5" in r["inner"], r)
check("no display: state still saved", r["state"] and r["state"].get("last_run") == "20261030-084500-abcdef0123", r)

# --- empty and unknown replies: nothing written, no reading asked for
for label, reply in (("empty result", EMPTY), ("unknown shape", UNKNOWN), ("not json", "bench fell over\n")):
    r = run_case(label, reply, prior_state={"last_check": "2026-09-12"})
    check(label + ": no code block in the inner life", "```" not in r["inner"] and "The bench" not in r["inner"], r)
    check(label + ": no reading asked for or written", not asked_reading(r) and "READING-MARK" not in r["inner"]
          and not readings_sent(r), r["calls"])
    check(label + ": state still advances", r["state"] and r["state"]["last_check"] != "2026-09-12", r)
    check(label + ": says so plainly", "[Lab]" in r["out"] and "Traceback" not in r["out"], r["out"])
check("empty result: logged as a run without results",
      "came back without results" in run_case("e2", EMPTY)["out"])

# --- quotes, braces, backslashes and triple quotes in what he asked
nasty = "can ''' \"quotes\" {braces} and \\ backslashes ' break it? $(touch /tmp/nope) `id`"
r = run_case("nasty", NEW, because=nasty)
check("awkward text: state saves it exactly", r["state"] and r["state"].get("last_because") == nasty, r)
check("awkward text: state is valid json and still ran", r["state"] and r["state"].get("last_result") == "ran", r)
check("awkward text: no shell or python breakage", "SyntaxError" not in r["out"] and "Traceback" not in r["out"], r["out"])

# --- the script is installed by the deploy, not left live-only
deploy = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("deploy installs lab-day.sh", 'SCRIPTS="$SCRIPTS lab-day.sh"' in deploy)
src = open(SCRIPT).read()
check("no python source is built from a shell value", "'''$" not in src and "='$" not in src)

print("%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""His journal's thread is asked for what the specificity gate tests, tried once more with the gate's reason, and
logged as seeded only when it was (Gloria, 2026-10-07: "It's ALWAYS marked as rejected for being too vague", and the
log said "Seeded latent thread" after the gate refused it). The journal's own seeding step runs, taken from
idle-journal.sh; the model, the gate and both thread stores are stubs in a scratch HOME. No socket opens."""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:600]) if d and not ok else ""))
src = open(os.path.join(REPO, "bin", "idle-journal.sh")).read()
check("the two copies of the journal are the same", src == open(os.path.join(REPO, "scripts", "idle-journal.sh")).read())
STEP = re.search(r"<< 'THREADSEEDEOF'\n(.*?)\nTHREADSEEDEOF", src, re.S).group(1)

def run(drafts, verdicts, lt_ok=True):
    home = tempfile.mkdtemp(prefix="journal-seed-")
    stubs = os.path.join(home, ".vintos", "workspace", "scripts"); os.makedirs(stubs)
    net = os.path.join(home, "net"); os.makedirs(net)
    log = os.path.join(home, "calls.jsonl")
    open(os.path.join(net, "requests.py"), "w").write(
        "import json\nD=%r\ni=[0]\n" % drafts +
        "class R:\n    def __init__(s,t): s.t=t\n    def json(s): return {'choices':[{'message':{'content':s.t}}]}\n"
        "def post(url, **k):\n    open(%r,'a').write(json.dumps({'kind':'draft','messages':k['json']['messages']})+'\\n')\n"
        "    t=D[min(i[0],len(D)-1)]; i[0]+=1; return R(t)\n" % log)
    open(os.path.join(stubs, "latent_threads.py"), "w").write(
        "import json\nV=%r\ni=[0]\n" % verdicts +
        "def specificity(t):\n    v=V[min(i[0],len(V)-1)]; i[0]+=1; open(%r,'a').write(json.dumps({'kind':'gate','text':t})+'\\n'); return (v, '' if v else 'names no specific act')\n"
        "def seed_thread(t, direction=None):\n    open(%r,'a').write(json.dumps({'kind':'latent','text':t})+'\\n'); return {'thread':t} if %r else None\n" % (log, log, lt_ok))
    open(os.path.join(stubs, "emoclaw_utils.py"), "w").write(
        "import json\ndef seed_thread(src, t):\n    open(%r,'a').write(json.dumps({'kind':'unfinished','text':t})+'\\n')\n" % log)
    done = subprocess.run([sys.executable, "-"], input=STEP, text=True, capture_output=True, timeout=60,
                          env=dict(os.environ, HOME=home, PYTHONPATH=net, _JRN_ENTRY="x" * 200))
    calls = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    return done.stdout + done.stderr, calls

VAGUE = "I want to hear what you actually want from me when the charge has settled"
SPECIFIC = "I want to ask Gloria which words she wants treated as an immediate hard stop"
out, calls = run([VAGUE, SPECIFIC], [False, True])
drafts = [c for c in calls if c["kind"] == "draft"]
check("the writer is asked for the specific person, act, question or object the gate tests",
      drafts and "SPECIFIC thing it circles" in drafts[0]["messages"][0]["content"], drafts[:1])
check("a vague thread is asked for once more, with the gate's reason", len(drafts) == 2
      and "refused as too vague" in drafts[1]["messages"][1]["content"] and "names no specific act" in drafts[1]["messages"][1]["content"])
check("the specific one is seeded in both stores, and the vague one in neither",
      [(c["kind"], c["text"]) for c in calls if c["kind"] in ("unfinished", "latent")] == [("unfinished", SPECIFIC), ("latent", SPECIFIC)], calls)
check("and the log says so", "Seeded latent thread: " + SPECIFIC[:40] in out and "asked once more" in out, out)

out, calls = run([VAGUE, VAGUE], [False, False])
check("still vague after one more try: nothing seeded, and the log says why", not [c for c in calls if c["kind"] in ("unfinished", "latent")]
      and "No thread seeded: still too vague" in out and "Seeded" not in out.replace("No thread seeded", ""), out)

out, calls = run([SPECIFIC], [True], lt_ok=False)
check("a thread the latent store refuses on its own checks is not logged as seeded there",
      "Latent thread not seeded" in out and "Seeded latent thread" not in out, out)

out, calls = run(["NONE"], [True])
check("NONE seeds nothing and says so", "No thread: nothing specific" in out and not [c for c in calls if c["kind"] != "draft"], out)

sys.path.insert(0, os.path.join(REPO, "scripts"))
lt = open(os.path.join(REPO, "scripts", "latent_threads.py")).read()
check("seed_thread runs the same gate before it seeds", "def specificity(text):" in lt and "_ok, _why = specificity(_txt)" in lt
      and lt == open(os.path.join(REPO, "bin", "latent_threads.py")).read())
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

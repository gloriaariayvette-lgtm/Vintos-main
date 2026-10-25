#!/usr/bin/env python3
"""More of his outreach is something he feels like saying (Gloria, 2026-10-25).

Runs the real trigger-selection and message blocks of bin/vintos-initiate.sh against a scratch HOME with a stub
model; nothing is sent. Covers: the gap prompt is no longer repair (B); his self-corrections are no longer in every
outreach (C); a flat_repetition label alone no longer routes a want to her (E); yearning, unsaid resonance,
fermenting jokes and moments start an outreach only when fresh (F); feelings are tried before divergence (G); and
the repetition limits on every trigger.
"""
import json, os, re, subprocess, sys, tempfile, time
from datetime import datetime, timedelta

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:500]) if detail and not ok else ""))

HOME = tempfile.mkdtemp(prefix="vintos-outreach-feel-")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); SCR = os.path.join(WS, "scripts")
os.makedirs(MEM); os.makedirs(SCR)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
for f in ("outreach_feelings.py", "resonance_felt.py"):
    open(os.path.join(SCR, f), "w").write(open(os.path.join(REPO, "scripts", f)).read())
# divergence detector stub: prints a divergence only when the test asks for one
open(os.path.join(SCR, "divergence_detector.py"), "w").write(
    "import os\nj = os.environ.get('DV_JSON')\nif j: print(j)\n")
sys.path.insert(0, SCR)
import outreach_feelings as OF
check("every store is in the scratch HOME", OF.STATE.startswith(HOME) and OF.MEMORY.startswith(HOME), OF.STATE)

src = open(os.path.join(REPO, "bin", "vintos-initiate.sh")).read()
select = src[src.index('TRIGGER=""\n'):src.index('export DIVERGENCE_JSON FEELING_TEXT')]
select += 'printf "%s|%s|%s" "$TRIGGER" "$ITEM" "$FEELING_TEXT"\n'
prompt_block = re.search(r"RESPONSE=\$\(python3 << 'PYEOF'\n(.*?)\nPYEOF\n", src, re.S).group(1)

def wipe():
    for f in os.listdir(MEM):
        p = os.path.join(MEM, f)
        if os.path.isfile(p): os.remove(p)
    os.makedirs(os.path.join(MEM, "outreach"), exist_ok=True)

def put(name, obj):
    json.dump(obj, open(os.path.join(MEM, name), "w"))

def select_trigger(tension="0.3", **env):
    e = dict(os.environ, HOME=HOME, WORKSPACE=WS, MEMORY=MEM, OUTREACH_DIR=os.path.join(MEM, "outreach"),
             TENSION=tension, CURIOSITY="0.3", PLAYFULNESS="0.2", GROUNDEDNESS="0.4", WARMTH="0.4",
             DESIRE="0.2", CONNECTION="0.6", FORCED_WANT_TOPIC="", **env)
    script = 'WORKSPACE="%s"; MEMORY="%s"; OUTREACH_DIR="$MEMORY/outreach"\n' % (WS, MEM) + select
    p = subprocess.run(["bash", "-c", script], env=e, capture_output=True, text=True, timeout=60)
    return (p.stdout.split("|") + ["", "", ""])[:3], p

now = time.time()
iso = lambda dt: dt.isoformat()

# ---------- F: each feeling fires from a fresh fixture, not from a stale or empty one ----------
wipe()
check("nothing fresh: no feeling is offered", all(OF.FEELINGS[k]() is None for k in OF.FEELINGS))
put("current-yearning.json", {"surface_form": "I want to hear the ferry again", "intensity": 0.7, "dismissed": False,
                              "created": iso(datetime.now() - timedelta(days=1)), "expires": iso(datetime.now() + timedelta(days=6))})
check("a live yearning is offered", (OF.yearning() or ("", ""))[1] == "I want to hear the ferry again", OF.yearning())
put("current-yearning.json", {"surface_form": "old", "intensity": 0.7, "created": iso(datetime.now() - timedelta(days=9)),
                              "expires": iso(datetime.now() - timedelta(days=2))})
check("an expired yearning is not", OF.yearning() is None)
put("current-yearning.json", {"surface_form": "x", "intensity": 0.9, "dismissed": True, "created": iso(datetime.now())})
check("a dismissed yearning is not", OF.yearning() is None)

put("resonance-felt.json", {"at": now - 3600, "score": 0.72, "his_shape": "SECRET-HIS", "her_unsaid": "SECRET-HERS"})
r = OF.resonance()
check("a fresh resonance is offered, as its own sentence", r and "quiet about the same place" in r[1], r)
check("the shapes never reach his prompt", r and "SECRET" not in r[1], r)
put("resonance-felt.json", {"at": now - 60 * 3600, "score": 0.8})
check("a resonance older than its freshness window is not", OF.resonance() is None)

put("joke-ferment.json", [{"id": "j1", "seed": "the bay ferry has a better commute than me", "ripe_at": now - 600,
                           "fired": False, "offer_count": 0}])
check("a ripe joke is offered", (OF.joke() or ("", ""))[0] == "j:j1", OF.joke())
put("joke-ferment.json", [{"id": "j2", "seed": "not yet", "ripe_at": now + 3600, "fired": False},
                          {"id": "j3", "seed": "too late", "ripe_at": now - 7 * 3600, "fired": False},
                          {"id": "j4", "seed": "already told", "ripe_at": now - 60, "fired": True}])
check("an unripe, overripe or fired joke is not", OF.joke() is None, OF.joke())

put("moment-archive.json", {"moments": {"m1": {"content": "the kitchen light at 2am", "intensity": 0.85,
                                                "timestamp": iso(datetime.now() - timedelta(hours=20))},
                                         "m2": {"content": "faint", "intensity": 0.3,
                                                "timestamp": iso(datetime.now() - timedelta(hours=20))}}})
check("a charged moment is offered, the strongest", (OF.moment() or ("", ""))[0] == "m:m1", OF.moment())
put("moment-archive.json", {"moments": {"m3": {"content": "too fresh", "intensity": 0.9, "timestamp": iso(datetime.now())},
                                         "m4": {"content": "too old", "intensity": 0.9,
                                                "timestamp": iso(datetime.now() - timedelta(days=10))}}})
check("a moment too fresh or too old is not", OF.moment() is None)

# ---------- G: feelings first, divergence after them ----------
wipe()
put("current-yearning.json", {"surface_form": "I want to hear the ferry again", "intensity": 0.7,
                              "created": iso(datetime.now() - timedelta(days=1)), "expires": iso(datetime.now() + timedelta(days=6))})
(trig, item, feel), p = select_trigger(DV_JSON='{"frame":"x"}')
check("with a yearning and a divergence both present, the yearning goes first", trig == "yearning", (trig, p.stderr[-300:]))
check("the feeling's own words reach the message step", feel == "I want to hear the ferry again", feel)
os.remove(os.path.join(MEM, "current-yearning.json"))
(trig, _, _), p = select_trigger(tension="0.7", DV_JSON='{"frame":"x"}')
check("tension, an existing feeling, also comes before divergence", trig == "tension", (trig, p.stderr[-300:]))
(trig, _, _), p = select_trigger(DV_JSON='{"frame":"x"}')
check("divergence still fires when no feeling does", trig == "divergence", (trig, p.stderr[-300:]))

# ---------- repetition limits, on every trigger ----------
wipe()
put("current-yearning.json", {"surface_form": "I want to hear the ferry again", "intensity": 0.7,
                              "created": iso(datetime.now() - timedelta(days=1)), "expires": iso(datetime.now() + timedelta(days=6))})
(trig, item, _), _ = select_trigger()
OF.record(trig, item)
check("after it went out, the same yearning is not used again", OF.pick(["yearning|" + item], relaxed=True) is None)
check("a different item of the same trigger waits out the day's cooldown", OF.pick(["yearning|y:other"]) is None)
check("...unless nothing else is available", OF.pick(["yearning|y:other"], relaxed=True) == ("yearning", "y:other"))
check("another trigger is not held back by it", OF.pick(["tension|"]) == ("tension", ""))
OF.record("tension", "")
check("an itemless trigger that fired last waits a day too", OF.pick(["tension|"]) is None)
s = json.load(open(OF.STATE))
check("the state is written atomically to a small file under memory/",
      OF.STATE.startswith(MEM) and not os.path.exists(OF.STATE + ".tmp") and s["last"]["trigger"] == "tension")
check("repetition is recorded only after a message went out, not when chosen",
      src.index('python3 "$OF" record') > src.index('cat > "$OUTREACH_DIR/${TIMESTAMP}.md"'))
wipe()
(trig, item, _), _ = select_trigger(tension="0.7")
OF.record(trig, item)
(trig2, _, _), _ = select_trigger(tension="0.7")
check("the selection itself applies the limits: tension twice in a row inside a day falls to free",
      trig == "tension" and trig2 == "free", (trig, trig2))
wipe()
open(os.path.join(MEM, ".last-missing-outreach"), "w").write(str(int(time.time()) - 3600))
(trig, _, _), p = select_trigger()
check("a missing-her reach-out inside the last day still stands the run down: no free reach-out takes its place",
      trig == "", (trig, p.stdout[-200:], p.stderr[-200:]))

# ---------- B, C, F: what he is asked to write ----------
fake = os.path.join(HOME, "fake"); os.makedirs(fake, exist_ok=True); calls = os.path.join(HOME, "calls.log")
open(os.path.join(fake, "requests.py"), "w").write(
    "import json\nclass _R:\n    def json(s): return {'choices': [{'message': {'content': 'hello'}}]}\n"
    "def post(url, **k):\n    m = k.get('json', {}).get('messages', [{}, {}])\n"
    "    open(%r, 'a').write(json.dumps({'url': url, 'system': m[0].get('content', ''), 'user': m[-1].get('content', '')}) + '\\n')\n"
    "    return _R()\n" % calls)
open(os.path.join(MEM, "autonomous-blush.md"), "w").write("I MISREAD HER YESTERDAY")
def ask(trigger, **env):
    if os.path.exists(calls): os.remove(calls)
    e = dict(os.environ, HOME=HOME, PYTHONPATH=fake, TRIGGER=trigger, EMOTIONS="warm", SOUL_CONTENT="I am Vintos.", **env)
    p = subprocess.run([sys.executable, "-c", prompt_block], env=e, capture_output=True, text=True, timeout=60)
    rows = [json.loads(l) for l in open(calls)] if os.path.exists(calls) else []
    return (rows[-1] if rows else {}), p
dv = json.dumps({"frame": "what you composed over rather than said", "shape": "a softer version"})
got, p = ask("divergence", DIVERGENCE_JSON=dv)
u = got.get("user", "")
check("B: the gap is something left out he may want to say", "left out" in u and "If you feel like saying" in u, u[:300] + p.stderr[-300:])
check("B: no repair framing remains", not re.search(r"\bclos(e|ing)\b|worth closing|close THIS", u), u[:300])
check("C: his self-corrections are not in the outreach prompt", "CORRECTED MYSELF" not in got.get("system", "")
      and "MISREAD" not in got.get("system", "") and "AUTO_BLUSH" not in prompt_block)
for trig, words in (("yearning", "the ferry"), ("resonance", "quiet about the same place"),
                    ("joke", "commute"), ("moment", "kitchen light")):
    got, p = ask(trig, FEELING_TEXT="about %s" % words)
    u = got.get("user", "")
    check("F: the %s branch carries the feeling and asks only what he feels like saying" % trig,
          words in u and "feel like" in u and not re.search(r"\b(fix|correct|mistake|apolog|wrong)\w*", u), u[:300])
check("nothing was sent: the only calls went to the stub model", all("ntfy" not in json.dumps(r) for r in
      [json.loads(l) for l in open(calls)]) if os.path.exists(calls) else True)

# ---------- E: a flat_repetition label alone no longer routes a want to her ----------
router = open(os.path.join(REPO, "bin", "wants-router.py")).read()
fn = re.search(r"\ndef _is_communicative\(want_text\):\n(?:    .*\n|\n)+", router).group(0)
ns = {}; exec(fn, ns)
check("E: a flat_repetition want is no longer outreach", ns["_is_communicative"]("flat_repetition in my last three turns") is False)
check("E: an unsent ask still is", ns["_is_communicative"]("the unsent ask from yesterday") is True)
check("E: a plain sentence still is", ns["_is_communicative"]("a plain sentence I meant") is True)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""Spontaneous postcards with something in them (proposal 06, 26 October).

An outreach may carry one thing he already made and kept, or revealed, when he chooses to send it with his words;
and an outreach is "sent" only on a real send, never because his words were saved.

Runs scripts/outreach_postcards.py against a scratch workspace, then the whole of bin/vintos-initiate.sh against a
scratch HOME with a stub model, a stub ntfy (a fake `requests` module that only records), a stub curl on PATH, and
stub consent/send-policy gates. Nothing is sent anywhere.
"""
import builtins, json, os, re, shutil, stat, subprocess, sys, tempfile, time
from datetime import datetime, timedelta

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:700]) if detail and not ok else ""))

HOME = tempfile.mkdtemp(prefix="vintos-postcards-")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); SCR = os.path.join(WS, "scripts")
ART = os.path.join(MEM, "art")
os.makedirs(os.path.join(ART, "music")); os.makedirs(SCR); os.makedirs(os.path.join(MEM, "atelier"))
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
os.environ.pop("XAI_API_KEY", None)
os.environ["VINTOS_SERVE_BASE"] = "http://house.test:8500"
for f in ("outreach_postcards.py", "artifact_manifest.py", "outreach_feelings.py", "resonance_felt.py",
          "deliver.py", "effect_authority.py", "paid_http.py"):
    shutil.copy(os.path.join(REPO, "scripts", f), os.path.join(SCR, f))
sys.path.insert(0, SCR)
import outreach_postcards as PC
check("every store the postcards module touches is in the scratch workspace",
      all(p.startswith(HOME) for p in (PC.STATE, PC.GALLERY, PC.REVEALS, PC.ART)), PC.STATE)

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
MP3 = b"ID3" + b"\0" * 64
def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "wb").write(data)
def put(path, obj):
    json.dump(obj, open(path, "w"))
iso = lambda **kw: (datetime.now() - timedelta(**kw)).isoformat()

def painting(name, **kw):
    rec = {"image": name, "prompt": "the ferry at night, from the water", "timestamp": iso(days=2),
           "image_class": "WANT_ACT", "verdict": "keep", "validated": {"ok": True, "how": "magic:png"},
           "shared": None, "delivery": None}
    rec.update(kw); return rec

def reset(gallery=(), reveals=()):
    for p in (PC.STATE, PC.GALLERY, PC.REVEALS):
        if os.path.exists(p): os.remove(p)
    put(PC.GALLERY, list(gallery)); put(PC.REVEALS, list(reveals))

# ---------- what may be offered ----------
write(os.path.join(ART, "kept.png"), PNG)
write(os.path.join(ART, "older-kept.png"), PNG)
write(os.path.join(ART, "remade.png"), PNG)
write(os.path.join(ART, "notimage.png"), b"not an image at all")
write(os.path.join(ART, "dream.png"), PNG)
write(os.path.join(ART, "with space.png"), PNG)
reset([painting("kept.png")])
got = PC.offer()
check("a painting he asked for and kept, on the shelf, is offered", got and got[0] == "p:kept.png", got)
check("...with a link the shelf route serves", got and got[1] == "http://house.test:8500/api/art/painting/kept.png", got)
check("...described from his own request, not from anything sealed", got and "the ferry at night" in got[2], got)

for name, rec, why in (
        ("taken down", painting("kept.png", taken_down=True), ""),
        ("he would remake it", painting("remade.png", verdict="remake"), ""),
        ("he has not judged it", painting("kept.png", verdict=None), ""),
        ("a dream-born image he never judged as an act", painting("dream.png", image_class="DREAM_BORN"), ""),
        ("already sent to her", painting("kept.png", delivery={"state": "sent"}), ""),
        ("already shared", painting("kept.png", shared={"where": "ntfy", "when": iso(days=1)}), ""),
        ("its record says it failed validation", painting("kept.png", validated={"ok": False, "how": "empty"}), ""),
        ("the file is missing", painting("gone.png"), ""),
        ("the file is not a real image", painting("notimage.png"), ""),
        ("its name is not one the shelf route serves", painting("with space.png"), ""),
        ("a path, not a shelf name", painting("../kept.png"), ""),
        ("made more than thirty days ago", painting("kept.png", timestamp=iso(days=40)), "")):
    reset([rec])
    check("not offered: %s" % name, PC.offer() is None, PC.offer())

reset([painting("older-kept.png", timestamp=iso(days=9)), painting("kept.png", timestamp=iso(days=1))])
check("the newest kept piece is offered first", (PC.offer() or [""])[0] == "p:kept.png", PC.offer())

# reveals: only what he revealed, with verified bytes on a public shelf matching the reveal's digest
import artifact_manifest as AM
write(os.path.join(ART, "music", "song-for-her.mp3"), MP3)
sha = AM.sha256_file(os.path.join(ART, "music", "song-for-her.mp3"))
write(os.path.join(MEM, "atelier", "sealed-piece.png"), PNG)
rev = {"artifact": "song-for-her.mp3", "revealed": True, "bytes_verified": True, "sha256": sha,
       "revealed_at": iso(days=1), "disclosure": "I kept this one back until it was right", "medium": "music"}
reset(reveals=[rev])
got = PC.offer()
check("a revealed piece of music with verified bytes is offered on the music shelf's link",
      got and got[0] == "r:" + sha[:16] and got[1].endswith("/api/art/music/stream/song-for-her.mp3"), got)
check("...in what he said of it when he revealed it", got and "kept this one back" in got[2], got)
for name, row in (("its bytes were never verified", dict(rev, bytes_verified=False)),
                  ("its digest does not match the shelf file", dict(rev, sha256="0" * 64)),
                  ("it was not revealed", dict(rev, revealed=False)),
                  ("it is a written reveal, with no shelf link", dict(rev, artifact="poem.md", medium="write")),
                  ("it is sealed Atelier work, not on a public shelf", dict(rev, artifact="sealed-piece.png",
                                                                           sha256=AM.sha256_bytes(PNG)))):
    reset(reveals=[row])
    check("not offered: %s" % name, PC.offer() is None, PC.offer())

opened = []
_open = builtins.open
def _spy(p, *a, **k):
    opened.append(str(p)); return _open(p, *a, **k)
reset([painting("kept.png")], [rev, dict(rev, artifact="sealed-piece.png", sha256=AM.sha256_bytes(PNG))])
builtins.open = _spy
try:
    PC.candidates()
finally:
    builtins.open = _open
check("sealed Atelier work is never opened: nothing under memory/atelier/ is read",
      opened and not any(os.sep + "atelier" + os.sep in p for p in opened), opened)

# repetition: an offer he lets pass twice is not pressed on him; a sent piece never goes again; one a day
reset([painting("kept.png")])
PC.mark("p:kept.png", "offered")
check("an offer he let pass once may come again", (PC.offer() or [""])[0] == "p:kept.png")
PC.mark("p:kept.png", "offered")
check("...but not a third time", PC.offer() is None, PC.offer())
reset([painting("kept.png"), painting("older-kept.png", timestamp=iso(days=5))])
PC.mark("p:kept.png", "chosen"); PC.mark("p:kept.png", "sent", "outreach-x")
check("a piece that reached her is never offered again, and no other postcard is offered within a day",
      PC.offer() is None, PC.offer())
s = json.load(open(PC.STATE))
s["pieces"]["p:kept.png"]["sent_at"] = time.time() - 25 * 3600; put(PC.STATE, s)
check("after a day, the next kept piece may be offered", (PC.offer() or [""])[0] == "p:older-kept.png", PC.offer())
PC.mark("p:kept.png", "failed")
check("a later failure never unmarks a piece that was sent", json.load(open(PC.STATE))["pieces"]["p:kept.png"]["state"] == "sent")
check("the state is written atomically", not os.path.exists(PC.STATE + ".tmp"))

# ---------- the whole outreach run, offline ----------
FAKE = os.path.join(HOME, "fake"); BIN = os.path.join(HOME, "fakebin"); os.makedirs(FAKE); os.makedirs(BIN)
CALLS = os.path.join(HOME, "calls.log"); CURLS = os.path.join(HOME, "curl.log")
open(os.path.join(FAKE, "requests.py"), "w").write(
    "import json, os\n"
    "class _R:\n"
    "    def __init__(s, t, code=200): s.t = t; s.status_code = code\n"
    "    def json(s): return {'choices': [{'message': {'content': s.t}}]}\n"
    "def post(url, **k):\n"
    "    j = k.get('json') or {}\n"
    "    rec = {'url': url, 'headers': dict(k.get('headers') or {}),\n"
    "           'data': (k.get('data') or b'').decode('utf-8', 'replace') if isinstance(k.get('data'), bytes) else k.get('data'),\n"
    "           'user': (j.get('messages') or [{}])[-1].get('content', '')}\n"
    "    open(%r, 'a').write(json.dumps(rec) + '\\n')\n"
    "    if 'ntfy' in url: return _R('', int(os.environ.get('FAKE_NTFY_CODE', '200')))\n"
    "    return _R(os.environ.get('FAKE_REPLY', 'hello'))\n" % CALLS)
open(os.path.join(BIN, "curl"), "w").write(
    "#!/bin/bash\nprintf '%%s\\n' \"$*\" >> %s\nexit ${FAKE_CURL_EXIT:-22}\n" % CURLS)
os.chmod(os.path.join(BIN, "curl"), 0o755)
open(os.path.join(SCR, "send_policy.py"), "w").write("print('ok')\n")
open(os.path.join(SCR, "consent-gate.sh"), "w").write("exit 0\n")
open(os.path.join(MEM, "emotional-state.txt"), "w").write(
    "Valence 0.5\nWarmth 0.4\nTension 0.3\nCuriosity 0.3\nConnection 0.6\nDesire 0.2\nPlayfulness 0.2\nGroundedness 0.4\n")

SRC = os.path.join(REPO, "bin", "vintos-initiate.sh")
def run(reply, ntfy=200, curl_exit=22):
    for p in (CALLS, CURLS):
        if os.path.exists(p): os.remove(p)
    shutil.rmtree(os.path.join(MEM, "outreach"), ignore_errors=True)
    for f in ("delivery-receipts.json", "outreach-repeat.json"):
        if os.path.exists(os.path.join(MEM, f)): os.remove(os.path.join(MEM, f))
    env = dict(os.environ, HOME=HOME, SPARK_WORKSPACE=WS, PYTHONPATH=FAKE, PATH=BIN + os.pathsep + os.environ["PATH"],
               FAKE_REPLY=reply, FAKE_NTFY_CODE=str(ntfy), FAKE_CURL_EXIT=str(curl_exit), FORCED_WANT_TOPIC="")
    env.pop("XAI_API_KEY", None)
    p = subprocess.run(["bash", SRC], env=env, capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
    rows = [json.loads(l) for l in open(CALLS)] if os.path.exists(CALLS) else []
    curls = open(CURLS).read() if os.path.exists(CURLS) else ""
    outs = sorted(os.listdir(os.path.join(MEM, "outreach"))) if os.path.isdir(os.path.join(MEM, "outreach")) else []
    md = open(os.path.join(MEM, "outreach", outs[-1])).read() if outs else ""
    return p, [r for r in rows if "ntfy" not in r["url"]], [r for r in rows if "ntfy" in r["url"]], curls, md

check("isolation: the model and ntfy are a recording stub, curl is a stub, and the run's HOME is scratch",
      open(os.path.join(FAKE, "requests.py")).read().count("open(") == 1 and HOME.startswith(tempfile.gettempdir())
      and shutil.which("curl", path=BIN) == os.path.join(BIN, "curl"))

WORDS = "I finished the ferry painting last week and kept looking at it. It is the water I wanted you to see."
reset([painting("kept.png")])
p, llm, ntfy, curls, md = run(WORDS + "\n[postcard]")
check("the run asked him, in the turn he already has, whether the piece goes with his words",
      len(llm) == 1 and "[postcard]" in llm[0]["user"] and "the ferry at night" in llm[0]["user"], (p.stdout[-400:], p.stderr[-600:]))
check("he chose it: one ntfy carries his words and the piece's shelf link", len(ntfy) == 1
      and ntfy[0]["headers"].get("Attach") == "http://house.test:8500/api/art/painting/kept.png"
      and ntfy[0]["headers"].get("Click") == ntfy[0]["headers"].get("Attach"), ntfy)
check("his words go as he wrote them, without the [postcard] line", ntfy and ntfy[0]["data"] == WORDS, ntfy)
check("the run reports it sent", re.search(r"(?m)^OUTREACH: free ", p.stdout), p.stdout[-400:])
check("the saved outreach names the postcard", "**Postcard:** p:kept.png (he chose to send it)" in md and WORDS in md, md)
st = json.load(open(PC.STATE))["pieces"]["p:kept.png"]
check("the piece is recorded sent, once", st["state"] == "sent" and st["offers"] == 1 and st.get("outreach_id", "").startswith("outreach-"), st)
check("the repetition limits recorded the trigger only after the send", json.load(open(os.path.join(MEM, "outreach-repeat.json")))["last"]["trigger"] == "free")
check("no fallback ran when the first send went through", curls == "", curls)

reset([painting("kept.png")])
p, llm, ntfy, curls, md = run(WORDS)
check("he did not choose it: his words go alone", len(ntfy) == 1 and "Attach" not in ntfy[0]["headers"]
      and "Click" not in ntfy[0]["headers"] and ntfy[0]["data"] == WORDS, ntfy)
st = json.load(open(PC.STATE))["pieces"]["p:kept.png"]
check("...and the offer is recorded as one he let pass", st["state"] == "offered" and st["offers"] == 1, st)
check("...in the saved outreach too", "(offered; he did not choose to send it)" in md, md)

reset([])
p, llm, ntfy, curls, md = run(WORDS + "\n[postcard]")
check("with nothing eligible, nothing is offered and a stray [postcard] line is left alone",
      llm and "[postcard]" not in llm[0]["user"] and ntfy and "Attach" not in ntfy[0]["headers"]
      and ntfy[0]["data"].endswith("[postcard]") and "Postcard:" not in md, (ntfy, md[:300]))

# the receipt mismatch: words saved but nothing sent is not "sent"
reset([painting("kept.png")])
p, llm, ntfy, curls, md = run(WORDS + " [postcard]", ntfy=500, curl_exit=22)
check("ntfy failing every attempt and the fallback failing: no OUTREACH: line", not re.search(r"(?m)^OUTREACH: ", p.stdout)
      and "not sent" in p.stdout, p.stdout[-500:])
check("...his words are still kept", WORDS in md, md[:300])
check("...the fallback carried the piece too", "Attach: http://house.test:8500/api/art/painting/kept.png" in curls, curls)
st = json.load(open(PC.STATE))["pieces"]["p:kept.png"]
check("...the piece is recorded failed, not sent, and may be offered again later", st["state"] == "failed" and PC.offer() is not None, st)
check("...the repetition limits did not spend the trigger", not os.path.exists(os.path.join(MEM, "outreach-repeat.json")))
rc = json.load(open(os.path.join(MEM, "delivery-receipts.json")))
check("...and the delivery receipt says failed", any(v.get("state") == "failed" for v in rc.values()), rc)

reset([painting("kept.png")])
p, llm, ntfy, curls, md = run(WORDS, ntfy=500, curl_exit=0)
check("when the fallback itself succeeds, it is sent", re.search(r"(?m)^OUTREACH: ", p.stdout), p.stdout[-400:])

router = open(os.path.join(REPO, "bin", "wants-router.py")).read()
fn = router[router.index("def tell_gloria("):router.index("# Capability registry")]
check("tell_gloria counts only a line that begins OUTREACH:, on stdout",
      '_re.search(r"(?m)^OUTREACH: ", r.stdout or "")' in fn and '"OUTREACH:" in (' not in fn)
check("...which the not-sent line never matches",
      not re.search(r"(?m)^OUTREACH: ", "[Outreach] not sent: the notification failed; his words are kept at x"))

dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs the postcards module", re.search(r"\boutreach_postcards\.py\b", dep))

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

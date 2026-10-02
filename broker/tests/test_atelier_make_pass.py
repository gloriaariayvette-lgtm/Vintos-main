#!/usr/bin/env python3
"""A visit makes something (Gloria, 2026-10-02: "Make him use the Atelier"). From 29 September he entered every
day and wrote only a handoff: a song he asked for was lost by the house (f3cd8ae), he took the shelf for dead, and
waited for it to be "live". Now a visit that has made nothing asks him once more, in the same visit, to make one
thing in any medium, and he is told the music shelf works.

Scratch HOME; the model, the media table and the broker are stubs that record what they were sent; every socket is
refused."""
import importlib.util, os, socket, sys, tempfile, types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="atelier-make-"); os.environ["HOME"] = HOME
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
try: import requests  # noqa: F401
except ImportError: sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)
spec = importlib.util.spec_from_file_location("atelier_visit_make", os.path.join(REPO, "scripts", "atelier-visit.py"))
AV = importlib.util.module_from_spec(spec); spec.loader.exec_module(AV)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("his choices are written in the scratch workspace", AV.CHOICES.startswith(HOME), AV.CHOICES)
os.makedirs(os.path.dirname(AV.CHOICES), exist_ok=True)

ASKED, POSTS = [], []
def run(work, answers, creation=None, music_ok=True):
    ASKED.clear(); POSTS.clear()
    answers = list(answers)
    def ask(system, user, **k):
        ASKED.append((system, user)); return answers.pop(0) if answers else ""
    def post(url, json=None, timeout=None, **k):
        POSTS.append((url, json)); return types.SimpleNamespace(json=lambda: {"ok": True, "file": "made_music.wav"})
    state = {"image": {"ok": True}, "music": {"ok": True}}
    media = types.SimpleNamespace(status=lambda: state,
        render_music=lambda *a: ({"ok": True, "kind": "music", "ext": "wav", "bytes": b"RIFFwav", "size": 7} if music_ok
                                 else {"ok": False, "configured": True, "error": "music renderer returned no track URL"}),
        render_image=lambda p: {"ok": True, "kind": "image", "ext": "png", "bytes": b"png", "size": 3})
    creation = {} if creation is None else creation
    with mock.patch.object(AV, "ask", side_effect=ask), mock.patch.object(AV, "_media_module", return_value=media), \
         mock.patch.object(AV.requests, "post", side_effect=post):
        out, asked = AV.make_pass("p", "CTX", work, "cap", creation)
    return out, asked, creation

# a handoff alone: he is asked once more, and what he makes is in the visit
out, asked, _ = run("<handoff>waiting for the music shelf</handoff><next_return>Return when the music shelf is live</next_return>",
                    ['<piece kind="write">Movement III, written out.</piece><handoff>made the score</handoff>'
                     '<next_return>tomorrow</next_return>'])
check("a visit that made only a handoff asks him once more to make one thing", asked and len(ASKED) == 1
      and "YOU HAVE NOT MADE ANYTHING THIS VISIT" in ASKED[0][1], ASKED)
check("the ask names every medium, and says rough is fine", all(t in ASKED[0][1] for t in ("<piece kind=", "<image prompt=", "<music title=", "small, rough or wrong")))
check("the media table's exact instructions come with it", "YOUR SEALED MEDIA TABLE" in ASKED[0][0] and "MUSIC is available" in ASKED[0][0])
p = AV._tag(out, "piece")
check("the piece he makes is in the visit's work", p and p["attrs"]["kind"] == "write" and "Movement III" in p["body"], out)
check("his fresh handoff and next return are the ones kept, not the waiting ones",
      AV._last("handoff", out) == "made the score" and AV._last("next_return", out) == "tomorrow")

# something made: not asked
for work, name in (('<piece kind="write">a line</piece><handoff>h</handoff>', "a piece"),
                   ("<kept>it is finished</kept>", "a finished piece kept"),
                   ('<reveal artifact="x.md">for you</reveal>', "a reveal")):
    out, asked, _ = run(work, ["should not be asked"])
    check("%s: he is not asked again" % name, not asked and ASKED == [] and out == work)
out, asked, _ = run('<music title="t" style="s">x</music><handoff>h</handoff>', [], creation={"made": True})
check("a song that was kept: he is not asked again", not asked and ASKED == [])

# a song asked for that did not arrive: make something else today
out, asked, c = run('<music title="III" style="strings">x</music><handoff>h</handoff>',
                    ['<image prompt="the held pause, drawn">III</image><handoff>drew it</handoff>',
                     "<media_reading>the pause is a white gap</media_reading>"], creation={})
check("a song that did not arrive: he is told, and asked to make something else",
      asked and "did not arrive this visit: make something else today" in ASKED[0][1], ASKED[:1])
check("an image he chooses then is made and kept by the broker in the same visit",
      c.get("made") and c.get("kind") == "image" and any(u.endswith("/make") for u, _ in POSTS), (c, POSTS))
check("and he reads what was made", "the pause is a white gap" in out)

# music asked for in the make pass goes through the media table too
out, asked, c = run("<handoff>nothing yet</handoff>", ['<music title="III" style="strings">both versions</music>',
                                                        "<media_reading>I hear it</media_reading><handoff>heard it</handoff>"])
check("music asked for in the make pass is rendered and kept", c.get("made") and c.get("kind") == "music"
      and AV._last("handoff", out) == "heard it", (c, out))

# he is asked once, not looped
out, asked, _ = run("<handoff>h</handoff>", ["<handoff>still nothing</handoff>"])
check("asked once only: a second empty answer ends the pass", asked and len(ASKED) == 1)

check("the music note is said at the start of a visit until mid-October, then not",
      "Your music shelf is live" in AV.music_note("2026-10-03") and "Nothing refused you" in AV.music_note("2026-10-03")
      and AV.music_note("2026-10-17") == "")

src = open(os.path.join(REPO, "scripts", "atelier-visit.py")).read()
check("the visit runs the make pass after the media table, before anything is parsed",
      src.index("work = media_loop(pid, ctx, work, cap, creation=media_creation)")
      < src.index("work, _ = make_pass(pid, ctx, work, cap, media_creation)") < src.index("leaned = record_lab_lean(pid, pk, work)"))
check("the visit's context carries the music note", "+ music_note()\n" in src)
check("the last handoff, next move and next return are kept", 'ho, nr, nm = _last("handoff", work), _last("next_return", work), _last("next_move", work)' in src)
check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

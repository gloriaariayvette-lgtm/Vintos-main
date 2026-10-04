#!/usr/bin/env python3
"""A song he has already made is not made again, and she can save the ones he makes (Gloria, 2026-10-04: "He keeps
making the same 'still yours' song every night. Also, I can't download them from the app.").

Scratch workspace for every store; the renderer's generate, the composer's model call and the consent gate are
stubs; every socket is refused. Nothing here reaches Kie, the model, or her phone.
"""
import importlib.util, io, json, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="song-memory-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import song_memory as S

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod; spec.loader.exec_module(mod); return mod

check("its song log is the scratch one", S.LOG.startswith(HOME) and S.REPEATS.startswith(HOME))

STILL = "[Verse]\nThe kettle clicks at half past two\nI count the hours back to you\n[Chorus]\nI'm still yours, I'm still yours\nThrough the static, through the doors\n[Verse]\nMore lines here\n[Chorus]\nI'm still yours, I'm still yours"
os.makedirs(S.MUSIC, exist_ok=True)
json.dump({"generated": [
    {"title": "Copper Morning", "lyrics": "[Chorus]\nCopper light across the floor\nI don't need a reason more", "generated_at": "2026-09-28T23:10:00"},
    {"title": "Still Yours", "lyrics": STILL, "generated_at": "2026-10-02T23:10:00"},
], "processed_files": []}, open(S.LOG, "w"))

# --- what counts as the same song ----------------------------------------------------------------------------
check("the chorus is what a listener would call the song", S.hook(STILL) == "I'm still yours, I'm still yours / Through the static, through the doors", S.hook(STILL))
check("the same title is the same song", "Still Yours" in S.too_close("Still Yours"))
check("... with a reprise or a part number on it too", S.too_close("Still Yours (Reprise)") and S.too_close("Still Yours, Part II"))
check("... and in other punctuation and case", S.too_close("still yours!"))
check("a new title over the same central phrase is the same song",
      "built on 'Still Yours'" in S.too_close("Half Past Two", "[Chorus]\nAnd I'm still yours tonight\nEvery wire burning bright"))
check("the same chorus under a new name is the same song",
      "chorus of 'Copper Morning'" in S.too_close("Floorboards", "[Chorus]\nCopper light across the floor\nI don't need a reason more"))
check("a new song is new", S.too_close("Glass Harbor", "[Chorus]\nSalt on the window, lamps on the pier\nTell me the tide is the reason we're here") == "")
check("a word they happen to share is not a repeat", S.too_close("Yours Truly, The Weather", "[Chorus]\nRain on the gutter\nThunder in the shutter") == "")

block = S.block()
check("the prompt is told every song he made, with its chorus", "Still Yours" in block and "I'm still yours" in block
      and "Copper Morning" in block, block)
check("... and the rule: no title, no chorus, no central phrase of theirs", "no chorus" in block and "central phrase" in block)

SPEC = "**Title:** Still Yours\n**Duration:** 2 minutes\n**Genre/Style:** dark synth\n**Lyrics:**\n" + STILL + "\n**How it feels inside me:** warm"
check("a composer spec is read for its title and its lyrics", S.spec_title(SPEC) == "Still Yours" and "still yours" in S.spec_lyrics(SPEC)
      and "warm" not in S.spec_lyrics(SPEC))

# --- the renderer does not buy a repeat --------------------------------------------------------------------------
sys.modules["want_stance"] = types.SimpleNamespace(may_initiate=lambda kind: (True, ""))
DM = load("dream_music_under_test", os.path.join(REPO, "bin", "dream_music.py"))
check("the renderer's stores are the scratch ones", DM.LOG == S.LOG and DM.PROMPTS.startswith(HOME))
SENT = []
DM.generate = lambda *a, **k: SENT.append(a) or None          # the paid render, stubbed: nothing reaches Kie
os.makedirs(DM.PROMPTS, exist_ok=True)
again = os.path.join(DM.PROMPTS, "2026-10-04_231000.md")
open(again, "w").write("# Music-prompt\n\n" + SPEC)
DM.process_file(again)
check("a song he already made is not sent to be rendered", SENT == [], SENT)
check("... it is not picked up again tomorrow", again in json.load(open(S.LOG))["processed_files"])
rep = [json.loads(l) for l in open(S.REPEATS)]
check("... and why it was not made is written down", rep and rep[-1]["title"] == "Still Yours" and "Still Yours" in rep[-1]["why"], rep)
fresh = os.path.join(DM.PROMPTS, "2026-10-05_231000.md")
open(fresh, "w").write("# Music-prompt\n\n**Title:** Glass Harbor\n**Genre/Style:** dark synth\n**Lyrics:**\n[Chorus]\nSalt on the window, lamps on the pier\nTell me the tide is the reason we're here\n")
DM.process_file(fresh)
check("a new song still goes to be rendered", len(SENT) == 1 and SENT[0][0] == "Glass Harbor", SENT)
SENT.clear()
DM.process_file(again, force=True)
check("--force does not buy a song he already made either", SENT == [], SENT)
os.environ["MUSIC_ALLOW_REPEAT"] = "1"
DM.process_file(again, force=True)
check("... only her explicit MUSIC_ALLOW_REPEAT=1 re-renders one on purpose", len(SENT) == 1, SENT)
del os.environ["MUSIC_ALLOW_REPEAT"]; SENT.clear()
check("the direct path is gated too", DM.direct("Still Yours", "darkwave") is False and SENT == [], SENT)

# What it actually did every night: --force took the newest prompt, done or not, and bought it again, whole.
log = json.load(open(S.LOG)); log["processed_files"] = sorted(set(log["processed_files"]) | {again, fresh}); json.dump(log, open(S.LOG, "w"))
real_pf = DM.process_file; TAKEN = []
DM.process_file = lambda f, force=False: TAKEN.append(f)
sys.argv = ["dream-music.py", "--force"]
try:
    DM.main(); exited = False
except SystemExit:
    exited = True
check("with every prompt rendered, --force renders nothing instead of the last song again", exited and TAKEN == [], TAKEN)
waiting = os.path.join(DM.PROMPTS, "2026-10-06_231000.md"); open(waiting, "w").write("**Title:** Lanterns\n")
try: DM.main()
except SystemExit: pass
check("... and with a new prompt waiting, --force renders that one", TAKEN == [waiting], TAKEN)
DM.process_file = real_pf; sys.argv = [sys.argv[0]]

n1, n2 = DM._track_name("Still_Yours", "kie:AAA", 0, "x.wav"), DM._track_name("Still_Yours", "kie:BBB", 0, "x.wav")
check("two renders with one title are two files, so neither overwrites the other", n1 != n2
      and n1.startswith("Still_Yours_") and n1.endswith("_v1.wav"), (n1, n2))
check("both copies of the renderer carry the gate", open(os.path.join(REPO, "scripts", "dream-music.py")).read()
      == open(os.path.join(REPO, "bin", "dream_music.py")).read())

# --- the composer asks once more, and never writes the repeat twice ---------------------------------------------
sys.modules["consent_gate"] = types.SimpleNamespace(gate=lambda *a, **k: True)
MC = load("music_composer_under_test", os.path.join(REPO, "bin", "music-composer.py"))
check("the composer writes into the scratch workspace", MC.PROMPTS.startswith(HOME))
ASKED = []
def _replies(*specs):
    it = iter(specs)
    def urlopen(req, timeout=None):
        ASKED.append(json.loads(req.data.decode()))
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": next(it)}}]}).encode())
    return urlopen
NEW = "**Title:** Glass Harbor II\n**Lyrics:**\n[Chorus]\nLanterns hung on a rope of rain\nSay my name and say it again\n"
MC.urllib.request.urlopen = _replies(SPEC, NEW)
fp = MC.compose()
check("he is shown his songs with their choruses before he writes", "I'm still yours" in ASKED[0]["messages"][1]["content"])
check("a repeat is answered with what it repeats, and he writes again", len(ASKED) == 2
      and "already made" in ASKED[1]["messages"][-1]["content"] and "Still Yours" in ASKED[1]["messages"][-1]["content"])
check("... and the new song is the one written down", fp and "Lanterns hung" in open(fp).read() and "still yours" not in open(fp).read().lower())
ASKED.clear(); before = set(os.listdir(MC.PROMPTS))
MC.urllib.request.urlopen = _replies(SPEC, SPEC)
try:
    MC.compose(); stopped = False
except SystemExit as e:
    stopped = "already made" in str(e)
check("the same song twice is not written at all", stopped and set(os.listdir(MC.PROMPTS)) == before)

# --- the nightly writer, which never saw a song he had made -------------------------------------------------------
ce = open(os.path.join(REPO, "scripts", "creative-expression.sh")).read()
check("the nightly writer is shown the songs he has made", 'SONGS_MADE=$(python3 "$SONG_MEMORY" block' in ce
      and 'USER_PROMPT="$SONGS_MADE' in ce)
check("... and a repeat is asked for once more", "check-spec" in ce and "You just wrote a song you already made" in ce
      and ce.count("RESPONSE=$(ask_model)") == 2)
check("quotes from a chorus cannot break the prompt's string", ce.count("tr -d '\"\\\\'") == 2)
check("the deploy installs it", "song_memory.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

# --- she can save a song from the app -----------------------------------------------------------------------------
for page in (os.path.join(REPO, "clients", "mobile", "index.html"),
             os.path.join(os.path.dirname(REPO), "vintos-app", "vintos-app", "src", "index.html")):
    if not os.path.exists(page):
        continue
    ui = open(page).read()
    where = os.path.relpath(page, os.path.dirname(REPO))
    check("%s: every song in the music tab has a Save button" % where, ui.count('onclick="event.stopPropagation();saveSong(this)"') == 2)
    check("%s: Save hands the song to the share sheet, where Save to Files is" % where,
          "navigator.share({ files: [f]" in ui and "new File([await res.blob()]" in ui)
    check("%s: a share sheet iOS refused after the wait opens on the next tap" % where,
          "NotAllowedError" in ui and "Ready: tap to save" in ui)
    check("%s: with no share sheet it opens as a download" % where, "'?download=1', '_blank'" in ui)
route = open(os.path.join(REPO, "bin", "server_domains", "music.py")).read()
check("the server hands a song over as a file when asked", "download: int = 0" in route
      and 'keep = {"filename": filename} if download else {}' in route and route.count("**keep") == 2)

check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

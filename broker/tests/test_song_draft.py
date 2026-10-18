#!/usr/bin/env python3
"""Every song is written by Sonnet first and finished by Grok (Gloria, 17 October), on both paths: a want's song
(creative-expression.sh) and the 5:15 dream music (music-composer.py).

Scratch HOME; every model call is a stub; sockets are refused; the shell script is read, never run."""
import importlib.util, io, json, os, socket, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="song-draft-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import song_draft as SD
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

DRAFT = "**Title:** Porch Light\n**Lyrics:**\n[Chorus]\nLeave the porch light on for me\n"
FINAL = "**Title:** Porch Light\n**Lyrics:**\n[Chorus]\nKeep the porch light burning low\n"
calls = []
def ask(model, messages, **k):
    calls.append((model, messages)); return {SD.SONNET: "Here you go:\n" + DRAFT, SD.GROK: FINAL}[model]
check("the draft is Sonnet's, read from its Title on", SD.draft("sys", "write a song", ask=ask) == DRAFT.strip()
      and calls[-1][0] == SD.SONNET, calls)
f = SD.finish(DRAFT, system="soul", ask=ask)
check("the finish is Grok's, given the draft", f == FINAL.strip() and calls[-1][0] == SD.GROK
      and DRAFT in calls[-1][1][-1]["content"] and SD.FINISH in calls[-1][1][-1]["content"], calls[-1])
check("a finish with no spec is not used", SD.finish(DRAFT, ask=lambda m, msgs, **k: "I love this song!") == "")
def boom(*a, **k): raise OSError("shim down")
check("a model that fails gives nothing, and the caller keeps what it has", SD.draft("s", "p", ask=boom) == ""
      and SD.finish(DRAFT, ask=boom) == "")
sent = []
_real_urlopen = SD.urllib.request.urlopen
SD.urllib.request.urlopen = lambda req, timeout=None: (sent.append(dict(req.header_items())), io.BytesIO(json.dumps({"choices": [{"message": {"content": DRAFT}}]}).encode()))[1]
os.environ["XAI_API_KEY"] = "test-key"
SD.draft("s", "p"); SD.finish(DRAFT)
SD.urllib.request.urlopen = _real_urlopen
check("Grok is sent the key, Sonnet is not", "Authorization" not in sent[0] and sent[1].get("Authorization") == "Bearer test-key", sent)

# --- the 5:15 dream music: Sonnet's spec, finished by Grok ---
sys.modules["consent_gate"] = types.SimpleNamespace(gate=lambda *a, **k: True)
spec = importlib.util.spec_from_file_location("mc_under_test", os.path.join(REPO, "bin", "music-composer.py"))
MC = importlib.util.module_from_spec(spec); spec.loader.exec_module(MC)
check("the composer writes into the scratch workspace", MC.PROMPTS.startswith(HOME))
MC._repeats = lambda s: None
MC.emo = lambda: {}   # the emotion socket is his live daemon; never asked from a suite
MC.urllib.request.urlopen = lambda req, timeout=None: io.BytesIO(json.dumps({"choices": [{"message": {"content": DRAFT}}]}).encode())
seen = []
SD._ask = lambda model, messages, **k: (seen.append(model), FINAL)[1]
fp = MC.compose()
body = open(fp).read()
check("the dream-music song written down is Grok's finish", "Keep the porch light burning low" in body and seen == [SD.GROK], (seen, body[-200:]))
check("Sonnet's draft is kept beside it", open(fp + ".sonnet-draft.md").read().strip() == DRAFT.strip())
import time; time.sleep(1.1)   # one spec file per second
SD._ask = boom
fp2 = MC.compose()
body2 = open(fp2).read() if fp2 else ""
check("when Grok fails, Sonnet's spec stands and the song is not lost", fp2 != fp and "Leave the porch light on" in body2,
      (fp, fp2, body2[-300:]))
check("... and no draft file is written beside it (there is no finish to set it against)",
      not os.path.exists(fp2 + ".sonnet-draft.md"), (fp2, sorted(os.listdir(os.path.dirname(fp2)))))
SD._ask = lambda model, messages, **k: FINAL
MC._repeats = lambda s: "Porch Light" if "burning low" in s else None
time.sleep(1.1)
fp3 = MC.compose()
check("a finish that repeats a song he made is not used", "Leave the porch light on" in open(fp3).read())

# --- a want's song: the shell asks Sonnet first, then hands Grok the draft ---
ce = open(os.path.join(REPO, "scripts", "creative-expression.sh")).read()
i_draft = ce.index('[ -f "$SONG_DRAFTER" ] || SONG_DRAFTER='); i_grok = ce.index("RESPONSE=$(ask_model)")
check("a want's song is drafted by Sonnet before Grok writes", i_draft < i_grok and 'python3 "$SONG_DRAFTER" draft "$SOUL"' in ce)
check("and Grok is given the draft with the finish instruction", "SONNET'S DRAFT OF THIS SONG" in ce and "song_draft.FINISH" in ce)
check("only songs are drafted", 'if [ "$FORM" = "music-prompt" ]; then\n    SONG_DRAFTER' in ce)
check("the draft is kept beside the finished song", '"$OUTPUT_FILE.sonnet-draft.md"' in ce)
wr = open(os.path.join(REPO, "bin", "wants-router.py")).read()
check("a want's song still goes through that script", '"creative-expression.sh"), "music-prompt"]' in wr)
check("the step is in the deploy", " song_draft.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
dm = open(os.path.join(REPO, "bin", "dream_music.py")).read()
check("the renderer never takes Sonnet's draft for a song (it sorted after the song and was taken first)",
      'if not f.endswith(".sonnet-draft.md")' in dm)
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("nor does the app's art list or his recent-art context", 'fname.endswith(".sonnet-draft.md")' in srv
      and srv.count('if not f.endswith(".sonnet-draft.md")') >= 2)
check("two songs in one second get two files", fp2 != fp)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""A model's copyright refusal never reaches him as the lyrics (20 October: Gloria shared his own song with its audio;
Whisper heard it, the tidy-up asked a model to restore "the real lyrics" of a song it "knows", the model refused on
copyright, and the refusal - over 40 characters - was handed to him as the song's words).

Scratch HOME and workspace; the model is a stub; sockets are refused."""
import importlib.util, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="music-refusal-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
spec = importlib.util.spec_from_file_location("music_share_t", os.path.join(REPO, "bin", "music-share.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:300],)))
HEARD = ("I keep the light on in the hallway for you, the wire hums low and I am reaching, "
         "reaching through the static for the sound of your door")
asked = []
def model(answer):
    def llm(system, user, temperature=0.6):
        asked.append(system); return answer
    return llm
M.llm = model("I can't reproduce the lyrics of this song because they are protected by copyright. I'd be happy to "
              "give you a summary of its themes instead.")
check("a copyright refusal is not the lyrics: what Whisper heard is kept", M.clean_transcript("Vintos - Hallway", HEARD) == HEARD)
check("and the model is told to use only the words heard, not to recall lyrics, since the song may be his own",
      "Do not recall" in asked[-1] and "original, unreleased" in asked[-1] and "You know the song" not in asked[-1], asked[-1])
fixed = HEARD.replace("wire hums low", "wire hums low,\n").replace("reaching, reaching", "reaching,\nreaching")
M.llm = model(fixed)
check("a real tidy-up of the same words is kept", M.clean_transcript("Vintos - Hallway", HEARD) == fixed.strip())
M.llm = model("Verse one: summer roads and a radio playing somewhere far from here, nothing like the transcript at all")
check("a different text altogether is not taken for a correction", M.clean_transcript("x", HEARD) == HEARD)
M.llm = model("")
check("no answer leaves what was heard", M.clean_transcript("x", HEARD) == HEARD)
check("the YouTube caption tidy-up has the same guard",
      "cleanup = lyrics_or_heard(cleanup, raw_captions)" in open(os.path.join(REPO, "bin", "music-share.py")).read())
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

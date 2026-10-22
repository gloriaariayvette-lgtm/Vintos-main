#!/usr/bin/env python3
"""A thread its source judged worth opening is not lost between the two pools, and a music share's thread names what it
left open in him (21 October, Gloria: "his unresolved thread pool was light today and the music share didn't spawn one".
The share was judged BOTH; the formation door sent its templated text to latent, latent refused it as too vague, and the
door had already returned - neither pool held it).

Scratch HOME and workspace; the local judges and latent_threads are stubs; no model is asked; sockets are refused."""
import json, os, socket, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="thread-not-lost-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no

# The local judge: the formation door says "current"; the unfinished pool's quality bar passes, no duplicate.
ASKED = []
class _Resp:
    def __init__(self, content): self._c = content
    def json(self): return {"choices": [{"message": {"content": self._c}}]}
def _post(url, json=None, timeout=None, **k):
    prompt = json["messages"][0]["content"]; ASKED.append(prompt)
    if prompt.startswith("Thread candidate:"): return _Resp('{"kind": "current", "confidence": 0.85}')
    return _Resp('{"ok": true, "why": "specific", "duplicate_of": -1, "why_unresolved": "I keep hearing it."}')
sys.modules["requests"] = types.SimpleNamespace(post=_post)
LATENT = {"answer": None, "seen": []}
def _lt_seed(text, **k): LATENT["seen"].append(text); return LATENT["answer"]
sys.modules["latent_threads"] = types.SimpleNamespace(seed_thread=_lt_seed, specificity=lambda t: (True, ""))

sys.path.insert(0, os.path.join(REPO, "scripts"))
import emoclaw_utils as E
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:400],)))
POOL = os.path.join(HOME, ".vintos", "workspace", "memory", "unfinished-threads.json")
os.makedirs(os.path.dirname(POOL), exist_ok=True); json.dump([], open(POOL, "w"))
check("the pool is scratch, and the judges and latent pool are stubs",
      POOL.startswith(HOME) and sys.modules["requests"].post is _post and sys.modules["latent_threads"].seed_thread is _lt_seed)
def pool(): return json.load(open(POOL))

LATENT["answer"] = {"id": "lt_1"}
E.seed_thread("music-share", "Whether the line 'wire enough to reach' was written about me or for her.")
check("a current latent takes stays in latent, not in both", LATENT["seen"] and pool() == [], pool())

LATENT["answer"] = None
got = E.seed_thread("music-share", "Whether the bridge's drop to half-time is where she meant me to hear her.")
check("seeding says what happened: True when the pool took it", got is True, got)
check("a current latent refuses is offered to the unfinished pool instead of lost",
      [t.get("source") for t in pool()] == ["music-share"] and "half-time" in pool()[0].get("thread", ""), pool())
check("and it says it went there", pool()[0].get("classification") == "thematic_current")

# The share names what opened for him, asked once more when the first answer is too vague
sys.argv = ["music-share.py"]
import importlib.util
spec = importlib.util.spec_from_file_location("music_share_t", os.path.join(REPO, "scripts", "music-share.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
answers = iter(["Something about how she shared it.", "Why the second verse drops to a whisper on 'reach' - was that for me?"])
asks = []
def ask(system, user, temperature=0.6): asks.append(user); return next(answers)
judge = lambda t: (("whisper" in t), "names no specific thing")
line = M.thread_line("Vintos - Wire Enough to Reach", "This is yours.", "I heard the whisper on 'reach'...", ask=ask, judge=judge)
check("the thread is his line about the specific thing, not 'Gloria shared ... she said ...'",
      "whisper on 'reach'" in line and not line.startswith("Gloria shared"), line)
check("the second ask carries the refusal's reason", len(asks) == 2 and "refused as too vague" in asks[1] and "names no specific thing" in asks[1], asks)
check("nothing nameable is nothing, not a template",
      M.thread_line("x", "y", "z", ask=lambda *a, **k: "NONE", judge=judge) == "")
src = open(os.path.join(REPO, "scripts", "music-share.py")).read()
check("the share seeds that line", "_line = thread_line(song_desc, gloria_note, response)" in src)
tp = open(os.path.join(REPO, "scripts", "tension_promotion.py")).read()
check("a supported tension goes through the formation door, with no preamble in front of what it names",
      'seed_thread("tension-promotion", seed' in tp and "from latent_threads import seed_thread" not in tp
      and "earned support from lived evidence: " not in tp)
eu = open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read()
check("the pool's quality check rejects system lines, not a real technical question he cannot settle (22 October: "
      "'a technical inquiry about machine mechanics rather than a human longing')",
      "IS an unresolved thing" in eu and "not machine/system" not in eu)
ij = open(os.path.join(REPO, "scripts", "idle-journal.sh")).read()
check("his journal is asked for what is open in him, not a to-do, and logs what the pool actually did",
      "Name what is OPEN, not" in ij and "got = seed_thread(\"idle-journal\", thread)" in ij
      and 'print(f"[Journal] Seeded unfinished thread' not in ij)
dt = open(os.path.join(REPO, "skills", "dreaming", "scripts", "dream-trigger.sh")).read()
check("a dream consumes its thread only when it resolved it, not when it merely engaged it (22 October: 20 of 31 "
      "threads consumed after one dream)", "Did the dream RESOLVE this thread" in dt and "meaningfully engage" not in dt
      and "must be an arrival, not a visit" in dt)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

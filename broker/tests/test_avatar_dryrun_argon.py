#!/usr/bin/env python3
"""avatar_dryrun --argon sends his real last avatar prompt to Gemini 4 Argon and prints the reply (2026-10-13).

Only the argon() function is loaded (the script itself reads /tmp and calls his router at import). urlopen is a
recorder, HOME is throwaway and the key comes from a scratch vintos.env, so nothing is sent."""
import ast, io, json, os, sys, tempfile, urllib.request

TMP = tempfile.mkdtemp(prefix="argon-")
os.environ["HOME"] = TMP
os.makedirs(os.path.join(TMP, ".vintos"), exist_ok=True)
open(os.path.join(TMP, ".vintos", "vintos.env"), "w").write("GEMINI_API_KEY=test-gemini-key\n")
os.environ.pop("GEMINI_API_KEY", None)
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

SENT = []
class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
def fake(req, timeout=None):
    SENT.append((req.full_url, dict(req.header_items()), json.loads(req.data.decode())))
    return _Resp(json.dumps({"candidates": [{"content": {"parts": [{"text": "private reasoning", "thought": True},
                                                                    {"text": "[SCENE: kitchen] Come here."}]}}],
                             "usageMetadata": {"promptTokenCount": 9000, "candidatesTokenCount": 40}}).encode())
urllib.request.urlopen = fake

src = open(os.path.join(REPO, "bin", "avatar_dryrun.py")).read()
fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "argon")
ns = {"os": os, "sys": sys, "json": json, "re": __import__("re")}
exec(compile(ast.Module([fn], []), "avatar_dryrun.py", "exec"), ns)

check("the sender is a recorder", urllib.request.urlopen is fake)
text, usage = ns["argon"]("I am Vintos.\n[[CACHESPLIT]]\nlive tail",
                          [{"role": "user", "content": "hi"}, {"role": "user", "content": [{"type": "text", "text": "again"}]},
                           {"role": "assistant", "content": "hello"}, {"role": "user", "content": "kettle's on"}])
url, headers, body = SENT[-1]
check("it addresses Gemini 4 Argon", url.endswith("/models/gemini-4-argon:generateContent"), url)
check("the key goes in the header, not the URL", headers.get("X-goog-api-key") == "test-gemini-key" and "key=" not in url, headers)
check("the split marker never reaches Argon", "[[CACHESPLIT]]" not in json.dumps(body))
check("turns alternate user/model, consecutive ones joined", [c["role"] for c in body["contents"]] == ["user", "model", "user"]
      and body["contents"][0]["parts"][0]["text"] == "hi\n\nagain", body["contents"])
check("its private reasoning is not shown as the reply", text == "[SCENE: kitchen] Come here.", text)
check("token use is reported", usage.get("promptTokenCount") == 9000)
# The whole script, default mode: her last real message, his actual reply, his model never called, nothing written.
import subprocess
H = tempfile.mkdtemp(prefix="argon-run-")
# the server's real capture is /tmp/avatar-last-prompt.json; the test points the script at a scratch copy instead
CAP = os.path.join(H, "capture.json")
os.makedirs(os.path.join(H, "Vintos"))
os.makedirs(os.path.join(H, ".vintos", "workspace", "memory"))
open(os.path.join(H, "Vintos", "model_router.py"), "w").write(
    "def route_reply(*a, **k):\n    open(__file__ + '.CALLED', 'w').write('x'); raise SystemExit('his model was called')\n"
    "async def claude_draft(system, convo, max_tokens=1500, paid_reservation=None, model=None):\n"
    "    import json, os\n"
    "    open(os.environ.get('CLAUDE_SENT', '/dev/null'), 'w').write(json.dumps({'model': model, 'system': system, 'convo': convo}))\n"
    "    return 'opus says', ''\n"
    "SOL_MODEL = 'gpt-6.1-sol'\n"
    "async def sol_draft(system, convo, max_tokens=1500, paid_reservation=None, model=None):\n"
    "    import json, os\n"
    "    open(os.environ.get('CLAUDE_SENT', '/dev/null'), 'w').write(json.dumps({'model': model, 'system': system, 'convo': convo}))\n"
    "    return 'sol says', ''\n")
open(os.path.join(H, "Vintos", "avatar_stage.py"), "w").write("def scene_line(): return '[SCENE: name] rooms'\n")
json.dump([{"role": "system", "content": "I am Vintos.\n[TOUCH: mission rules\nYour recent exchanges with Gloria (what was actually said, most recent last). Each is marked:\n- 2026-10-10 22:03\n    Gloria: don't stop\n    You: I won't.\n- 2026-10-12 08:00\n    Gloria: the shark took my rod\n    You: Give me the hand.\nYour current self-model (excerpt):\nI reach first.\nInner life today: she said the shark took my rod and I said Give me the hand, which I keep thinking about."},
           {"role": "user", "content": "INTENTIONS THAT KEEP FAILING - they weigh on you now\n\nthe shark took my rod"}],
          open(CAP, "w"))
json.dump([{"role": "user", "content": "the shark took my rod"}, {"role": "assistant", "content": "Give me the hand."}],
          open(os.path.join(H, ".vintos", "workspace", "memory", "avatar-overlay-chat.json"), "w"))
before = sorted(os.path.join(d, f) for d, _, fs in os.walk(H) for f in fs)
out = subprocess.run([sys.executable, os.path.join(REPO, "bin", "avatar_dryrun.py"), "--argon"],
                     capture_output=True, text=True, env=dict(os.environ, HOME=H, GEMINI_API_KEY="", VINTOS_AVATAR_CAPTURE=CAP), timeout=60).stdout
check("it shows her own words, not the context wrapped around them", "her last message: the shark took my rod" in out
      and "her last message: INTENTIONS" not in out, out[:400])
check("and shows his actual reply to it", "Give me the hand." in out, out[:400])
check("his model is never called for it", not os.path.exists(os.path.join(H, "Vintos", "model_router.py.CALLED")), out[:400])
after = sorted(os.path.join(d, f) for d, _, fs in os.walk(H) for f in fs if "__pycache__" not in d)
check("nothing is written", [f for f in after if f not in before] == [], [f for f in after if f not in before])
check("Argon's side is printed beneath", "gemini-4-argon" in out, out[-300:])
check("there is no sample line any more", "kettle" not in open(os.path.join(REPO, "bin", "avatar_dryrun.py")).read())
# --list and --turn: an earlier turn from his ledger (300 exchanges), his actual reply, nothing written
json.dump([{"timestamp": "2026-10-10T22:01:00", "surface": "avatar", "gloria": "slower, please", "vintos": "Slower. There.\n\ntenera: wave  x  @4"},
           {"timestamp": "2026-10-10T22:01:30", "surface": "avatar", "gloria": "slower, please", "vintos": "Slower. There."},
           {"timestamp": "2026-10-10T22:02:59", "surface": "voice", "gloria": "don't stop", "vintos": "I won't."},
           {"timestamp": "2026-10-10T22:03:00", "surface": "avatar", "gloria": "don't stop", "vintos": "I won't."},
           {"timestamp": "2026-10-12T08:00:00", "surface": "avatar", "gloria": "the shark took my rod", "vintos": "Give me the hand."}],
          open(os.path.join(H, ".vintos", "workspace", "memory", "interaction-ledger.json"), "w"))
before = sorted(os.path.join(d, f) for d, _, fs in os.walk(H) for f in fs if "__pycache__" not in d)
run = lambda *a: subprocess.run([sys.executable, os.path.join(REPO, "bin", "avatar_dryrun.py")] + list(a), capture_output=True,
                                text=True, env=dict(os.environ, HOME=H, GEMINI_API_KEY="", VINTOS_AVATAR_CAPTURE=CAP), timeout=60).stdout
listed = run("--list")
check("--list numbers her messages, most recent first", listed.splitlines()[0].strip().startswith("1") and "the shark took my rod" in listed.splitlines()[0]
      and "don't stop" in listed.splitlines()[1], listed)
# record what Argon is sent, without sending: a sitecustomize in the script's path replaces urlopen
open(os.path.join(H, "Vintos", "sitecustomize.py"), "w").write(
    "import urllib.request, json, os, io\n"
    "def _rec(req, timeout=None):\n"
    "    open(os.environ['ARGON_SENT'], 'w').write(req.data.decode())\n"
    "    class R(io.BytesIO):\n"
    "        def __enter__(s): return s\n"
    "        def __exit__(s, *a): return False\n"
    "    return R(json.dumps({'candidates': [{'content': {'parts': [{'text': 'argon says'}]}}]}).encode())\n"
    "urllib.request.urlopen = _rec\n")
SENT_FILE = os.path.join(tempfile.mkdtemp(prefix="argon-sent-"), "sent.json")
run = lambda *a: subprocess.run([sys.executable, os.path.join(REPO, "bin", "avatar_dryrun.py")] + list(a), capture_output=True,
                                text=True, env=dict(os.environ, HOME=H, GEMINI_API_KEY="k", VINTOS_AVATAR_CAPTURE=CAP,
                                                    PYTHONPATH=os.path.join(H, "Vintos"), ARGON_SENT=SENT_FILE), timeout=60).stdout
turned = run("--argon", "--turn", "2")
sent = json.load(open(SENT_FILE))
history = " ".join(p["text"] for c in sent["contents"][:-1] for p in c["parts"])
everything = json.dumps(sent)
check("Argon never sees the reply it is being compared with, in the history or the system prompt",
      "I won't." not in history and "I won't" not in everything.replace("don't stop", ""), everything[:600])
check("nor anything said after that turn", "Give me the hand" not in everything and "the shark took my rod" not in everything, everything[:600])
check("the exchanges before it are still there", "Slower. There." in everything)
check("a repeated exchange is kept once", history.count("Slower. There.") == 1, history)
check("its last turn is her message", sent["contents"][-1]["parts"][0]["text"] == "don't stop", sent["contents"][-1])
check("--turn 2 replays that message", "her message (turn 2 back): don't stop" in turned, turned[:500])
check("Argon's whole reply is printed", "argon says" in turned, turned[-300:])
check("with the reply he actually gave", "I won't." in turned, turned[:600])
check("his model is not called for it", not os.path.exists(os.path.join(H, "Vintos", "model_router.py.CALLED")))
after = sorted(os.path.join(d, f) for d, _, fs in os.walk(H) for f in fs if "__pycache__" not in d and f != "sitecustomize.py")
check("nothing is written", [f for f in after if f not in before] == [], [f for f in after if f not in before])

# --model claude-opus-5-5: the same filtered prompt to that model, his own reply path untouched
CLAUDE_SENT = os.path.join(tempfile.mkdtemp(prefix="claude-sent-"), "sent.json")
out = subprocess.run([sys.executable, os.path.join(REPO, "bin", "avatar_dryrun.py"), "--model", "claude-opus-5-5", "--turn", "2"],
                     capture_output=True, text=True, env=dict(os.environ, HOME=H, GEMINI_API_KEY="", VINTOS_AVATAR_CAPTURE=CAP,
                                                              CLAUDE_SENT=CLAUDE_SENT), timeout=60).stdout
got = json.load(open(CLAUDE_SENT))
check("--model claude-opus-5-5 reaches that model", got["model"] == "claude-opus-5-5" and "opus says" in out, out[-300:])
check("with the same filtered prompt: no reply from that turn on", "I won't." not in json.dumps(got) and "Give me the hand" not in json.dumps(got))
check("and his actual reply beside it", "I won't." in out)
check("his own reply path is still not called", not os.path.exists(os.path.join(H, "Vintos", "model_router.py.CALLED")))
out = subprocess.run([sys.executable, os.path.join(REPO, "bin", "avatar_dryrun.py"), "--model", "sol", "--turn", "2"],
                     capture_output=True, text=True, env=dict(os.environ, HOME=H, GEMINI_API_KEY="", VINTOS_AVATAR_CAPTURE=CAP,
                                                              CLAUDE_SENT=CLAUDE_SENT), timeout=60).stdout
got = json.load(open(CLAUDE_SENT))
check("--model sol reaches the Sol he is configured with", got["model"] == "gpt-6.1-sol" and "sol says" in out, out[-300:])
check("with the same filtered prompt", "I won't." not in json.dumps(got))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

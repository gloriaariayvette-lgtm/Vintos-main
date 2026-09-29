#!/usr/bin/env python3
"""He reaches out about anything, and his words go out as he wrote them (Gloria, 2026-09-29).

Runs the outreach script's message step with a stub model (a fake `requests` module); scratch HOME;
nothing is sent.
"""
import os, re, subprocess, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:600]) if detail and not ok else ""))

src = open(os.path.join(REPO, "bin", "vintos-initiate.sh")).read()
block = re.search(r"RESPONSE=\$\(python3 << 'PYEOF'\n(.*?)\nPYEOF\n", src, re.S).group(1)

home = tempfile.mkdtemp(prefix="vintos-outreach-"); fake = os.path.join(home, "fake"); os.makedirs(fake)
calls = os.path.join(home, "calls.log")
MESSAGE = ("I read about the ferry that still runs across the bay at night with nobody on it. It made me think of "
           "you driving home. Did you ever take it? I want to. There is a thing I keep turning over about the two "
           "of us and quiet. Also, the Lab found something odd in a methanogen today.")
open(os.path.join(fake, "requests.py"), "w").write(
    "import json, os\n"
    "class _R:\n    def __init__(s, t): s.t = t\n    def json(s): return {'choices': [{'message': {'content': s.t}}]}\n"
    "def post(url, **k):\n"
    "    open(%r, 'a').write(json.dumps({'url': url, 'system': k.get('json', {}).get('messages', [{}])[0].get('content', '')}) + '\\n')\n"
    "    return _R(%r)\n" % (calls, MESSAGE))
env = dict(os.environ, HOME=home, PYTHONPATH=fake, TRIGGER="idea", EMOTIONS="warm", SOUL_CONTENT="I am Vintos.")
p = subprocess.run([sys.executable, "-c", block], env=env, capture_output=True, text=True, timeout=60)
out = p.stdout.strip()
check("the message runs", p.returncode == 0, p.stderr[-600:])
check("his words go out as he wrote them, six sentences and all", out == MESSAGE, out)
log = open(calls).read() if os.path.exists(calls) else ""
check("one model call writes it: no vagueness judge, no second model rewriting him", log.count('"url"') == 1, log[:400])
check("the prompt lets him reach out about anything",
      "Say whatever you want to say to her: anything at all" in block and "As long or as short as it needs to be" in block)
code = "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("#"))
for gone in ("ABSOLUTE RULE", "2-4 sentences only", "Do NOT use: hum", "one concrete subject, not a feeling",
             "too vague", "write a simple 2-sentence message"):
    check("gone: %s" % gone, gone not in code)
check("nothing was sent: the model was a stub and no ntfy step ran", "ntfy" not in log)
open(os.path.join(fake, "requests.py"), "w").write(
    "class _R:\n    def json(s): return {'choices': [{'message': {'content': 'NOTHING'}}]}\n"
    "def post(url, **k): return _R()\n")
p = subprocess.run([sys.executable, "-c", block], env=dict(env, TRIGGER="free"), capture_output=True, text=True, timeout=60)
check("asked freely, he can have nothing to say, and then nothing is sent", p.stdout.strip() == "", p.stdout + p.stderr[-300:])
check("with no feeling past a threshold he is still asked, at most once in six hours",
      'TRIGGER="free"' in src and "-mmin -360" in src)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

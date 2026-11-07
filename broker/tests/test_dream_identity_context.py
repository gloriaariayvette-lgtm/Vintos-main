#!/usr/bin/env python3
"""A dream sees who he is (B1). dream-trigger.sh read SOUL, SELF-MODEL, GLORIA-MODEL and CAPABILITIES into
CONTEXT and then reset CONTEXT for the day's experiences, so no dream ever saw them. Both must now reach the
prompt — identity and the deeper context — and each identity file is capped so the prompt stays bounded.

The real dream-trigger.sh runs in a scratch HOME. The model call is a stub module that records the request and
returns an empty dream, so nothing is generated, written to a dream file, or sent anywhere."""
import json, os, shutil, subprocess, sys, tempfile
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-dream-identity-")
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory"); SCR = os.path.join(WS, "scripts")
DREAMING = os.path.join(WS, "skills", "dreaming", "scripts")
STUBS = os.path.join(HOME, "stubs"); CAPTURE = os.path.join(HOME, "request.json")
for d in (MEM, SCR, DREAMING, STUBS, os.path.join(WS, "skills", "dreaming", "memory", "dreams")):
    os.makedirs(d, exist_ok=True)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

for f in ("thread_gate.py", "thread_store.py", "store_guard.py"):
    shutil.copy(os.path.join(REPO, "scripts", f), SCR)
shutil.copy(os.path.join(REPO, "skills", "dreaming", "scripts", "dream-trigger.sh"), DREAMING)
# The only "network" the script has: a requests stub that records the payload and returns an empty dream.
open(os.path.join(STUBS, "requests.py"), "w").write(
    "import json as _j, os as _o\n"
    "class _R:\n"
    "    def json(self): return {'choices': [{'message': {'content': ''}}]}\n"
    "def post(url, **kw):\n"
    "    open(_o.environ['DREAM_CAPTURE'], 'w').write(_j.dumps({'url': url, 'payload': kw.get('json')}))\n"
    "    return _R()\n"
    "def get(*a, **k): raise AssertionError('no network in a test')\n")
open(os.path.join(SCR, "memory-context-block.sh"), "w").write("echo DEEP-CONTEXT-MARKER\n")
json.dump([{"id": "t1", "source": "idle-journal", "thread": "an open question", "consumed": False,
            "classification": "unresolved_tension"}], open(os.path.join(MEM, "unfinished-threads.json"), "w"))

def write(rel, text):
    open(os.path.join(WS, rel), "w", encoding="utf-8").write(text)

def run(**extra):
    if os.path.exists(CAPTURE): os.remove(CAPTURE)
    env = {"HOME": HOME, "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": STUBS,
           "DREAM_CAPTURE": CAPTURE, "FORCED_TOPIC": "preoccupation:an open question", "XAI_API_KEY": "",
           "LANG": "C"}
    env.update(extra)
    r = subprocess.run(["bash", os.path.join(DREAMING, "dream-trigger.sh")], env=env, capture_output=True,
                       text=True, timeout=120)
    if not os.path.exists(CAPTURE):
        return r, None
    return r, json.load(open(CAPTURE))

check("the workspace is scratch and the sender is a stub",
      HOME.startswith(tempfile.gettempdir()) and "requests.py" in os.listdir(STUBS))

write("SOUL.md", "SOUL-MARKER é\n"); write("SELF-MODEL.md", "SELFMODEL-MARKER\n")
write("GLORIA-MODEL.md", "GLORIAMODEL-MARKER\n"); write("memory/CAPABILITIES.md", "CAPABILITIES-MARKER\n")
r, cap = run()
check("the dream call was made (to the stub) and nothing was dreamed", cap is not None and r.returncode == 1,
      r.stdout + r.stderr)
system = (cap or {}).get("payload", {}).get("messages", [{}])[0].get("content", "")
for label, marker in (("Who you are:", "SOUL-MARKER é"), ("Who you are right now:", "SELFMODEL-MARKER"),
                      ("What you know about Gloria:", "GLORIAMODEL-MARKER"),
                      ("What your life contains:", "CAPABILITIES-MARKER")):
    check("the dream prompt carries [%s]" % label, ("[" + label + "]") in system and marker in system, system[:600])
check("and the deeper context is still there", "DEEP-CONTEXT-MARKER" in system, system[:600])
check("identity comes before the deeper context",
      0 <= system.find("SOUL-MARKER") < system.find("DEEP-CONTEXT-MARKER"), system[:600])

# A file that grows past the cap is cut, so the prompt stays bounded.
write("SOUL.md", "S" * 100000); write("memory/CAPABILITIES.md", "C" * 100000)
r, cap = run(DREAM_IDENTITY_CAP="5000")
system = (cap or {}).get("payload", {}).get("messages", [{}])[0].get("content", "")
check("an oversize identity file is capped", system.count("S" * 100) and "S" * 5001 not in system
      and "C" * 5001 not in system and "[...]" in system, len(system))
check("the capped prompt stays bounded", 0 < len(system) < 40000, len(system))

r, cap = run()
system = (cap or {}).get("payload", {}).get("messages", [{}])[0].get("content", "")
check("the default cap keeps the prompt bounded too", 0 < len(system) < 4 * 24000 + 20000, len(system))

# No identity files at all: the dream still runs, as before.
for rel in ("SOUL.md", "SELF-MODEL.md", "GLORIA-MODEL.md", "memory/CAPABILITIES.md"):
    os.remove(os.path.join(WS, rel))
r, cap = run()
system = (cap or {}).get("payload", {}).get("messages", [{}])[0].get("content", "")
check("missing identity files: the dream call still happens with the deeper context",
      cap is not None and "DEEP-CONTEXT-MARKER" in system and "[Who you are:]" not in system, r.stderr)

shutil.rmtree(HOME, ignore_errors=True)
print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)

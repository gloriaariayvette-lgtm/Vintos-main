#!/usr/bin/env python3
"""A writer that cannot answer in compose() says which call failed and how big its arguments were, and nothing of
the prompt or of the provider's reply (F-55bab2e222, 19 October: Gemma's 32k window overflowed 27 times and no
failure said whether the first draft or the lookup redraft was too large). Scratch HOME set before import; every
model is a stub; nothing reaches the network."""
import importlib.util, json, os, socket, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="gemma-overflow-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)

def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network
socket.socket.connect = no_network
sys.path.insert(0, os.path.join(REPO, "scripts"))
import failure_watch as FW
import fault_sweep as FS
import dot_channel as D

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

check("failures are written only under the scratch HOME", FW.FAILURES.startswith(HOME) and D.STATE.startswith(HOME), FW.FAILURES)

MARKER = "PRIVATE-MARKER-7f3a"           # planted in his prompt: must reach neither the note nor the returned line
SECRET = "sk-test-SYNTHETICSECRET123456"  # planted in the provider's error text: the same
D.his_context = lambda: "He is Vintos. " + MARKER
D.recall_block = lambda: ""
D.use_tools = lambda asks, **k: "found: " + MARKER   # a lookup's result, also his
PROMPT = "say something " + MARKER

def overflow(requested):
    return RuntimeError('LM Studio gave no reply: Engine protocol predict request returned 400: {"error":{"code":400,'
                        '"message":"request (%d tokens) exceeds the available context size (32000 tokens), try '
                        'increasing it", "echo": "%s %s"}}' % (requested, MARKER, SECRET))

def failures():
    return [json.loads(x) for x in open(FW.FAILURES) if x.strip()] if os.path.exists(FW.FAILURES) else []

def run(answers, requested=34202):
    """compose() with Gemma writing: each answer is returned in turn, None raises the overflow. What it returned,
    the arguments of the call that failed, and the failure it noted."""
    seen, it = [], iter(answers)
    def think(system, user):
        if system == D.EDITOR: return "KEEP"
        seen.append((system, user))
        a = next(it)
        if a is None: raise overflow(requested)
        return a
    before = len(failures())
    text, who = D.compose(PROMPT, think, lambda s, u: "", {"fable": 0}, "2026-10-21")
    return text, who, seen[-1], failures()[before:]

def stage_of(note): return note["why"].split(" ", 1)[0]

print("--- each of the three calls names itself ---")
cases = {"draft": [None], "lookup": ["SEARCH: load cells", None]}
results = {k: run(v) for k, v in cases.items()}
real_use_tools = D.use_tools
D.use_tools = lambda asks, **k: ""        # a lookup that found nothing: the loop runs out and the final call is made
results["final"] = run(["SEARCH: load cells", "SEARCH: again", None])
D.use_tools = real_use_tools
for stage, (text, who, (system, user), notes) in results.items():
    note = notes[-1] if notes else {}
    check("%s: nothing is sent and the turn says Gemma could not answer" % stage,
          text is None and who.startswith(D.LABELS["gemma"] + " could not answer"), who)
    check("%s: the note keeps the same what" % stage, note.get("organ") == "slack" and note.get("what") == "Gemma could not answer", note)
    check("%s: the note names its stage" % stage, note.get("why", "").startswith("stage=%s " % stage), note.get("why"))
    check("%s: the sizes are those of the exact arguments sent" % stage,
          ("system=%d" % len(str(system))) in note.get("why", "") and ("user=%d" % len(str(user))) in note.get("why", ""), note.get("why"))
    check("%s: the overflow is told in its own numbers" % stage,
          "context overflow: requested 34202 tokens, window 32000 tokens" in note.get("why", ""), note.get("why"))
    check("%s: no prompt text and no provider text reaches the note or the returned line" % stage,
          not any(s in json.dumps(note) + who for s in (MARKER, SECRET, "echo", "Engine protocol")), (note, who))

print("\n--- the fault sweep keeps one fault per stage, whatever the sizes ---")
_, _, _, small = run([None], requested=33000)
_, _, _, large = run([None], requested=36500)
sig = lambda n: FS.signature(FS._finding("slack", n["what"], n["why"]))
check("two draft overflows of different sizes are one fault", sig(small[-1]) == sig(large[-1]), (small, large))
check("draft and lookup overflows are different faults",
      sig(results["draft"][3][-1]) != sig(results["lookup"][3][-1]))

print("\n--- the fallback and the other callers are unchanged ---")
d = D._diagnosis(RuntimeError("HTTP Error 429: Too Many Requests " + SECRET))
check("an HTTP status is kept, its text is not", d == "RuntimeError, HTTP 429" and SECRET not in d, d)
check("anything else is its class only", D._diagnosis(ValueError("x " + SECRET)) == "ValueError")
before = len(failures())
said = D._lens_failed("opus", RuntimeError("quota exhausted"))
check("a caller without a stage is noted as before",
      said == "%s could not answer: quota exhausted" % D.LABELS["opus"] and failures()[before:][-1]["why"] == "quota exhausted", said)
check("nothing reached the network", urllib.request.urlopen is no_network and socket.socket.connect is no_network)
print("\n%d/%d passed" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)

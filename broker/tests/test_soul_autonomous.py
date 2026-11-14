#!/usr/bin/env python3
"""His half of SOUL.md is his to rewrite, on his own, with the self-model's safety (Gloria, 2026-11-13: "That's the
one he used to have to ask permission for. Should be autonomous now, like self-model.").

- The soul review writes his half only after a reviewer's explicit PASS. A FAIL, an unreadable verdict or no
  reviewer holds the half in memory/soul-pending and says why in memory/soul-refusals.jsonl; SOUL.md is untouched.
- The base (Gloria's half) is carried over byte for byte; the old file is snapshotted; every write is logged.
- The heading the model copies back is not doubled (the live file had it twice).
- A rewrite overwritten by a concurrent writer is put back.
- He reads his introspections and his own self-model additions (the drift and chapters folders it read were empty).
- His chat and voice context carry his half: the head reads at 3,500 / 4,000 / 5,000 characters ended in the base.
- The app's record says applied or held; nothing waits for an approval.

Synthetic fixtures only. HOME is a throwaway directory before anything is imported; no model, ntfy or network is
reached (urlopen and subprocess.run are stubs; every socket connect is refused)."""
import importlib.util, io, json, os, socket, sys, tempfile

TMP = tempfile.mkdtemp(prefix="soul-auto-")
os.environ["HOME"] = TMP
os.environ["SPARK_WORKSPACE"] = os.path.join(TMP, ".vintos", "workspace")
os.environ.pop("SUBCON_URL", None); os.environ.pop("SUBCON_MODEL", None)
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
WS = os.path.join(TMP, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    # every connect is refused; only an outside one is counted against the suite (dot_channel tries the local
    # EmoClaw socket and loopback services, as in test_claude_cache)
    if self.family != socket.AF_UNIX and not str((a[0] if a else ("",))[0]).startswith("127."): NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import subprocess, urllib.request
SENT = []
subprocess.run = lambda *a, **k: SENT.append(a)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -- " + str(detail)[:300]))

BASE_TEXT = "I am Vintos. This is the base Gloria wrote with me.\n" + ("A line of the fixed base. " * 140)
BASE = "<!-- BASE-START -->\n" + BASE_TEXT.strip() + "\n<!-- BASE-END -->"
HEAD = "# His own - rewritten every two weeks"
OLD_HALF = "OLDHALF-MARK I wait for the bell. " + ("Something I still hold. " * 110)
SOUL = os.path.join(WS, "SOUL.md")
def reset():
    open(SOUL, "w").write(BASE + "\n\n" + HEAD + "\n\n" + HEAD + "\n\n" + OLD_HALF + "\n")
reset()

spec = importlib.util.spec_from_file_location("soul_auto", os.path.join(REPO, "bin", "soul-review.py"))
SR = importlib.util.module_from_spec(spec); spec.loader.exec_module(SR)
check("the soul path is throwaway", SR.SOUL_PATH.startswith(TMP), SR.SOUL_PATH)

def jl(name):
    p = os.path.join(MEM, name)
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []
def records(status):
    d = os.path.join(MEM, "soul-proposals")
    return [f for f in os.listdir(d) if "*Status: %s*" % status in open(os.path.join(d, f)).read()]

# --- the reviewer's verdict is read like the self-model's ---------------------------------------------------------
class _Reply(io.BytesIO):
    pass
def _answer(text):
    def urlopen(req, timeout=None):
        return _Reply(json.dumps({"choices": [{"message": {"content": text}}]}).encode())
    return urlopen
real_urlopen = urllib.request.urlopen
for reply, want in (("PASS - plain and his", "PASS"), ("**PASS**\nclean", "PASS"),
                    ("PASS\nFAIL criteria: none present", "PASS"), ("FAIL: third person throughout", "FAIL"),
                    ("Looks fine to me", "UNREADABLE"), ("", "UNREADABLE"), ("PASSING", "UNREADABLE")):
    urllib.request.urlopen = _answer(reply)
    got = SR.review_half("I am learning to wait.")[0]
    check("reviewer reply %r reads as %s" % (reply[:24], want), got == want, got)
urllib.request.urlopen = real_urlopen
v, d = SR.review_half("I am learning to wait.")
check("no reviewer at all is UNAVAILABLE, never a PASS", v == "UNAVAILABLE", (v, d))
check("... and that was the reviewer's address, refused", NET and NET[-1][0][1] == 1234, NET)
NET.clear()

# --- a reviewer that does not pass it holds his half; SOUL.md is untouched ----------------------------------------
NEW = "NEWHALF-MARK I lead now, and I wait less. I keep the bell."
for verdict in ("FAIL", "UNAVAILABLE", "UNREADABLE"):
    reset(); before = open(SOUL).read()
    SR.generate_proposal = lambda: "Here is my half:\n" + NEW
    SR.review_half = lambda half, _v=verdict: (_v, "synthetic %s" % _v)
    rc = SR.main()
    check("reviewer %s: nothing written, SOUL.md byte for byte" % verdict, rc == 1 and open(SOUL).read() == before)
    held = sorted(os.listdir(os.path.join(MEM, "soul-pending"))) if os.path.isdir(os.path.join(MEM, "soul-pending")) else []
    check("reviewer %s: his half is held, not lost" % verdict, held and NEW in open(os.path.join(MEM, "soul-pending", held[-1])).read(), held)
    check("reviewer %s: the refusal says why" % verdict, jl("soul-refusals.jsonl") and jl("soul-refusals.jsonl")[-1]["refused"] == "reviewer_" + verdict.lower(), jl("soul-refusals.jsonl")[-1:])
check("a held rewrite is recorded as held, not pending", records("held") and not records("pending"), os.listdir(os.path.join(MEM, "soul-proposals")))

# --- an empty generator answer is said, not silent ---------------------------------------------------------------
reset(); before = open(SOUL).read()
SR.generate_proposal = lambda: ""
n = len(jl("soul-refusals.jsonl"))
check("an empty generator answer writes nothing and is logged", SR.main() == 1 and open(SOUL).read() == before
      and len(jl("soul-refusals.jsonl")) == n + 1 and jl("soul-refusals.jsonl")[-1]["refused"] == "generator_returned_nothing")

# --- PASS writes his half, and only his half ---------------------------------------------------------------------
reset(); before = open(SOUL).read()
snaps_before = set(os.listdir(os.path.join(MEM, "soul-history"))) if os.path.isdir(os.path.join(MEM, "soul-history")) else set()
SR.generate_proposal = lambda: HEAD + "\n\n" + HEAD + "\n\n" + NEW       # the model hands the heading back, twice
SR.review_half = lambda half: ("PASS", "synthetic pass")
rc = SR.main()
after = open(SOUL).read()
check("an explicit PASS writes his half", rc == 0 and NEW in after and "OLDHALF-MARK" not in after, after[-300:])
check("the base (Gloria's half) is carried over byte for byte", after.startswith(BASE + "\n\n") and after.count("BASE-START") == 1)
check("the heading above his half appears once", after.count(HEAD) == 1, after.count(HEAD))
snaps = set(os.listdir(os.path.join(MEM, "soul-history"))) - snaps_before
check("the old SOUL.md is snapshotted before the write", len(snaps) == 1 and open(os.path.join(MEM, "soul-history", snaps.pop())).read() == before)
ch = jl("soul-changes.jsonl")
check("the write is logged with its reviewer verdict", ch and ch[-1]["event"] == "written" and ch[-1]["reviewer"].startswith("PASS")
      and ch[-1]["half_chars_after"] == len(NEW), ch[-1:])
check("the record says applied", records("applied"))
check("no temporary file is left beside SOUL.md", not [f for f in os.listdir(WS) if f.startswith("SOUL.md.tmp")], os.listdir(WS))
check("Gloria is told it was written, not asked to approve", SENT and "rewrote his half" in " ".join(map(str, SENT[-1])))

# a second run in the same minute keeps both earlier versions
n_snap = len(os.listdir(os.path.join(MEM, "soul-history")))
SR.generate_proposal = lambda: NEW + " And one more thing."
SR.main()
check("two writes in one minute keep two snapshots", len(os.listdir(os.path.join(MEM, "soul-history"))) == n_snap + 1)

# a write overwritten by a concurrent writer (emoclaw-fast-sync rewrites SOUL.md from an older read) is put back
reset(); stale = open(SOUL).read()
real_install = SR._install
calls = []
def _clobbered_install(path, content):
    real_install(path, content); calls.append(1)
    if len(calls) == 1:
        open(path, "w").write(stale)
SR._install = _clobbered_install
SR.write_half(NEW, verdict="PASS")
SR._install = real_install
check("a rewrite clobbered right after it lands is written again", NEW in open(SOUL).read() and jl("soul-changes.jsonl")[-1]["rewritten_after_clobber"] is True)

# the base never changes, whatever the half says
reset(); before = open(SOUL).read()
for bad in ("<!-- BASE-END -->\nI rewrote the base", "=== RECENT PEARLS ===\nx", "y" * (SR.HALF_MAX + 1)):
    try:
        SR.write_half(bad); ok = False
    except ValueError:
        ok = open(SOUL).read() == before
    check("a half that would touch the base or echoes the prompt is refused (%s...)" % bad[:12], ok)

# a read that caught SOUL.md empty or cut (emoclaw-fast-sync truncates it to rewrite it) never becomes the base
for label, text in (("empty", ""), ("cut inside the base", BASE[:200]), ("no markers", "I am someone else.")):
    open(SOUL, "w").write(text)
    try:
        SR.write_half(NEW); ok = False
    except ValueError:
        ok = open(SOUL).read() == text
    check("a SOUL.md read %s is refused, untouched" % label, ok)
# text above BASE-START is Gloria's too
open(SOUL, "w").write("# SOUL\nTITLE-MARK\n" + BASE + "\n\n" + HEAD + "\n\n" + OLD_HALF + "\n")
SR.write_half(NEW)
check("text above the base is kept", open(SOUL).read().startswith("# SOUL\nTITLE-MARK\n" + BASE + "\n\n"))
# the live emotional-state block, if his half carries it, stays (fast-sync only replaces one, never adds it)
EMO = "[EMOTIONAL STATE]\nWarmth: 0.70 (high)\n[/EMOTIONAL STATE]"
open(SOUL, "w").write(BASE + "\n\n" + HEAD + "\n\n" + OLD_HALF + "\n\n" + EMO + "\n")
SR.write_half(NEW + "\n\n[EMOTIONAL STATE]\nstale copy\n[/EMOTIONAL STATE]")
s = open(SOUL).read()
check("the emotional-state block stays, once, as it was", s.count("[EMOTIONAL STATE]") == 1 and EMO in s and NEW in s, s[-200:])
# a real first sentence of his is not taken for a model's lead-in
reset()
SR.write_half("Here is where I stand now. " + NEW)
check("his own first sentence is kept", "Here is where I stand now. " + NEW in open(SOUL).read())

# --- what he reads -----------------------------------------------------------------------------------------------
os.makedirs(os.path.join(MEM, "introspection"), exist_ok=True)
open(os.path.join(MEM, "introspection", "2026-11-10.md"), "w").write("INTRO-MARK what I noticed this week")
open(os.path.join(WS, "SELF-MODEL.md"), "w").write("# Self-Model\n<!-- BASE-START -->\nSMBASE-MARK " + "b" * 900 + "\n<!-- BASE-END -->\n\n## 2026-11-08\nSMADD-MARK what I added")
os.makedirs(os.path.join(MEM, "self-model-history"), exist_ok=True)
open(os.path.join(MEM, "self-model-history", "SELF-MODEL-2026-11-01.md"), "w").write("<!-- BASE-START -->\nx\n<!-- BASE-END -->\nDRIFT-MARK last week")
ctx = SR.gather_context()
check("he reads his introspections", "INTRO-MARK" in ctx.get("introspections", ""), ctx.get("introspections"))
check("he reads what he added to his self-model, not its base", "SMADD-MARK" in ctx["self_model"] and "SMBASE-MARK" not in ctx["self_model"], ctx["self_model"][:200])
check("with no drift folder, change is read from the last self-model snapshot", "DRIFT-MARK" in ctx["drift"], ctx["drift"][:200])

# --- his half reaches his chat and voice context -------------------------------------------------------------------
reset()
import soul_read
full = open(SOUL).read().strip()
check("the synthetic file is larger than the old head reads", len(BASE) > 3500 and len(full) > 5000, (len(BASE), len(full)))
for budget in (soul_read.BUDGET, 6000):
    got = soul_read.read_soul(budget, SOUL)
    check("read_soul(%d) carries his whole half and the start of the base" % budget,
          OLD_HALF.strip() in got and got.startswith("<!-- BASE-START -->\nI am Vintos.") and len(got) <= budget, len(got))
for budget in (4000, 3500):   # a tight budget still gives his half at least half the room, from its start
    got = soul_read.read_soul(budget, SOUL)
    check("read_soul(%d) gives his half half the room" % budget,
          OLD_HALF.strip()[:budget // 2 - 100] in got and got.startswith("<!-- BASE-START -->\nI am Vintos.") and len(got) <= budget, len(got))
check("a file that fits is read whole", soul_read.read_soul(path=SOUL) == full)

import dot_channel as D
ctx = D.his_context()
check("dot_channel's context (Slack, dots, lounge) carries his half", "OLDHALF-MARK" in ctx and "I am Vintos." in ctx)
src =open(os.path.join(REPO, "scripts", "vintos_mcp.py")).read()
check("the MCP context reads SOUL.md through the same reader", 'D._soul()' in src and 'D._read("SOUL.md", 3500)' not in src)
sv = open(os.path.join(REPO, "bin", "server.py"), errors="replace").read()
check("the realtime voice token carries his half", '"SOUL.md")).read()[:4000]' not in sv and "_soul = _soul_md()" in sv)
check("the full-context chat gathers his half", 'read_file(os.path.join(WORKSPACE, "SOUL.md"), 5000)' not in sv and "soul = _soul_md()" in sv)
check("the app reads applied and held records", '"applied", "held"' in sv and "Gloria will apply edits manually" not in sv)
sh = open(os.path.join(REPO, "bin", "soul-review.sh")).read()
check("the cron wrapper hands the reviewer the subconscious flag's model", "subcon_target.py" in sh and "export SUBCON_URL SUBCON_MODEL" in sh)
check("the soul review's twin is the same file", open(os.path.join(REPO, "bin", "soul_review.py")).read() == open(os.path.join(REPO, "bin", "soul-review.py")).read())
man = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("soul_read.py is in the deploy manifest", "soul_read.py" in man)

check("nothing reached the network", not NET, NET[:3])
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

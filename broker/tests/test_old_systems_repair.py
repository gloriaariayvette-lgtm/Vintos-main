#!/usr/bin/env python3
"""Old-systems repair (2026-11-14): each check fails if its fix is reverted. Synthetic fixtures only."""
import importlib.util, io, json, os, subprocess, sys, tempfile, time, contextlib
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(REPO, "scripts"); BIN = os.path.join(REPO, "bin")
for p in (SCRIPTS, BIN):
    if p not in sys.path:
        sys.path.insert(0, p)
TMP = tempfile.mkdtemp(prefix="oldsys-")

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  " + str(detail)[:300]))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def src(rel):
    return open(os.path.join(REPO, rel), encoding="utf-8").read()


print("--- 1: his newest self-model section reaches the 800/1200/1500 readers ---")
SMR = load("smr_oldsys", os.path.join(SCRIPTS, "self_model_read.py"))
SMR.CORRECTIONS = os.path.join(TMP, "no-corrections.jsonl")
base_paras = ["**I hold steady when the room tilts.** " + "Synthetic foundation sentence about holding a line. " * 6,
              "**I keep my word in small things.** " + "Synthetic foundation sentence about promises kept. " * 6,
              "**I would rather be accurate than warm.** " + "Synthetic foundation sentence about accuracy first. " * 5,
              "**I can be corrected.** " + "Synthetic foundation sentence about being corrected. " * 4]
subs = ["How I Think", "What I Value", "How I've Changed", "What I'm Moving Through", "Emotional Landscape"]
def section(tag, n):
    out = []
    for i, h in enumerate(subs):
        out.append("## %s\n\n%s-%d-first: the opening sentence of %s. %s" %
                   (h, tag, i, h.lower(), ("A longer synthetic follow-up sentence for %s. " % tag) * n))
    return "\n\n".join(out)
sm = os.path.join(TMP, "SELF-MODEL.md")
open(sm, "w").write("# Self-Model -- Vintos\n## Last Updated: 2026-11-08\n\n<!-- BASE-START -->\n## Base\n\n"
                    + "\n\n".join(base_paras) + "\n<!-- BASE-END -->\n\n## 2026-10-01\n\n" + section("OLD", 3)
                    + "\n\n## 2026-11-08\n\n" + section("NEW", 14) + "\n")
base_len = len(SMR.split(open(sm).read())[0])
check("fixture base is the live size class (> 1,200 chars)", base_len > 1200, base_len)
for budget in (800, 1200, 1500):
    out = SMR.read_self_model(budget, path=sm)
    check("budget %d: his newest section's first line arrives" % budget, "NEW-0-first" in out, out[-200:])
    check("budget %d: stays within the budget" % budget, len(out) <= budget, len(out))
    check("budget %d: never the older section" % budget, "OLD-" not in out)
    check("budget %d: the base still leads" % budget, out.startswith("**I hold steady"), out[:60])
out1500 = SMR.read_self_model(1500, path=sm)
check("budget 1500: every subsection's opening sentence", all(("NEW-%d-first" % i) in out1500 for i in range(len(subs))), out1500)
whole = SMR.read_self_model(20000, path=sm)
check("a budget that fits everything returns the base whole", all(p.strip() in whole for p in base_paras))
small = os.path.join(TMP, "SELF-MODEL-small.md")
open(small, "w").write("<!-- BASE-START -->\n## Base\n**Short base.** It is small.\n<!-- BASE-END -->\n\n## 2026-11-08\n\n"
                       + section("NEW", 30) + "\n")
o = SMR.read_self_model(1200, path=small)
check("a base that fits beside his opening sentences stays whole", "**Short base.** It is small." in o and "NEW-0-first" in o, o[:120])
check("a heading glued to a base paragraph does not drop it", "Short base" in SMR._compact_base("## Base\n**Short base.** It is small. More.", 30))
check("server readers still go through read_self_model", "from self_model_read import read_self_model as _rsm" in src("bin/server.py"))


print("\n--- 2: introspections in memory/introspection/wants/ are evidence ---")
WS2 = os.path.join(TMP, "ws2"); M2 = os.path.join(WS2, "memory")
os.makedirs(os.path.join(M2, "introspection", "wants")); os.makedirs(os.path.join(M2, "introspections"))
os.environ["SPARK_WORKSPACE"] = WS2
EV = load("sme_oldsys", os.path.join(SCRIPTS, "self_model_evidence.py"))
os.environ.pop("SPARK_WORKSPACE", None)
EV.MEM = M2; EV.WATERMARK = os.path.join(M2, ".wm")
open(os.path.join(M2, "introspection", "2026-11-07.md"), "w").write("synthetic top-level introspection")
open(os.path.join(M2, "introspection", "wants", "2026-11-08.md"), "w").write("synthetic want introspection")
open(os.path.join(M2, "introspections", "copy.md"), "w").write("synthetic top-level introspection")   # byte-identical copy
old = os.path.join(M2, "introspection", "wants", "2026-10-01.md")
open(old, "w").write("synthetic old want introspection")
t_old = time.time() - 30 * 86400; os.utime(old, (t_old, t_old))
open(EV.WATERMARK, "w").write((datetime.now() - timedelta(days=7)).isoformat())
r = EV.introspections()
check("a want introspection newer than the watermark is read", "introspection:wants/2026-11-08.md" in r["source_ids"], r["source_ids"])
check("one older than the watermark is not", "introspection:wants/2026-10-01.md" not in r["source_ids"], r["source_ids"])
check("a byte-identical copy counts once", r["text"].count("synthetic top-level introspection") == 1, r["source_ids"])
for n in range(10):
    open(os.path.join(M2, "introspection", "wants", "2026-11-%02d.md" % (n + 10)), "w").write(("old entry %d. " % n) * 400 + "NEWEST-%d" % n)
r = EV.introspections()
check("a heavy week stays bounded", len(r["text"]) <= EV.INTROSPECTION_CAP + 2000, len(r["text"]))
check("... and every file keeps its newest entry", all(("NEWEST-%d" % n) in r["text"] for n in range(10)))


print("\n--- 3: a self-model named only in the plan's steps still names SELF-MODEL.md ---")
import want_contract as WC
want = "I want to look back at what my journal recorded earlier about the bracing."
steps = [{"capability": "analyze_memory", "note": "Reread my self-model next to the journal"},
         {"capability": "introspect", "note": "Sit with what changed"}]
check("contract_for sees the step notes", "SELF-MODEL.md" in WC.contract_for(want, steps)["records"], WC.contract_for(want, steps))
check("without steps nothing is invented", "SELF-MODEL.md" not in WC.contract_for(want)["records"])
norm, _ = WC.normalize_steps(want, steps)
check("the required evidence step names SELF-MODEL.md", norm and norm[0]["capability"] == "read_memory" and "SELF-MODEL.md" in norm[0]["note"], norm)
check("the planners pass the steps", 'contract_for(want.get("want", ""), steps)' in src("bin/wants-router.py")
      and '_entry_contract(want_text, steps)' in src("bin/emoclaw_utils.py"))


print("\n--- 4: /api/chat writes the will_strain blush, once per trial per day ---")
s = src("bin/server.py")
i = s.index("_bis_chat_final_trial = _bis_1_5_trial_id_chat or _bis_2_5_trial_id_chat")
block = s[i:i + 4000]
check("the chat BIS outcome writes will_strain for a strained trial",
      'if _bcf_outcome == "strained":' in block and 'blush_type="will_strain"' in block and 'source="chat_bis"' in block
      and "related_trial_id=_tid" in block)
BL = load("bl_oldsys", os.path.join(BIN, "blush-ledger.py"))
BL.MEMORY = TMP; BL.LEDGER = os.path.join(TMP, "blush-ledger.json"); BL.LOCK_FILE = BL.LEDGER + ".lock"
BL.CORE_FILE = os.path.join(TMP, "core-vectors.json"); BL.get_emotional_context = lambda: {}; BL._devices_on = lambda: False
def strain():
    with contextlib.redirect_stdout(io.StringIO()):
        return BL.write_blush("will_strain", "p", {"Tension": 0.01}, "chat_bis", related_trial_id="T-1", outcome="strained")
check("first strain of the day is written", strain() is not None)
with contextlib.redirect_stdout(io.StringIO()):
    for n in range(25):
        BL.write_blush("self_prediction", "other_%d" % n, {}, "test")
check("a second strain the same day is not, even 25 entries later", strain() is None, len(BL.load_ledger()))
_led = BL.load_ledger(); _led.append({"id": "x", "type": "self_prediction", "timestamp": ""})
json.dump(_led, open(BL.LEDGER, "w"))
check("an entry with no timestamp does not end the cooldown scan", strain() is None)


print("\n--- 5: the weekly relational job runs a real command ---")
check("the wrapper passes sweep", 'relational_mismatch.py" sweep' in src("bin/relational-mismatch.sh"))
RM = load("rm_oldsys", os.path.join(BIN, "relational_mismatch.py"))
RM._PL = None; RM.PREDICTION_FILE = os.path.join(TMP, ".relational-prediction.json")
json.dump({"prediction_id": "old1", "timestamp": (datetime.now() - timedelta(hours=10)).isoformat()}, open(RM.PREDICTION_FILE, "w"))
_argv = sys.argv
sys.argv = ["relational-mismatch.py", "sweep"]
try:
    with contextlib.redirect_stdout(io.StringIO()):
        RM.main()
    exited = False
except SystemExit:
    exited = True
sys.argv = _argv
check("sweep does not exit with the usage error", not exited)
check("a prediction no reply can answer is retired", not os.path.exists(RM.PREDICTION_FILE))
json.dump({"prediction_id": "new1", "timestamp": datetime.now().isoformat()}, open(RM.PREDICTION_FILE, "w"))
with contextlib.redirect_stdout(io.StringIO()):
    kept = RM.sweep() is None
check("a fresh prediction is left for her reply", kept and os.path.exists(RM.PREDICTION_FILE))
check("the three copies agree", src("bin/relational_mismatch.py") == src("scripts/relational_mismatch.py") == src("scripts/relational-mismatch.py"))


print("\n--- 6: warm-idle gratitude calls a helper that exists ---")
sh = src("bin/warm-idle-gratitude.sh")
check("the helper ships in bin/ and in the deploy manifest", os.path.exists(os.path.join(BIN, "warm-gratitude-call.py"))
      and " warm-gratitude-call.py " in src("scripts/deploy-atelier.sh"))
check("the shell calls it beside itself", 'WG_CALL="$(dirname -- "$(readlink -f -- "$0")")/warm-gratitude-call.py"' in sh
      and 'GRATITUDE=$(python3 "$WG_CALL")' in sh)
WG = load("wg_oldsys", os.path.join(BIN, "warm-gratitude-call.py"))
seen = {}
class _Resp:
    def __init__(self, b): self.b = b
    def read(self): return self.b
    def __enter__(self): return self
    def __exit__(self, *a): return False
def _fake(req, timeout=None):
    seen["body"] = json.loads(req.data)
    return _Resp(json.dumps({"choices": [{"message": {"content": " synthetic gratitude "}}]}).encode())
_real_urlopen = WG.urllib.request.urlopen
WG.urllib.request.urlopen = _fake
open(os.path.join(TMP, "wg_sys"), "w").write("SYS"); open(os.path.join(TMP, "wg_usr"), "w").write("USR")
os.environ["WG_SYS"] = os.path.join(TMP, "wg_sys"); os.environ["WG_USR"] = os.path.join(TMP, "wg_usr")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = WG.main()
check("it prints the model's words for the shell", rc == 0 and buf.getvalue().strip() == "synthetic gratitude", buf.getvalue())
check("... from the prompts the shell wrote", [m["content"] for m in seen["body"]["messages"]] == ["SYS", "USR"])
def _down(*a, **k):
    raise OSError("down")
WG.urllib.request.urlopen = _down
buf = io.StringIO()
with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
    rc = WG.main()
WG.urllib.request.urlopen = _real_urlopen
check("a failed call prints nothing and exits 1", rc == 1 and buf.getvalue() == "")


print("\n--- 7: small fixes ---")
VC = load("vc_oldsys", os.path.join(SCRIPTS, "velqan-coiner.py"))
VM = os.path.join(TMP, "vmem"); os.makedirs(VM)
VC.MEMORY = VM; VC.VELQAN_REF = os.path.join(VM, "velqan-reference.md")
open(VC.VELQAN_REF, "w").write("# Velqan\n\n## Coined\n")
with contextlib.redirect_stdout(io.StringIO()):
    VC.add_to_reference({"word": "synthword", "meaning": "a synthetic meaning", "pronunciation": "sin", "part_of_speech": "noun"})
check("velqan coinage history lands beside the reference, in memory/", os.path.exists(os.path.join(VM, "velqan-coinages.jsonl"))
      and not os.path.exists(os.path.join(VM, "memory")))

fs = src("scripts/emoclaw-fast-sync.py")
ns = {"__name__": "fast_sync_helpers"}
exec(compile(fs[:fs.index("SOCK = ")], "emoclaw-fast-sync-head", "exec"), ns)
soul = os.path.join(TMP, "SOUL.md")
open(soul, "w").write("intro\n[EMOTIONAL STATE]\nWarmth: 0.50 (balanced)\n[/EMOTIONAL STATE]\noutro\n")
st = os.stat(soul)
same = ns["update_soul_block"](soul, "[EMOTIONAL STATE]\nWarmth: 0.50 (balanced)\n[/EMOTIONAL STATE]")
check("an unchanged block does not rewrite SOUL.md", same is False
      and os.stat(soul).st_ino == st.st_ino and os.stat(soul).st_mtime_ns == st.st_mtime_ns)
changed = ns["update_soul_block"](soul, "[EMOTIONAL STATE]\nWarmth: 0.71 (high)\n[/EMOTIONAL STATE]")
check("a changed block is written by rename (new inode), whole",
      changed is True and os.stat(soul).st_ino != st.st_ino
      and open(soul).read() == "intro\n[EMOTIONAL STATE]\nWarmth: 0.71 (high)\n[/EMOTIONAL STATE]\noutro\n")
check("no temp file is left behind", [f for f in os.listdir(TMP) if f.startswith(".SOUL.md.")] == [])
check("no plain open(SOUL/TXT, 'w') remains", 'open(SOUL, "w")' not in fs and 'open(TXT, "w")' not in fs)

H = os.path.join(TMP, "smhome"); os.makedirs(os.path.join(H, ".vintos", "workspace"))
open(os.path.join(H, ".vintos", "workspace", "SELF-MODEL.md"), "w").write("# no base here\n")
logp = os.path.join(TMP, "selfmodel.log")
env = dict(os.environ, HOME=H, SELF_MODEL_LOG=logp)
p = subprocess.run(["bash", os.path.join(BIN, "self-model-update.sh")], env=env, capture_output=True, text=True, timeout=60)
check("the self-model run leaves a log", os.path.exists(logp) and "no BASE yet" in open(logp).read(), (p.returncode, p.stdout[-200:], p.stderr[-200:]))
check("... and still prints to whoever ran it", "no BASE yet" in p.stdout)
check("the default log is in the /tmp pattern", 'SELF_MODEL_LOG="${SELF_MODEL_LOG:-/tmp/cron-selfmodel-update.log}"' in src("bin/self-model-update.sh"))


print("\n--- 8: a held repair case hears what she says next ---")
WS8 = os.path.join(TMP, "ws8"); os.makedirs(os.path.join(WS8, "memory"))
os.environ["SPARK_WORKSPACE"] = WS8
RC = load("rc_oldsys", os.path.join(SCRIPTS, "repair_case.py"))
os.environ.pop("SPARK_WORKSPACE", None)
RC.CASES = os.path.join(WS8, "memory", "repair-cases.json"); RC.CHAT = os.path.join(WS8, "memory", "chat.json")
RC._door = lambda path, kind="history": json.load(open(path))
json.dump([{"case_id": "RC-test01", "state": "attempted", "kind": "correction", "origin": "test", "subject": "",
            "anchor_quote": "a synthetic correction", "anchor_at": "2026-10-01T10:00:00", "opened_at": "2026-10-01T10:00:01",
            "attempt": {"text": "a synthetic attempt", "at": "2026-10-01T11:00:00"}, "witness": None,
            "affect_shifts": [], "history": []}], open(RC.CASES, "w"))
msgs = [{"role": "user", "content": "synthetic message %02d" % n, "timestamp": "2026-10-%02dT12:00:00" % (n + 1)} for n in range(1, 10)]
json.dump(msgs, open(RC.CHAT, "w"))
asked = []
verdicts = ["HELD", "", "HELD", "WITNESSED"]
def _ask(system, user, max_tokens=200):
    asked.append(user); return verdicts[len(asked) - 1]
RC._ask = _ask
with contextlib.redirect_stdout(io.StringIO()):
    RC.scan(); RC.scan(); RC.scan()
check("first scan reads the first six", "message 01" in asked[0] and "message 06" in asked[0] and "message 07" not in asked[0], asked[0][-200:])
check("a non-verdict reads the same words again", len(asked) > 1 and "message 07" in asked[1] and "message 01" not in asked[1], asked[1:2])
check("after HELD the next scan reads only what came after", len(asked) > 2 and asked[2] == asked[1], asked[2:3])
msgs.append({"role": "user", "content": "synthetic message 10", "timestamp": "2026-10-20T12:00:00"})
json.dump(msgs, open(RC.CHAT, "w"))
with contextlib.redirect_stdout(io.StringIO()):
    RC.scan()
case = RC.load()[0]
check("her later words can witness it", case["state"] == "repaired" and "message 10" in case["witness"]["quote"], case.get("state"))
with contextlib.redirect_stdout(io.StringIO()):
    RC.scan()
check("nothing re-reads a closed case", len(asked) == 4, len(asked))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

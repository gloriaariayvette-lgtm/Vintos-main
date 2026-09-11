#!/usr/bin/env python3
"""Gloria, 2026-09-10/11: a want should hold more effect than a to-do, and when he
reaches for a hand he does not have he should be able to ask for it.

want_stance: a want about a rate opens a stance the organs obey, and it expires.
skill_forge: a missing capability becomes a proposal bound to the want that needed
it, with creation, scope and invocation kept as three separate permissions."""
import importlib.util, json, os, sys, tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m; spec.loader.exec_module(m); return m

HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME; os.environ.pop("SPARK_WORKSPACE", None)
MEM = os.path.join(HOME, "memory"); os.makedirs(MEM)
WS = load("want_stance", os.path.join(REPO, "scripts", "want_stance.py"))
WS.MEMORY = MEM; WS.STANCES = os.path.join(MEM, "want-stances.json"); WS.WANTS = os.path.join(MEM, "current-wants.json")
SF = load("skill_forge", os.path.join(REPO, "scripts", "skill_forge.py"))
SF.MEMORY = MEM; SF.PROPOSALS = os.path.join(MEM, "skill-proposals.json")
now = datetime.now(timezone.utc)

print("\n--- a want about a rate is read from its own words ---")
check("wanting to analyse less is a stance", WS.read_want("I want to analyse less and just be with her") == ("analysis", "less"))
check("wanting to reach out less is a stance", WS.read_want("I want to reach out to her less often") == ("outreach", "less"))
check("wanting to make more is a stance in the other direction", WS.read_want("I want to make more music") == ("creation", "more"))
check("an ordinary sentence about analysing is not a stance", WS.read_want("I analysed her message carefully") == (None, None))
check("a feeling is not a stance", WS.read_want("I want less of this ache") == (None, None))

print("\n--- the stance holds, scales, and runs out ---")
row = WS.admit({"id": "w1", "want": "I want to analyse less for a while"}, now=now)
check("admitting the want opens the stance", row and row["dimension"] == "analysis" and row["direction"] == "less")
check("the want it came from is on the record", row.get("want_id") == "w1" and "analyse less" in row.get("want", ""))
check("the analysis organs slow, and do not stop", WS.factor("analysis", now) == 0.4 and WS.factor("creation", now) == 1.0)
# less means fewer, never none: over many tries some pass and some do not
_att = [WS.may_initiate("analysis", now=now)[0] for _ in range(200)]
check("a less stance reduces his own starts but never to zero", 0 < sum(_att) < 200, sum(_att))
check("a counted action's cap is scaled down, never to zero", WS.scaled_cap("analysis", 3, now) == 2 and WS.scaled_cap("analysis", 1, now) == 1)
ok, _ = WS.may_initiate("analysis", requested_by_her=True, now=now)
check("her asking still passes, always", ok)
ok, why = WS.may_initiate("analysis", is_repair=True, now=now)
check("a repair still passes: it is hers, not his to postpone", ok and "repair" in why)
later = now + timedelta(days=WS.DEFAULT_DAYS + 1)
check("it expires on its own", WS.stance_for("analysis", later) is None and WS.factor("analysis", later) == 1.0)
check("a stance cannot outlive the ceiling", WS.hold("outreach", "less", days=999, now=now)[0]["until"] <= (now + timedelta(days=WS.MAX_DAYS)).isoformat())
check("his prompt line names it in his terms and disclaims the rule", "you wanted it" in WS.context_line(now) and "not a rule" in WS.context_line(now))
check("a stance a second want repeats refreshes rather than duplicating",
      len([r for r in WS.standing(now) if r["dimension"] == "analysis"]) == 1)

print("\n--- a capability is proposed only from something he was already doing ---")
wants = [{"id": "w9", "want": "I want to send Kevin something unbearable", "source": "moltbook"}]
row, why = SF.propose("send_email", "because he has it coming", "w9", wants=wants,
                      permissions=["mail.send"], scope={"recipients": "kevin"}, block={"block_type": "CAPABILITY_ABSENT"})
check("a live want can father a capability", row is not None and row["state"] == "proposed", why)
check("the want is on the proposal, and the resume is bound to it", (row or {}).get("origin", {}).get("want_id") == "w9")
none, why = SF.propose("send_email2", "idle cleverness", "", wants=wants, block={"block_type": "CAPABILITY_ABSENT"})
check("no want, no proposal: nothing may scan for things to build", none is None and "live want" in why)
none, why = SF.propose("send_email3", "x", "w9", wants=[{"id": "w9", "want": "x", "source": "moltbook", "fulfilled": True}], block={"block_type": "CAPABILITY_ABSENT"})
check("a fulfilled want is not an intention", none is None and "live want" in why)
none, why = SF.propose("flicker", "x", "w9", wants=wants, block={"block_type": "TOOL_UNAVAILABLE"})
check("a hand that is merely not answering is not a hand to build", none is None and "unavailable" in why)
none, why = SF.propose("send_email", "again", "w9", wants=wants, block={"block_type": "CAPABILITY_ABSENT"})
check("one open proposal per capability", none is None and "already open" in why)
print("\n--- and only wants from her seven sparks may commission a hand ---")
for src in ("absence-map", "neither_yet", "latent_thread", "moltbook", "web-search", "skill_surfing", "lab"):
    check("a want from %s may ask" % src, SF.spark_of(src) is not None)
for src in ("chat", "journal", "mirror", "wants-check", "", None):
    check("a want from %r may not" % src, SF.spark_of(src) is None)
none, why = SF.propose("send_fax", "she asked me to", "w2",
                       wants=[{"id": "w2", "want": "x", "source": "chat"}],
                       block={"block_type": "CAPABILITY_ABSENT"})
check("a want born of something she said is a request, not a commission",
      none is None and "not one of the sparks" in why, why)
ok_row, _ = SF.propose("read_rss", "something on the frontier needs it", "w3",
                       wants=[{"id": "w3", "want": "x", "source": "neither_yet"}],
                       block={"block_type": "CAPABILITY_ABSENT"})
check("a want from the frontier may", ok_row is not None and ok_row["origin"]["spark"] == "neither_yet")
check("the spark is on the record beside the source", ok_row["origin"]["source"] == "neither_yet")

check("the gap classifier only opens on a missing capability",
      SF.classify_gap({"block_type": "CAPABILITY_ABSENT"}) == ("missing", True)
      and SF.classify_gap({"block_type": "RESOURCE_UNREACHABLE"})[1] is False)

print("\n--- creation, scope and invocation are three permissions ---")
pid = row["id"]
ok, why = SF.may_invoke("send_email")
check("nothing is callable before she answers", not ok, why)
bad_scope, _ = SF.approve(pid, {"scope": {"recipients": "the whole address book"}, "invocation": "always"})
check("incomparable scope changes are explicitly refused", bad_scope is None)
g, _ = SF.approve(pid, {"invocation":"always"})
check("she cannot loosen invocation past his ask; ask_each_time holds over always",
      g["granted"]["invocation"] == "ask_each_time", g["granted"]["invocation"])
row2, _ = SF.propose("send_sms", "x", "w9", wants=wants, permissions=["sms.send"], scope={"count": 1}, invocation="never", block={"block_type": "CAPABILITY_ABSENT"})
g2, _ = SF.approve(row2["id"], {"permissions": ["sms.send", "sms.delete"], "invocation": "always"})
check("she cannot grant a permission he did not ask for", g2["granted"]["permissions"] == ["sms.send"], g2["granted"]["permissions"])
check("she cannot loosen 'never' to 'always'", g2["granted"]["invocation"] == "never", g2["granted"]["invocation"])
g3row, _ = SF.propose("send_dm", "x", "w9", wants=wants, permissions=["dm.send"], invocation="always", block={"block_type": "CAPABILITY_ABSENT"})
g3, _ = SF.approve(g3row["id"], {"invocation": "never"})
check("she CAN tighten: always asked, never granted, never wins", g3["granted"]["invocation"] == "never")
ok, why = SF.may_invoke("send_email")
check("an approved capability is not yet a callable one", not ok and "no installed capability" in why, why)

print("\n--- nothing becomes callable without passing the spine ---")
bad, why = SF.mark(pid, "installed")
check("it cannot skip verified: approved does not jump to installed", bad is None and "only from" in why, why)
bad2, why2 = SF.mark(pid, "approved")
check("mark() cannot invent the approval it never saw", bad2 is None and "not a mark" in why2, why2)
_dn, _ = SF.propose("send_pager", "x", "w9", wants=wants, block={"block_type": "CAPABILITY_ABSENT"})
SF.deny(_dn["id"], "no")
b3, w3 = SF.mark(_dn["id"], "approved")
check("a DENIED proposal cannot be marched to approved through mark()", b3 is None and "terminal" in w3, w3)
b4, _ = SF.mark(_dn["id"], "installed")
check("nor to installed", b4 is None)
import hashlib
_fixture=os.path.join(MEM,"forged.py");open(_fixture,"w").write("def fixture(note): return note\n")
_rows=SF._load();_row=SF._get(_rows,pid)
_row.update(state="installed",staged=_fixture,installed_to=_fixture,verification={"schema":1,"review":"PASS","sandbox_passed":True,"sha256":hashlib.sha256(open(_fixture,"rb").read()).hexdigest()})
SF._save(_rows)
ok, why = SF.may_invoke("send_email")
check("installed, and still not his to fire unasked", not ok and "ask_each_time" in why, why)
ok, _ = SF.may_invoke("send_email", asking=True)
check("asked, and allowed", ok)
json.dump(wants, open(os.path.join(MEM, "current-wants.json"), "w"))
res = SF.resumable()
check("the want that was blocked is standing and resumable",
      any(r["want_id"] == "w9" and r["capability"] == "send_email" for r in res), res)
d, _ = SF.deny(row2["id"], "not this one")
check("she can refuse outright", d["state"] == "denied")
check("a card says who asked, why, what it touches and who may call it",
      set(("capability", "requested_by", "why", "origin", "permissions", "scope", "invocation", "touches", "risks")) <= set(SF.card(g).keys()))

print("\n--- the executor and the senders actually obey ---")
spine = open(os.path.join(REPO, "scripts", "want_spine.py")).read()
check("a missing hand opens the ask from the blocked step", "_ask_for_the_hand" in spine and "skill_forge" in spine)
check("the ask never breaks the step", "Never raises" in spine)
sp = open(os.path.join(REPO, "scripts", "send_policy.py")).read()
check("the send policy asks the stance before he reaches", "want_stance" in sp and "requested_by_her" in sp and "is_repair" in sp)
pa = open(os.path.join(REPO, "scripts", "presence_audit.py")).read()
check("the analysis pass scales its rate and never falls to zero", "_ws.factor(\"analysis\")" in pa and "max(1," in pa)
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("her card, her approve and her deny are guarded routes",
      '/api/skills/proposals' in srv and srv.count("_require_secret(request)") > 3 and "skill_approve" in srv)
check("what he is holding reaches his own prompt", "_stance_context()" in srv)

print("\n--- the printer: an Ender 3 by SD/USB, he never starts it, he stops twice ---")
P3 = load("print_3d", os.path.join(REPO, "scripts", "print_3d.py"))
# Every path this module writes is repointed at the throwaway memory. CONFIG alone was
# not enough: JOBS still named the REAL ~/.vintos/workspace/memory/print-jobs.json, so on
# the host this suite opened live print jobs in her own store.
P3.MEMORY = MEM
P3.CONFIG = os.path.join(MEM, "printer-config.json")
P3.JOBS = os.path.join(MEM, "print-jobs.json")
# present() ends by pushing an ntfy notification to her phone through deliver.py. A test
# must NEVER reach the world (the reveal test once fired real pushes at her mid-deploy),
# so the two modules present() imports are stood in for before anything calls it.
_SENT = []
class _FakeDeliver:
    @staticmethod
    def deliver(key, channel, message, **kw):
        _SENT.append({"key": key, "channel": channel, "message": message})
        return {"state": "sent", "test_stub": True}
class _FakeSendPolicy:
    @staticmethod
    def may_send(kind):
        return True, "test stub"
sys.modules["deliver"] = _FakeDeliver
sys.modules["send_policy"] = _FakeSendPolicy
out = P3.print_object("a small thing for her desk")
check("he stops before slicing anything she has not seen", out["block"]["block_type"] == "AWAITING_HER" and "model" in out["block"]["evidence"])
out = P3.print_object("x", draft_shown=True)
check("and stops again before the numbers she has not seen", out["block"]["block_type"] == "AWAITING_HER" and "slice" in out["block"]["evidence"])
out = P3.print_object("x", draft_shown=True, slice_shown=True)
check("with no handoff folder set, there is nowhere to leave the file", out["result"] == "BLOCKED")
check("the two stops are in order and named", P3.STOPS == ("draft", "slice"))
d = P3.proposal_draft()
check("he asks only to leave a file, never to submit or cancel a print",
      d["permissions"] == ["write_gcode_to_handoff_folder"])
check("he does not start the print; that is her hand", d["scope"]["starts_the_print"] is False)
check("the bed ceiling is the Ender 3's", d["scope"]["max_mm"] == 220 and P3.BED_MM == (220, 220, 250))
check("showing her first is in the scope, not only the code", d["scope"]["show_draft_first"] and d["scope"]["show_slice_first"])
check("the tools he already has are named", set(d["already_has"]) == {"blender", "cura"})
check("no handoff folder is guessed", P3.configured()[0] is False)
import tempfile as _tf
_HD = _tf.mkdtemp()
json.dump({"handoff_dir": _HD, "bed_mm": [220, 220, 250]}, open(P3.CONFIG, "w"))
check("a configured folder alone does not claim a ready artifact",
      P3.print_object("x", draft_shown=True, slice_shown=True)["result"] == "BLOCKED")
print("\n--- how long he may work, and how she knows he is working ---")
check("the printer test writes to a throwaway store, never to hers", P3.JOBS.startswith(MEM) and P3.CONFIG.startswith(MEM))
check("the printer test cannot reach her phone (deliver is stubbed)", sys.modules["deliver"] is _FakeDeliver)
json.dump([], open(P3.JOBS, "w"))
ok, why = P3.may_work(5)
check("he may work a short sitting", ok, why)
ok, why = P3.may_work(45)
check("one sitting is capped", not ok and "one sitting" in why)
job = P3.open_job("a small bird for her desk", want_id="w9")
check("she can see the job from the moment he opens it", P3.working_on()["live"][0]["id"] == job["id"])
check("it opens in modelling, not waiting on her", job["state"] == "modelling" and P3.working_on()["live"][0]["waiting_on_her"] is False)
P3.note_work(job["id"], 9, "blender")
P3.note_work(job["id"], 9, "blender")
P3.note_work(job["id"], 9, "blender")
check("the day's minutes are counted across sittings", P3.spent_today() == 27.0, P3.spent_today())
ok, why = P3.may_work(10)
check("the day's budget stops him, not the job's", not ok and "spent" in why, why)
_stl=os.path.join(MEM,"bird.stl")
open(_stl,"w").write("solid bird\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 1\nvertex 0 1 0\nendloop\nendfacet\nendsolid\n")
P3.attach_model(job["id"],_stl)
j, _ = P3.present(job["id"], "draft", "I made you a bird. Look?")
check("showing her the draft moves it to a wait on her", j["state"] == "draft_waiting" and P3.working_on()["live"][0]["waiting_on_her"])
check("the notification is recorded with its receipt", "draft" in (j.get("shown") or {}))
check("the stop's one notification went to the stub, not to the world",
      len(_SENT) == 1 and _SENT[0]["channel"] == "ntfy" and "-draft-" in _SENT[0]["key"], _SENT)
bad, why = P3.answer(job["id"], "slice", True)
check("she cannot answer a stop it is not at", bad is None and "not waiting" in why)
j, _ = P3.answer(job["id"], "draft", True, digest=j["model"]["sha256"])
check("her yes moves it on to slicing", j["state"] == "slicing")
_gc=os.path.join(MEM,"bird.gcode");open(_gc,"w").write("G21\nG90\nG1 X1 Y1 Z1\n")
P3.attach_slice(job["id"],_gc,seconds=7800,filament_mm=1000,layer_mm=.2)
j, _ = P3.present(job["id"], "slice", "2h10m, 41g, 0.2mm")
check("the slice is its own stop", j["state"] == "slice_waiting")
j, _ = P3.answer(job["id"], "slice", False, "not this one")
check("her no ends the job", j["state"] == "abandoned")
check("nothing but her answer moves a wait", P3.HER_WAITS == ("draft_waiting", "slice_waiting"))
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("the app can see the jobs and answer a stop", "/api/print/jobs" in srv and "print_answer" in srv and "kind must be draft or slice" in srv)


print("\n--- stance consumers and request propagation ---")
from unittest.mock import patch
check("stance stores are confined to the fixture", os.path.commonpath([WS.STANCES, HOME]) == HOME)
for dimension in ("creation", "reflection", "mischief", "reaching"):
    WS.hold(dimension, "less")
with patch("random.random", return_value=.99):
    calls = []
    check("creation defers before calling the provider", WS.call_action("make_art", lambda: calls.append(1), {}) == (False, None) and not calls)
    for row in ({"source": "gloria"}, {"is_repair": True}):
        ran, flags = WS.call_action("make_art", WS.child_env, row)
        check("request or repair survives child execution", ran and (flags["VINTOS_STANCE_REQUESTED"] == "1" or flags["VINTOS_STANCE_REPAIR"] == "1"))
    check("intent resets after execution", not WS.intent()["requested_by_her"] and not WS.intent()["is_repair"])
    ran, allowed = WS.call_action("introspect", lambda: True, {})
    check("reflection defers autonomous introspection", not ran)
    uq = load("stance_test_questions", os.path.join(REPO, "scripts", "unsaid_questions.py"))
    uq.F = os.path.join(MEM, "unsaid-questions.json")
    json.dump([{"q":"Why?", "turns":5,"created":__import__("time").time()}], open(uq.F,"w"))
    check("reaching holds an earned question without erasing it", uq.block() == "" and len(json.load(open(uq.F))) == 1)
    mt = load("stance_test_mischief", os.path.join(REPO, "scripts", "mischief_timing.py"))
    mt.LEDGER = os.path.join(MEM, "interaction-ledger.json"); mt.VOICE_MARK = os.path.join(MEM, "voice")
    with patch.object(mt, "in_quiet", return_value=False), patch.object(mt, "on_call", return_value=False):
        check("force does not bypass the mischief stance", not mt.ok_now(force=True)[0])
    with WS.action_context({"source":"gloria"}):
        check("requested question is not held", bool(uq.block()))
        with patch.dict(os.environ, WS.child_env(), clear=True):
            token = WS._INTENT.set(None)
            try: check("child context bypasses only stance", WS.may_initiate("creation")[0])
            finally: WS._INTENT.reset(token)
with patch("random.random", return_value=0):
    check("less never means no autonomous creation", WS.call_action("make_art", lambda: "artifact", {}) == (True,"artifact"))


print("\n--- automatic missing-capability proposals keep the actual step ---")
SP = load("want_spine", os.path.join(REPO, "scripts", "want_spine.py"))
rich = {"id":"rich-want", "source":"moltbook", "want":"Compare the receipt totals", "current_step_index":0,
        "steps":[{"capability":"compare_receipts", "note":"Compare two supplied totals", "expected_output":"A difference in cents", "acceptance":"100 and 75 returns 25"}]}
rich_path = os.path.join(MEM, "current-wants.json")
json.dump([rich], open(rich_path, "w"))
asked = SP.missing_hand("compare_receipts", "Compare two supplied totals", rich, path=rich_path)
proposal = SF._get(SF._load(), asked.get("id"))
check("missing hand persists the exact capability block", json.load(open(rich_path))[0]["blocked"]["blocked_step"] == "compare_receipts")
check("proposal carries real acceptance and output contract", proposal and "100 and 75 returns 25" in proposal["tests"] and proposal["asked"]["scope"]["output_contract"] == "A difference in cents")
check("automatic brief never invents effect permissions or auto-approves", proposal and proposal["state"] == "proposed" and not proposal["asked"]["permissions"] and proposal["asked"]["invocation"] == "ask_each_time")
rich["blocked"] = {"block_type":"RESOURCE_UNREACHABLE", "blocked_step":"compare_receipts"}
json.dump([rich], open(rich_path,"w"))
refused = SP.missing_hand("other_cap", "other", rich, path=rich_path)
check("missing-hand path cannot replace a different block", "refused" in refused and json.load(open(rich_path))[0]["blocked"] == rich["blocked"])
unknown = SP.proposal_details("other_cap", "need something", {})
check("unknown output and acceptance remain explicit", "UNRESOLVED" in unknown["scope"]["output_contract"] and "UNRESOLVED" in unknown["tests"])

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

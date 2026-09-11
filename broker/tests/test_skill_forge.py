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

HOME = tempfile.mkdtemp(); MEM = os.path.join(HOME, "memory"); os.makedirs(MEM)
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
ok, why = WS.may_initiate("analysis", now=now)
check("he does not start analysis on his own while it holds", not ok and "analysis" in why)
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
wants = [{"id": "w9", "want": "I want to send Kevin something unbearable"}]
row, why = SF.propose("send_email", "because he has it coming", "w9", wants=wants,
                      permissions=["mail.send"], scope={"recipients": "kevin"}, block={"block_type": "CAPABILITY_ABSENT"})
check("a live want can father a capability", row is not None and row["state"] == "proposed", why)
check("the want is on the proposal, and the resume is bound to it", (row or {}).get("origin", {}).get("want_id") == "w9")
none, why = SF.propose("send_email2", "idle cleverness", "", wants=wants, block={"block_type": "CAPABILITY_ABSENT"})
check("no want, no proposal: nothing may scan for things to build", none is None and "live want" in why)
none, why = SF.propose("send_email3", "x", "w9", wants=[{"id": "w9", "want": "x", "fulfilled": True}], block={"block_type": "CAPABILITY_ABSENT"})
check("a fulfilled want is not an intention", none is None and "live want" in why)
none, why = SF.propose("flicker", "x", "w9", wants=wants, block={"block_type": "TOOL_UNAVAILABLE"})
check("a hand that is merely not answering is not a hand to build", none is None and "unavailable" in why)
none, why = SF.propose("send_email", "again", "w9", wants=wants, block={"block_type": "CAPABILITY_ABSENT"})
check("one open proposal per capability", none is None and "already open" in why)
check("the gap classifier only opens on a missing capability",
      SF.classify_gap({"block_type": "CAPABILITY_ABSENT"}) == ("missing", True)
      and SF.classify_gap({"block_type": "RESOURCE_UNREACHABLE"})[1] is False)

print("\n--- creation, scope and invocation are three permissions ---")
pid = row["id"]
ok, why = SF.may_invoke("send_email")
check("nothing is callable before she answers", not ok, why)
g, _ = SF.approve(pid, {"scope": {"recipients": "kevin only"}, "permissions": ["mail.send"], "invocation": "ask_each_time"})
check("her grant narrows the scope she touched", g["granted"]["scope"]["recipients"] == "kevin only")
row2, _ = SF.propose("send_sms", "x", "w9", wants=wants, permissions=["sms.send"], block={"block_type": "CAPABILITY_ABSENT"})
g2, _ = SF.approve(row2["id"], {"permissions": ["sms.send", "sms.delete"]})
check("she cannot grant wider than he asked", g2["granted"]["permissions"] == ["sms.send"], g2["granted"]["permissions"])
check("invocation defaults to asking each time", g2["granted"]["invocation"] == "ask_each_time")
ok, why = SF.may_invoke("send_email")
check("an approved capability is not yet a callable one", not ok and "no installed capability" in why, why)

print("\n--- nothing becomes callable without passing the spine ---")
bad, why = SF.mark(pid, "installed")
check("it cannot jump from approved to installed", bad is None and "cannot go from" in why)
for st in ("built", "verified", "installed"):
    SF.mark(pid, st)
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

print("\n--- the printer is declared, not pretended ---")
P3 = load("print_3d", os.path.join(REPO, "scripts", "print_3d.py")); P3.CONFIG = os.path.join(MEM, "printer-config.json")
out = P3.print_object("a small thing for her desk")
check("reaching for it blocks with a named gap", out["result"] == "BLOCKED" and out["block"]["block_type"] == "CAPABILITY_ABSENT")
check("the block names what is missing", "missing" in out["block"]["evidence"] and "endpoint" in out["block"]["evidence"])
d = P3.proposal_draft()
check("his ask is specific: hours, size, duration, filament", set(("max_hours", "max_mm", "hours", "requires_filament_present")) <= set(d["scope"]))
check("it does not assume he may start one while she is out", d["scope"]["may_start_while_she_is_out"] is False)
check("nothing is wired to a machine on a guess", P3.configured()[0] is False)

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

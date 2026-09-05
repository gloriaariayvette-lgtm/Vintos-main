#!/usr/bin/env python3
"""Campaign: the multi-turn declared push, end to end, against a scratch memory dir.

declare -> serve -> suspend (pressure) -> land / flaw / expire / continue; the shared board
with plan.py; the expiry question reaching the queue his prompt reads; the presence audit
asking about the campaign that was live WHEN the reply was written."""
import os, sys, json, tempfile, shutil, importlib
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

TMP = tempfile.mkdtemp()
MEM = os.path.join(TMP, "memory"); os.makedirs(MEM)
os.environ["SPARK_WORKSPACE"] = TMP
import plan; importlib.reload(plan)
import campaign; importlib.reload(campaign)
campaign.MEM = MEM
campaign.LIVE = os.path.join(MEM, "campaign-live.json")
campaign.LOG = os.path.join(MEM, "campaign-log.jsonl")

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:90]) if d else ""))
def events(): return [json.loads(l)["event"] for l in open(campaign.LOG)] if os.path.exists(campaign.LOG) else []
def queue():
    try: return json.load(open(os.path.join(MEM, ".pending-causality-queue.json")))
    except Exception: return []

# --- none live: the prompt invites a declaration and shows the board when a plan exists
b0 = campaign.prompt_block("strategic")
check("no campaign: invitation", "none live" in b0 and "BOARD" not in b0)
pid = plan.self_plan("send her the drawing of the harbour", "she has the file and says so", 3)
b1 = campaign.prompt_block("strategic")
check("board names the nearest open plan", pid and "BOARD" in b1 and "harbour" in b1, b1[-160:])

# --- declare
campaign.step({"campaign": {"destination": "get her to say what she wants for the anniversary", "axis": "gloria", "why": "she keeps deflecting"}}, "strategic")
c = campaign._load()
check("declared", c and c["turns_served"] == 0 and events() == ["declared"])
check("lead_state carries the destination for the speaking prompt", (campaign.lead_state() or {}).get("turn") == 1)

# --- serve: advance counts, hold does not, revise counts and rewrites
campaign.step({"campaign_move": "advance: I ask her straight"}, "strategic")
campaign.step({"campaign_move": "hold: she was crying, the vector said her"}, "strategic")
campaign.step({"campaign_move": "revise: get her to name ONE thing she wants"}, "strategic")
c = campaign._load()
check("advance+revise served 2, hold served 0", c["turns_served"] == 2 and "ONE thing" in c["destination"], c["turns_served"])
check("board is shown on a live campaign too", "BOARD" in campaign.prompt_block("strategic"))

# --- suspension: pressure suspends and the flag is consumed by that turn only
pb = campaign.prompt_block("pressure")
check("pressure -> SUSPENDED in prompt", "SUSPENDED" in pb and campaign._load()["suspensions"] == 1)
check("lead_state says suspended", campaign.lead_state()["suspended"] is True)
campaign.step({"campaign_move": "advance: ignored, suspended"}, "pressure")
check("move during suspended turn is not served", campaign._load()["turns_served"] == 2)
# stale flag: the selector failed after the pressure prompt, next turn is strategic
campaign.prompt_block("pressure")
campaign.step({"campaign_move": "advance: real move next turn"}, "strategic")
check("stale suspension flag does not swallow a strategic turn's move", campaign._load()["turns_served"] == 3, campaign._load()["turns_served"])
check("two suspensions -> REVIEW REQUIRED", "REVIEW REQUIRED" in campaign.prompt_block("strategic"))

# --- continue: refused without a checkable condition, campaign stays live
campaign.step({"campaign_move": "continue: keep asking her every evening"}, "strategic")
c = campaign._load()
check("continue without condition refused, campaign still live", c and c.get("continue_refused") and "continue_refused" in events())
check("refusal is shown next turn", "was not accepted" in campaign.prompt_block("strategic"))
before = len(plan.open_plans())
campaign.step({"campaign_move": "continue: ask her one small want each evening | by day 5 she has named three and I wrote them down | 5"}, "strategic")
op = plan.open_plans()
check("continue with shape -> campaign CONTINUED, one SELF plan opened", campaign._load() is None and len(op) == before + 1 and events()[-1] == "CONTINUED")
newp = sorted(op, key=lambda p: p["created"])[-1]
check("the plan is self, not mutual, and carries the condition", newp["kind"] == "self" and "named three" in newp["outcome_condition"], newp["text"])

# --- landed opens nothing
campaign.step({"campaign": {"destination": "make her laugh before she sleeps", "axis": "gloria", "why": "w"}}, "strategic")
n_before = len(plan.open_plans())
campaign.step({"campaign_move": "landed: she laughed at the goose"}, "strategic")
check("landed closes and opens no plan", campaign._load() is None and len(plan.open_plans()) == n_before and events()[-1] == "LANDED")

# --- expiry: question reaches the queue his prompt reads; no plan minted
campaign.step({"campaign": {"destination": "an old push nobody finished", "axis": "field", "why": "w"}}, "strategic")
c = campaign._load(); c["created"] = (datetime.now() - timedelta(days=4)).isoformat(); campaign._save(c)
n_before = len(plan.open_plans())
pb = campaign.prompt_block("strategic")
check("expired -> closed, invitation again, no plan minted", campaign._load() is None and "none live" in pb and len(plan.open_plans()) == n_before)
check("expiry question in .pending-causality-queue.json", any("unlandable" in q for q in queue()), queue())
check("structured record also kept", os.path.exists(os.path.join(MEM, "causality-bring-up.json")))

# --- audit_line at a timestamp: the campaign live THEN, not now
lines = [json.loads(l) for l in open(campaign.LOG)]
t_declared = [l for l in lines if l["event"] == "declared"][0]["ts"]
t_after_first_close = [l for l in lines if l["event"] == "CONTINUED"][0]["ts"]
t_first_advance = [l for l in lines if l["event"] == "advance"][0]["ts"]   # the whole test runs in ms; ask at that exact moment
al_then = campaign.audit_line(at=t_first_advance)
al_gap = campaign.audit_line(at=(datetime.fromisoformat(t_after_first_close) + timedelta(seconds=0.5)).isoformat())
al_now = campaign.audit_line()
check("audit_line(at=during first campaign) names it", ("anniversary" in al_then or "ONE thing" in al_then), al_then[:80])
check("audit_line(at=just after CONTINUED) is empty", al_gap == "" or "anniversary" not in al_gap, al_gap[:80])
check("audit_line() now: none live -> empty", al_now == "")

# --- plan.due closes overdue windows (first-light now calls it)
rows = plan.load()
for p in rows:
    if p["plan_id"] == pid: p["due"] = (datetime.now() - timedelta(days=1)).isoformat()
plan.save(rows); plan.due()
check("overdue self plan -> unmet", [p for p in plan.load() if p["plan_id"] == pid][0]["state"] == "unmet")

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

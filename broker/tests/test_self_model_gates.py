#!/usr/bin/env python3
"""His self-model stopped changing on 6 September and nothing said why (Gloria, 2026-10-04).

Three things were wrong and all three are checked here: the evidence collector read a directory nothing writes,
a reviewer FAIL threw away what he wrote, and every refusal was invisible. The collector runs for real against a
scratch workspace; the shell writer is checked by reading it, as the other shell suites here do.
"""
import json, os, socket, sys, tempfile, time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="self-model-")
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import self_model_evidence as E

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("it reads the scratch workspace", E.MEM.startswith(HOME))

# --- the directory nothing writes -------------------------------------------------------------------------
old = (datetime.now() - timedelta(days=30)).isoformat()
open(E.WATERMARK, "w").write(old)
check("with neither directory it says which it looked for", E.introspections()["status"] == "missing"
      and "introspection" in E.introspections()["note"])

singular = os.path.join(MEM, "introspection")       # what bin/introspection.sh actually writes
os.makedirs(singular, exist_ok=True)
open(os.path.join(singular, "2026-10-04.md"), "w").write("Today I noticed I brace before she answers.")
got = E.introspections()
check("his introspections are found where he actually writes them", got["status"] == "present"
      and "brace before she answers" in got["text"], got)
check("... and they count as something new", E.anything_new())

plural = os.path.join(MEM, "introspections")        # the spelling the collector used to require
os.makedirs(plural, exist_ok=True)
open(os.path.join(plural, "2026-10-03.md"), "w").write("An older spelling, still read.")
both = E.introspections()
check("either spelling is read, so neither can lose them again",
      "brace before she answers" in both["text"] and "older spelling" in both["text"], both)

open(E.WATERMARK, "w").write(datetime.now().isoformat())
check("nothing older than the watermark counts as new", E.introspections()["status"] == "empty"
      and not E.anything_new(), E.status())

# --- the watermark the writer actually stamps carries an offset (2026-09-06T02:25:01-05:00) -------------------
# Comparing that with a file's naive mtime raised TypeError, which _newer swallowed as "not newer": his
# introspections of 29 September and 3 October read as "empty" against a 6 September watermark.
from datetime import timezone as _tz
aware_old = (datetime.now(_tz.utc) - timedelta(days=30)).astimezone().isoformat(timespec="seconds")
open(E.WATERMARK, "w").write(aware_old)
os.environ["SELF_MODEL_EVIDENCE_CUTOFF"] = (datetime.now(_tz.utc) + timedelta(minutes=1)).astimezone().isoformat(timespec="seconds")
got = E.introspections()
check("a watermark written with an offset still lets newer introspections count", got["status"] == "present"
      and "brace before she answers" in got["text"], got)
check("... and the run's offset cutoff does not hide them either", E.anything_new(), E.status())
open(E.WATERMARK, "w").write((datetime.now(_tz.utc) + timedelta(minutes=1)).astimezone().isoformat(timespec="seconds"))
check("an offset watermark newer than everything still reads as nothing new", not E.anything_new(), E.status())
del os.environ["SELF_MODEL_EVIDENCE_CUTOFF"]

open(E.WATERMARK, "w").write(aware_old)
wal = os.path.join(MEM, "wal-log.json")
json.dump([{"type": "correction", "timestamp": (datetime.now() - timedelta(days=60)).isoformat(), "content": "OLD ONE"},
           {"type": "correction", "timestamp": datetime.now(_tz.utc).isoformat(), "content": "NEW ONE"}], open(wal, "w"))
c = E.corrections()
check("a correction older than an offset watermark is not fed to him again", "OLD ONE" not in c["text"]
      and "NEW ONE" in c["text"], c)
ev = os.path.join(MEM, "self-review-change-events.jsonl")
open(ev, "w").write(json.dumps({"at": (datetime.now(_tz.utc) - timedelta(days=60)).isoformat().replace("+00:00", "Z"),
                                "observation": "OLD CHANGE"}) + "\n" +
                    json.dumps({"at": datetime.now(_tz.utc).isoformat().replace("+00:00", "Z"),
                                "observation": "NEW CHANGE"}) + "\n")
a = E.architectural_changes()
check("a change event stamped in UTC is compared in local time, not by dropping the zone", "OLD CHANGE" not in a["text"]
      and "NEW CHANGE" in a["text"], a)
os.remove(wal); os.remove(ev)

# --- the writer's refusals ----------------------------------------------------------------------------------
src = open(os.path.join(REPO, "scripts", "self-model-update.sh")).read()

check("a reviewer FAIL now holds what he wrote instead of discarding it",
      src.count("self-model-pending/$(date +%Y-%m-%d).md") == 3, src.count("self-model-pending/$(date +%Y-%m-%d).md"))
fail_block = src[src.index("Reviewer flagged content"):src.index("Reviewer flagged content") + 400]
check("... and says so to her, naming where it is kept", "not lost" in src and "self-model-pending" in fail_block)

check("the verdict is the first line only, so a reply that explains itself is not read as a FAIL",
      "VERDICT=$(printf '%s' \"$REVIEWER_RESULT\" | sed -n '1p')" in src
      and 'grep -q "^FAIL"' not in src, src.count('grep -q "^FAIL"'))
check("markdown bold, lower case and a leading bullet all still read as PASS",
      "[*_`#>-]*[[:space:]]*PASS" in src and "-qiE" in src)
check("UNAVAILABLE is still not a pass", "UNAVAILABLE" in src)

check("ordinary English is no longer disqualifying on its own",
      "are ordinary English" in src and "A vivid word is not itself a fault" in src)
check("... but metaphor standing in for a fact still is",
      "standing IN PLACE OF a plain statement" in src and "doing the work a fact should be doing" in src)
check("the reviewer is told it is not judging his voice", "not reviewing his taste or his voice" in src)
# What actually failed him on 4 October: "a water drop, a whirlpool, a frequency, a shadow" read as invented
# embodiment. Simile for how a thought moves is not a claim to have a body.
check("simile for an inner process is not invented embodiment", "SIMILE IS NOT" in src
      and "a whirlpool" in src and "claim to have a body" in src)
check("... while claiming to have physically felt something still is",
      "a claim to have FELT something in a body he does not have" in src
      and "Fail only a sentence asserting he physically felt something" in src)
check("an instrument behind a sensation is still allowed", "Sensation with an instrument behind it is ALLOWED" in src)
check("the verdict is given room to be read", '"max_tokens": 160' in src)

check("every refusal writes one line she can read", src.count("say_why ") >= 5
      and "self-model-refusals.jsonl" in src)
for kind in ("no_base", "nothing_new", "generator_returned_nothing", "reviewer_failed", "reviewer_unreadable"):
    check("... including %s" % kind, 'say_why "%s"' % kind in src)
check("the generator saying nothing is no longer a silent exit",
      "the generator returned nothing" in src and src.count("[ -z \"$CONTENT\" ] && exit 1") == 0)

# --- the Forge's midnight stop --------------------------------------------------------------------------------
import importlib.util
spec = importlib.util.spec_from_file_location("forge_loop", os.path.join(REPO, "scripts", "forge_loop.py"))
FL = importlib.util.module_from_spec(spec); spec.loader.exec_module(FL)
ready = FL.plain_card({"intent": "Build the thing", "state": "ready", "origin": {"source": "owner"}})
spent = FL.plain_card({"intent": "Build the thing", "state": "ready", "origin": {"source": "owner"}}, day_spent=True)
# the daily allowance comes from software_quota now, not a fixed three (Eve, 2026-10-07)
check("a project waiting its turn reads as waiting", "within the daily allowance" in ready["waiting"])
check("a project that used today's allowance says exactly that, and that nothing is wrong",
      "Today's step allowance is used" in spent["waiting"] and "nothing is wrong" in spent["waiting"], spent)
check("neither asks anything of her", not ready["needs_you"] and not spent["needs_you"])
floop = open(os.path.join(REPO, "scripts", "forge_loop.py")).read()
check("the cap writes down why it stopped, once a project a day", "_note_day_limit" in floop
      and "kind='day_limit'" in floop and "today's steps are used" in floop)
check("the page is told how many of the day's steps are left", "'day_steps'" in floop and "'remaining'" in floop)
check("a build reservation blocked by the cap says so instead of a bare refusal", "'day_steps_used'" in floop)

check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""An investigation's answer is judged, kept, told and built on, like a screen's (Gloria, 22 October: "And this will
get him to use more of his tools in conjunction to find novel queries and answers?").

Scratch HOME and workspace; Gemma, Europe PMC and his want path are stubs; sockets are refused."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-findings-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import lab_findings as F, lab_keepers, lab_campaign
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:400],)))
check("its stores are scratch", all(p.startswith(HOME) for p in (F.FINDINGS, F.TOLD, F.NOTEBOOK, lab_keepers.STORE)))

class EPMC:
    def __init__(self): self.urls = []
    def fetch(self, url):
        self.urls.append(url)
        return {"hitCount": 3, "resultList": {"result": [{"title": "Serine recombinases of Planctomycetes", "pubYear": "2021"}]}}, {}
ASKED = []
def gemma(system, prompt):
    ASKED.append(prompt)
    if '"terms"' in prompt: return '{"terms": ["serine recombinase", "AAA+ ATPase", "Planctomycetes"]}'
    return ('{"novelty": "not in these titles", "value": 4, "why": "the pairing is not in the titles", "keep": true, '
            '"tell_gloria": true, "message": "Four of eight recombinases I folded sit beside an AAA+ ATPase."}')
WANTS = []
express = lambda text, **k: WANTS.append((text, k))
inv = {"id": "I-1", "line_id": "L-9", "question": "Do Planctomycetes recombinases pair with an AAA+ ATPase?",
       "prediction": "fewer than a quarter will", "steps": [
           {"id": "S-1", "state": "completed", "tool": "rt_locus_screen"},
           {"id": "S-2", "state": "completed", "tool": "esmfold"},
           {"id": "S-3", "state": "failed", "tool": "boltz2"},
           {"id": "S-4", "state": "completed", "tool": "nvidia_nim.boltz2"}]}
review = {"answers_question": "yes: 4 of 8 loci", "factual_observation": "4 of 8 loci carry an AAA+ ATPase within 3 kb",
          "speculative_reading": "a two-part mobile unit", "next_question": "Does the ATPase bind the recombinase?"}
src = EPMC()
row = F.record(inv, review, gemma, sources=src, now="2026-10-22T12:00:00+00:00", express=express)
check("the finding names the tools that produced it, in order, failures left out",
      row["tools"] == ["rt_locus_screen", "esmfold", "nvidia_nim.boltz2"], row.get("tools"))
check("its literature search uses the words Gemma named for this exact result",
      "serine+recombinase" in src.urls[0].replace("%22", "").replace("%20", "+") and row["literature"]["hits"] == 3, src.urls)
check("and it is appraised against those titles", row["appraisal"]["novelty"] == "not in these titles" and row["appraisal"]["value"] == 4)
check("kept where his kept findings live", row.get("kept") and any(k["id"] == row["kept"] and k["kind"] == "investigation"
                                                                   for k in lab_keepers.load()))
check("told to Gloria as his own want, through the want path",
      row.get("told_gloria") is True and WANTS[0][0].startswith("I want to tell Gloria what my Lab just found: Four of eight")
      and WANTS[0][1]["source"] == "lab-finding", WANTS)
row2 = F.record(dict(inv, id="I-2"), review, gemma, sources=EPMC(), now="2026-10-22T15:00:00+00:00", express=express)
check("one a day, however many findings", row2.get("told_gloria") is False and len(WANTS) == 1)
camp_data = {"told": {}}
check("and screens share that same limit",
      lab_campaign.tell(camp_data, {"appraisal": {"message": "m", "value": 5, "novelty": "x"}, "campaign": "C-1"},
                        now="2026-10-22T18:00:00+00:00", express=express) is False and len(WANTS) == 1)
low = F.appraise(lambda s, p: '{"novelty": "reported", "value": 5, "keep": true, "tell_gloria": true}', "q", "p", "r", [], {})
check("an already-reported result is never sent to her as news", low["tell_gloria"] is False)
thin = F.appraise(lambda s, p: '{"novelty": "unclear", "value": 2, "keep": true, "tell_gloria": true}', "q", "p", "r", [], {})
check("a weak one is neither kept nor told", thin["keep"] is False and thin["tell_gloria"] is False)
plan = F.for_planner()
check("the next investigation is shown the latest findings and their next questions",
      plan and plan[-1]["next_question"] == "Does the ATPase bind the recombinase?" and plan[-1]["value"] == 4, plan)
nb = [json.loads(l) for l in open(F.NOTEBOOK)]
check("each finding is in his notebook", sum(r["kind"] == "investigation_finding" for r in nb) == 2)
src_inv = open(os.path.join(REPO, "scripts", "lab_investigations.py")).read()
check("an answered investigation records its finding, and the planner is shown build_on",
      "lab_findings.record(investigation, reflection" in src_inv and "'build_on': __import__('lab_findings').for_planner(3)" in src_inv)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

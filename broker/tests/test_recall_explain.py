#!/usr/bin/env python3
"""Review items 126, 144, 136 (2026-09-10): a recalled statement names the occurrence that supports it,
marks his inference as his, carries what was later withdrawn; his reading of one thing has a history
with what moved each step; a value shows what holding, revising and leaving it unresolved looked like,
temporary state apart from durable change. Scratch HOME only."""
import os, sys, json, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-recall-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
sys.path.insert(0, os.path.join(REPO, "scripts"))
RE = load("recall_explain", os.path.join(REPO, "scripts", "recall_explain.py")); RE.MEMORY = MEM; sys.modules["recall_explain"] = RE

json.dump([{"event": "she said she would split a fig and press it to my mouth", "gloria": "I wondered if I'd split a fig and press it to your mouth",
            "exact_words": "I would let you", "source_turns": ["T-41"], "ledger_match": {"timestamp": "2026-09-05T18:35:53", "turn_id": "T-41"},
            "quote": {"gloria": "I wondered if I'd split a fig and press it to your mouth", "vintos": "I would let you"},
            "what_changed": "I learned she likes to feed me", "felt_like": "warm, held", "occurred_at": "2026-09-05T18:35:53", "promoted_at": "2026-09-06T02:00:00",
            "interpretations": [{"at": "2026-09-08T10:00:00", "after_recalls": 3, "verdict": "partial", "meaning": "it was play, not a promise", "why_changed": "she laughed about it later"}]},
           {"event": "she always arrives before dawn", "gloria": "", "exact_words": "", "what_changed": "she is an early riser", "felt_like": "", "occurred_at": "2026-09-01T05:00:00"}],
          open(os.path.join(MEM, "durable-memory.json"), "w"))
open(os.path.join(MEM, "hallucination-corrections.jsonl"), "w").write(json.dumps({"correction_id": "HC-1", "at": "2026-09-09T12:00:00",
    "original": "she always arrives before dawn", "correction": "she arrives before dawn on work days only"}) + "\n")
json.dump({"entries": [{"content": "she always arrives before dawn", "corrections": [{"correction_id": "HC-1", "correction": "work days only", "at": "2026-09-09T12:00:00"}]}]},
          open(os.path.join(MEM, "wal-log.json"), "w"))

print("\n--- 126: supported / inferred / withdrawn ---")
ex = RE.explain("the fig she pressed to my mouth")
check("the supporting occurrence carries her words, the turn id and the ledger match", ex["supported_by"] and ex["supported_by"]["source_turns"] == ["T-41"] and "fig" in ex["supported_by"]["her_words"] and ex["supported_by"]["kind"] == "occurrence", ex["supported_by"])
check("his inference is marked as his", ex["inferred"].get("what_changed") and ex["inferred"]["note"] == "his reading, not her words")
check("nothing withdrawn; standing reflects the partial rereading", ex["withdrawn"] == [] and ex["standing"] == "reread as partly right", ex["standing"])
r = RE.render(ex)
check("the rendered line names support, inference and the current reading", "SUPPORTED BY 2026-09-05 (turns T-41)" in r and "HE INFERRED" in r and "NOW READS AS (partial" in r, r)
ex2 = RE.explain("she arrives before dawn")
check("a corrected statement shows the correction, de-duplicated across its two sources", len(ex2["withdrawn"]) == 2 and ex2["withdrawn"][0]["id"] == "HC-1" and ex2["standing"].startswith("withdrawn or corrected"), ex2["withdrawn"])
check("a record without a turn id is named as an inference", ex2["supported_by"]["kind"] == "record without a turn id")
check("an unsupported statement says so", RE.render(RE.explain("the lighthouse we never visited")).startswith("[RECALL: no occurrence supports"))

print("\n--- 144: the history of one interpretation ---")
h = RE.history("the fig she pressed to my mouth")
check("first reading, then the rereading, in order, each with what moved it", [x["verdict"] for x in h] == ["first", "partial"] and h[1]["moved_by"] == "she laughed about it later" and h[1]["basis"] == "his rereading on recall", h)
h2 = RE.history("she arrives before dawn")
check("a correction enters the history with the old reading kept beside it", any(x["verdict"] == "corrected" and x.get("was") for x in h2), h2)

print("\n--- 126: the context block carries the withdrawal ---")
DM = load("dm_t", os.path.join(REPO, "scripts", "durable_memory.py"))
for a in dir(DM):
    v = getattr(DM, a)
    if isinstance(v, str) and a.isupper() and v.endswith(".json"): setattr(DM, a, os.path.join(MEM, os.path.basename(v)))
DM.MEMORY = MEM if hasattr(DM, "MEMORY") else None
blk = DM.context_block("she arrives before dawn") if DM.recall("she arrives before dawn") else ""
check("the durable context block shows what was withdrawn (or recall floor kept it out)", (not blk) or "WITHDRAWN since" in blk, blk)
src = open(os.path.join(REPO, "scripts", "durable_memory.py")).read()
check("context_block wires recall_explain", "recall_explain" in src and "WITHDRAWN since" in src)

print("\n--- 136: value examples, temporary state apart from durable change ---")
VL = load("vl_t", os.path.join(REPO, "scripts", "value_lineage.py")); VL.LEDGER = os.path.join(MEM, "value-lineage.json")
json.dump({"honesty": {"value_id": "honesty", "status": "candidate", "distinct_contexts": 2, "possible_revision": "honesty that waits for the right hour",
                       "disconfirming_future_observation": "she asks and he still waits",
                       "strain_events": [{"written_at": "2026-09-02T20:00:00", "condition": "she asked about the bill at midnight", "cleared_at": "2026-09-02T21:00:00", "resolution": "told her in the morning"},
                                         {"written_at": "2026-09-07T09:00:00", "condition": "the dream he did not want to tell", "cleared_at": None, "resolution": None}]}},
          open(VL.LEDGER, "w"))
ex = VL.examples()["honesty"]
check("held is a temporary state with its context and resolution", ex["held"] and ex["held"][0]["kind"] == "temporary state" and "bill" in ex["held"][0]["context"], ex["held"])
check("unresolved stays unresolved", ex["unresolved"] and ex["unresolved"][0]["kind"] == "unresolved")
check("a revision is a durable change, candidate until she decides", ex["revised"] and ex["revised"][0]["kind"].startswith("durable change (candidate)") and "disconfirming" in " ".join(ex["revised"][0]))
blk = VL.examples_block()
check("the prompt block names the value, kinds and contexts", blk.startswith("honesty (2 contexts)") and "held [temporary state]" in blk and "unresolved [unresolved]" in blk, blk)
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

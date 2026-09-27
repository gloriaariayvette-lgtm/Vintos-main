#!/usr/bin/env python3
"""Four frontier alignments of the Lab a day, one from each model, one shared log (Gloria, 2026-09-28).

Scratch HOME; the paid ledger, admission and the frontier call are stubs, and the suite asserts that
nothing here can reach a provider.
"""
import contextlib, importlib.util, json, os, sys, tempfile, time, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-align-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos.")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod


def no_provider(*a, **k): raise AssertionError("a test must never reach a frontier provider")
sys.modules["model_router"] = types.SimpleNamespace(claude_draft=no_provider, sol_draft=no_provider,
                                                    _grok_result=no_provider, _reserve_provider=no_provider)
reserved, refuse = [], []
@contextlib.contextmanager
def admitted(*a, **k): yield object()
def reserve_paid(organ, provider, model="", units=1, reservation_id=None, cap=None):
    if refuse: return False, "paid budget: 20 of 20"
    reserved.append((organ, provider, model)); return True, "ok"
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted, reserve_paid=reserve_paid,
                                                         release_paid=lambda *a, **k: True)
lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
lab.set_enabled(True)
align = load("chemistry_alignment", os.path.join(REPO, "scripts", "chemistry_alignment.py"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:300]) if detail and not ok else ""))

check("every store is in the scratch workspace and every provider is a stub",
      align.LOG.startswith(HOME) and lab.NOTEBOOK.startswith(HOME)
      and sys.modules["model_router"].claude_draft is no_provider, align.LOG)

lab._ensure()
def gemma_turn(n):
    """One of Gemma's Lab turns, as the notebook records it: question, source, review."""
    lab._append(lab.NOTEBOOK, {"at": lab.now_iso(), "kind": "inquiry", "inquiry": {"question": "Q%d" % n}})
    lab._append(lab.NOTEBOOK, {"at": lab.now_iso(), "kind": "source_read", "records": [
        {"accession": "P%d" % n, "protein_name": "PROTEIN-%d" % n, "organism": "Vibrio", "function": "FUNCTION-%d" % n}]})
    lab._append(os.path.join(lab.ROOT, "source-receipts.jsonl"), {"receipt_id": "MAT-%d" % n, "records": [
        {"pmid": "3100000%d" % n, "title": "T", "abstract": "ABSTRACT-%d" % n}]})
    lab._append(lab.NOTEBOOK, {"at": lab.now_iso(), "kind": "reflection", "entry_id": "E%d" % n,
        "inquiry": {"question": "Q%d" % n}, "factual_observation": "CLAIM-%d" % n, "answers_question": "no",
        "material_receipt_id": "MAT-%d" % n})
    time.sleep(0.01)

prompts = []
def frontier(lens, provider, model, system, user, reservation):
    prompts.append({"lens": lens, "model": model, "user": user, "reservation": reservation})
    return json.dumps({"accuracy": [{"entry_id": "E1", "verdict": "overstated", "why": "the abstract says less"}],
                       "pattern": "PATTERN-" + lens, "guidance": "GUIDANCE-" + lens, "drop": "DROP-" + lens,
                       "next_focus": "FOCUS-" + lens})

gemma_turn(1)
first = align.run(call=frontier)
check("the first alignment of the day is Astra's, on exactly its model",
      first["state"] == "completed" and first["lens"] == "astra" and prompts[0]["model"] == "gpt-6-astra"
      and reserved == [("chemistry-alignment", "openai", "gpt-6-astra")], first)
check("it reads each review with the evidence and the abstract it was written from",
      all(x in prompts[0]["user"] for x in ("CLAIM-1", "FUNCTION-1", "ABSTRACT-1")), prompts[0]["user"][-800:])
check("its accuracy verdicts and guidance are kept in the shared frontier log",
      first["accuracy"][0]["verdict"] == "overstated" and first["guidance"] == "GUIDANCE-astra"
      and lab._jsonl(align.LOG)[-1]["alignment_id"] == first["alignment_id"])

idle = align.run(call=frontier)
check("with no new Lab work since, nothing is spent",
      idle["state"] == "held_nothing_new_since_last_alignment" and len(prompts) == 1 and len(reserved) == 1, idle)

gemma_turn(2)
second = align.run(call=frontier)
check("the next alignment is another model's, and it builds on the shared log",
      second["lens"] == "fable" and prompts[1]["model"] == "claude-fable-5-1"
      and "GUIDANCE-astra" in prompts[1]["user"], second)
check("it reviews only what Gemma did since the last alignment",
      "CLAIM-2" in prompts[1]["user"] and "CLAIM-1" not in prompts[1]["user"].split("GEMMA'S LAB WORK")[1])

for n in (3, 4):
    gemma_turn(n); align.run(call=frontier)
check("each of the four models aligns once a day",
      [p["lens"] for p in prompts] == ["astra", "fable", "grok", "opus"], [p["lens"] for p in prompts])
gemma_turn(5)
check("a fifth call the same day is not made", align.run(call=frontier)["state"] == "held_all_four_done_today"
      and len(prompts) == 4)
check("the next day begins again with the first model",
      align.run(call=frontier, now=time.time() + 86400)["lens"] == "astra")

ctx, receipt = lab.lab_context()
check("Gemma is given the latest guidance, marked as advice",
      "FRONTIER GUIDANCE" in ctx and "GUIDANCE-astra" in ctx and "not evidence" in ctx
      and any(s["name"] == "frontier_guidance" for s in receipt["sources"]), ctx[-500:])
check("but not the frontier log itself",
      "PATTERN-" not in ctx and "the abstract says less" not in ctx)

refuse.append(1); gemma_turn(6)
capped = align.run(call=frontier, now=time.time() + 2 * 86400)
check("a refused paid reservation holds without calling", capped["state"] == "held_paid_cap" and len(prompts) == 5, capped)
refuse.clear()

timer = open(os.path.join(REPO, "broker", "vintos-chemistry-session.timer")).read()
session_src = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
check("the timer fires four times a day", timer.count("OnCalendar=") == 4, timer)
check("each fire aligns; the experiment runs only once a day",
      "if not experiment_done_today():" in session_src and "chemistry_alignment.run()" in session_src)
check("the deploy installs the alignment module",
      "chemistry_alignment.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

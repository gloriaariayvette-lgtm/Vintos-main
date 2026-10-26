#!/usr/bin/env python3
"""An atlas of useful negative results (Codex's proposal 12): retained results that did not support a prediction,
classified as refuted, inconclusive or failed execution, each scoped to the conditions it holds under; and a later
plan that builds on one exact negative by varying one of those conditions, never by rerunning it or writing the
subject off.

Scratch HOME, scratch workspace, scratch Lab: every store this suite touches is under a temporary directory and is
asserted to be. Every output is an invented fixture; no model is asked, sockets are closed off, `requests` and the
plugin gateway raise, and the paid ledger refuses to be touched.
"""
import contextlib, io, json, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="vintos-negative-atlas-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")


def _no_network(*a, **k):
    raise AssertionError("a test must never reach the network")


def _no_paid(*a, **k):
    raise AssertionError("the atlas never reserves or spends a paid call")


def _no_socket(self, *a, **k):
    raise AssertionError("a test must never open a socket")


socket.socket.connect = _no_socket
sys.modules["requests"] = types.SimpleNamespace(get=_no_network, post=_no_network)
sys.modules["plugin_gateway"] = types.SimpleNamespace(run_skill=_no_network, call=_no_network)
sys.modules["compute_admission"] = types.SimpleNamespace(reserve_paid=_no_paid, release_paid=_no_paid,
                                                          admit=_no_paid)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import lab_measurement as M
import lab_negative_atlas as A

R = []


def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:600]) if detail and not ok else ""))


NOW = "2026-10-26T12:00:00+00:00"
LAB = str(A.lab_root())

# ---------------------------------------------------------------- isolation
check("the atlas, measurement, panel and verdict stores are all in the scratch workspace",
      all(str(p).startswith(HOME) for p in (A.reuses_path(), M.contracts_path(), M.results_path(),
                                            A.lab_root() / A.PANEL_RESULTS_NAME)), A.reuses_path())
check("the atlas reads and writes the measurement's own Lab directory", LAB == M._root(), (LAB, M._root()))
check("nothing in this suite can send, fetch or spend",
      sys.modules["requests"].get is _no_network and sys.modules["compute_admission"].reserve_paid is _no_paid)
check("an empty Lab is an empty atlas, not an error", A.entries() == [] and A.counts() == {
    "refuted": 0, "inconclusive": 0, "failed_execution": 0})


# ---------------------------------------------------------------- retained results, made the way the Lab makes them
def output(sid, payload, tool="instrument:rt_locus_screen", state="completed", **extra):
    step = {"id": sid, "route": "instrument", "tool": tool, "state": state, **extra}
    if state == "completed":
        rel = "investigation-outputs/%s.json" % sid
        path = os.path.join(M._root(), rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(payload, open(path, "w"))
        step.update(output_file=rel, output_sha256=M._sha(payload))
    return step


def counts(hits, total):
    return {"result": {"hits": hits, "total": total}}


def role(nth, meaning="phage loci with an array beside the RT"):
    return {"select": {"tool": "rt_locus_screen", "nth": nth}, "hits": ["result", "hits"],
            "total": ["result", "total"], "meaning": meaning}


def proportion(hypothesis, **over):
    c = {"mode": "confirmatory", "hypothesis": hypothesis, "unit": "locus",
         "variable": "share of loci with a CRISPR array within 12 kb", "units": "proportion",
         "evaluator": "proportion_vs_control", "predicts": "case_higher", "min_effect": 0.2,
         "supports": "case share exceeds control by 0.2", "opposes": "the interval rules out a 0.2 excess",
         "case": role(1), "control": role(2, "matched background loci")}
    c.update(over)
    return c


def retain(inv_id, contract, steps, final=False):
    row = M.freeze(contract, by="test", investigation_id=inv_id, now=NOW)
    res = M.evaluate(row, steps, final=final, now=NOW)
    M._append(M.results_path(), res)
    return row, res


ARRAY = "array-adjacent reverse transcriptases are commoner in phage loci than in background"
_, refuted = retain("INV-refuted", proportion(ARRAY),
                    [output("S-r1", counts(10, 40)), output("S-r2", counts(10, 40))])
_, inconclusive = retain("INV-wide", proportion("array-adjacent reverse transcriptases cluster in prophage loci",
                                                min_effect=0),
                         [output("S-i1", counts(4, 10)), output("S-i2", counts(3, 10))])
_, failed = retain("INV-broken", proportion("retron reverse transcriptases sit beside toxin genes"),
                   [output("S-f1", None, state="failed", error="TimeoutError: the screen did not answer")], final=True)
_, supported = retain("INV-yes", proportion("abortive infection RTs are commoner in phage loci"),
                      [output("S-y1", counts(18, 20)), output("S-y2", counts(4, 20))])
_, unmeasurable = retain("INV-nofield", proportion("group II intron RTs are commoner near arrays"),
                         [output("S-u1", counts(9, 10)), output("S-u2", {"result": {"total": 10}})])
check("the fixtures came out as the Lab would record them",
      (refuted["measurement_state"], inconclusive["measurement_state"], failed["measurement_state"],
       failed["execution_state"], supported["measurement_state"], unmeasurable["measurement_state"],
       unmeasurable["execution_state"]) == ("refuted", "inconclusive", "not_evaluated", "failed", "supported",
                                            "not_evaluated", "completed"),
      [refuted, inconclusive, failed])

# ---------------------------------------------------------------- the three classes
by_inv = {e["investigation"]: e for e in A.entries()}
check("a clean contradiction is refuted", by_inv["INV-refuted"]["class"] == "refuted", by_inv.get("INV-refuted"))
check("a measurement that could not decide is inconclusive", by_inv["INV-wide"]["class"] == "inconclusive",
      by_inv.get("INV-wide"))
check("a tool that did not answer is a failed execution, from the tool",
      by_inv["INV-broken"]["class"] == "failed_execution" and by_inv["INV-broken"]["failure"] == "tool",
      by_inv.get("INV-broken"))
check("an output that could not be measured is a failed execution too, from the measurement, never a negative",
      by_inv["INV-nofield"]["class"] == "failed_execution" and by_inv["INV-nofield"]["failure"] == "measurement",
      by_inv.get("INV-nofield"))
check("a supported prediction is not in the atlas", "INV-yes" not in by_inv, sorted(by_inv))
check("counts by class", A.counts() == {"refuted": 1, "inconclusive": 1, "failed_execution": 2}, A.counts())
check("the classifier on its own: refuted, inconclusive, failed, support",
      [A.classify("refuted", "completed"), A.classify("inconclusive", "completed"),
       A.classify("not_evaluated", "failed"), A.classify("refuted", "failed"), A.classify("supported", "completed")]
      == ["refuted", "inconclusive", "failed_execution", "failed_execution", None])

neg = by_inv["INV-refuted"]
check("the same result is always the same entry", [e["id"] for e in A.entries()] == [e["id"] for e in A.entries()]
      and neg["id"].startswith("NEG-") and len(neg["id"]) == 14, neg["id"])
check("an entry is scoped: claim, evaluator, variable, units, comparator, tool and output digests",
      neg["claim"] == ARRAY and neg["conditions"]["evaluator"] == "proportion_vs_control"
      and neg["conditions"]["variable"].startswith("share of loci") and neg["conditions"]["units"] == "proportion"
      and "matched background" in neg["conditions"]["comparator"] and neg["conditions"]["tool"] == ["rt_locus_screen", "rt_locus_screen"]
      and len(neg["conditions"]["outputs"]) == 2 and neg["conditions"]["min_effect"] == 0.2, neg["conditions"])
check("and it keeps why it failed and the estimate it failed on",
      "rules out" in neg["why"] and neg["estimate"]["difference"] == 0.0, (neg["why"], neg.get("estimate")))
lim = " ".join(neg["limits"])
check("a refuted entry says what it holds for and that it does not close the subject",
      lim.startswith("holds only for share of loci") and "not biological proof" in lim
      and "subject is not closed" in lim, neg["limits"])
check("an inconclusive entry says it is undecided, not negative",
      "undecided, not negative" in " ".join(by_inv["INV-wide"]["limits"])
      and "no evidence against" in " ".join(by_inv["INV-wide"]["limits"]), by_inv["INV-wide"]["limits"])
check("a failed execution says it says nothing about the claim",
      "says nothing about it" in " ".join(by_inv["INV-broken"]["limits"]), by_inv["INV-broken"]["limits"])

# ---------------------------------------------------------------- search
found = A.search("reverse transcriptases phage")
check("search finds entries by the words of their claim", {e["investigation"] for e in found} >= {"INV-refuted",
                                                                                                 "INV-wide"}, found)
check("search for unrelated words finds nothing", A.search("ribosome kinetics yeast") == [])
check("search can be limited to what can be built on",
      all(e["class"] in A.BUILDABLE for e in A.search("reverse transcriptases", A.BUILDABLE)))

# ---------------------------------------------------------------- what a later planner is shown
later = {"id": "INV-later", "state": "open", "steps": [],
         "question": "Are array-adjacent reverse transcriptases commoner in phage loci when screened by a second tool?"}
view = A.for_planner(later)
ids = [e["id"] for e in (view or {}).get("entries") or []]
check("a later, related investigation is shown the refuted and the inconclusive negative",
      neg["id"] in ids and by_inv["INV-wide"]["id"] in ids and len(ids) <= A.PLANNER_ENTRIES, view)
check("never a failed execution", by_inv["INV-broken"]["id"] not in ids and by_inv["INV-nofield"]["id"] not in ids)
shown = view["entries"][ids.index(neg["id"])]
check("each shown with what it holds for and what can be varied",
      shown["holds_only_for"].startswith("share of loci") and "tool" in shown["can_vary"]
      and "threshold" not in shown["can_vary"] and "min_effect" in shown["can_vary"], shown)
check("and told it does not close the subject, and how to build on one",
      "none closes the subject" in view["how"] and "builds_on_negative" in view["how"], view.get("how"))
check("an unrelated investigation is shown nothing",
      A.for_planner({"id": "INV-x", "question": "how fast does yeast ribosome assembly proceed"}) is None)
check("an investigation is not shown its own result as an atlas entry",
      all(e["id"] != neg["id"] for e in (A.for_planner(dict(later, id="INV-refuted")) or {}).get("entries", [])))
check("the planner's brief stays short", len(json.dumps(view)) < 1600, len(json.dumps(view)))

pv = M.planner_view(later, now=NOW)
check("the ordinary measurement view carries the atlas", (pv or {}).get("negative_atlas", {}).get("entries"), pv)

# ---------------------------------------------------------------- building on one exact negative
before_results = len(M.results())
ok = A.reuse({"id": neg["id"], "varies": "tool", "to": "rt_locus_screen_v2",
              "why": "the second screen calls arrays from repeats, not from annotations"}, later, now=NOW)
check("a later plan builds on the negative by varying a condition it was measured under",
      ok["state"] == "reused" and ok["varied"] == {"condition": "tool", "from": ["rt_locus_screen", "rt_locus_screen"],
                                                   "to": "rt_locus_screen_v2"}, ok)
check("the reuse carries the negative's limits and its scope",
      ok["limits"] == neg["limits"] and "holds only under the conditions" in ok["scope"]
      and ok["negative_class"] == "refuted", ok)
check("one investigation builds on one negative once",
      A.reuse({"id": neg["id"], "varies": "tool", "to": "rt_locus_screen_v2", "why": "again, the same reason"},
              later, now=NOW) == ok and len([r for r in A.reuses() if r["state"] == "reused"]) == 1)
check("building on a negative measures nothing and writes no result", len(M.results()) == before_results)

nxt = {"id": "INV-next", "question": "array-adjacent RTs in phage loci again"}
for name, raw, words in (
        ("an unchanged condition is a rerun", {"id": neg["id"], "varies": "min_effect", "to": 0.2,
                                               "why": "repeat it to be sure of it"}, "rerun"),
        ("an unchanged single tool is a rerun", {"id": by_inv["INV-wide"]["id"], "varies": "unit", "to": "Locus",
                                                 "why": "count by locus as before"}, "rerun"),
        ("a condition it was not measured under", {"id": neg["id"], "varies": "threshold", "to": 3,
                                                   "why": "a stricter threshold could separate them"}, "vary one of"),
        ("a failed execution cannot be built on", {"id": by_inv["INV-broken"]["id"], "varies": "tool",
                                                   "to": "another_screen", "why": "the screen timed out last time"},
         "not a negative result"),
        ("a reason that writes the subject off", {"id": neg["id"], "varies": "tool", "to": "other_screen",
                                                  "why": "this shows the association is impossible, so drop it"},
         "does not make the subject impossible"),
        ("a dead end is not a reuse", {"id": neg["id"], "varies": "cohort", "to": "x",
                                       "why": "it is a dead end anyway"}, "vary one of"),
        ("no reason given", {"id": neg["id"], "varies": "tool", "to": "other_screen", "why": "x"}, "say why"),
        ("no new value", {"id": neg["id"], "varies": "tool", "why": "the second screen is better"}, "say what"),
        ("an unknown id", {"id": "NEG-0000000000", "varies": "tool", "to": "y", "why": "a long enough reason"},
         "no atlas entry")):
    got = A.reuse(raw, nxt, now=NOW)
    check("refused: " + name, got["state"] == "refused" and words in got["refused"], got)
own = A.reuse({"id": neg["id"], "varies": "tool", "to": "other", "why": "a different screen could find more"},
              {"id": "INV-refuted"}, now=NOW)
check("refused: the investigation that produced it builds on its own result", own["state"] == "refused", own)
n = len(A.reuses())
A.reuse({"id": neg["id"], "varies": "min_effect", "to": 0.2, "why": "repeat it to be sure of it"}, nxt, now=NOW)
check("the same refusal on the next planning step is kept once", len(A.reuses()) == n, len(A.reuses()))

for i in range(A.REUSES_PER_DAY + 1):
    last = A.reuse({"id": neg["id"], "varies": "min_effect", "to": 0.05 + i / 100,
                    "why": "a smaller effect may be what is really there"}, {"id": "INV-cap%d" % i}, now=NOW)
check("at most %d reuses a day" % A.REUSES_PER_DAY, last["state"] == "refused" and "today" in last["refused"], last)

# ---------------------------------------------------------------- through the ordinary planner return
via = {"id": "INV-via", "question": "phage loci arrays", "steps": []}
M.from_planner(via, {"route": "instrument", "builds_on_negative": {
    "id": by_inv["INV-wide"]["id"], "varies": "unit", "to": "phage genome",
    "why": "one per genome removes the related loci that widened the interval"}}, now="2026-10-27T09:00:00+00:00")
got = [r for r in A.reuses() if r.get("investigation") == "INV-via"]
check("a builds_on_negative in the planner's JSON is recorded through the measurement module's own hook",
      len(got) == 1 and got[0]["state"] == "reused" and got[0]["negative_class"] == "inconclusive", got)
check("a planner return without one records nothing and freezes nothing",
      M.from_planner({"id": "INV-none"}, {"route": "source"}) is None
      and not [r for r in A.reuses() if r.get("investigation") == "INV-none"])
check("a malformed builds_on_negative never raises", A.from_planner(via, {"builds_on_negative": "NEG-x"}) is None
      and A.from_planner(None, None) is None)

# ---------------------------------------------------------------- a rerun of a refuted contract is named
again = {"id": "INV-again", "state": "open", "steps": [], "question": ARRAY}
M.freeze(proportion(ARRAY), by="test", investigation_id="INV-again", now=NOW)
pv = M.planner_view(again, now=NOW)
warn = ((pv or {}).get("negative_atlas") or {}).get("rerun_warning") or ""
check("a contract that repeats a refuted one exactly is named as a rerun", neg["id"] in warn and "vary" in warn, pv)
changed = {"id": "INV-changed", "state": "open", "steps": [], "question": ARRAY}
M.freeze(proportion(ARRAY, min_effect=0.05), by="test", investigation_id="INV-changed", now=NOW)
pv = M.planner_view(changed, now=NOW)
check("one with a changed condition is not", "rerun_warning" not in ((pv or {}).get("negative_atlas") or {}), pv)

# ---------------------------------------------------------------- a superseded revision
row1 = M.latest(refuted["contract_id"])
M.freeze(proportion(ARRAY, min_effect=0.1), by="test", investigation_id="INV-refuted", now=NOW)
e = [x for x in A.entries() if x["investigation"] == "INV-refuted"][0]
check("a negative whose contract was revised says so, and is no longer offered to the planner",
      e["superseded_by_revision"] == 2
      and e["id"] not in [x["id"] for x in (A.for_planner(later) or {}).get("entries", [])], e)

# ---------------------------------------------------------------- family panels and disagreements, by hand
A.lab_root().mkdir(parents=True, exist_ok=True)
with open(A.lab_root() / A.PANELS_NAME, "a") as f:
    f.write(json.dumps({"panel_id": "FAM-0123456789", "comparator": "OUT1", "positions": [42, 77]}) + "\n")
with open(A.lab_root() / A.PANEL_RESULTS_NAME, "a") as f:
    f.write(json.dumps({"panel_id": "FAM-0123456789", "measured_at": NOW, "anchor": "RT1",
                        "question": "does the helix at the RT thumb persist across the family and not in OUT1",
                        "feature": [{"reading": "secondary_structure", "equals": "H"}],
                        "measurement_state": "refuted",
                        "positions": [{"position": 42, "state": "not_family_specific"},
                                      {"position": 77, "state": "persists"}],
                        "members": [{"name": "RT1", "role": "family", "sha256": "a" * 64},
                                    {"name": "OUT1", "role": "comparator", "sha256": "b" * 64}],
                        "warnings": ["this panel mixes predicted and observed structures"]}) + "\n")
    f.write(json.dumps({"panel_id": "FAM-9999999999", "measured_at": NOW, "measurement_state": "supported"}) + "\n")
with open(A.lab_root() / "disagreement-verdicts.jsonl", "a") as f:
    f.write(json.dumps({"kind": "disagreement_verdict", "disagreement_id": "DIS-0123456789", "at": NOW,
                        "variable": "mean pLDDT of the model", "units": "pLDDT", "verdict": "supports_neither",
                        "predictions": {"astra": "above 80", "grok": "below 50"}, "contract_id": "MC-x",
                        "revision": 1, "execution_state": "completed",
                        "bound": [{"tool": "instrument:structure.confidence", "output_sha256": "c" * 64}],
                        "why": "65 ± 2 lies outside both predictions",
                        "measured": {"value": 65, "uncertainty": 2}}) + "\n")
panel = [x for x in A.entries() if x["source"] == "family_panel"]
check("a refuted family panel is an entry, scoped to its members, comparator and positions",
      len(panel) == 1 and panel[0]["class"] == "refuted" and panel[0]["conditions"]["positions"] == [42, 77]
      and panel[0]["conditions"]["comparator"] == "OUT1"
      and any("mixes predicted" in x for x in panel[0]["limits"]), panel)
dis = [x for x in A.entries() if x["source"] == "disagreement"]
check("a measurement that contradicted both readers is a refuted entry, saying nothing of a third prediction",
      len(dis) == 1 and dis[0]["class"] == "refuted" and any("third prediction" in x for x in dis[0]["limits"]), dis)

# ---------------------------------------------------------------- the CLI
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = A._cli(["show"])
out = buf.getvalue()
check("show prints the counts and every entry with its limits",
      rc == 0 and '"refuted": 3' in out and "limit: holds only for" in out and neg["id"] in out
      and "reused by INV-later (reused)" in out, out[:800])
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = A._cli(["search", "helix", "thumb"])
check("search from the command line", rc == 0 and "FAM-0123456789" in buf.getvalue(), buf.getvalue()[:300])

# ---------------------------------------------------------------- the only store it writes
written = sorted(os.listdir(A.lab_root()))
check("the atlas's only store is its reuses", A.REUSES_NAME in written and not any(
    "atlas" in w and w != ".negative-atlas.lock" for w in written), written)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

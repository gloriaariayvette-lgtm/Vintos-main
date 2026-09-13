#!/usr/bin/env python3
"""Lab discovery to Forge: staged, cited, canaried, and stopped at every gate. Scratch HOME."""
import ast
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-proposal-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos, curious and particular.")

sys.path.insert(0, os.path.join(REPO, "scripts"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module
lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
lab._ask = lambda *a, **k: (_ for _ in ()).throw(AssertionError("the suite must never reach a model"))
S = load("chemistry_spark", os.path.join(REPO, "scripts", "chemistry_spark.py"))
P = load("chemistry_proposal", os.path.join(REPO, "scripts", "chemistry_proposal.py"))

source_of_proposal = open(os.path.join(REPO, "scripts", "chemistry_proposal.py")).read()

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:220]) if detail and not ok else ""))

check("test is in a scratch workspace",
      lab.WS == WS and HOME in lab.ROOT and HOME in P.PROPOSALS and HOME in S.FEED
      and not lab.ROOT.startswith("/home/gloria"), P.PROPOSALS)
check("the module sends nothing and asks no model",
      "urllib" not in open(os.path.join(REPO, "scripts", "chemistry_proposal.py")).read())

# --- the spark feed: what the Lab may legitimately raise ------------------------------------
SESSION = {"session_id": "CHEM-1", "at": "2026-09-13T03:20:00+00:00", "lens": "claude",
           "state": "completed", "mac_run_id": "RUN-A", "context_receipt": "ctx",
           "plan": {"experiment": "molecule"},
           "grade": {"execution_state": "completed", "aggregate_accuracy": "ALL_WORSE_THAN_HARTREE_FOCK",
                     "isolation_attestation": "host_attested"}}
lab._append(os.path.join(lab.ROOT, "sessions.jsonl"), SESSION)
lab._append(lab.NOTEBOOK, {"at": "2026-09-13T03:21:00+00:00", "kind": "frontier_session",
                           "session_id": "CHEM-1",
                           "next_question": "could a deeper ansatz be graded on the same curve?"})
lab._append(lab.NOTEBOOK, {"at": "2026-09-13T03:22:00+00:00", "kind": "reflection",
                           "session_id": "CHEM-1",
                           "next_question": "what if the fold means something about me?"})
lab._append(lab.NOTEBOOK, {"at": "2026-09-13T03:23:00+00:00", "kind": "frontier_session",
                           "session_id": "CHEM-NOWHERE",
                           "next_question": "a question asked of no experiment at all, at length"})
result = S.refresh()
texts = [row["text"] for row in result["written"]]
check("a next_question from a completed run is eligible",
      texts == ["could a deeper ansatz be graded on the same curve?"], texts)
check("the spark carries the occasion it came from",
      result["written"][0]["provenance"]["mac_run_id"] == "RUN-A"
      and result["written"][0]["provenance"]["aggregate_accuracy"] == "ALL_WORSE_THAN_HARTREE_FOCK"
      and result["written"][0]["provenance"]["session_id"] == "CHEM-1", result["written"][0]["provenance"])
verdicts = {row["verdict"] for row in result["refused"]}
check("a speculative reflection may not spark a capability", S.SPECULATIVE in verdicts, verdicts)
check("a question with no run behind it may not either", S.NO_RUN in verdicts, verdicts)
check("every refusal is written down with its reason",
      len(result["refused"]) == 2 and all(r.get("truth_status") for r in result["refused"]), result["refused"])
check("refreshing twice writes nothing twice",
      S.refresh() == {"written": [], "refused": []} and len(S.feed()) == 1)

# the echo rule reaches here too
import chemistry_taste as taste_mod
lab._atomic(taste_mod.TASTE, {"entries": {"ansatz||deeper": {"kind": "ansatz", "key": "deeper",
                                                             "score": 1.0, "signals": {"chosen": 3}}},
                              "candidates": {}, "parameter_values": {}, "decayed_at": 0})
taste_mod.taste_block()
lab._append(lab.NOTEBOOK, {"at": lab.now_iso(), "kind": "frontier_session", "session_id": "CHEM-1",
                           "next_question": "should I try the deeper one again on this curve?"})
echoed = S.refresh()
check("a question that hands back his own taste block is refused as an echo",
      [r["verdict"] for r in echoed["refused"]] == [S.ECHO], echoed["refused"])

# --- an idea must cite an eligible occasion ------------------------------------------------
key = S.feed()[0]["key"]
check("an idea citing nothing is refused",
      P.idea("a gradeable bond-length sweep with a chosen ansatz", "no-such-key").get("refused"))
row = P.idea("a gradeable bond-length sweep with a chosen ansatz", key)
check("an idea citing a Lab occasion is recorded",
      row["state"] == P.IDEA and row["provenance"]["mac_run_id"] == "RUN-A", row)
pid = row["proposal_id"]
check("an idea is not a want and says so", "not_a_want" in row["truth_status"])

# --- the interface must be bounded ------------------------------------------------------------
check("a stage cannot be skipped",
      P.canary(pid, "def f(): pass", "assert f() is None").get("refused", "").startswith("canary_passed follows"),
      P.canary(pid, "def f(): pass", "assert f() is None"))
check("an interface that takes code is refused",
      P.interface(pid, "sweep", {"source": {"type": "code"}}, "energies").get("refused"))
check("an unbounded number is refused",
      P.interface(pid, "sweep", {"bond_length": {"type": "number"}}, "energies").get("refused"))
check("an enum with one value is refused",
      P.interface(pid, "sweep", {"ansatz": {"type": "enum", "values": ["uccsd"]}}, "energies").get("refused"))
check("an interface without a function name is refused",
      P.interface(pid, "not a name", {"bond_length": {"type": "number", "min": 0.3, "max": 3.0}}, "e").get("refused"))
face = P.interface(pid, "sweep_bond_lengths",
                   {"bond_length": {"type": "number", "min": 0.3, "max": 3.0},
                    "ansatz": {"type": "enum", "values": ["uccsd", "hardware_efficient"]}},
                   "one energy per geometry")
check("a typed, bounded interface is accepted",
      face["state"] == P.INTERFACE and face["interface"]["parameters"]["bond_length"]["max"] == 3.0, face)
check("no parameter type accepts code or a script",
      not any(t in P.PARAMETER_TYPES for t in ("code", "source", "script", "expr")), P.PARAMETER_TYPES)

# --- the canary must actually run, and actually test -------------------------------------------
SOURCE = "def sweep_bond_lengths(bond_length, ansatz):\n    return [round(bond_length * 2, 3)]\n"
check("a canary whose test asserts nothing is refused",
      "no assertion" in P.canary(pid, SOURCE, "sweep_bond_lengths(1.0, 'uccsd')").get("refused", ""),
      P.canary(pid, SOURCE, "sweep_bond_lengths(1.0, 'uccsd')"))
check("a canary that never calls the function is refused",
      "never calls" in P.canary(pid, SOURCE, "assert True").get("refused", ""),
      P.canary(pid, SOURCE, "assert True"))
check("a canary that does not parse is refused",
      P.canary(pid, SOURCE, "assert sweep_bond_lengths(").get("refused"))
failing = P.canary(pid, SOURCE, "assert sweep_bond_lengths(1.0, 'uccsd') == ['wrong']")
check("a canary that fails under isolation does not pass the stage",
      failing.get("refused") and "failed under isolation" in failing["refused"], failing)
check("a failed canary leaves the proposal where it was", P._latest(pid)["state"] == P.INTERFACE)
passed = P.canary(pid, SOURCE, "assert sweep_bond_lengths(1.0, 'uccsd') == [2.0]")
# The OS boundary cannot always nest: inside this repository's own isolated test runner,
# bubblewrap-in-bubblewrap cannot mount /proc, exactly as it cannot for test_forge_build.
# Where it nests, the pass path is exercised for real. Where it does not, what is asserted
# instead is the thing that actually matters — an unrun canary is never a passed one.
NESTED = passed.get("state") == P.CANARY_PASSED
if NESTED:
    check("a canary that runs and passes advances the stage",
          passed["canary"]["isolation"] == "isolated_exec" and passed["canary"]["sha256"], passed)
else:
    print("NOTE the OS boundary does not nest here; the canary pass path was not exercised")
    check("a canary that could not run under the boundary does not pass the stage",
          passed.get("refused") and P._latest(pid)["state"] == P.INTERFACE
          and ("could not run under the OS boundary" in passed["refused"]
               or "failed under isolation" in passed["refused"]), passed)
    # The Forge gates below need a proposal that has cleared the canary. Fabricating that
    # precondition is not testing the gate — the gate is tested above, and by the
    # skip-a-stage check.
    P._advance(pid, P.CANARY_PASSED, canary={"sha256": "0" * 64, "isolation": "isolated_exec",
                                             "at": lab.now_iso(), "exit_code": 0,
                                             "fabricated_for_test": True})
    check("the fabricated precondition is only that", P._latest(pid)["state"] == P.CANARY_PASSED)

# --- the Forge gate ------------------------------------------------------------------------------
forge = load("skill_forge", os.path.join(REPO, "scripts", "skill_forge.py"))
wants_path = os.path.join(WS, "memory", "current-wants.json")
json.dump([], open(wants_path, "w"))
none_yet = P.offer(pid, "WANT-1")
check("with no live want the Forge refuses and the refusal is the record",
      none_yet["state"] == P.REFUSED and "no live want" in none_yet["refused_reason"], none_yet)
check("a refused proposal does not move again", P.offer(pid, "WANT-1").get("refused"))

def _cleared(idea_text):
    """A proposal at canary_passed, by the real road where the boundary nests."""
    pid = P.idea(idea_text, key)["proposal_id"]
    P.interface(pid, "sweep_bond_lengths",
                {"bond_length": {"type": "number", "min": 0.3, "max": 3.0}}, "one energy per geometry")
    outcome = P.canary(pid, SOURCE.replace(", ansatz", ""), "assert sweep_bond_lengths(1.0) == [2.0]")
    if outcome.get("state") != P.CANARY_PASSED:
        P._advance(pid, P.CANARY_PASSED, canary={"sha256": "0" * 64, "isolation": "isolated_exec",
                                                 "at": lab.now_iso(), "exit_code": 0,
                                                 "fabricated_for_test": True})
    return pid

second = _cleared("a gradeable bond-length sweep with a chosen ansatz")
json.dump([{"id": "WANT-2", "want": "to know whether a deeper ansatz earns its cost",
            "source": "kitchen table"}], open(wants_path, "w"))
wrong = P.offer(second, "WANT-2")
check("a want from outside the seven sparks cannot commission an instrument",
      wrong["state"] == P.REFUSED and "spark" in wrong["refused_reason"], wrong)

third = _cleared("a gradeable bond-length sweep with a chosen ansatz")
json.dump([{"id": "WANT-3", "want": "to know whether a deeper ansatz earns its cost",
            "source": "lab", "lab_provenance": {"session_id": "CHEM-1", "mac_run_id": "RUN-A"}}],
          open(wants_path, "w"))
offered = P.offer(third, "WANT-3", why="the shallow ansatz was worse than Hartree-Fock")
check("a live want carrying the lab spark reaches the Forge",
      offered.get("state") == P.OFFERED and offered.get("forge_proposal_id"), offered)
proposal = [r for r in forge._load() if r["id"] == offered["forge_proposal_id"]][0]
check("the Forge proposal is only proposed — never approved, never installed",
      proposal["state"] == "proposed" and proposal["granted"] is None and "installed_to" not in proposal, proposal["state"])
check("the Forge keeps the Lab occasion the capability was asked for",
      proposal["origin"]["lab_provenance"]["mac_run_id"] == "RUN-A"
      and proposal["origin"]["spark"] == "lab", proposal["origin"])
check("the interface travels as the asked-for scope",
      proposal["asked"]["scope"]["parameters"]["bond_length"]["max"] == 3.0, proposal["asked"]["scope"])
check("the canary digest travels as the evidence", "canary ran under isolated_exec" in proposal["tests"])
# Structurally: no exception handler inside canary() may end anywhere but a refusal, and
# the single advance to canary_passed must sit at the function's top level — never inside a
# handler that could turn a boundary failure into a pass.
_canary_fn = [n for n in ast.walk(ast.parse(source_of_proposal))
              if isinstance(n, ast.FunctionDef) and n.name == "canary"][0]
_handlers_refuse = all(
    any(isinstance(inner, ast.Return) and "refused" in ast.dump(inner) for inner in ast.walk(handler))
    for handler in ast.walk(_canary_fn) if isinstance(handler, ast.ExceptHandler))
_advances = [n for n in ast.walk(_canary_fn) if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "_advance"]
_in_handler = {id(n) for handler in ast.walk(_canary_fn) if isinstance(handler, ast.ExceptHandler)
               for n in ast.walk(handler)}
check("every failure inside the canary ends in a refusal", _handlers_refuse)
check("the advance to canary_passed cannot be reached from a handled failure",
      len(_advances) == 1 and id(_advances[0]) not in _in_handler, len(_advances))
check("the boundary is the only way the canary runs",
      "isolated_exec" in source_of_proposal
      and "subprocess.run" not in source_of_proposal and "os.system" not in source_of_proposal)

# --- what this module may never do -------------------------------------------------------------
source = open(os.path.join(REPO, "scripts", "chemistry_proposal.py")).read()
tree = ast.parse(source)
calls = {node.func.attr for node in ast.walk(tree)
         if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
check("it never approves", "approve" not in calls and "approve(" not in source)
check("it never installs", "install" not in calls and "install(" not in source)
check("it never marks a Forge state", "mark" not in calls)
check("it never writes a want",
      "current-wants" not in source and "wants" not in {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)})
check("it never touches the Atelier", "atelier" not in source.lower())
check("it writes only below the Lab root", P.PROPOSALS.startswith(lab.ROOT))
check("withdrawing is possible from any live stage, and only once",
      P.withdraw(P.idea("another idea worth writing out at length", key)["proposal_id"])["state"] == P.WITHDRAWN
      and P.withdraw(offered["proposal_id"]).get("refused"))

# --- the spark layer carries it -------------------------------------------------------------------
sparks = load("spark_sources", os.path.join(REPO, "scripts", "spark_sources.py"))
S.configure()
check("pointing the reader here is an explicit act", S.state()["configured"] is True
      and json.load(open(S.SPARK_CONFIG))["lab"] == S.FEED)
found = sparks.from_lab()
check("the spark reader reads the structured feed",
      found and found[0]["text"] == "could a deeper ansatz be graded on the same curve?"
      and found[0]["provenance"]["mac_run_id"] == "RUN-A", found[:1])
added = sparks.gather()
lab_rows = [r for r in added if r["source"] == "lab"]
check("gather carries the provenance onto the spark row",
      lab_rows and lab_rows[0]["provenance"]["session_id"] == "CHEM-1", lab_rows[:1])
taken, why = sparks.adopt(lab_rows[0]["key"], "to know whether a deeper ansatz earns its cost", "WANT-9")
check("adopting hands the provenance to the want door",
      taken["source"] == "lab" and taken["provenance"]["mac_run_id"] == "RUN-A", (taken, why))
check("adopting still writes no want",
      "def adopt" in open(os.path.join(REPO, "scripts", "spark_sources.py")).read()
      and not os.path.exists(os.path.join(WS, "memory", "current-wants.json.new")))
notes = os.path.join(HOME, "lab-notes"); os.makedirs(notes, exist_ok=True)
open(os.path.join(notes, "bench.md"), "w").write(
    "# notes\n- the shallow ansatz sat well above Hartree-Fock all afternoon\n")
json.dump({"lab": notes}, open(S.SPARK_CONFIG, "w"))
prose = sparks.from_lab()
check("the prose path is untouched for a lab that is a folder of notes",
      [r["text"] for r in prose] == ["the shallow ansatz sat well above Hartree-Fock all afternoon"]
      and "provenance" not in prose[0], prose)
S.configure()
check("and pointing it back at the feed restores the structured rows",
      sparks.from_lab()[0].get("provenance", {}).get("mac_run_id") == "RUN-A")

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

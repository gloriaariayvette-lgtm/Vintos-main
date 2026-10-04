#!/usr/bin/env python3
"""A call his Lab may not make alone goes to Gloria with the exact call on it, and only her Accept runs it
(Gloria, 2026-10-04: "how do we give him a way to be watched?").

Scratch workspace; every socket refused; the connector gateway and her Forge page are stubs. Nothing here reaches
her account, her page, or a paid tool.
"""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-asks-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import lab_asks as A
import lab_lines as LL
import claude_connector_catalog as catalog

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("its ledger is in the scratch workspace", A.STORE.startswith(HOME))

ARGS = {"input": {"entities": [{"type": "protein", "chain_ids": ["A"], "value": "MKV"},
                               {"type": "protein", "chain_ids": ["B"], "value": "MQT"}],
                  "binding": {"type": "protein_protein_binding", "binder_chain_ids": ["B"]}}}

# --- what he may ask for, and what he may not ------------------------------------------------------------
row, why = A.propose("boltz", "boltz_start_structure_and_binding", ARGS,
                     "the estimate says $1.40 and it answers whether the RT binds Cas1", estimate="$1.40",
                     line_id="L-gloria-phage-rt", question="Does the phage RT bind Cas1?")
check("he can ask her for a paid Boltz run", row and row["state"] == "asked" and row["id"].startswith("A-"), (row, why))
check("a tool he can already run himself is not something to ask for",
      A.propose("boltz", "boltz_get_guidance", {}, "x")[1] == "that tool is not one he may ask for")
check("a tool nobody put on the asking list is refused",
      A.propose("boltz", "boltz_get_job_status", {"id": "x"}, "y")[1] == "that tool is not one he may ask for")
check("a reason is required", A.propose("boltz", "boltz_start_small_molecule_adme", {"smiles": ["CCO"]}, "  ")[1]
      == "say why it is worth it")
check("the same call twice is one card", A.propose("boltz", "boltz_start_structure_and_binding", ARGS, "again")[1]
      .startswith("already asked"))

# --- her page shows the exact call ------------------------------------------------------------------------
card = A.cards()[0]
check("one card per waiting call, with the tool named in its title", len(A.cards()) == 1
      and card["kind"] == "ask" and card["ref"] == row["id"]
      and card["title"] == "Run boltz.boltz_start_structure_and_binding for him?", card)
check("the card carries the price from the free estimate", card["cost"] == "$1.40")
body = "\n".join(card["details"])
check("she sees what would be sent, not a summary of it", "He would send exactly this:" in body
      and '"binder_chain_ids"' in body and "MQT" in body, body)
check("and which line and question it serves", "L-gloria-phage-rt" in body and "Does the phage RT bind Cas1?" in body)
unpriced, _ = A.propose("boltz", "boltz_start_small_molecule_adme", {"smiles": ["CCO"]}, "ADME on the one I sourced")
check("a call with no estimate says plainly that accepting may spend money",
      "may spend money" in next(c for c in A.cards() if c["ref"] == unpriced["id"])["cost"])

# --- a tool that MAKES something says so on the card before she accepts it (Gloria added these 2026-10-04) ----
_cap = A.PER_DAY; A.PER_DAY = 9        # the cap is its own check below; these two are about the card's words
for plugin, tool, args in (("boltz", "boltz_start_protein_design", {"target": "X"}),
                           ("eden", "generate_antimicrobial_peptides", {"n": 4})):
    g, why = A.propose(plugin, tool, args, "it would make candidates to look at")
    check("he may ask her for %s" % tool, g and g["state"] == "asked" and g["generative"] is True, (g, why))
    body = "\n".join(next(c for c in A.cards() if c["ref"] == g["id"])["details"])
    check("... and the card says plainly that it makes something new, and what it is not", "MAKES something new" in body
          and "not a tested molecule" in body and "never a step toward making it for real" in body, body)
    check("... and he still cannot run it himself", not catalog.policy.__module__ or
          tool not in (catalog.PLUGINS[plugin]["read"] | catalog.PLUGINS[plugin]["action"]))
    A.decided(g["id"], "denied", "not this week")
A.PER_DAY = _cap
check("a predicting tool is not labelled as making anything", A.get(row["id"])["generative"] is False)

# --- nothing runs until she accepts -------------------------------------------------------------------------
calls = []
def gateway(surface, plugin, tool, arguments, purpose):
    calls.append((surface, plugin, tool, arguments, purpose))
    return {"ok": True, "receipt": {"receipt_id": "RCPT-1"}, "summary": "a predicted complex, ipTM 0.74"}
check("a waiting call does not run", A.run_accepted(call=gateway) == [] and calls == [])

A.decided(row["id"], "accepted", "go on then")
check("her Accept is written down", A.get(row["id"])["state"] == "accepted" and A.get(row["id"])["note"] == "go on then")
out = A.run_accepted(call=gateway)
check("... and only then is it sent, exactly once, exactly as shown", len(calls) == 1
      and calls[0][:4] == ("lab", "boltz", "boltz_start_structure_and_binding", ARGS), (out, calls))
check("the result comes back with its receipt", A.get(row["id"])["state"] == "ran"
      and A.get(row["id"])["receipt_id"] == "RCPT-1" and "ipTM" in A.get(row["id"])["summary"])
check("it does not run twice", A.run_accepted(call=gateway) == [] and len(calls) == 1)
check("a call that ran is off her page", not [c for c in A.cards() if c["ref"] == row["id"]])

# --- her no is an answer, and it reaches the line ------------------------------------------------------------
line = LL.get("L-gloria-phage-rt")       # the line the ask named
steps = [s for s in (line.get("steps") or []) if s.get("source") == "asked Gloria"]
check("what she decided is on his line of inquiry", steps and "accepted it and it ran" in steps[-1]["result"],
      line.get("steps"))
A.decided(unpriced["id"], "denied", "not worth the money this week")
check("her Deny is written down", A.get(unpriced["id"])["state"] == "denied")
check("asking again for one she refused is refused, with what she said",
      "she already said no" in A.propose("boltz", "boltz_start_small_molecule_adme", {"smiles": ["CCO"]}, "please")[1])

# --- it cannot flood her page ---------------------------------------------------------------------------------
made = 0
for i in range(6):
    r, _ = A.propose("boltz", "boltz_start_protein_screen", {"n": i}, "screen %d" % i)
    made += bool(r)
check("at most %d calls a day reach her" % A.PER_DAY, made == 0 and len(A.asked_today()) >= A.PER_DAY, made)

# --- a failed run says so, and is not left looking accepted ----------------------------------------------------
A.PER_DAY = 9
pend, _ = A.propose("boltz", "boltz_start_structure_and_binding", {"input": {"entities": [{"v": 2}]}},
                    "the other complex")
A.PER_DAY = _cap
A.decided(pend["id"], "accepted")
def broken(*a, **k):
    raise RuntimeError("the relay was unreachable")
A.run_accepted(call=broken)
check("a call that could not run is marked failed, with why", A.get(pend["id"])["state"] == "failed"
      and "unreachable" in A.get(pend["id"])["error"])

check("his Lab is told what is waiting and what she answered", "CALLS YOU ASKED GLORIA FOR" in A.block()
      and "she said no" in A.block() and "Do not ask again" in A.block())

# --- the wiring ------------------------------------------------------------------------------------------------
house = open(os.path.join(REPO, "scripts", "forge_house.py")).read()
check("her Forge page is given these cards", "lab_asks.cards()" in house)
check("her verdict on one is carried back", "lab_asks" in house and "lab_asks.decided(" in house)
check("and what she accepted runs on the next pass", "_run_accepted_calls" in house and "run_accepted()" in house)
check("the Forge accepts the new kind of decision",
      "'card', 'parts', 'arrived', 'ask'" in open(os.path.join(REPO, "scripts", "forge_loop_runtime.py")).read())
ui = open(os.path.join(REPO, "scripts", "forge_loop_ui.html")).read()
check("her page labels it and its button says what it does", "A call his Lab cannot make alone" in ui and "'Run it'" in ui)
lab = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("a withheld tool in his Lab becomes an ask, not a dead end", "lab_asks.propose(" in lab and "asked_gloria" in lab)
check("the deploy installs it", "lab_asks.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""A call his Lab may not make alone goes to Gloria with the exact call on it, and only her Accept runs it
(Gloria, 2026-10-04: "how do we give him a way to be watched?").

Scratch workspace; every socket refused; the connector gateway and her Forge page are stubs. Nothing here reaches
her account, her page, or a paid tool.
"""
import json, os, socket, sys, tempfile, types

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

# Every propose() pushes to her phone; the real sender is held here and the push is a recorder, so this suite
# cannot reach ntfy. The push itself is checked below with its own stub.
_real_notify, NOTIFIED = A.notify, []
A.notify = lambda row, send=None: NOTIFIED.append(row)

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
check("every new card pushes to her phone", NOTIFIED and NOTIFIED[0]["id"] == row["id"], NOTIFIED)
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

# --- her Accept really runs: through the gateway's accepted door, not its ordinary policy --------------------------
# The paid tools are outside policy() on purpose, so the ordinary call refused every Accept (found 2026-10-04).
import claude_connector_gateway as G
import claude_connector_relay as relay
A.PER_DAY = 9
door, _ = A.propose("boltz", "boltz_start_structure_and_binding", {"input": {"entities": [{"v": "door"}]}}, "the door")
try:
    G.call("lab", "boltz", "boltz_start_structure_and_binding", door["arguments"], "x", transport=lambda r: {"ok": True, "result": {}}); ordinary = True
except PermissionError:
    ordinary = False
check("the ordinary gateway still refuses a paid tool", not ordinary)
try:
    G.call_accepted(door, transport=lambda r: {"ok": True, "result": {}}); before = True
except PermissionError:
    before = False
check("a card she has not accepted cannot run", not before)
A.decided(door["id"], "accepted", "yes")
SENT_REQ = []
row = A.get(door["id"])
got = G.call_accepted(row, transport=lambda r: SENT_REQ.append(r) or {"ok": True, "result": {"job": "J-1"}})
check("her accepted card runs through the gateway, marked as hers", got["ok"] and SENT_REQ[-1]["accepted"] == door["id"]
      and SENT_REQ[-1]["tool"] == "boltz_start_structure_and_binding" and SENT_REQ[-1]["arguments"] == door["arguments"], SENT_REQ)
try:
    G.call_accepted(dict(row, arguments={"input": {"entities": [{"v": "SOMETHING ELSE"}]}}), transport=lambda r: {"ok": True, "result": {}}); swapped = True
except PermissionError:
    swapped = False
check("the arguments cannot be changed after she accepted the card", not swapped)
seen_by_relay = []
relay._run_with_timeout = lambda *a: (seen_by_relay.append(a) or __import__("asyncio").sleep(0, {"result": {"job": "J-1"}, "source": "tool_result"}))
ok = relay.connector({"plugin": "boltz", "surface": "lab", "tool": "boltz_start_structure_and_binding",
                      "arguments": door["arguments"], "accepted": door["id"]})
check("the relay's own door lets her accepted call through", ok["ok"] and seen_by_relay, ok)
try:
    relay.connector({"plugin": "boltz", "surface": "lab", "tool": "boltz_start_protein_design", "arguments": {}, "accepted": door["id"]}); smuggled = True
except PermissionError:
    smuggled = False
check("... and nothing else rides in under her Accept", not smuggled)
check("run_accepted uses that door when no stub is given", "claude_connector_gateway.call_accepted(row)" in open(os.path.join(REPO, "scripts", "lab_asks.py")).read())
A.PER_DAY = _cap

# --- an ask from #vintos-dot, from him or from dot ---------------------------------------------------------------------
A.PER_DAY = 9
EST = []
fake_gw = types.SimpleNamespace(call=lambda s, p, t, a, why: EST.append((s, p, t)) or {"summary": "about $0.08"})
said = A.from_slack('Running it.\nASK: boltz.boltz_start_structure_and_binding {"input": {"entities": [{"v": "PYP"}]}} | PYP binding, up to $0.10',
                    by="dot", gateway=fake_gw)
check("an ASK line in Slack puts the exact call on her Forge page", said and said[0][0] and "On Gloria's Forge page" in said[0][1], said)
card = next(c for c in A.cards() if "PYP" in "\n".join(c["details"]))
check("... priced by Boltz's own free estimate", "about $0.08" in card["cost"] and EST[-1] == ("lab", "boltz", "boltz_estimate_structure_and_binding"), (card["cost"], EST))
check("... with the reason it was asked", "PYP binding, up to $0.10" in card["what"])
check("a tool nobody may ask for is not put on her page", not A.from_slack("ASK: boltz.boltz_get_guidance {}", gateway=fake_gw)[0][0])
check("arguments that are not JSON say so", "not JSON" in A.from_slack("ASK: boltz.boltz_start_protein_screen {nope}", gateway=fake_gw)[0][1])
A.PER_DAY = _cap
import dot_channel as Dc
check("the channel reads the same ASK line as the asks module", Dc.ASK_LINE.pattern == A.ASK.pattern)
dsrc = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("his ASK lines and dot's both reach her page, and dot gets the card number in its thread",
      'lab_asks.from_slack(text, by="vintos")' in dsrc and 'lab_asks.from_slack(r["text"], by="dot")' in dsrc and '"thread_ts": r.get("thread") or r["ts"]' in dsrc)
check("no ASK line reaches her results channel", "ASK:" not in Dc._no_tags("Done.\nASK: boltz.x {}"))
check("he is told how to ask", "ASK: plugin.tool" in Dc.RULES_HANDS)
check("dot is told to ask this way, never to send her to a task she cannot open",
      "ASK: boltz.boltz_start_structure_and_binding" in open(os.path.join(REPO, "docs", "dot", "operating-rules.md")).read())

# --- the push to her phone: the price, Yes and No (Gloria, 2026-10-04: "no card no notifications no approval link") ---
PUSHED = []
def push(req, timeout=None):
    PUSHED.append((req.full_url, dict(req.headers), req.data.decode()))
A.PER_DAY = 9
A.AEGIS = "http://100.72.225.119:8500"
pri, _ = A.propose("boltz", "boltz_start_structure_and_binding", {"input": {"entities": [{"v": "PYP-push"}]}},
                   "one PYP sample", estimate='Free estimate: {"estimated_cost_usd": "0.0250"}')
check("the price is read out of Boltz's own estimate", A.price(pri) == "$0.03", A.price(pri))
check("... and an estimate with no number says plainly that it may spend money",
      "may spend money" in A.price({"estimate": "runtime-dependent"}))
_real_notify(pri, send=push)
url, headers, body = PUSHED[-1]
check("the push says the price in its title", "Run this for him?" in headers["Title"] and "$0.03" in headers["Title"], headers)
check("... and what the call is, in its body", "boltz.boltz_start_structure_and_binding" in body and "one PYP sample" in body, body)
act = headers["Actions"]
check("... with a Yes that runs it and a No", "Yes - run it" in act and "state=accepted" in act and "state=denied" in act, act)
check("... each carrying this card's own one-use token, never her app secret",
      pri["token"] in act and "secret" not in act.lower() and len(pri["token"]) == 32, act)
check("a wrong token decides nothing", A.decide_with_token(pri["id"], "0" * 32, "accepted") == (None, "that is not this call's button")
      and A.get(pri["id"])["state"] == "asked")
done, _ = A.decide_with_token(pri["id"], pri["token"], "accepted")
check("her Yes from the push is her Accept", done and A.get(pri["id"])["state"] == "accepted")
check("... and the same button cannot run it twice", A.decide_with_token(pri["id"], pri["token"], "accepted")[1].startswith("already"))
gen, _ = A.propose("eden", "generate_antimicrobial_peptides", {"n": 2}, "candidates")
_real_notify(gen, send=push)
check("a tool that makes something says so on the push, before she taps Yes", "MAKES something new" in PUSHED[-1][2], PUSHED[-1][2])
PUSHED.clear()
A.told(pri["id"], "a predicted complex, ipTM 0.74", send=push)
check("what came of it reaches her too", "ipTM 0.74" in PUSHED[-1][2] and pri["id"] in PUSHED[-1][1]["Title"])
check("a push that cannot be sent never breaks the ask",
      _real_notify(pri, send=lambda *a, **k: (_ for _ in ()).throw(OSError("no network"))) is False)
A.PER_DAY = _cap
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("the buttons reach a route that runs as her, beside the store", '@app.post("/api/lab/asks/{ask_id}/decide")' in srv
      and '@app.get("/api/lab/asks")' in srv and "_la_s.path.insert(0, \"/home/gloria/.vintos/workspace/scripts\")" in srv)
check("... which accepts the card's token or her app secret, and nothing else", "A.decide_with_token(ask_id, t, state)" in srv
      and 'request.headers.get("X-Vintos-Secret") == APP_SECRET' in srv and "status_code=403" in srv)
check("... and her Yes actually runs it, then tells her what came of it", "A.run_accepted()" in srv and "A.told(aid," in srv)

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

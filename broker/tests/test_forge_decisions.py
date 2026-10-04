#!/usr/bin/env python3
"""What waits on Gloria gets Accept and Deny on her Forge page, and a parts list goes to Muse for real prices
(2026-10-03: "Yes, we need the accept button. I only have a stop button."; "Muse should be able to find actual
listings and prices for Forge materials. If muse makes a list I can accept or deny from there.").

A real Forge controller on a scratch SQLite file and its WSGI API; the house side against stubs (Forge transport,
Slack); skill proposals in a scratch workspace. No socket opens."""
import io, json, os, socket, sys, tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="forge-decisions-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
from forge_loop import Controller
from forge_loop_atelier import AtelierProjection
from forge_loop_runtime import Runtime, API
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

root = Path(HOME) / "forge"; root.mkdir()
OWNER = "o" * 40
c = Controller(root / "forge.sqlite", OWNER, "w" * 40, "https://atelier.invalid")
r = Runtime(c, AtelierProjection(root), lambda *a, **k: None, lambda *a, **k: None, "t")
api = API(r)
def call(method, path, body=None, token=""):
    raw = json.dumps(body).encode() if body is not None else b""
    env = {"PATH_INFO": path, "REQUEST_METHOD": method, "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw)}
    if token: env["HTTP_AUTHORIZATION"] = "Bearer " + token
    got = {}
    out = api(env, lambda status, headers: got.update(status=status))
    return int(got["status"].split()[0]), json.loads(b"".join(out))

CARD = {"id": "card:SK-51562337", "kind": "card", "ref": "SK-51562337", "title": "Citation graph traversal",
        "what": "Follow citations both ways.", "cost": "Built by the Forge; nothing is bought.", "details": ["Asked: from dot"]}
st, body = call("POST", "/api/decisions-sync", {"cards": [CARD]})
check("her page cannot write cards: the house's sync needs the owner key", st == 403)
st, body = call("POST", "/api/decisions-sync", {"cards": [CARD]}, OWNER)
check("the house's sync adds a waiting card", st == 200 and body[0]["state"] == "waiting" and body[0]["title"] == "Citation graph traversal", body)
st, body = call("GET", "/api/decisions")
check("her page sees what is waiting, without a key", st == 200 and [d["id"] for d in body] == ["card:SK-51562337"])
st, body = call("POST", "/api/decisions/card:SK-51562337/accept", {})
check("Accept on her page decides it", st == 200 and body["state"] == "accepted", body)
st, body = call("POST", "/api/decisions/card:SK-51562337/deny", {"note": "changed my mind"})
check("a decided card cannot be decided again", st == 403)
st, body = call("POST", "/api/decisions-sync", {"cards": [dict(CARD, title="Citation graph traversal (renamed)")]}, OWNER)
check("a later sync keeps her decision", body[0]["state"] == "accepted" and "renamed" in body[0]["title"], body)
call("POST", "/api/decisions-sync", {"cards": [dict(CARD, id="parts:P-11a7cf56", kind="parts", title="Parts for: a pressure pad")]}, OWNER)
st, body = call("POST", "/api/decisions/parts:P-11a7cf56/deny", {"note": "too much"})
check("Deny keeps her word on why", body["state"] == "denied" and body["note"] == "too much", body)
check("an unknown kind is refused", call("POST", "/api/decisions-sync", {"cards": [dict(CARD, id="x", kind="buy")]}, OWNER)[0] == 403)

ui = open(os.path.join(REPO, "scripts", "forge_loop_ui.html")).read()
check("her page shows Waiting on you with Accept and Deny, above the projects",
      '<section id="waiting"></section>' in ui and ui.index('id="waiting"') < ui.index('id="projects"')
      and "'/accept','POST'" in ui and "'/deny','POST'" in ui and "Accept this list" in ui and "await renderWaiting();" in ui)

# ---- the house side -----------------------------------------------------------------------------------
import skill_forge as SF
import forge_house as H
check("the house's stores are in the scratch workspace", SF.MEMORY.startswith(HOME))
os.makedirs(SF.MEMORY, exist_ok=True)
gap, _ = SF.propose_from_gap_review("citation_graph_traversal", "Follow citations both ways", ["dot: two-way traversal design"],
                                    path="/mnt/c/Users/glori/Documents/design.md", touches=["scripts/citations.py"], tests="a two-way test")
denied, _ = SF.propose_from_gap_review("old_idea", "an idea she will refuse", ["evidence"])
cards = H.decision_cards()
card = next(x for x in cards if x["ref"] == gap["id"])
check("every card waiting for her yes becomes a decision, dot's (no want behind it) included",
      card["title"] == "Citation graph traversal" and card["what"] == "Follow citations both ways"
      and any("design.md" in l for l in card["details"]) and "nothing is bought" in card["cost"], card)

FORGE = {"decisions": []}
def transport(req, timeout=0):
    body = json.loads(req.data) if req.data else None
    path = req.full_url.replace(H.BASE, "")
    if path == "/api/decisions-sync":
        known = {d["id"]: d for d in FORGE["decisions"]}
        for cd in body["cards"]:
            known.setdefault(cd["id"], dict(cd, state="waiting"))
        FORGE["decisions"] = list(known.values()); out = FORGE["decisions"]
    elif path == "/api/projects":
        out = FORGE.get("projects", [])
    elif path.endswith("/artifacts"):
        out = FORGE.get("artifacts", {}).get(path.split("/")[3], [])
    else:
        out = {}
    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return Resp(json.dumps(out).encode())
H.secret = None
import forge_loop_runtime
forge_loop_runtime.secret = lambda path: "o" * 40
SAID = []
check("nothing is carried out before she decides", H.sync_decisions(transport=transport, post=SAID.append) == [])
for d in FORGE["decisions"]:
    if d["ref"] == gap["id"]: d["state"] = "accepted"
    if d["ref"] == denied["id"]: d.update(state="denied", note="not now")
done = H.sync_decisions(transport=transport, post=SAID.append)
check("her Accept approves the card in the Forge's own law, as hers",
      SF._get(SF._load(), gap["id"])["state"] == "approved"
      and SF._get(SF._load(), gap["id"])["history"][-1]["by"] == "gloria", SF._get(SF._load(), gap["id"])["history"])
check("her Deny denies it, with her reason", SF._get(SF._load(), denied["id"])["state"] == "denied")
check("each decision is carried out once", sorted(done) == sorted(["card:" + gap["id"], "card:" + denied["id"]])
      and H.sync_decisions(transport=transport, post=SAID.append) == [])

# a parts list to Muse, Muse's reply kept, then a card
FORGE["projects"] = [{"id": "forge-11a7cf5677b44a88", "state": "ready", "cycles": 2, "title": "Missing Lab instrument: a pressure pad"},
                     {"id": "forge-0000aaaa", "state": "cancelled", "cycles": 1}]
HW = {"title": "Pressure pad for the bed", "parts": [{"name": "Arduino Nano", "quantity": 1, "rough_cost_usd": 20, "purpose": "read the sensor"},
                                                     {"name": "FSR 406", "quantity": 2, "rough_cost_usd": 9, "purpose": "pressure"}]}
FORGE["artifacts"] = {"forge-11a7cf5677b44a88": [{"artifact": json.dumps({"capability_assessment": {"hardware_proposal": HW}})}]}
sent = H.ask_muse_for_parts(transport=transport, post=SAID.append)
check("a parts list goes to Muse and Vintos to settle part by part in its thread, tagged, and nobody buys",
      sent == ["P-11a7cf56"] and SAID[-1].startswith("@Muse [Forge parts P-11a7cf56]") and "Arduino Nano x1" in SAID[-1]
      and "FSR 406 x2" in SAID[-1] and "Nobody buys anything" in SAID[-1] and "one part at a time" in SAID[-1], SAID[-1:])
check("it is asked once", H.ask_muse_for_parts(transport=transport, post=SAID.append) == [])
import dot_channel as D
MUSE = {"who": "agent", "name": "Muse", "at": "2026-10-03T12:00:00",
        "text": "[Muse] [Forge parts P-11a7cf56] FINAL\nArduino Nano | $24.90 | Arduino Store | https://store.arduino.cc/nano | yes\n"
                "FSR 406 x2 | $19.90 | Adafruit | https://adafruit.com/product/1075 | yes\nTotal: $44.80"}
check("Muse's messages while they work through each part are not the list", D.keep_parts_lists(
      [dict(MUSE, text="[Muse] [Forge parts P-11a7cf56] Arduino Nano: two options...")], mem=SF.MEMORY) == [])
check("someone else using the tag is not taken for Muse", D.keep_parts_lists([dict(MUSE, name="Grok Bot")], mem=SF.MEMORY) == [])
check("Muse's tagged reply is kept", D.keep_parts_lists([MUSE], mem=SF.MEMORY) == ["P-11a7cf56"])
parts = next(x for x in H.decision_cards() if x["kind"] == "parts")
check("and becomes a parts card: her list, its total, and that nothing is bought for her",
      parts["title"] == "Parts for: Pressure pad for the bed" and parts["cost"] == "Total: $44.80"
      and any("adafruit.com" in l for l in parts["details"]) and "nothing is bought for you" in parts["what"], parts)
H.sync_decisions(transport=transport, post=SAID.append)
for d in FORGE["decisions"]:
    if d["kind"] == "parts": d["state"] = "accepted"
H.sync_decisions(transport=transport, post=SAID.append)
check("her Accept on a parts list is told to him in Slack: she will buy them",
      SAID[-1].startswith("Gloria accepted the parts list for Pressure pad for the bed") and "she will buy them" in SAID[-1], SAID[-1:])
# an accepted parts list starts the build; their arrival starts the walkthrough
import study_fix as SFX
check("the Study's queue is the scratch one", SFX.QUEUE.startswith(HOME))
fixes = [r for r in SFX._load() if r.get("by") == "forge:P-11a7cf56"]
check("her accepted list sends the software side to the Study: the device code and the house side, with a test",
      len(fixes) == 1 and "hardware/pressure_pad_for_the_bed/" in fixes[0]["what"] and "Arduino Nano" in fixes[0]["what"]
      and "with a test that feeds it a sample reading" in fixes[0]["what"], fixes)
HW2 = dict(HW, wiring=["FSR 406 leg to A0", "10k resistor from A0 to GND"], acceptance_tests=["pressing reads above 500"])
asked = json.load(open(os.path.join(SF.MEMORY, "forge-parts-asked.json")))
asked["forge-11a7cf5677b44a88"].update(wiring=HW2["wiring"], acceptance_tests=HW2["acceptance_tests"])
json.dump(asked, open(os.path.join(SF.MEMORY, "forge-parts-asked.json"), "w"))
arr = [x for x in H.decision_cards() if x["kind"] == "arrived"]
check("then a card asks whether the parts have arrived, with the wiring planned",
      len(arr) == 1 and arr[0]["title"] == "Have the parts for Pressure pad for the bed arrived?"
      and "Wiring: FSR 406 leg to A0" in arr[0]["details"], arr)
H.sync_decisions(transport=transport, post=SAID.append)
for d in FORGE["decisions"]:
    if d["kind"] == "arrived": d["state"] = "accepted"
H.sync_decisions(transport=transport, post=SAID.append)
check("'They are here' starts him walking her through it in Slack, one step at a time, then the checks",
      SAID[-1].startswith("[Forge build P-11a7cf56] Gloria has the parts") and "one step at a time" in SAID[-1]
      and "1. FSR 406 leg to A0" in SAID[-1] and "- pressing reads above 500" in SAID[-1], SAID[-1:])
check("and the arrival card is gone", not [x for x in H.decision_cards() if x["kind"] == "arrived"])

# a Forge card that is a change in his own code goes to the Study, not to her
code, _ = SF.propose_from_gap_review("slack_thread_reader", "Read Slack threads whole", ["dot: threads read as lone lines"],
                                     touches=["scripts/dot_channel.py"], tests="a thread test")
guarded, _ = SF.propose_from_gap_review("jepa_window", "Widen the JEPA window", ["evidence"], touches=["scripts/jepa_predictor.py"])
sent = H.route_to_study()
check("a code change inside his reach goes to the Study by itself", sent == [code["id"]]
      and any(r.get("by") == "forge:" + code["id"] and "Read Slack threads whole" in r["what"] for r in SFX._load()), sent)
check("one touching his subconscious or JEPA stays with her", guarded["id"] not in sent
      and any(x["ref"] == guarded["id"] for x in H.decision_cards()))
check("while the Study is doing it, it is not a card for her", not any(x["ref"] == code["id"] for x in H.decision_cards()))
rows = SFX._load(); sfid = json.load(open(os.path.join(SF.MEMORY, "forge-to-study.json")))[code["id"]]
for r in rows:
    if r["id"] == sfid: r.update(state="failed", log=[{"what": "still failing after 3 tries: test_x.py"}])
SFX._save(rows)
back = next((x for x in H.decision_cards() if x["ref"] == code["id"]), None)
check("if the Study could not land it, it comes to her, saying so", back and "did not land: still failing after 3 tries" in back["what"], back)
for r in rows:
    if r["id"] == sfid: r["state"] = "done"
SFX._save(rows); H.route_to_study()
check("done in the Study, the card closes itself", SF._get(SF._load(), code["id"])["state"] == "withdrawn"
      and "done in the Study" in SF._get(SF._load(), code["id"])["history"][-1]["detail"])
check("withdraw only closes a card still waiting, and grants nothing", SF.withdraw(gap["id"])[0] is None)

muse_doc = open(os.path.join(REPO, "docs", "muse", "vintos-skill.md")).read()
check("Muse's skill says how to answer a Forge parts request, and still never to buy",
      "[Muse] [Forge parts P-xxxxxxxx] FINAL" in muse_doc and "one part at a time" in muse_doc and "item | price | store | link | in stock?" in muse_doc and "Never buy" in muse_doc)
house = open(os.path.join(REPO, "scripts", "forge_house.py")).read()
check("the house sync runs each step after the gap sync, and none can stop the others",
      "for step in (route_to_study, sync_decisions, _run_accepted_calls, ask_muse_for_parts):" in house)
check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

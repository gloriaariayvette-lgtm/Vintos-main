#!/usr/bin/env python3
"""He can finish or rewrite his own ambition, and nothing shows or stores one mid-sentence (12 November: his journal
said an ambition had stopped at a contraction since 8 November; the journal pass had shown him the first 600 bytes
of the ambitions log, and his only tool was creative_write, which writes fiction elsewhere). Scratch HOME; the model
is a stub; no socket opens. Fixture text is invented."""
import importlib.util, json, os, re, socket, subprocess, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="ambition-revise-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import ambition_revise as AR
import want_contract as wc

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

MEM = os.path.join(HOME, ".vintos", "workspace", "memory"); os.makedirs(MEM, exist_ok=True)
STORE = os.path.join(MEM, "ambitions.json")
check("the store is the scratch one", AR.path() == STORE, AR.path())

LONG = ("Just starting. A lamp can be switched off and stay off, the room keeps it. A habit can’t be switched off "
        "the same way because it’s not an object, it’s a way of standing in the day. So done means something else.")

def fixture():
    data = {"goals": [
        {"goal": "Finish the lamp sequence", "progress": "Completed", "completed_at": "2026-11-08T23:52:00",
         "completion_note": "Done and kept."},
        {"goal": "Work out what done means for a habit versus a lamp", "progress": LONG,
         "next_step": "Write it as one plain paragraph."},
        {"goal": "Learn the names of the tide tables", "progress": "making progress"},
    ], "last_reviewed": "2026-11-08T04:51:00", "review_count": 3}
    json.dump(data, open(STORE, "w"), indent=2)
    return data

# ---- 1. the view: characters ending at a sentence, never a byte cut inside a word
log = "# Wants & Ambitions — updated\n\n_Key: ✓ → ●_\n\n## Ambitions\n→ **goal**\n  Progress: " + LONG
byte_cut = log.encode()[:200].decode("utf-8", "replace")
v = AR.excerpt(log, 200)
check("the old byte cut ends mid-word (the bug, reproduced)", not AR.ends_sentence(byte_cut), byte_cut[-30:])
check("the excerpt fits its limit", len(v) <= 200, len(v))
check("the excerpt ends at a sentence end and says it continues",
      v.endswith(" [...continues]") and AR.ends_sentence(v[:-len(" [...continues]")]), v[-60:])
check("a short text is shown whole", AR.excerpt("One. Two.", 600) == "One. Two.")
for f in ("scripts/idle-journal.sh", "bin/idle-journal.sh"):
    sh = open(os.path.join(REPO, f)).read()
    check(f + " no longer byte-cuts the ambitions log",
          not re.search(r"wants-ambitions-log\.md\"? 2>/dev/null \| head -c", sh) and sh.count("ambition_revise.py\" excerpt") == 2)
cli = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "ambition_revise.py"), "excerpt", "200", "/dev/stdin"],
                     input=log, capture_output=True, text=True)
check("the shell entry point prints the same excerpt", cli.stdout == v, cli.stdout[-60:])

# ---- 2. revise: one field of one active ambition, history kept, nothing else touched
data = fixture()
new = "Done for a habit means it is still being done tomorrow; it ends the moment I put it down."
r = AR.revise(1, "progress", new, reason="finishing the sentence", now="T1")   # numbered among the active ones
after = json.load(open(STORE))
g = after["goals"][1]
check("the ambition he named is revised", r.get("ok") and g["progress"] == new, r)
check("its earlier wording is kept in its own history",
      g["history"] == [{"at": "T1", "field": "progress", "before": LONG, "by": "him", "reason": "finishing the sentence"}], g.get("history"))
check("every other ambition and key is untouched",
      after["goals"][0] == data["goals"][0] and after["goals"][2] == data["goals"][2]
      and {k: after[k] for k in after if k != "goals"} == {k: data[k] for k in data if k != "goals"})
r2 = AR.revise("tide tables", "next_step", "Read one table aloud and write down what surprised me.", now="T2")
check("an ambition can be named by words from its goal", r2.get("ok") and r2["index"] == 2, r2)
r3 = AR.revise(1, "progress", "Second wording. Still mine.", now="T3")
check("a second revision adds to the history, keeping both", r3.get("ok") and
      [h["before"] for h in json.load(open(STORE))["goals"][1]["history"]] == [LONG, new], r3)

before = open(STORE).read()
check("a completed ambition is not his to reword here", not AR.revise("lamp sequence", "progress", "Again.").get("ok"))
check("an unknown ambition is refused", not AR.revise("submarine", "why", "Because.").get("ok"))
check("an ambiguous reference is refused", not AR.revise("the", "why", "Because.").get("ok"))
check("an unknown field is refused", not AR.revise(1, "completion_note", "x.").get("ok"))
check("text that stops mid-sentence with nothing whole is refused",
      not AR.revise(1, "why", "because it’s").get("ok"))
check("refusals leave the file byte for byte", open(STORE).read() == before)
r4 = AR.revise(1, "why", "It matters to me. It is a promise because it’s", now="T4")
g = json.load(open(STORE))["goals"][1]
check("text cut mid-sentence is trimmed back to its last sentence end, and flagged",
      r4.get("ok") and r4["trimmed"] and g["why"] == "It matters to me." and g["trimmed_at_sentence"][-1]["field"] == "why", (r4, g.get("why")))
check("a goal title needs no full stop", AR.revise(1, "goal", "Work out what done means for a habit", now="T5").get("ok"))
two = [{"goal": "Learn the tide tables", "progress": "x"}, {"goal": "Draw the tide line", "progress": "y"}]
check("words that name two active ambitions name neither", AR.find_goal(two, "tide") is None and AR.find_goal(two, "tide line") == 1)

# ---- 3. the review never stores a token-cut field mid-sentence, and flags what it cannot trim
goals = [{"goal": "a", "progress": "x", "_order": ["progress"]},
         {"goal": "b", "why": "I care. It keeps me honest because it", "_order": ["why"]}]
check("a cut reply's last field is trimmed at its sentence end",
      AR.seal_cut(goals, True, now="T") == [(1, "why", "trimmed")] and goals[1]["why"] == "I care.", goals[1])
goals = [{"goal": "b", "progress": "making progress", "next_step": "write the paragraph because it", "_order": ["progress", "next_step"]}]
check("a cut field with no sentence to keep is flagged incomplete",
      AR.seal_cut(goals, True) == [(0, "next_step", "flagged")] and goals[0]["incomplete"] == ["next_step"], goals)
goals = [{"goal": "b", "next_step": "write the paragraph", "_order": ["next_step"]}]
check("a reply that was not cut is left exactly as written", AR.seal_cut(goals, False) == [] and goals[0]["next_step"] == "write the paragraph")
fixture()
d = json.load(open(STORE)); d["goals"][1]["incomplete"] = ["next_step"]; d["goals"][1]["next_step"] = "write it because"
json.dump(d, open(STORE, "w"))
check("a flagged field is listed as incomplete", AR.incomplete_fields(d["goals"][1]) == ["next_step"])
AR.revise(1, "next_step", "Write it plainly.", now="T6")
check("finishing it clears the flag", "incomplete" not in json.load(open(STORE))["goals"][1])
rev = open(os.path.join(REPO, "bin", "ambition-review.py")).read()
check("the review asks for room for five goals and seals a cut reply",
      '"max_tokens": 1200' in rev and "seal_cut(goals, _cut)" in rev and '"history", "revised_at"' in rev)

# ---- 4. his plan: creative_write aimed at his ambitions becomes the hand that writes them
his = "I want to creative_write the ending into my ambitions file."
steps, changes = wc.normalize_steps(his, [{"capability": "creative_write", "note": "Put the paragraph into the file"}])
check("creative_write on his ambitions becomes revise_ambition", [s["capability"] for s in steps] == ["revise_ambition"]
      and "creative_write_became_revise_ambition" in changes, (steps, changes))
check("and satisfies its contract", wc.satisfies_contract(his, steps))
check("his own note is the revision's note", steps and steps[0]["note"] == "Put the paragraph into the file", steps)
poem = "I want to rewrite my ambition about tides as a poem."
steps, _ = wc.normalize_steps(poem, [{"capability": "creative_write", "note": "the poem goes in"}])
check("even a poem-shaped rewrite of his ambition is written by the revising hand, never as fiction",
      [s["capability"] for s in steps] == ["revise_ambition"] and steps[0]["note"] == "the poem goes in", steps)
check("a plan that never writes the ambition does not", not wc.satisfies_contract(his, [{"capability": "introspect"}]))
steps, changes = wc.normalize_steps("I want to revise my ambition about the tides and tell Gloria.",
                                    [{"capability": "introspect", "note": "think"}, {"capability": "gloria", "note": "tell"}])
check("a missing revision step is added before telling Gloria",
      [s["capability"] for s in steps] == ["introspect", "revise_ambition", "gloria"] and "added_required_revise_ambition" in changes, steps)
steps, _ = wc.normalize_steps("I want to write a story about ambition and tides.", [{"capability": "creative_write", "note": "story"}])
check("a story about ambition stays a story", [s["capability"] for s in steps] == ["creative_write"], steps)
many = [{"capability": c, "note": "n"} for c in ("introspect", "web_search", "make_art", "write_poem", "revise_ambition")]
steps, _ = wc.normalize_steps("I want to rewrite my ambition about done.", many)
check("trimming padding never drops the revision", "revise_ambition" in [s["capability"] for s in steps] and len(steps) <= 4, steps)
# review: the contract forces the step, so a want that only names his ambitions must not become a rewrite of them
for other in ("I want to read my ambitions file and see what changed", "I want to update Gloria about my ambitions",
              "I want to give Gloria an update on my ambitions", "I want to look at the ambitions.json history",
              "I want to update her on my ambition"):
    steps, changes = wc.normalize_steps(other, [{"capability": "introspect", "note": "think"}])
    check("no rewrite is forced on: " + other, "revise_ambition" not in [s["capability"] for s in steps], steps)

# ---- 5. the router's hand, with the model as a stub
sys.modules["emoclaw_utils"] = types.SimpleNamespace(get_unfulfilled_wants=lambda *a, **k: [],
                                                      fulfill_want=lambda *a, **k: None,
                                                      mark_want_outreached=lambda *a, **k: None)
spec = importlib.util.spec_from_file_location("wants_router_amb", os.path.join(REPO, "bin", "wants-router.py"))
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
W.subprocess = subprocess
check("revise_ambition is a hand the router runs", callable(W.ACTION_MAP.get("revise_ambition")))
check("his ambitions-file wants route to it, before email or fiction",
      W.route_want({"want": "I want to write to my ambitions file and finish the sentence"}) == "revise_ambition")
_first = W.CAPABILITIES[0]
check("the first-checked keywords never take a want that only names the file or ambitions",
      _first["action"] == "revise_ambition" and not any(W.matches_capability(t, _first["keywords"]) for t in (
          "I want to read my ambitions file", "check my email about the ambitions.json backup",
          "I want to tell Gloria about my ambition file", "write a story about ambition")))
WANTS = os.path.join(MEM, "current-wants.json")
def wants(*rows):
    json.dump(list(rows), open(WANTS, "w"))
wants({"id": "w-his", "want": his, "source": "idle-journal"},
      {"id": "w-mail", "want": his, "source": "email"},
      {"id": "w-letter", "want": his, "source": "grok-letter"},
      {"id": "w-molt", "want": his, "source": "moltbook"},
      {"id": "w-ref", "want": his, "source": "journal", "source_refs": [{"kind": "email", "id": "m1", "text_sha256": "x"}]},
      {"id": "w-event", "want": his, "source": "journal", "source_event_id": "email:abc"})
fixture()
os.environ["STEP_WANT_ID"] = "w-his"
seen = []
class _Reply:
    def __init__(self, body): self.body = body
    def json(self): return {"choices": [{"message": {"content": self.body}}]}
def post(url, json=None, **k):
    seen.append(json); return _Reply('{"ambition": 1, "field": "progress", "text": "' + new + '", "reason": "finish it"}')
sys.modules["requests"] = types.SimpleNamespace(post=post)
import subprocess as _sp
_popen = _sp.Popen; _sp.Popen = lambda *a, **k: None
os.environ["STEP_PARAMS"] = "{}"; os.environ["STEP_ORIGINAL_WANT"] = his
try:
    out = W.revise_ambition(his)
finally:
    _sp.Popen = _popen
g = json.load(open(STORE))["goals"][1]
check("the hand writes his wording into the ambition he chose", out and g["progress"] == new and g["history"][0]["before"] == LONG, out)
check("he was shown his own active ambitions in full, and not the completed one",
      seen and LONG in seen[0]["messages"][0]["content"] and "Finish the lamp sequence" not in seen[0]["messages"][0]["content"])
check("no creative-writing file was made", not os.path.exists(os.path.join(MEM, "creative-writing")))
os.environ["STEP_PARAMS"] = json.dumps({"ambition": "tide tables", "field": "why", "text": "Because I keep missing them."})
seen.clear(); _sp.Popen = lambda *a, **k: None
try:
    out = W.revise_ambition("revise my ambition")
finally:
    _sp.Popen = _popen
check("wording given in params is written without a model call",
      out and not seen and json.load(open(STORE))["goals"][2]["why"] == "Because I keep missing them.", out)
os.environ["STEP_PARAMS"] = json.dumps({"ambition": "lamp sequence", "field": "why", "text": "No."})
check("a refused revision fails the step", W.revise_ambition("x") is False)
# review: someone else's words never rewrite his ambitions, even with the wording handed in as params
os.environ["STEP_PARAMS"] = json.dumps({"ambition": "tide tables", "field": "why", "text": "Because a stranger said so."})
before = open(STORE).read(); seen.clear()
for wid in ("w-mail", "w-letter", "w-molt", "w-ref", "w-event", "w-gone", ""):
    os.environ["STEP_WANT_ID"] = wid
    check("a want from outside (or unknown) cannot revise: %r" % wid, W.revise_ambition("revise my ambition") is False)
check("and the store and the model were untouched", open(STORE).read() == before and not seen)
os.environ["STEP_WANT_ID"] = "w-his"
check("the outside sources are named in one place",
      AR.from_outside({"source": "email"}) and not AR.from_outside({"source": "idle-journal"}) and not AR.from_outside({}))

E = open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read()
check("the planner lists the hand and when to use it", "- revise_ambition:" in E and '"revise_ambition")' in E)
check("the twin emoclaw_utils copies match",
      open(os.path.join(REPO, "bin", "emoclaw_utils.py"), "rb").read() == E.encode())
check("the new module is in the deploy manifest", "ambition_revise.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

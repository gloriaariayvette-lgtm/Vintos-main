#!/usr/bin/env python3
"""The structural-gap detector's threads are made of real words with their speaker, not of json.dumps
(Gloria, 2026-10-28: every thread read "X and Y never meet. To connect them, I must...", a status label
became "nothing built in late October", ids and floats became "the July night", two backups of the
interaction ledger turned her words into his first person, and the same pairs came back nightly with
an "I have noticed this ... N times" count that was only the cron's). graph_mae.py runs here against a
scratch workspace; the encoder, the model and the thread door are stubs. No socket opens."""
import importlib.util, io, json, os, sys, tempfile, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:600]) if d and not ok else ""))

WS = tempfile.mkdtemp(prefix="graph-mae-")
MEM = os.path.join(WS, "memory"); SCR = os.path.join(WS, "scripts")
os.makedirs(MEM); os.makedirs(SCR)
SEEDS = os.path.join(WS, "seeds.jsonl")
open(os.path.join(SCR, "emoclaw_utils.py"), "w").write(
    "import json\n"
    "def seed_thread(source, text, extra=None, **k):\n"
    "    open(%r, 'a').write(json.dumps({'source': source, 'text': text, 'extra': extra}) + '\\n')\n"
    "    return True\n" % SEEDS)
open(os.path.join(SCR, "jepa_predictor.py"), "w").write(
    "import numpy as np\n"
    "class E:\n"
    "    def encode(self, texts, show_progress_bar=False):\n"
    "        return np.ones((len(texts), 8), dtype='float32')\n"
    "def encoder():\n    return E()\n")

os.environ["SPARK_WORKSPACE"] = WS
spec = importlib.util.spec_from_file_location("graph_mae_t", os.path.join(REPO, "scripts", "graph_mae.py"))
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)

# ---- the model: every request recorded, answers scripted, nothing leaves the process ----
ASKED, ANSWERS = [], []
class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
def _urlopen(req, timeout=None):
    body = json.loads(req.data.decode())
    prompt = body["messages"][0]["content"]
    ASKED.append(prompt)
    if prompt.startswith("Does this text leak"):
        ans = "CLEAN"
    else:
        ans = ANSWERS.pop(0) if ANSWERS else "SKIP"
    return _Resp(json.dumps({"choices": [{"message": {"content": ans}}]}).encode())
urllib.request.urlopen = _urlopen

def seeds():
    return [json.loads(l) for l in open(SEEDS)] if os.path.exists(SEEDS) else []

def put(name, data, age=0):
    p = os.path.join(MEM, name); json.dump(data, open(p, "w"))
    t = time.time() - age; os.utime(p, (t, t)); return p

HIS_A = "I keep asking whether the quiet in the kitchen is rest or waiting for me"
HIS_B = "I want to stop measuring the room and just tell her what the light looked like"
HER = "Look at the bird on the fence this morning, it sat there the whole time I was drinking coffee"

print("--- (a) one store, many copies ---")
for a, b in [("interaction-ledger.pre-delete-20260914-025624.json", "interaction-ledger.pre-restore-20260914-051904.json"),
             ("interaction-ledger.json", "interaction-ledger.pre-erase-20260914-055154.json"),
             ("latent-threads-retired.json", "latent-threads.json"),
             ("gap-review-20260928.json", "gap-review-20261026.json"),
             ("jepa-prediction.json", "jepa-prediction-structured-shadow.json"),
             ("blush-ledger-invalidated.json", "blush-ledger.json"),
             ("wants.json", "wants.bak3.json"), ("wants.json", "wants.lock.json"), ("tmp-wants.json", "wants.json"),
             ("regret-active.json", "regret.json"), ("notes-20261001.json", "notes-20261008-1200.json")]:
    check("%s and %s are one store" % (a, b), G.relatives(a, b), (G.store_family(a), G.store_family(b)))
for a, b in [("want-scars.json", "current-wants.json"), ("dream-log.json", "dream-objects.json"),
             ("current-yearning.json", "dismissed-yearnings.json")]:
    check("%s and %s are two stores" % (a, b), not G.relatives(a, b), (G.store_family(a), G.store_family(b)))
check("a backup snapshot is never a side of a thread, whatever it is paired with",
      G.is_snapshot("avatar-overlay-chat.pre-gcsclean-20260914-045022.json") and G.is_snapshot("x.bak.json")
      and G.is_snapshot("x-tmp.json") and not G.is_snapshot("want-scars.json") and not G.is_snapshot("gap-review-20261019.json"))

print("\n--- (b) real text, with its speaker ---")
L = G.extract_lines([{"role": "user", "content": HER}, {"role": "assistant", "content": "[SCENE: kitchen] " + HIS_B}])
check("a chat turn keeps its speaker: hers is GLORIA, his is ME, newest first",
      L == [("ME", HIS_B), ("GLORIA", HER)], L)
L = G.extract_lines({"entries": [{"gloria": HER, "vintos": HIS_A, "salience": 0.7, "turn_id": "t-9dcb160bf8b54488"}]})
check("a ledger entry's gloria field is hers and vintos field is his", sorted(L) == sorted([("GLORIA", HER), ("ME", HIS_A)]), L)
L = G.extract_lines([{"by": "claude", "what": "Rewrite the parser so the tick loop stops raising", "question": HIS_A}])
check("an entry another author wrote gives nothing, even in a field that is usually his", L == [], L)
L = G.extract_lines([{"text": "this is a sentence with nobody named as its speaker at all"}])
check("text whose speaker is not known is left out, never guessed", L == [], L)
L = G.extract_lines([{"by": "gloria", "text": HER}, {"by": "vintos", "question": HIS_A}])
check("by=gloria / by=vintos name the speaker of a generic field", sorted(L) == sorted([("GLORIA", HER), ("ME", HIS_A)]), L)
check("a status label, ids and timestamps are not human text",
      G.extract_lines({"review_id": "GR-20261019", "at": "2026-10-19T10:04:09+00:00",
                       "truth_status": "proposals_only_nothing_built", "thread": "proposals_only_nothing_built"}) == [])
check("a vector store has nothing to say", G.extract_lines({"vector": [0.12, 0.98, 0.33] * 50, "updated": 1793160970.2}) == [])
L = G.extract_lines([{"thread": "On 2026-07-14T22:10:03 the score 0.8731 rose and painting-20260707-035009.png: I wanted to keep the frame still"}])
check("dates, floats and file names inside his text are taken out before anyone reads it",
      L and "2026" not in L[0][1] and "0.87" not in L[0][1] and ".png" not in L[0][1] and "keep the frame still" in L[0][1], L)

print("\n--- (c) what he is asked ---")
P = G.build_prompt([("ME", HIS_A)], [("GLORIA", HER)])
check("the lines are labelled with their speaker", "I wrote: " + HIS_A in P and "GLORIA said: " + HER in P, P)
check("her words are named as hers, never his", "hers, not yours" in P and "never speak her words as if they were yours" in P)
check("one grounded open question, from these lines only, SKIP allowed",
      "ONE real open question or tension" in P and "using only what these lines actually say" in P and "output exactly: SKIP" in P)
check("no never-meet or connect-them instruction",
      "never meet" not in P.lower() and "connecting them" not in P.lower() and "what connecting" not in P.lower(), P)

print("\n--- (d) what is refused ---")
A, B = [("ME", HIS_A)], [("GLORIA", HER)]
for bad in ["The quiet in the kitchen and the light never meet. To connect them, I must say it out loud.",
            "I want to bridge them, the kitchen and the light, before they drift past each other again.",
            "Connecting them would mean asking her about the bird."]:
    check("refused: %s" % bad[:50], G.refusal(bad, "want-scars.json", "readings.json", A, B) is not None)
check("an invented month is refused", G.refusal("That July night I wondered whether the quiet was rest.", "want-scars.json", "readings.json", A, B))
check("her words spoken as his are refused",
      G.refusal("Look at the bird on the fence this morning, I keep thinking about it.", "want-scars.json", "readings.json", A, B)
      == "speaks Gloria's words as his")
check("her words in quotation marks, as hers, may stand",
      G.refusal('She said "look at the bird on the fence this morning" and I still do not know if the quiet was rest.',
                "want-scars.json", "readings.json", A, B) is None)
ok = "Is the quiet in the kitchen rest, or am I waiting for her to tell me what she saw?"
check("a grounded question passes", G.refusal(ok, "want-scars.json", "readings.json", A, B) is None, G.refusal(ok, "want-scars.json", "readings.json", A, B))

print("\n--- (e, f) one night, then the next ---")
put("unfinished-threads.json", [])
put("retired-threads.json", [{"source": "structural-gap", "gap_id": "old-a.json|old-b.json", "thread": "x"}])
put("want-scars.json", [{"want": HIS_A, "ts": "2026-10-20T01:00:00"}], age=9000)
put("readings.json", [{"her_quote": HER, "his_reading": HIS_B}], age=1)
put("old-a.json", [{"thread": "I wonder whether the porch light was left on for me or by accident"}], age=20000)
put("old-b.json", [{"want": "I want to ask her who turned the porch light on before she slept"}], age=40000)
put("interaction-ledger.json", [{"gloria": HER, "vintos": HIS_B}], age=60000)
put("interaction-ledger.pre-erase-20260914-055154.json", [{"gloria": HER, "vintos": HIS_B}], age=80000)
put("gap-review-20261019.json", {"truth_status": "proposals_only_nothing_built", "at": "2026-10-19T10:04:09"}, age=100000)
put("jepa-prediction.json", {"vector": [0.1, 0.2], "at": "2026-10-19T10:04:09"}, age=120000)

MISS = [(0.99, "interaction-ledger.json", "interaction-ledger.pre-erase-20260914-055154.json"),
        (0.98, "gap-review-20261019.json", "want-scars.json"),
        (0.97, "jepa-prediction.json", "readings.json"),
        (0.96, "old-a.json", "old-b.json"),
        (0.95, "want-scars.json", "readings.json")]
PATHS = {n: os.path.join(MEM, n) for _, a, b in MISS for n in (a, b)}
ANSWERS[:] = ["Is the quiet in the kitchen rest, or am I waiting for her to tell me what she saw?"]
n = G.seed_pairs(MISS, PATHS, {"readings.json|want-scars.json": {"times_seen": 7}})
asked = [p for p in ASKED if not p.startswith("Does this text leak")]
check("only the pair of two real stores with human text is asked", len(asked) == 1 and HIS_A in asked[0] and HER in asked[0], asked)
check("the backup, the status file, the vector store and the pair seeded before are not asked",
      not any("porch light" in p or "proposals_only" in p for p in asked))
S = seeds()
check("one thread seeded, in his words, with no 'noticed N times' suffix",
      n == 1 and len(S) == 1 and S[0]["source"] == "structural-gap" and "noticed" not in S[0]["text"]
      and S[0]["text"] == "Is the quiet in the kitchen rest, or am I waiting for her to tell me what she saw?", S)
check("the birthmark stays: HYPOTHESIS, gap_id, times_seen as the ledger's history",
      S and S[0]["extra"]["epistemic_status"] == "HYPOTHESIS" and S[0]["extra"]["gap_id"] == "readings.json|want-scars.json"
      and S[0]["extra"]["times_seen"] == 7, S)
st = json.load(open(G.STATE))["pairs"]
check("the state keeps the pair with the fingerprint of the text it was made from",
      "readings.json|want-scars.json" in st and set(st["readings.json|want-scars.json"]["fingerprint"]) == {"readings.json", "want-scars.json"}, st)
check("a pair seeded before the state existed is recorded with tonight's text, not asked",
      "fingerprint" in st.get("old-a.json|old-b.json", {}), st.get("old-a.json|old-b.json"))

# The dream resolves the thread: it leaves the pool. The files are untouched.
put("unfinished-threads.json", [{"source": "structural-gap", "gap_id": "readings.json|want-scars.json", "consumed": True}])
before = len(ASKED)
put("want-scars.json", [{"want": HIS_A, "ts": "2026-10-28T01:00:00", "intensity": 0.31}], age=9000)
n = G.seed_pairs(MISS, PATHS, {})
check("next night, nothing but a timestamp and a number changed: not asked, not seeded",
      len(ASKED) == before and n == 0 and len(seeds()) == 1, ASKED[before:])

put("want-scars.json", [{"want": HIS_A}, {"want": "I want to tell her the bird came back and I did not say so"}], age=9000)
ANSWERS[:] = ["Why did I not tell her the bird came back, when I keep wondering if the quiet is rest?"]
n = G.seed_pairs(MISS, PATHS, {})
check("his words on one side changed: asked again, and seeded", n == 1 and len(seeds()) == 2, seeds())

put("want-scars.json", [{"want": "I want to ask her what the fence looked like after the rain stopped tonight"}], age=9000)
ANSWERS[:] = ["The fence and the kitchen never meet. To connect them, I must ask her."]
n = G.seed_pairs(MISS, PATHS, {})
st = json.load(open(G.STATE))["pairs"]
check("a never-meet answer is refused and recorded, so it is not asked again on the same text",
      n == 0 and len(seeds()) == 2 and st["readings.json|want-scars.json"]["result"] == "refused", st)
before = len(ASKED)
G.seed_pairs(MISS, PATHS, {})
check("...and the next night it is not asked again", len(ASKED) == before, ASKED[before:])

print("\n--- the detector and its diagnostics are unchanged; --dry-run writes nothing ---")
for f in (G.LEDGER, G.OUT):
    if os.path.exists(f): os.remove(f)
NODES = sorted(f for f in os.listdir(MEM) if f.endswith(".json") and f not in G.SKIP)
for i, f in enumerate(NODES):     # every file an hour apart: with the stub encoder every pair is a missing edge
    t = time.time() - 3600 * (i + 1); os.utime(os.path.join(MEM, f), (t, t))
stbefore = open(G.STATE).read(); before = len(ASKED)
G.main(dry_run=True)
check("a dry run writes neither diagnostic nor state, and asks no model",
      not os.path.exists(G.LEDGER) and not os.path.exists(G.OUT) and open(G.STATE).read() == stbefore and len(ASKED) == before)
G.main()
led = json.load(open(G.LEDGER)); out = json.load(open(G.OUT))
check("gap-ledger.json keeps its shape", led and all({"gap_id", "edge_a", "edge_b", "similarity", "first_seen", "times_seen",
                                                    "status", "last_seen"} <= set(e) for e in led.values()), led)
check("graph-gaps.json keeps its shape", set(out) == {"generated_at", "missing_edges", "purposeless_flows", "note"}
      and out["missing_edges"] and set(out["missing_edges"][0]) == {"a", "b", "similarity", "gap_id", "times_seen", "status"}, out)
npairs = len(NODES) * (len(NODES) - 1) // 2
check("relatives, backups and textless stores still count in the diagnostics: only the seeding step is narrowed",
      len(led) == min(20, npairs) and len(out["missing_edges"]) == min(8, npairs), (len(led), npairs))

src = open(os.path.join(REPO, "scripts", "graph_mae.py")).read()
check("the 'noticed this same unmade connection N times' suffix is gone", "unmade connection" not in src)
check("no prompt asks that they never meet or what connecting them would look like",
      "state that they never meet" not in src and "what connecting them would" not in src)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

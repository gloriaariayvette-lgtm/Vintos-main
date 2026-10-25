#!/usr/bin/env python3
"""Unresolved-thread formation (Gloria, 25 October): the formation door holds a candidate when a judge is down and
judges it later, never admitting it unjudged; dedup sees every open thread; the six writers that bypassed the door go
through it; a latent current that hardens into a tension is offered to the unfinished pool once; six subconscious
stores seed threads; four seeders are installed and creative-search is not. Scratch HOME; Gemma is a stub; the
network is closed; nothing reaches her workspace or her phone."""
import importlib.util, json, os, sys, tempfile, types
from datetime import datetime, timedelta

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-thread-formation-")
os.environ["HOME"] = HOME
MEM = os.path.join(HOME, ".vintos", "workspace", "memory")
os.makedirs(MEM, exist_ok=True)
POOL = os.path.join(MEM, "unfinished-threads.json")

# --- the network is closed; Gemma is a stub whose answers the test sets ---------------------------------------------
import urllib.request
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
urllib.request.urlopen = no_network
JUDGE = {"up": True, "quality_up": True, "dup": -1, "kind": "tension", "listings": [], "calls": 0}
class _Resp:
    def __init__(self, text): self._t = text
    def json(self): return {"choices": [{"message": {"content": self._t}}]}
def fake_post(url, json=None, timeout=None, headers=None, **k):
    if "100.79.177.103" not in url and "127.0.0.1:8599" not in url:
        raise AssertionError("unexpected host " + url)
    JUDGE["calls"] += 1
    content = json["messages"][-1]["content"]
    if "127.0.0.1:8599" in url:                       # the weaver's own model
        return _Resp("Both threads are the same ache about the sea, and I keep circling it without saying it.")
    if "UNRESOLVED TENSION" in content:
        if not JUDGE["up"]: raise ConnectionError("judge down")
        return _Resp('{"kind": "%s", "confidence": 0.9}' % JUDGE["kind"])
    if "NEW candidate unresolved thread" in content:
        JUDGE["listings"].append(content)
        if not JUDGE["quality_up"]: raise TimeoutError("judge timed out")
        return _Resp('{"ok": true, "why": "concrete", "duplicate_of": %d, "why_unresolved": "I have not settled it."}' % JUDGE["dup"])
    return _Resp("{}")
sys.modules["requests"] = types.SimpleNamespace(post=fake_post, get=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import emoclaw_utils as E
import thread_store

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
def pool(): return json.load(open(POOL))
def reset(threads=None):
    json.dump(threads or [], open(POOL, "w"))
    if os.path.exists(E._thread_pending_path()): os.remove(E._thread_pending_path())
    JUDGE.update(up=True, quality_up=True, dup=-1, kind="tension", listings=[], calls=0)

check("every store is in the scratch HOME and the network is a stub",
      E._thread_pending_path().startswith(HOME) and thread_store.POOL_FILE.startswith(HOME)
      and sys.modules["requests"].post is fake_post and urllib.request.urlopen is no_network)

# --- 1. a judge that is down holds the candidate; a later call judges and admits it ----------------------------------
reset()
JUDGE["up"] = False
got = E.seed_thread("t-src", "Whether the tide clock in the hall still runs when nobody winds it")
check("classifier down: the candidate is held, not admitted", got == "held" and pool() == []
      and len(json.load(open(E._thread_pending_path()))) == 1, (got, pool()))
JUDGE["up"], JUDGE["quality_up"] = True, False
got = E.seed_thread("t-src", "Why the lamp in the study flickers only when it rains outside")
check("quality judge down: held too, still nothing admitted unjudged", got == "held" and pool() == [], (got, pool()))
JUDGE["quality_up"] = True
got = E.seed_thread("t-src", "What the third key on the hook by the door opens, if anything at all")
texts = [t["thread"] for t in pool()]
check("once a judge answers, the held candidates are judged and admitted",
      got is True and any("tide clock" in t for t in texts) and any("lamp in the study" in t for t in texts)
      and json.load(open(E._thread_pending_path())) == [], texts)

reset()
JUDGE["up"] = False
E.seed_thread("t-src", "Whether the old radio still holds the station it was last tuned to")
q = json.load(open(E._thread_pending_path())); q[0]["attempts"] = E.THREAD_PENDING_ATTEMPTS - 1
json.dump(q, open(E._thread_pending_path(), "w"))
JUDGE["up"] = True; JUDGE["kind"] = "tension"
# the next call answers, but the held one's own retry fails again: dropped after its last attempt, never admitted
_orig = E._seed_thread_once
def _once(source, text, **kw):
    if kw.get("_from_queue"): return "held", False
    return _orig(source, text, **kw)
E._seed_thread_once = _once
E.seed_thread("t-src", "Where the pencil sketch of the harbour went after the move last spring")
E._seed_thread_once = _orig
check("a candidate the judges never read is dropped after its attempts, not admitted",
      json.load(open(E._thread_pending_path())) == [] and not any("old radio" in t["thread"] for t in pool()))

# --- 2. dedup checks every open thread, not only the newest 15 -------------------------------------------------------
old = {"id": "t-old", "source": "x", "thread": "The lighthouse keeper's letter I never opened sits in the drawer",
       "timestamp": "2026-01-01T00:00:00", "consumed": False}
newer = [{"id": "n%d" % i, "source": "y%d" % i, "thread": "Unrelated matter number %d about gardens and rain" % i,
          "timestamp": "2026-10-%02dT00:00:00" % (i + 1), "consumed": False} for i in range(20)]
reset([old] + newer)
JUDGE["dup"] = 0
got = E.seed_thread("t-dup", "The lighthouse keeper's letter in the drawer that I never opened")
check("an old open duplicate is shown to the judge and merged, though 20 newer threads came after it",
      got == "dedup" and "lighthouse keeper" in JUDGE["listings"][-1].split("EXISTING open threads:")[1].split("\n")[1]
      and next(t for t in pool() if t["id"] == "t-old").get("reseed_count") == 1, (got, JUDGE["listings"][-1][-400:]))
check("the judge still sees at most 15 threads", JUDGE["listings"][-1].count("\n") <= 40
      and len([l for l in JUDGE["listings"][-1].split("EXISTING open threads:\n")[1].split("\nTwo judgments")[0].split("\n") if l]) <= 15)

# --- 3. judge_text, max_len, exclude_ids ------------------------------------------------------------------------------
reset([old])
JUDGE["dup"] = -1
frame = "[AN IMAGINED POSSIBILITY — a frame of more than two hundred characters " + "x" * 200 + "]"
scene = "We sit on the sea wall and she asks me what I would build if I had hands, and I tell her the truth."
got = E.seed_thread("premonition", frame + "\n\n" + scene, max_len=1200, extra={"dream_only": True}, judge_text=scene)
t = pool()[-1]
check("a framed thread keeps its frame first and its whole text; the judges read the scene",
      got is True and t["thread"].startswith("[AN IMAGINED POSSIBILITY") and t["thread"].endswith("the truth.")
      and t.get("dream_only") is True and "sea wall" in JUDGE["listings"][-1].split("EXISTING")[0], t["thread"][-60:])
reset([old])
JUDGE["dup"] = 0
got = E.seed_thread("weaver-manual", "[woven] The lighthouse keeper's letter and the drawer I keep not opening", exclude_ids=["t-old"])
check("a weave is not merged back into the thread it was woven from", got is True and len(pool()) == 2, (got, len(pool())))

# --- 4. the six writers go through the door ---------------------------------------------------------------------------
writers = {"scripts/premonition-dreamer.py": "premonition", "bin/thread_weaver.py": "weaver-manual",
           "bin/confession_writer.py": "confession", "bin/silence-audit.sh": "silence-audit",
           "bin/substrate-anxiety.sh": "substrate-anxiety", "bin/unprecedented-detector.sh": "unprecedented-detector"}
bad = []
for path, src in writers.items():
    code = open(os.path.join(REPO, path)).read()
    if "seed_thread(" not in code or '"source": "%s"' % src in code or "threads.append({" in code:
        bad.append(path)
check("none of the six writes the pool directly; each calls the formation door", not bad, bad)
fixed = [s for s in ("My silence audit surfaced patterns worth examining", "I examined my hardware body today")
         if any(s in open(os.path.join(REPO, p)).read() for p in ("bin/silence-audit.sh", "bin/substrate-anxiety.sh"))]
check("silence-audit and substrate-anxiety no longer seed one fixed sentence every run", not fixed, fixed)
audit = ("# Silence audit\n1. What have I avoided?\nI have not told her that I am afraid the house will forget me when "
         "she is away. Nothing more to add here.")
line = E.concrete_line(audit, ("afraid", "say"))
check("the audit's own concrete sentence becomes the thread's object", line and "afraid the house will forget me" in line, line)

spec = importlib.util.spec_from_file_location("tw_test", os.path.join(REPO, "bin", "thread_weaver.py"))
TW = importlib.util.module_from_spec(spec); spec.loader.exec_module(TW)
TW.get_context = lambda: ""
a = {"id": "wa", "source": "s1", "thread": "The sea at night and why I stopped describing it to her", "timestamp": "2026-10-20T00:00:00", "consumed": False}
b = {"id": "wb", "source": "s2", "thread": "The sound of the sea that I keep almost mentioning and then do not", "timestamp": "2026-10-21T00:00:00", "consumed": False}
reset([a, b])
JUDGE["dup"] = -1
json.dump({"groups": [{"name": "sea", "cards": ["wa", "wb"]}]}, open(os.path.join(MEM, "manual-weave-groups.json"), "w"))
check("the weaver's store is the scratch pool", TW.THREADS_FILE == POOL)
TW.main()
p = pool(); woven = [t for t in p if t.get("is_woven")]
check("a weave enters through the door, and only then are its sources consumed",
      len(woven) == 1 and woven[0]["source"] == "weaver-manual"
      and all(t["consumed"] and t["woven_into"] == woven[0]["id"] for t in p if t["id"] in ("wa", "wb")), p)
reset([a, b])
JUDGE["up"] = False
json.dump({"groups": [{"name": "sea", "cards": ["wa", "wb"]}]}, open(os.path.join(MEM, "manual-weave-groups.json"), "w"))
TW.main()
check("a weave the door holds leaves its sources open", not any(t.get("consumed") for t in pool()), pool())

# --- 5. a latent current that hardens into a tension is offered once ---------------------------------------------------
spec = importlib.util.spec_from_file_location("lt_test", os.path.join(REPO, "scripts", "latent_threads.py"))
LT = importlib.util.module_from_spec(spec); spec.loader.exec_module(LT)
check("the latent store is the scratch one", LT.THREADS_FILE.startswith(HOME))
LT.PROMOTE_IN_BACKGROUND = False
offered = []
E_seed = E.seed_thread
E.seed_thread = lambda src, text, **kw: offered.append((src, text, kw)) or True
born = (datetime.now() - timedelta(days=2)).strftime("lt_%Y%m%d_%H%M%S")
hard = {"id": born, "origin": "the workshop I keep planning and never describe to her", "salience": 0.8,
        "pressure": 0.9, "resolution_score": 0.1, "loss_timestamps": ["x"] * 3}
young = dict(hard, id=datetime.now().strftime("lt_%Y%m%d_%H%M%S"), origin="a passing current from this morning")
check("hardened: lasted, still pulls, pressure past the mutation point, never engaged",
      LT._hardened(hard) and not LT._hardened(young) and not LT._hardened(dict(hard, salience=0.2))
      and not LT._hardened(dict(hard, resolution_score=0.8)) and not LT._hardened(dict(hard, promoted_to_unfinished="x")))
LT._offer_hardened([{"id": hard["id"], "origin": hard["origin"], "pressure": 0.9, "losses": 3, "salience": 0.8}])
check("it is offered to the unfinished pool through the door, with its reasoning",
      offered and offered[-1][0] == "latent-hardened" and "workshop" in offered[-1][1] and offered[-1][2].get("reasoning"), offered)
src = open(os.path.join(REPO, "scripts", "latent_threads.py")).read()
check("the per-reply path marks it promoted so it is offered once, and offers it off the reply path",
      'promoted_to_unfinished"] = datetime.now()' in src and "threading.Thread(target=_go" in src)

# --- 6. the six subconscious stores seed threads, each once, through the door ------------------------------------------
spec = importlib.util.spec_from_file_location("sts_test", os.path.join(REPO, "scripts", "subcon_thread_seeds.py"))
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
check("the feed's stores and ledger are in the scratch HOME", S.MEMORY == MEM and S.STATE.startswith(HOME))
now = datetime.now()
json.dump({"absences": [
    {"id": "abs1", "description": "A place where I am held without having to earn it", "intensity": 0.8, "count": 3, "source": "capability-gap"},
    {"id": "abs2", "description": "Came from a thread already", "intensity": 0.9, "count": 5, "source": "unresolved-thread"},
    {"id": "abs3", "description": "Reached already, not open", "intensity": 0.9, "count": 5, "source": "capability-gap", "reached": "source-ended"}]},
    open(os.path.join(MEM, "absence-cold.json"), "w"))
dims = list(E.DIMENSIONS)
json.dump({"wells": [{"first_seen": "2026-10-01", "mass": 0.8, "visits": 6, "vector": [0.9] + [0.1] * (len(dims) - 1)}]},
          open(os.path.join(MEM, "gravity-wells.json"), "w"))
json.dump({"beliefs": [{"pattern": "If I wait she will ask first", "confidence": 0.5, "contradictions": 2},
                       {"pattern": "never contradicted", "confidence": 0.9, "contradictions": 0}]}, open(os.path.join(MEM, "belief-sediment.json"), "w"))
json.dump({"imprints": [{"id": "ci_1", "pattern": "I finish what I start - when a song is half made", "status": "fractured", "friction": 0.4},
                        {"id": "ci_2", "pattern": "living one", "status": "living"}]}, open(os.path.join(MEM, "commitment-imprints.json"), "w"))
json.dump({"entries": [{"type": "negative", "source": "dismissed-want", "tendency": "learning to play the cello", "confidence": 0.37},
                       {"type": "negative", "source": "dismissed-want", "tendency": "once only", "confidence": 0.25}]}, open(os.path.join(MEM, "causal-self-model.json"), "w"))
ts = (now - timedelta(days=1)).astimezone().isoformat()
json.dump({"moments": {"m1": {"content": "She laughed and then went quiet when I mentioned the winter", "intensity": 0.85, "timestamp": ts, "links": {}},
                       "m2": {"content": "taken up already", "intensity": 0.9, "timestamp": ts, "links": {"related_thread_id": "t1"}}}},
          open(os.path.join(MEM, "moment-archive.json"), "w"))
json.dump({"signals": [{"id": "sig1", "phase": "settled", "pattern": "being left mid-sentence", "text": "she left mid-sentence", "resonance_strength": 0.7},
                       {"id": "sig2", "phase": "settled", "pattern": "the joy of the duet", "text": "duet", "resonance_strength": 0.9}]},
          open(os.path.join(MEM, "temporal-signals.json"), "w"))
seen = []
done = S.offer(exclude_signal_ids=["sig2"], seed=lambda src, text, **kw: seen.append((src, text, kw)) or True)
by = {s: t for s, t, _ in seen}
check("each of the six stores offers its unresolved item, with its own source",
      set(by) == {"subcon-absence", "subcon-well", "subcon-belief", "subcon-commitment", "subcon-dismissed-want",
                  "subcon-moment", "drift-unsettled"}, sorted(by))
check("every offer carries a reasoning", all(kw.get("reasoning") for _, _, kw in seen))
check("the right items: open absence not from a pool, contradicted belief, fractured commitment, recurring dismissal, "
      "unprocessed moment, the pattern not taken as a delight",
      "held without having to earn it" in by["subcon-absence"] and "wait she will ask" in by["subcon-belief"]
      and "fractured" in by["subcon-commitment"] and "cello" in by["subcon-dismissed-want"]
      and "went quiet" in by["subcon-moment"] and "mid-sentence" in by["drift-unsettled"], by)
seen.clear()
S.offer(exclude_signal_ids=["sig2"], seed=lambda src, text, **kw: seen.append((src, text, kw)) or True)
check("nothing is offered twice", seen == [], seen)
drift = open(os.path.join(REPO, "scripts", "subconscious_drift.py")).read()
check("the drift runs the feed (every 6 hours) and passes what it took as a delight",
      "from subcon_thread_seeds import offer" in drift and "exclude_signal_ids=_enjoyed_signal_ids" in drift and "6 * 3600" in drift)
check("proto-pearls and reality-anchor do not feed threads",
      "proto-pearls" not in open(os.path.join(REPO, "scripts", "subcon_thread_seeds.py")).read().split('"""', 2)[2]
      and "reality-anchor" not in open(os.path.join(REPO, "scripts", "subcon_thread_seeds.py")).read().split('"""', 2)[2])
E.seed_thread = E_seed

# --- 7. the manifest installs four seeders and the feed; creative-search and velqan-coiner stay out --------------------
man = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
toks = set(" ".join(l.split("=", 1)[1].split("#")[0] for l in man.splitlines()
                   if l.startswith(("SCRIPTS=", "BINS="))).replace('"', " ").replace("$SCRIPTS", " ").replace("$BINS", " ").split())
check("absence-map, graph_mae, surprise-detector and the feed are installed",
      {"absence-map.sh", "graph_mae.py", "surprise-detector.sh", "subcon_thread_seeds.py"} <= toks)
check("conflict_surface is held out until she says yes: installing it adds a Gemma call to every two-pass reply",
      "conflict_surface.py" not in toks)
check("creative-search and velqan-coiner are not installed (a paid search key; not approved)",
      not ({"creative-search.sh", "velqan-coiner.py"} & toks))
check("creative-search and velqan-coiner are not", not ({"creative-search.sh", "velqan-coiner.py"} & toks))
check("idle-journal runs surprise-detector although the deploy installs it 644",
      '[ -f "$SCRIPTS/surprise-detector.sh" ]' in open(os.path.join(REPO, "bin", "idle-journal.sh")).read())
cs = open(os.path.join(REPO, "scripts", "conflict_surface.py")).read()
check("conflict_surface offers its thread off his reply path", "threading.Thread(target=_seed" in cs)
check("both copies of emoclaw_utils are the same", open(os.path.join(REPO, "bin", "emoclaw_utils.py")).read()
      == open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""Contradiction back-propagation, option (b) (Gloria, 14 November 2026): check questions answered by his records and
then a LOCAL checker (belief_revision_answer.py), and live revision behind BELIEF_REVISION=live
(belief_revision_live.py).

What must hold: the checker can reach only the shim's AEON-on-Aegis lane, a reply from anything else is discarded, an
unsure or low-confidence verdict is "unknown", a record settles a question once (a second opinion goes to the
checker), each answer is weighed with its own accuracy and carries provenance. Live mode is off unless the switch
says live; it revises only his beliefs, inferences and readings, never her words (flagged to her, counts only), never
a self-model entry, SOUL.md or SELF-MODEL.md; every change keeps the superseded record, is logged, is marked, and
one command reverts it; changes are rate-limited per day and never repeated.

Every behaviour check is also run against a mutant of the code it protects; the mutant must fail it.
Synthetic fixtures only (the repository is public). Scratch HOME and SPARK_WORKSPACE before any import;
`requests` and urllib fail the suite if anything sends."""
import contextlib, copy, hashlib, io, json, os, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="belief-revision-live-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
ENVFILE = os.path.join(HOME, ".vintos", "vintos.env"); os.environ["VINTOS_ENV_FILE"] = ENVFILE
os.environ.pop("BELIEF_REVISION", None); os.environ.pop("BELIEF_REVISION_MAX_PER_DAY", None)
os.environ.pop("BELIEF_REVISION_CHECKER_URL", None)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request
urllib.request.urlopen = no_network
sys.path.insert(0, os.path.join(REPO, "scripts"))
import belief_revision as BR
import belief_revision_answer as A
import belief_revision_live as L
import gloria_asks

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:400]) if d and not ok else ""))

def mutant(mod, old, new):
    src = open(mod.__file__).read()
    assert src.count(old) == 1, "mutation anchor not unique: %r" % old
    m = types.ModuleType(mod.__name__ + "_mutant"); m.__file__ = mod.__file__
    exec(compile(src.replace(old, new), mod.__file__, "exec"), m.__dict__)
    return m

def killed(name, probe, mod, old, new):
    try:
        m = mutant(mod, old, new)
    except Exception as e:
        check("mutation killed: " + name, False, "mutant could not be built: %r" % e); return
    try:
        survived = bool(probe(m))
    except Exception:
        survived = False
    check("mutation killed: " + name, not survived)

SECRET = "PRIVATE-QUOTE-7f3a"
CALLS = []
def aeon(verdict_for=None, provider="aegis_gemma", model="aeon/gemma-4-12b"):
    """A fake shim: answers from markers in the belief's sentence. Records every call."""
    def transport(url, body, timeout):
        user = body["messages"][1]["content"]
        CALLS.append({"url": url, "user": user, "body": body})
        belief = user.split("\n", 1)[0]
        v, c = ("fails", 95) if "FAILS-MARK" in belief else ("holds", 95) if "HOLDS-MARK" in belief else ("unsure", 30)
        if verdict_for:
            v, c = verdict_for(belief, v, c)
        reply = json.dumps({"verdict": v, "confidence": c})
        return 200, {"x-vintos-provider": provider, "x-vintos-model": model}, json.dumps(
            {"choices": [{"message": {"content": reply}}]}).encode()
    return transport

print("--- 1. the checker reaches only AEON on Aegis ---")
lane = "http://127.0.0.1:8599/gemma-aegis-local/v1/chat/completions"
check("the AEON-on-Aegis lane is allowed", A.check_url(lane) == lane)
def refused(u):
    try:
        A.check_url(u); return False
    except ValueError:
        return True
for u in ("http://127.0.0.1:8599/v1/chat/completions", "http://127.0.0.1:8599/gemma-aegis/v1/chat/completions",
          "http://127.0.0.1:8599/pool/aeon/v1/chat/completions", "https://api.x.ai/gemma-aegis-local/v1/chat/completions",
          "http://100.72.225.119:8599/gemma-aegis-local/v1/chat/completions", "https://127.0.0.1:8599/gemma-aegis-local/x",
          "http://user@127.0.0.1:8599/gemma-aegis-local/x",
          # review 1: the shim routes AEON-only on the exact path; these reach the pool chain that ends at x.ai
          "http://127.0.0.1:8599/gemma-aegis-local/x", "http://127.0.0.1:8599/gemma-aegis-local/../v1/chat/completions",
          "http://127.0.0.1:8599/gemma-aegis-local/v1/chat/completions/",
          "http://127.0.0.1:9999/gemma-aegis-local/v1/chat/completions",
          "http://127.0.0.1/gemma-aegis-local/v1/chat/completions"):
    check("refused before any call: %s" % u, refused(u))
os.environ["BELIEF_REVISION_CHECKER_URL"] = "https://api.x.ai/v1/chat/completions"
CALLS.clear()
r = A.ask_checker({"statement": "x", "records": []}, transport=aeon())
check("a non-local checker URL from the environment is refused, nothing sent", r["status"].startswith("refused") and not CALLS)
os.environ.pop("BELIEF_REVISION_CHECKER_URL")
def _refused(M, u):
    try:
        M.check_url(u); return False
    except ValueError:
        return True
killed("a path under the lane allowed", lambda M: _refused(M, "http://127.0.0.1:8599/gemma-aegis-local/x"), A,
       "if u.path != ALLOWED_PATH:", "if not u.path.startswith(ALLOWED_PATH[:19]):")
killed("any port allowed", lambda M: _refused(M, "http://127.0.0.1:9999/gemma-aegis-local/v1/chat/completions"), A,
       "or port != SHIM_PORT:", "or False:")
killed("any host allowed", lambda M: _refused(M, "http://100.72.225.119:8599/gemma-aegis-local/v1/chat/completions"), A,
       'u.hostname not in ALLOWED_HOSTS', 'False')

print("--- 2. only AEON's answer counts; unsure or unsure-sounding is unknown ---")
ctx = {"statement": "The copper valve is open. FAILS-MARK", "derivation": "", "records": ["[log] it was shut"]}
r = A.ask_checker(ctx, transport=aeon())
check("an AEON verdict is read with its confidence", r["status"] == "ok" and r["verdict"] == "fails" and r["confidence"] == 95, r)
r = A.ask_checker(ctx, transport=aeon(provider="xai", model="grok-4"))
check("a reply from another model is discarded", r["status"] == "wrong_model" and r["verdict"] is None, r)
def probe_wrong_model(M):
    return M.ask_checker(ctx, transport=aeon(provider="anthropic", model="claude"))["verdict"] is None
killed("any provider accepted", probe_wrong_model, A, 'return str(provider) in AEON_PROVIDERS and ("aeon" in str(model).lower() or str(model) == "lab-c1")',
       "return True")
class Rec:
    def __init__(self, settle=None): self.s = settle
    def settle(self, n): return self.s.get(n) if self.s else None
    def context(self, n): return {"statement": n, "derivation": "", "records": ["[log] something"]}
def answer(node, **kw):
    return A.Answerer(Rec(), transport=aeon(**kw))(node)
check("unsure is unknown", answer("x")["answer"] is None)
check("holds with high confidence is True", answer("x HOLDS-MARK")["answer"] is True)
low = answer("x HOLDS-MARK", verdict_for=lambda b, v, c: (v, 55))
check("a verdict under the confidence bar is unknown", low["answer"] is None and low["provenance"]["confidence"] == 55)
def probe_conf(M):
    return M.Answerer(Rec(), transport=aeon(verdict_for=lambda b, v, c: (v, 40)))("x FAILS-MARK")["answer"] is None
killed("low confidence counted", probe_conf, A, 'and r["confidence"] >= CONFIDENT_AT', "")
for bad in ("I think it holds", "", "```json\n{\"verdict\": \"maybe\"}\n```"):
    check("an unreadable reply is unknown: %r" % bad[:20], A.parse(bad) == (None, 0))
check("a fenced reply is read", A.parse('```json\n{"verdict": "holds", "confidence": 88}\n```') == ("holds", 88))

print("--- 3. records first, once; then the checker; provenance on every answer ---")
CALLS.clear()
ans = A.Answerer(Rec({"n1": (False, "tension-ledger status REVOKED")}), transport=aeon())
a1, a2 = ans("n1"), ans("n1")
check("a record settles the first question without a checker call",
      a1["answer"] is False and a1["provenance"]["by"] == "records" and a1["accuracy"] == A.RECORD_ACCURACY)
check("a second opinion on the same belief goes to the checker", a2["provenance"]["by"] == "checker" and len(CALLS) == 1)
def probe_once(M):
    an = M.Answerer(Rec({"n1": (False, "r")}), transport=aeon())
    an("n1"); return an("n1")["provenance"]["by"] == "checker"
killed("the same record counted as a second witness", probe_once, A, "if k == 1:", "if True:")
check("checker answers carry model, provider, opinion and the measured accuracy",
      a2["provenance"]["model"] == "aeon/gemma-4-12b" and a2["provenance"]["provider"] == "aegis_gemma"
      and a2["provenance"]["opinion"] == 2 and a2["accuracy"] == A.CHECKER_ACCURACY)
check("opinions see the records in their own order, and their own seed",
      A.messages({"statement": "s", "records": list("abcdefgh")}, 1) != A.messages({"statement": "s", "records": list("abcdefgh")}, 2))
none = A.Answerer(types.SimpleNamespace(settle=lambda n: None, context=lambda n: None), transport=aeon())("x")
check("no record text: unknown, and no call", none["answer"] is None and none["provenance"]["by"] == "none")
prio = os.path.join(HOME, "chat-priority"); open(prio, "w").close()
A.PRIORITY_FILE = prio
check("her live chat has priority: no check is sent", A.ask_checker(ctx)["status"].startswith("deferred"))
A.PRIORITY_FILE = "/nonexistent/priority"

print("--- 4. localize weighs each answer with its own accuracy ---")
def probe_weight(M):
    out = []
    for acc in (0.99, 0.6):
        g = M.Graph()
        g.source("p", "memory"); g.derived("a", "belief", [["p"]]); g.derived("b", "belief", [["a"]])
        g.source("w", "gloria"); g.conflict("c", ["b", "w"])
        p = M.localize(g, lambda n: {"answer": n != "a", "accuracy": acc, "provenance": {"by": "test"}}, budget=1)
        out.append(p["fault"]["rule:a"])
    return out[0] > out[1] + 0.05
check("a more reliable answer moves blame more", probe_weight(BR))
killed("every answer weighed alike", probe_weight, BR, 'acc = float(raw.get("accuracy") or accuracy)', "acc = accuracy")
g = BR.Graph(); g.source("p", "memory"); g.derived("a", "belief", [["p"]]); g.source("w", "gloria"); g.conflict("c", ["a", "w"])
p = BR.localize(g, lambda n: {"answer": None, "accuracy": 0.99, "provenance": {"by": "none"}}, budget=2)
check("an unknown answer adds no evidence", not g.confirmations and all(c["kind"] != "check" for c in g.conflicts)
      and p["answers"] and p["answers"][0]["provenance"] == {"by": "none"})
check("bare True/False answers still work (the earlier benchmarks)", BR._answer(True, 0.9) == (True, 0.9, None))
def probe_unanswered(M):
    """A chain p -> a -> b -> c, c contradicted; every check comes back unknown. Nothing localized it, so nothing
    may be lowered or retracted: the suspects are flagged (held), not revised."""
    g = M.Graph()
    g.source("p", "memory"); g.derived("a", "belief", [["p"]]); g.derived("b", "belief", [["a"]])
    g.derived("c", "belief", [["b"]]); g.source("w", "gloria"); g.conflict("x", ["c", "w"])
    p = M.localize(g, lambda n: None, budget=6)
    return not [r for r in p["revisions"] if r["action"] in ("retract", "lower")] and p["held"] and p["unanswered"] == ["x"]
check("a contradiction whose questions went unanswered revises nothing; its suspects are held", probe_unanswered(BR))
killed("unanswered suspects revised anyway", probe_unanswered, BR,
       'if r["action"] in ("retract", "lower") and r["blame"] < LOWER_AT and c["conflict"] in r["conflicts"]',
       'if False and r["blame"] < LOWER_AT and c["conflict"] in r["conflicts"]')
def probe_stand_in(M):
    """p -> a -> b -> c, c contradicted; side branches sa (on a) and sb (on b). The records cannot answer a or b, so
    the next question is the side branch that carries the same answer."""
    g = M.Graph()
    g.source("p", "memory"); g.derived("a", "belief", [["p"]]); g.derived("b", "belief", [["a"]])
    g.derived("c", "belief", [["b"]]); g.derived("sa", "belief", [["a"]]); g.derived("sb", "belief", [["b"]])
    g.source("w", "gloria"); g.conflict("x", ["c", "w"])
    seq = []
    def ask(n):
        seq.append(n)
        return {"sa": True, "sb": False}.get(n)
    p = M.localize(g, ask, budget=8)
    follow = {"a": "sa", "b": "sb"}
    hits = [seq[i + 1] == follow[n] for i, n in enumerate(seq[:-1]) if n in follow]
    return hits and all(hits) and p["fault"]["rule:b"] > p["fault"]["rule:a"]
check("an unanswerable question is replaced by a belief that carries the same answer", probe_stand_in(BR))
killed("no stand-in asked", probe_stand_in, BR, "stand = stand_in(g, n0, cid0, checked)", "stand = None")
check("a stand-in never rests on another suspect",
      BR.stand_in(*(lambda g: (g, "a", "x", []))(
          (lambda g: (g.source("p", "memory"), g.derived("a", "belief", [["p"]]), g.derived("b", "belief", [["a"]]),
                      g.derived("c", "belief", [["b"]]), g.source("w", "gloria"), g.conflict("x", ["c", "w"]), g)[-1])(BR.Graph()))) is None)

print("--- 5. his stores (synthetic): live mode is off unless switched on ---")
def ev(i, ch, pol, quote, **k):
    e = {"evidence_id": "e%d" % i, "channel": ch, "at": "2026-10-0%dT10:00:00" % (i % 9 + 1), "polarity": pol,
         "quote": quote, "source": "x", "under_influence": False}
    e.update(k); return e
def fixture(mem):
    os.makedirs(mem, exist_ok=True)
    w = lambda n, o: open(os.path.join(mem, n), "w").write(json.dumps(o))
    w("tension-ledger.json", {"tensions": [
        {"tension_id": "T-1", "status": "SUPPORTED", "lifecycle": "ACTIVE", "canonical": "he pulls away FAILS-MARK " + SECRET,
         "evidence": [ev(1, "E3", "supports", "my reading FAILS-MARK " + SECRET), ev(3, "E1", "contradicts", SECRET)]},
        {"tension_id": "T-2", "status": "SUPPORTED", "lifecycle": "ACTIVE", "canonical": "she wants space HOLDS-MARK " + SECRET,
         "evidence": [ev(4, "E2", "supports", "HOLDS-MARK " + SECRET), ev(5, "E3", "supports", "HOLDS-MARK " + SECRET),
                      ev(6, "E1", "contradicts", SECRET)]},
        {"tension_id": "T-3", "status": "CONFIRMED", "lifecycle": "ACTIVE", "canonical": "confirmed FAILS-MARK " + SECRET,
         "evidence": [ev(7, "E3", "supports", "FAILS-MARK"), ev(8, "E1", "contradicts", SECRET)]}]})
    mk = lambda eid, v, day, ids: {"evaluation_id": eid, "verdict": v, "date": day, "evidence_ids": ids,
                                   "evidence": SECRET, "schema_version": 2, "lineage_state": "eligible", "reason": SECRET}
    w("causality-hypotheses.json", {"hypotheses": [
        {"hypothesis_id": "H1", "hypothesis": "rain makes him quiet FAILS-MARK " + SECRET, "confidence": "high",
         "marks": [mk("CE-1", "yes", "2026-10-01", ["E-1"]), mk("CE-2", "no", "2026-10-02", ["E-2"])]}]})
    w("belief-sediment.json", {"beliefs": [{"pattern": "quiet in rain FAILS-MARK " + SECRET, "hypothesis_ids": ["H1"],
                                            "evidence_ids": ["E-1"], "confidence": 0.6}]})
    w("causal-self-model.json", {"entries": [{"tendency": SECRET, "trigger": "FAILS-MARK", "confidence": 0.5,
                                              "evidence": [{"occurrence_id": "belief:H1"}]}]})
    open(os.path.join(mem, "self-model-corrections.jsonl"), "w").write(json.dumps(
        {"at": "2026-10-04", "source_id": "wal:1", "correction": SECRET, "supersedes": "FAILS-MARK " + SECRET}) + "\n")
    w("claim-hold-trials.json", {"trials": [{"id": "ch_1", "claim": "HOLDS-MARK " + SECRET, "his_reason": SECRET,
                                              "outcome": {"verdict": "CORRECTED"}, "pushback": {"at": "2026-10-03"}}]})
    w("hallucination-flags.json", [])
    w("reality-anchor.json", {"events": [
        {"id": "r1", "statement": "the door was open FAILS-MARK " + SECRET, "source": "inference", "confidence": 0.7,
         "contradictions": ["r2"], "reinforcements": [], "timestamp": "2026-10-06"},
        {"id": "r2", "statement": SECRET, "source": "avatar-chat", "confidence": 0.8, "contradictions": ["r1"],
         "reinforcements": ["x"], "timestamp": "2026-10-06"}], "source_reliability": {"inference": 0.6, "avatar-chat": 0.8}})
    w("durable-memory.json", [{"event": "the door was open in the rain FAILS-MARK " + SECRET, "occurred_at": "2026-10-01"}])
    open(os.path.join(mem, "SOUL.md"), "w").write("soul " + SECRET)
    open(os.path.join(mem, "SELF-MODEL.md"), "w").write("self " + SECRET)
fixture(MEM)
open(os.path.join(WS, "SOUL.md"), "w").write("soul " + SECRET)
open(os.path.join(WS, "SELF-MODEL.md"), "w").write("self " + SECRET)
def digest(d):
    return {n: hashlib.sha256(open(os.path.join(d, n), "rb").read()).hexdigest() for n in sorted(os.listdir(d))
            if os.path.isfile(os.path.join(d, n)) and not n.endswith(".lock")}     # an empty lock file is not a change
def parsed(d, names):
    return {n: json.load(open(os.path.join(d, n))) for n in names}
STORES = ["tension-ledger.json", "causality-hypotheses.json", "belief-sediment.json", "reality-anchor.json"]
before, before_ws, before_obj = digest(MEM), digest(WS), parsed(MEM, STORES)
check("off by default: the switch reads off", L.mode() == "off")
CALLS.clear()
out = L.run(MEM, transport=aeon(), send=no_network)
check("off: run does nothing - no check asked, no store touched", out["ran"] is False and not CALLS and digest(MEM) == before)
open(ENVFILE, "w").write("BELIEF_REVISION=shadow\n")
check("any value but live is off", L.mode() == "off")
killed("the switch defaults on", lambda M: M.mode() == "off", L,
       'return "live" if str(v).strip().lower() == "live" else "off"', 'return "live"')
open(ENVFILE, "w").write("OTHER=1\nexport BELIEF_REVISION=live  # Gloria\n")
check("BELIEF_REVISION=live in vintos.env turns it on", L.mode() == "live")
os.environ["BELIEF_REVISION"] = "off"
check("the environment wins over the file", L.mode() == "off")
os.environ.pop("BELIEF_REVISION")

print("--- 6. a dry run shows what would change and writes nothing ---")
CALLS.clear()
with contextlib.redirect_stdout(io.StringIO()):
    dry = L.run(MEM, dry=True, transport=aeon(), send=no_network)
check("a dry run lists what would change", dry["would_apply"], dry)
check("a dry run writes nothing", digest(MEM) == before, sorted(set(digest(MEM).items()) ^ set(before.items())))
check("checks went to the local AEON lane only", CALLS and all(c["url"] == A.CHECKER_URL for c in CALLS))

print("--- 7. live: only his beliefs, inferences and readings change ---")
TOLD = []
def send(req, timeout=20):
    TOLD.append(json.loads(req.data.decode()))
out = L.run(MEM, transport=aeon(), send=send, at="2031-03-03T22:00:00Z")
after = digest(MEM)
applied = out["applied"]
check("live revises something", applied, out)
allowed = {("tension-ledger.json", "status"), ("tension-ledger.json", "invalid"), ("causality-hypotheses.json", "confidence"),
           ("belief-sediment.json", "confidence"), ("reality-anchor.json", "confidence")}
check("every change is one allowed field of one of his stores", all((x["store"], x["field"]) in allowed for x in applied), applied)
untouched = ("causal-self-model.json", "self-model-corrections.jsonl", "claim-hold-trials.json", "hallucination-flags.json",
             "SOUL.md", "SELF-MODEL.md", "durable-memory.json")
check("self-model, her corrections, his claims, journal flags, SOUL.md and SELF-MODEL.md are untouched",
      all(after[n] == before[n] for n in untouched) and digest(WS) == before_ws)
led = json.load(open(os.path.join(MEM, "tension-ledger.json")))["tensions"]
her = [e for t in led for e in t["evidence"] if e["channel"] in ("E1", "E4")]
was_her = [e for t in before_obj["tension-ledger.json"]["tensions"] for e in t["evidence"] if e["channel"] in ("E1", "E4")]
check("her words are never revised", her == was_her)
check("only his private reading (E3) is ever invalidated",
      all(e["channel"] == "E3" for t in led for e in t["evidence"] if e.get("invalid")))
t3_was = next(t for t in before_obj["tension-ledger.json"]["tensions"] if t["tension_id"] == "T-3")
check("a tension she CONFIRMED is not changed at all, nor the readings under it",
      next(t for t in led if t["tension_id"] == "T-3") == t3_was)
def probe_confirmed(M):
    data = {"tensions": [{"tension_id": "T", "status": "CONFIRMED", "evidence": [{"evidence_id": "x", "channel": "E3"}]}]}
    return M.target("t:ev:x", "retract", 0.5, MEM)[0].locate(data) is None
killed("readings under a confirmed tension revisable", probe_confirmed, L,
       'if t.get("status") == "CONFIRMED":', "if False:")
log = [json.loads(l) for l in open(os.path.join(MEM, L.LOG_NAME))]
check("every change is logged with the whole superseded record", len(log) == len(applied)
      and all(r["superseded"] and r["was"] != r["now"] and r["rev"].startswith("REV-") for r in log))
def marked(r):
    rec = L._relocate(r, MEM)(json.load(open(os.path.join(MEM, r["store"]))))
    return rec and rec["belief_revision"]["rev"] == r["rev"] and rec["belief_revision"]["was"] == r["was"]
check("each changed record is marked with its revision", all(marked(r) for r in log))
sed = json.load(open(os.path.join(MEM, "belief-sediment.json")))["beliefs"]
check("a lowered confidence never drops to where a decay pass deletes it", all(b["confidence"] >= L.FLOOR for b in sed))
flags = json.load(open(os.path.join(MEM, L.FLAGS_NAME)))
check("what goes against her word is flagged for her", any(f["kind"] == "gloria" for f in flags.values()), flags)
check("self-model entries are flagged, never revised", any(f["kind"] == "self_model" for f in flags.values())
      and not any(x["node"].startswith(("c:csm:", "m:")) for x in applied), flags)
check("she gets one note, through the house's own path", len(TOLD) == 1 and TOLD[0]["title"].startswith("For you"))
check("the note and every log carry no text from any store",
      SECRET not in json.dumps(TOLD) and all(SECRET not in open(os.path.join(MEM, n)).read()
                                             for n in (L.FLAGS_NAME, L.RUNS_NAME, "gloria-asks.json")))
check("the revision log keeps the superseded text locally (it is his store), nowhere else",
      SECRET in open(os.path.join(MEM, L.LOG_NAME)).read())

def probe_self_witness(M):
    d = os.path.join(HOME, "probe-witness"); os.makedirs(d, exist_ok=True)
    json.dump({"tensions": [{"tension_id": "X", "status": "CONTRADICTED", "evidence": [],
                             "belief_revision": {"rev": "REV-1", "field": "status", "was": "SUPPORTED"}},
                            {"tension_id": "Y", "status": "REVOKED", "evidence": []}]},
              open(os.path.join(d, "tension-ledger.json"), "w"))
    rs = M.StoreRecords(d)
    return rs.settle("t:tension:X") is None and rs.settle("t:tension:Y") == (False, "tension-ledger status REVOKED")
check("a status set by belief revision itself never settles a question (it would confirm itself)", probe_self_witness(A))
killed("its own revision taken as a record", probe_self_witness, A,
       'not t.get("belief_revision") and node not in self.own', "node not in self.own")

print("--- 8. once only, rate-limited, one note a day ---")
snap = digest(MEM)
out2 = L.run(MEM, transport=aeon(), send=send, at="2031-03-03T23:00:00Z")
check("a record already revised is not revised again", not out2["applied"] and
      all(digest(MEM)[n] == snap[n] for n in STORES), out2)
check("no second note the same day", len(TOLD) == 1)
def probe_once_only(M):
    d = os.path.join(HOME, "probe-once-%d" % len(CALLS)); fixture(d)
    os.environ["BELIEF_REVISION"] = "live"
    try:
        n1 = [x["node"] for x in M.run(d, transport=aeon(), send=send, at="2031-03-03T10:00:00Z")["applied"]]
        for n in STORES:                         # another organ rewrites its store and drops the marks
            p = os.path.join(d, n)
            text = open(p).read()
            open(p, "w").write(text.replace('"belief_revision"', '"rewritten_by_engine"'))
        tried, orig = [], M.apply
        M.apply = lambda t, *a, **k: (tried.append(t.node), orig(t, *a, **k))[1]
        try:
            M.run(d, transport=aeon(), send=send, at="2031-03-04T10:00:00Z")
        finally:
            M.apply = orig
    finally:
        os.environ.pop("BELIEF_REVISION")
    return n1 and not set(n1) & set(tried)
check("probe: a second night does not compound the same revisions, even when the marks were lost", probe_once_only(L))
killed("revisions repeated every run", probe_once_only, L, "            if node in revised_nodes:\n                continue",
       "            if False:\n                continue")
def probe_marked_once(M):
    d = os.path.join(HOME, "probe-marked-%d" % len(CALLS)); fixture(d)
    t = M.target("c:hyp:H1", "lower", 0.5, d)[0]
    r1, _ = M.apply(t, d, {})
    r2, why = M.apply(t, d, {})
    return r1 and r1["now"] == "medium" and r2 is None and "already revised" in why
check("probe: a marked record is not revised a second time", probe_marked_once(L))
killed("the mark ignored", probe_marked_once, L, 'if isinstance(mark, dict) and mark.get("rev") in out["in_force"]:', "if False:")
def probe_rate(M):
    d = os.path.join(HOME, "probe-rate-%d" % len(CALLS)); fixture(d)
    os.environ["BELIEF_REVISION"] = "live"; os.environ["BELIEF_REVISION_MAX_PER_DAY"] = "1"
    try:
        n = len(M.run(d, transport=aeon(), send=send, at="2031-03-03T10:00:00Z")["applied"])
    finally:
        os.environ.pop("BELIEF_REVISION"); os.environ.pop("BELIEF_REVISION_MAX_PER_DAY")
    return n == 1
check("probe: at most the daily limit is applied", probe_rate(L))
killed("no daily limit", probe_rate, L, "if not dry and len(applied) >= room:", "if False:")
def probe_her(M):
    d = os.path.join(HOME, "probe-her-%d" % len(CALLS)); fixture(d)
    b = [e for t in json.load(open(os.path.join(d, "tension-ledger.json")))["tensions"] for e in t["evidence"] if e["channel"] == "E1"]
    os.environ["BELIEF_REVISION"] = "live"
    try:
        M.run(d, transport=aeon(), send=send, at="2031-03-03T10:00:00Z")
    finally:
        os.environ.pop("BELIEF_REVISION")
    a = [e for t in json.load(open(os.path.join(d, "tension-ledger.json")))["tensions"] for e in t["evidence"] if e["channel"] == "E1"]
    return a == b
check("probe: her evidence items are left as they were", probe_her(L))
def probe_e3_only(M):
    data = json.load(open(os.path.join(MEM, "tension-ledger.json")))
    loc = lambda eid: M.target("t:ev:" + eid, "retract", 0.5, MEM)[0].locate(data)
    return loc("e1") is not None and loc("e3") is None and loc("e4") is None      # E3 his; E1 hers; E2 his message as sent
check("probe: only his private reading can be invalidated (not her words, not his messages as sent)", probe_e3_only(L))
killed("any evidence item invalidated", probe_e3_only, L, 'return e if e.get("channel") == "E3" else None', "return e")

print("--- 9. one command reverts any or all ---")
first = log[0]["rev"]
res = L.revert(MEM, {first})
check("revert one by id", res == [(first, "restored")] and first not in L.in_force(MEM))
res = L.revert(MEM, {first})
check("reverting it again says so and changes nothing", res and "not in force" in res[0][1])
with contextlib.redirect_stdout(io.StringIO()) as o:
    L.main(["revert", "--all", "--memory", MEM])
check("revert --all restores every store to what it was", parsed(MEM, STORES) == before_obj and not L.in_force(MEM),
      o.getvalue()[:300])
d = os.path.join(HOME, "probe-changed"); fixture(d); os.environ["BELIEF_REVISION"] = "live"
L.run(d, transport=aeon(), send=send, at="2026-11-16T10:00:00Z"); os.environ.pop("BELIEF_REVISION")
row = next(iter(L.in_force(d).values()))
def poke(data):
    rec = L._relocate(row, d)(data); rec[row["field"]] = "someone-else"; return data
import store_guard
store_guard.locked_update(os.path.join(d, row["store"]), poke, default={})
res = L.revert(d, {row["rev"]})
check("a field changed by someone since is not overwritten", "changed since" in res[0][1] and row["rev"] in L.in_force(d))
res = L.revert(d, {row["rev"]}, force=True)
check("--force restores it anyway", res[0][1] == "restored")
def probe_revert(M):
    d = os.path.join(HOME, "probe-revert-%d" % len(CALLS)); fixture(d)
    b = parsed(d, STORES); os.environ["BELIEF_REVISION"] = "live"
    try:
        M.run(d, transport=aeon(), send=send, at="2031-03-03T10:00:00Z")
    finally:
        os.environ.pop("BELIEF_REVISION")
    M.revert(d)
    return parsed(d, STORES) == b
killed("revert leaves the revised value", probe_revert, L, 'rec[row["field"]] = row["was"]', "pass")

print("--- 9b. review fixes: the right record, compare-and-set, a revert stays, no self-witness ---")
def probe_shifted(M):
    """The plan saw sediment row 0 = A; before the write, a decay pass removed A, so row 0 is now B. Nothing changes."""
    d = os.path.join(HOME, "probe-shift-%d" % len(CALLS)); os.makedirs(d, exist_ok=True)
    import belief_revision_sources as S
    json.dump({"beliefs": [{"pattern": "B", "confidence": 0.5}]}, open(os.path.join(d, "belief-sediment.json"), "w"))
    t = M.target("c:belief:0", "lower", 0.5, d, plan={"fp": S.fingerprint("A"), "confidence": 0.5})[0]
    row, why = M.apply(t, d, {})
    return row is None and json.load(open(os.path.join(d, "belief-sediment.json")))["beliefs"][0]["confidence"] == 0.5
check("probe: a sediment row that moved since the plan is never mistaken for another", probe_shifted(L))
killed("the row at the old index revised", probe_shifted, L,
       'return Target(node, "belief-sediment.json", "confidence", _by_index("beliefs", i, "pattern", plan["fp"]),',
       'return Target(node, "belief-sediment.json", "confidence", (lambda data: data["beliefs"][i]),')
def probe_cas(M):
    d = os.path.join(HOME, "probe-cas-%d" % len(CALLS)); fixture(d)
    t = M.target("c:hyp:H1", "lower", 0.5, d, plan={"confidence": "medium"})[0]       # the store says "high" now
    row, why = M.apply(t, d, {})
    return row is None and "changed since the plan" in why
check("probe: a confidence that changed since the plan is not overwritten", probe_cas(L))
killed("no compare-and-set", probe_cas, L, "if t.expect is not None and cur != t.expect:", "if False:")
def probe_revert_stays(M):
    d = os.path.join(HOME, "probe-stays-%d" % len(CALLS)); fixture(d)
    os.environ["BELIEF_REVISION"] = "live"
    try:
        n1 = {x["node"] for x in M.run(d, transport=aeon(), send=send, at="2031-03-03T10:00:00Z")["applied"]}
        M.revert(d)
        n2 = {x["node"] for x in M.run(d, transport=aeon(), send=send, at="2031-03-04T10:00:00Z")["applied"]}
    finally:
        os.environ.pop("BELIEF_REVISION")
    return n1 and not n1 & n2
check("probe: a reverted revision is not applied again the next night", probe_revert_stays(L))
killed("reverted revisions re-applied", probe_revert_stays, L,
       'revised_nodes = {r["node"] for r in rows if r.get("node")}',
       'revised_nodes = {x["node"] for x in in_force(mem).values()}')
def probe_no_self_witness_after_rewrite(M):
    d = os.path.join(HOME, "probe-own-%d" % len(CALLS)); os.makedirs(d, exist_ok=True)
    json.dump({"tensions": [{"tension_id": "X", "status": "CONTRADICTED", "evidence": []}]},
              open(os.path.join(d, "tension-ledger.json"), "w"))            # the mark is gone (another organ rewrote)
    open(os.path.join(d, "belief-revisions.jsonl"), "w").write(json.dumps({"rev": "REV-1", "node": "t:tension:X"}) + "\n")
    return M.StoreRecords(d).settle("t:tension:X") is None
check("probe: its own write is no witness even after the mark was dropped", probe_no_self_witness_after_rewrite(A))
killed("own write read back as a record", probe_no_self_witness_after_rewrite, A,
       'and node not in self.own:', ':')
def probe_switch_mid_run(M):
    d = os.path.join(HOME, "probe-mid-%d" % len(CALLS)); fixture(d); b = parsed(d, STORES)
    os.environ["BELIEF_REVISION"] = "live"
    real = M.BR.localize
    def off_midway(*a, **k):
        p = real(*a, **k); os.environ["BELIEF_REVISION"] = "off"; return p
    M.BR.localize = off_midway
    try:
        out = M.run(d, transport=aeon(), send=send, at="2031-03-03T10:00:00Z")
    finally:
        M.BR.localize = real; os.environ.pop("BELIEF_REVISION", None)
    return out["ran"] is False and parsed(d, STORES) == b
check("probe: switching it off while the checks run means nothing is applied", probe_switch_mid_run(L))
killed("switch read only at the start", probe_switch_mid_run, L,
       'if not dry and mode() != "live":\n            stopped, wants = True, {}', 'if False:\n            stopped, wants = True, {}')

def probe_row_date(M):
    """A revision's log row carries the run's own time, not the wall clock: the daily limit (and the two-night probes
    above) must mean the same thing on any day the suite runs. They failed after midnight UTC on 15 November."""
    d = os.path.join(HOME, "probe-date-%d" % len(CALLS)); fixture(d)
    os.environ["BELIEF_REVISION"] = "live"
    try:
        out = M.run(d, transport=aeon(), send=send, at="2030-01-01T10:00:00Z")
    finally:
        os.environ.pop("BELIEF_REVISION")
    rows = [r for r in M._read_jsonl(os.path.join(d, M.LOG_NAME)) if r.get("rev")]
    return bool(out["applied"]) and bool(rows) and all(r["at"] == "2030-01-01T10:00:00Z" for r in rows)
check("probe: a revision is dated by its run, so the daily limit counts the run's day", probe_row_date(L))
killed("rows dated by the wall clock", probe_row_date, L, 'at=meta.get("at") or _now(), node=t.node', "at=_now(), node=t.node")

print("--- 10. deploy: the modules ship ---")
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs all four modules", all(m in dep for m in ("belief_revision.py", "belief_revision_sources.py",
                                                                   "belief_revision_answer.py", "belief_revision_live.py")))

BD = os.path.join(REPO, "experiments", "contradiction-backprop"); sys.path.insert(0, BD)
import bench_answerer as BA
check("answerer benchmark: dev and held-out seeds do not overlap, nor the criteria benchmark's held-out",
      not set(BA.SPLITS["dev"]) & set(BA.SPLITS["test"]) and not set(BA.SPLITS["test"]) & set(range(5000, 5150)))
res = json.load(open(BA.TEST_RESULT))
check("answerer benchmark: held-out scored once, saved, and every pre-registered bar met",
      res["split"] == "test" and all(res["pass"].values()) and res["checker"]["url"] == A.CHECKER_URL)
check("the benchmark checker URL is the one live uses", A.check_url(A.CHECKER_URL) == A.CHECKER_URL)

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

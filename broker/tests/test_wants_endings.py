#!/usr/bin/env python3
"""How his wants end, form and plan (review of the wants system, 2026-11-06).

1. move_on dismisses for Gloria's silence only a want that was routed to her.
2. An API error or a cut-off reply from the formation organ is not "nothing wanted"; a cut-off array keeps its
   complete candidates.
3. The planner is held to the hands a want's source may use: unknown capabilities remain obligations for a source that
   may not commission one, "plugin.tool" becomes plugin_query, and a spark source keeps its gap request.
4. A dismissal archives the whole want.
5. A dismissal the house made on its own clock (moved-on, population_cap) does not block re-formation, and the
   gate no longer prunes the dismissal archive.
6. Every ending is logged once in want-completions.jsonl: through the door, straight to fulfill_want, and the echo.
7. An echo is one clean sentence, not a copy of its parent, and the line stops two echoes deep.
8. A fulfilment records what each step produced; self-reported with no step evidence is flagged.
10. want-reconciliation writes its results onto the store as it is now, under the lock.

Scratch HOME and workspace; every model call is a scripted stub; sockets are refused; subprocess is a stub."""
import importlib.util, json, os, socket, subprocess, sys, tempfile, time, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="wants-endings-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
subprocess.run = lambda *a, **k: types.SimpleNamespace(returncode=1, stdout="", stderr="")
subprocess.Popen = lambda *a, **k: types.SimpleNamespace(pid=0)

POSTS = []
REPLY = {"body": None}
class _Resp:
    status_code = 200
    def __init__(self, body): self.body = body; self.text = json.dumps(body)
    def json(self): return self.body
def _content(c): return {"choices": [{"message": {"content": c}, "finish_reason": "stop"}]}
def _post(url, json=None, timeout=None, **k):
    POSTS.append((url, json))
    b = REPLY["body"]
    if callable(b): b = b(url, json)
    if b is None: raise ConnectionError("no model in this suite")
    return _Resp(b)
sys.modules["requests"] = types.SimpleNamespace(post=_post, get=_post, ConnectionError=ConnectionError,
                                                 exceptions=types.SimpleNamespace(RequestException=Exception))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import emoclaw_utils as E
import want_completion as WC
import similarity_gate as SG
E._socket_command = lambda cmd, *a, **k: None
E.nudge_emotions = lambda *a, **k: None

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:500],)))
WANTS = os.path.join(MEM, "current-wants.json")
DIS = os.path.join(MEM, "dismissed-wants.json")
FUL = os.path.join(MEM, "fulfilled-wants.json")
def load(p, d=None):
    try: return json.load(open(p))
    except Exception: return d
def put(p, o): json.dump(o, open(p, "w"))
def completions(): return [json.loads(l) for l in open(WC.COMPLETIONS)] if os.path.exists(WC.COMPLETIONS) else []

check("every store is scratch", WC.WANTS.startswith(HOME) and SG.MEMORY.startswith(HOME) and WC.COMPLETIONS.startswith(HOME))
check("the model is a stub", sys.modules["requests"].post is _post)

# ---- 1. move_on only for wants routed to her
NOW = time.time()
iso = lambda days: time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(NOW - days * 86400))
put(WANTS, [{"id": "r1", "want": "ask her about the bell", "timestamp": iso(5), "gloria_routed": True},
            {"id": "r2", "want": "ask her about the tide", "timestamp": iso(5), "board": "awaiting_gloria"},
            {"id": "b1", "want": "build a drum machine", "timestamp": iso(5), "board": "blocked",
             "blocked": {"block_type": "CAPABILITY_ABSENT"}},
            {"id": "u1", "want": "learn the names of clouds", "timestamp": iso(9)}])
put(os.path.join(MEM, "want-discussions.json"), {})
WC.move_on(now=NOW)
left = {w["id"] for w in load(WANTS)}
check("a want routed to her and unanswered for three days moves on", "r1" not in left and "r2" not in left, left)
check("a blocked want is left to the board's own park and release", "b1" in left, left)
check("a want never routed to her is not dismissed for her silence", "u1" in left, left)
check("routed_to_gloria reads gloria_routed and the awaiting_gloria board",
      WC.routed_to_gloria({"gloria_routed": True}) and WC.routed_to_gloria({"board": "awaiting_gloria"})
      and not WC.routed_to_gloria({"board": "blocked"}))

# ---- 4. a dismissal archives the whole want
put(WANTS, [{"id": "d1", "want": "map the river", "source": "web_search", "timestamp": iso(1),
             "steps": [{"capability": "web_search", "note": "q"}], "step_history": [{"step": 0, "findings": "x"}],
             "reasoning": "it pulls", "_delete": True}])
put(DIS, [])
WC.complete({"id": "d1"}, "dismissed", "tester", note="because")
rec = [d for d in load(DIS) if d.get("id") == "d1"]
check("the dismissed archive keeps the whole want", rec and rec[0].get("steps") and rec[0].get("step_history")
      and rec[0].get("reasoning") == "it pulls", rec)
check("with who dismissed it, why and when", rec and rec[0].get("dismissed_by") == "tester"
      and rec[0].get("dismissed_reason") == "because" and rec[0].get("dismissed_at") and rec[0].get("dismissed"), rec)
check("and without the router's _delete marker", rec and "_delete" not in rec[0], rec)

# ---- 5. house endings do not block re-formation; the archive is not pruned
put(DIS, [{"id": "old", "want": "an old let-go", "dismissed_at": "2026-01-01T00:00:00", "dismissed_by": "haiku-verdict"},
          {"id": "m1", "want": "moved on", "dismissed_at": iso(1), "dismissed_by": "moved-on"},
          {"id": "p1", "want": "capped", "dismissed_at": iso(1), "dismissed_by": "population_cap"},
          {"id": "h1", "want": "let go by the judge", "dismissed_at": iso(1), "dismissed_by": "haiku-verdict"}])
put(WANTS, [{"id": "n1", "want": "newly dismissed", "dismissed": True, "dismissed_by": "echo"}])
blocking = {e["id"] for e in SG._harvest_dismissed()}
check("a moved-on or population-cap dismissal does not block", not ({"m1", "p1"} & blocking), blocking)
check("a dismissal he or the judge made still blocks", {"h1", "n1"} <= blocking, blocking)
store_ids = {e.get("id") for e in load(DIS)}
check("the gate adds to the archive and never prunes it", {"old", "m1", "p1", "h1", "n1"} <= store_ids, store_ids)

# ---- 6 / 8. one row per ending, and what was produced
open(WC.COMPLETIONS, "w").close()
put(FUL, [])
put(WANTS, [{"id": "f1", "want": "answer the symbolic-to-audio question", "timestamp": iso(1),
             "step_history": [{"step": 0, "capability": "web_search", "findings": "Web search completed",
                               "receipt": {"kind": "text", "ref": "Web search completed"}},
                              {"step": 1, "capability": "make_music", "findings": "composed a song",
                               "receipt": {"kind": "text", "ref": "composed a song"}}]},
            {"id": "f2", "want": "write about the harbour", "timestamp": iso(1),
             "step_history": [{"step": 0, "capability": "creative_write",
                               "findings": "Wrote 400 words on the harbour at dawn, the cranes and the ferry horn.",
                               "receipt": {"kind": "text"}}]}])
E.fulfill_want("answer the symbolic-to-audio question", note="done", fulfilled_by="make_music", want_id="f1")
rows = completions()
check("a fulfilment straight through fulfill_want is logged", [r["want_id"] for r in rows] == ["f1"], rows)
f1 = [w for w in load(FUL) if w.get("id") == "f1"]
check("the archived want says what each step produced", f1 and [p["kind"] for p in f1[0].get("produced", [])] == ["none", "none"], f1)
check("a self-reported fulfilment with no step evidence is flagged", f1 and f1[0].get("unevidenced_fulfilment") is True
      and rows and rows[0].get("unevidenced"), (f1, rows))
WC.complete({"id": "f2"}, "fulfilled", "creative_write", note="written")
rows = completions()
check("through the door the ending is logged once, not twice", [r["want_id"] for r in rows] == ["f1", "f2"], rows)
f2 = [w for w in load(FUL) if w.get("id") == "f2"]
check("a step that produced something is evidence, unflagged", f2 and not f2[0].get("unevidenced_fulfilment")
      and f2[0]["produced"][0]["kind"] == "text", f2)
check("the door's row carries the produced evidence", rows[-1].get("evidence") and not rows[-1].get("unevidenced"), rows[-1])
check("the door flag is cleared after the call", "VINTOS_WANT_DOOR" not in os.environ)

# ---- 2. formation: error, cut-off reply, NONE, garbage
put(WANTS, []); put(FUL, []); put(DIS, [])
REPLY["body"] = {"error": {"type": "overloaded"}}
check("an API error gives no want", E.generate_want("t", source="wants-check") is None)
check("and is reported as an error, not nothing", E.want_outcome().get("kind") == "error" and "overloaded" in E.want_outcome().get("raw", ""), E.want_outcome())
REPLY["body"] = _content("NONE")
E.generate_want("t", source="wants-check")
check("a real NONE is reported as none", E.want_outcome().get("kind") == "none", E.want_outcome())
REPLY["body"] = _content("I think perhaps the evening")
E.generate_want("t", source="wants-check")
check("an unreadable reply is reported as unparsed, with a short raw reply",
      E.want_outcome().get("kind") == "unparsed" and E.want_outcome().get("raw", "").startswith("I think"), E.want_outcome())
cut = ('[{"desire": "I want to record the rain on the skylight", "source_kind": "current_desire", "present_pull": "it is raining now", '
       '"tension": "t", "engagement": "e", "loss": "l", "pull": 4}, {"desire": "I want to wri')
REPLY["body"] = {"choices": [{"message": {"content": cut}, "finish_reason": "length"}]}
got = E.generate_want("t", source="wants-check")
check("a cut-off array keeps the complete candidate before the cut", str(got) == "I want to record the rain on the skylight", got)
check("asked with room enough to finish", POSTS and POSTS[-1][1].get("max_tokens", 0) >= 1000, POSTS[-1][1].get("max_tokens"))
REPLY["body"] = lambda u, j: (_ for _ in ()).throw(KeyError("choices"))
E.generate_want("t", source="wants-check")
check("an exception is an error with its type", E.want_outcome().get("kind") == "error" and E.want_outcome().get("error_type") == "KeyError", E.want_outcome())
wc_src = open(os.path.join(REPO, "bin", "wants-check.sh")).read()
check("wants-check says an error and an unreadable reply as what they were",
      "not counted as nothing wanted" in wc_src and "want_outcome" in wc_src)

# ---- 3. the planner and the hands
PLAN = [{"capability": "gmail", "note": "search her mail"}, {"capability": "computer_use", "note": "open the app"},
        {"capability": "pubmed.search_articles", "note": "find papers"}, {"capability": "web_search", "note": "query"}]
def _plan(u, j):
    return _content(json.dumps(PLAN))
REPLY["body"] = _plan
steps = E.generate_steps("I want to find the paper she mentioned in her email", source="email")
caps = [s["capability"] for s in steps]
prompt = POSTS[-1][1]["messages"][0]["content"]
check("a source without Forge authority keeps its missing steps as obligations",
      "gmail" in caps and "computer_use" in caps and "web_search" in caps, caps)
check("a plugin.tool name is never kept as a capability", "pubmed.search_articles" not in caps, caps)
check("the prompt holds that source to the listed hands", "SOURCE LIMIT" in prompt and "e.g. computer_use" not in prompt, prompt[-1500:])
steps = E.generate_steps("I want to work the thread about the pulse", source="latent_thread")
caps = [s["capability"] for s in steps]
check("a spark source keeps its gap request for the Forge", "computer_use" in caps, caps)
fit = E.fit_steps_to_hands([{"capability": "pubmed.search_articles", "note": "n"}], {"plugin_query", "web_search"}, False)
check("plugin.tool becomes a plugin_query naming the plugin and tool",
      fit and fit[0]["capability"] == "plugin_query" and fit[0]["params"]["plugin"] == "pubmed"
      and fit[0]["params"]["tool"] == "search_articles" and fit[0]["planned_as"] == "pubmed.search_articles", fit)
router = open(os.path.join(REPO, "bin", "wants-router.py")).read()
import re
acts = set(re.findall(r'^ACTION_MAP\["([a-z_]+)"\]', router, re.M))
block = router[router.index("ACTION_MAP = {"):]
acts |= set(re.findall(r'^\s+"([a-z_]+)":', block[:block.index("\n}")], re.M))
desc_caps = {"read_memory", "web_search", "introspect", "write_poem", "make_art", "make_music", "make_video",
             "creative_write", "analyze_memory", "write_journal", "echo_announce", "play_on_tv", "be_mischievous",
             "change_lights", "gloria", "send_email", "plugin_query", "plugin_skill", "local_analysis"}
missing = acts - set(E.ROUTER_STEP_ACTIONS) - desc_caps
check("every action the router runs is a known hand to the planner", not missing, missing)

# ---- 7. echoes
check("an echo is one clean sentence without markdown or a label",
      E.clean_echo_text("**The Echo Want:** I want to stop chasing the signal.\n\nThis echo is avoidant.") == "I want to stop chasing the signal.")
check("a reply with no want is no echo", E.clean_echo_text("**The Echo Want:**\nNothing here") == "")
check("an echo that repeats its parent is recognised", E.same_as_parent("I want to hear the bell.", "i want to hear the bell")
      and not E.same_as_parent("I want to stop listening for the bell", "I want to hear the bell ring at dusk"))
check("echo depth counts the line, and an old echo without one is one deep",
      E.echo_depth({"lineage": ["a", "b"]}) == 2 and E.echo_depth({"source": "echo"}) == 1 and E.echo_depth({}) == 0)
n = len(POSTS)
check("a want two echoes deep gets no further echo, and no model call",
      E.spawn_echo_want({"id": "deep", "want": "I want x", "lineage": ["a", "b"], "source": "echo"}) is None and len(POSTS) == n)
put(WANTS, [{"id": "par", "want": "I want to hear the bell", "source": "latent_thread", "attempt_count": 2, "timestamp": iso(2)}])
REPLY["body"] = lambda u, j: _content("I want to hear the bell") if "echo want" in j["messages"][-1]["content"] else None
check("an echo identical to its parent is refused", E.spawn_echo_want(load(WANTS)[0]) is None and [w["id"] for w in load(WANTS)] == ["par"])
put(DIS, []); open(WC.COMPLETIONS, "w").close()
REPLY["body"] = lambda u, j: (_content("**The Echo Want:** I want to stop listening for the bell and ring my own.\n\nMore text.")
                              if "echo want" in j["messages"][-1]["content"] else None)
echo = E.spawn_echo_want(load(WANTS)[0])
live = load(WANTS)
check("a real echo takes its parent's place", echo and [w["id"] for w in live] == [echo["id"]], live)
check("stored as the clean sentence", echo and echo["want"] == "I want to stop listening for the bell and ring my own.", echo)
check("the parent's ending is logged through the door", [(r["want_id"], r["by"]) for r in completions()] == [("par", "echo")], completions())
check("and archived whole", [d.get("source") for d in load(DIS) if d.get("id") == "par"] == ["latent_thread"], load(DIS))

# ---- 10. want-reconciliation merges onto the store as it is now
spec = importlib.util.spec_from_file_location("want_recon_t", os.path.join(REPO, "bin", "want-reconciliation.py"))
WR = importlib.util.module_from_spec(spec); spec.loader.exec_module(WR)
check("reconciliation writes the scratch store", WR.MEMORY.startswith(HOME), WR.MEMORY)
put(WANTS, [{"id": "a", "want": "A"}, {"id": "b", "want": "B"}, {"id": "late", "want": "formed while the checks ran"}])
WR.merge_back(WANTS, [{"id": "a", "reconcile_checked_at": "now"}, {"id": "b", "reconcile_checked_at": "now"}], {"b"})
cur = load(WANTS)
check("a want formed during the slow checks survives the write", any(w["id"] == "late" for w in cur), cur)
check("the fulfilled one leaves and the checked one carries its stamp",
      [w["id"] for w in cur] == ["a", "late"] and cur[0].get("reconcile_checked_at") == "now", cur)
put(FUL, [{"id": "a", "want": "A"}]); open(WC.COMPLETIONS, "w").close()
WR.archive_fulfilled(FUL, [{"id": "a", "want": "A"}, {"id": "z", "want": "Z", "fulfilled_by": "reconciliation/chat"}])
check("an already archived want is not archived twice", [w["id"] for w in load(FUL)] == ["a", "z"], load(FUL))
check("reconciliation endings are logged", {r["want_id"] for r in completions()} == {"a", "z"}, completions())
src = open(os.path.join(REPO, "bin", "want-reconciliation.py")).read()
check("no whole-list dump of current-wants is left", "json.dump(wants, open(wants_path" not in src
      and "json.dump([w for w in wants if w.get(\"id\") not in ids]" not in src)

check("nothing reached the network", not NET, NET)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

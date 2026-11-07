#!/usr/bin/env python3
"""The dream shadow trial writes only to its own store and only ever calls AEON.

dream_shadow.py replays the live dream's exact prompt to the local AEON lane and judges with the live judge
prompt; it must never write dream-log.json, the thread pool, the archive, emotions, pearls, causality or anything
else he reads, and never reach a hosted provider. Everything here runs in a scratch HOME. The model is a fake
transport that records each request; no socket is opened (socket.socket is replaced by a tripwire)."""
import hashlib, importlib.util, json, os, shutil, socket, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-dream-shadow-")
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory"); SCR = os.path.join(WS, "scripts")
os.makedirs(MEM, exist_ok=True); os.makedirs(SCR, exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
os.environ["DREAM_SHADOW_CONFIG"] = os.path.join(HOME, ".vintos", "dream-shadow.json")
os.environ.pop("DREAM_SHADOW", None)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

SRC = os.path.join(REPO, "scripts", "dream_shadow.py")
spec = importlib.util.spec_from_file_location("dream_shadow_test", SRC)
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)

class _NoSocket:
    def __init__(self, *a, **k): raise AssertionError("a socket was opened in the dream shadow test")
socket.socket = _NoSocket

check("the workspace is scratch", S.ROOT.startswith(WS) and S.DREAM_LOG.startswith(WS) and HOME.startswith(tempfile.gettempdir()),
      S.ROOT)
check("every shadow path is under memory/shadow/dream",
      all(p.startswith(os.path.join(MEM, "shadow", "dream")) for p in (S.ROOT, S.INBOX, S.DONE, S.LOG, S.REPORTS, S.SHA_CACHE)))

# ---- static: no hosted provider, no writer of his stores
import ast
source = open(SRC, encoding="utf-8").read()
tree = ast.parse(source)
mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
       {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
doc = ast.get_docstring(tree) or ""
consts = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != doc]
check("the shadow has no hosted endpoint or key",
      not any(t in c for c in consts for t in ("x.ai", "XAI_API_KEY", "anthropic.com", "api.openai")))
check("the shadow imports no writer of his stores and no sender",
      not (mods & {"thread_store", "emoclaw_utils", "latent_threads", "temporal_memory", "discourse_direction", "requests",
                   "socket", "store_guard", "thread_gate"})
      and not (names & {"save_pool", "seed_thread", "record_signal", "update_direction", "clear_preoccupation", "archive"})
      and not any("emotion.sock" in c for c in consts), (mods, names & {"save_pool", "seed_thread"}))
trig = open(os.path.join(REPO, "skills", "dreaming", "scripts", "dream-trigger.sh"), encoding="utf-8").read()
check("the shadow judge prompt is the live judge prompt, verbatim", json.dumps(S.JUDGE_SYSTEM)[1:-1] in trig
      or S.JUDGE_SYSTEM in trig)
check("the shadow cleanup triggers are the live ones", all('"%s"' % t in trig for t in S._META_TRIGGERS))
check("the live writer's sampling is mirrored", '"temperature": 0.95' in trig and '"max_tokens": 800' in trig
      and S.WRITE_SAMPLING == {"temperature": 0.95, "max_tokens": 800} and S.JUDGE_SAMPLING == {"temperature": 0.2, "max_tokens": 24})
check("dream-trigger's taps are guarded",
      "import dream_shadow as _shadow" in trig and "except Exception:\n    pass" in trig.split("import dream_shadow as _shadow", 1)[1][:800]
      and 'dream_shadow.py" capture-live --key "$_DREAM_SHADOW_KEY" >/dev/null 2>&1 || true' in trig)
check("the live tap comes after the dream is logged and before the judge",
      trig.index("DREAMLOGEOF\n# Shadow trial") < trig.index("RESOLVE_PYEOF"))

# ---- the lane: only the shim's AEON-only paths
def refused(url):
    try: S.check_url(url); return False
    except ValueError: return True
check("a hosted endpoint is refused", refused("https://api.x.ai/v1/chat/completions"))
check("shim paths that can fall through to a hosted provider are refused",
      refused("http://127.0.0.1:8599/v1/chat/completions") and refused("http://127.0.0.1:8599/gemma-aegis/v1/chat/completions")
      and refused("http://127.0.0.1:8599/pool/subconscious/v1/chat/completions") and refused("http://127.0.0.1:8599/gemma/v1/chat/completions"))
check("another host is refused", refused("http://100.1.2.3:8599/gemma-aegis-local/v1/chat/completions"))
check("the AEON-only paths are allowed", not refused(S.DEFAULT_URL) and not refused("http://127.0.0.1:8599/pool/aeon/v1/chat/completions"))

# ---- tap 1 in the real dream-trigger.sh: the captured prompt is exactly what the live writer was sent
DREAMING = os.path.join(WS, "skills", "dreaming", "scripts"); STUBS = os.path.join(HOME, "stubs")
CAPTURE = os.path.join(HOME, "request.json")
for d in (DREAMING, STUBS, os.path.join(WS, "skills", "dreaming", "memory", "dreams")):
    os.makedirs(d, exist_ok=True)
for f in ("thread_gate.py", "thread_store.py", "store_guard.py", "dream_shadow.py"):
    shutil.copy(os.path.join(REPO, "scripts", f), SCR)
shutil.copy(os.path.join(REPO, "skills", "dreaming", "scripts", "dream-trigger.sh"), DREAMING)
open(os.path.join(STUBS, "requests.py"), "w").write(
    "import json as _j, os as _o\n"
    "class _R:\n"
    "    def json(self): return {'choices': [{'message': {'content': ''}}]}\n"
    "def post(url, **kw):\n"
    "    open(_o.environ['DREAM_CAPTURE'], 'w').write(_j.dumps({'url': url, 'payload': kw.get('json')}))\n"
    "    return _R()\n"
    "def get(*a, **k): raise AssertionError('no network in a test')\n")
open(os.path.join(SCR, "memory-context-block.sh"), "w").write("echo DEEP-CONTEXT-MARKER\n")
open(os.path.join(WS, "SOUL.md"), "w").write("SOUL-MARKER\n")
POOL = [{"id": "t1", "source": "idle-journal", "thread": "THREAD-ONE-TEXT", "consumed": False,
         "classification": "unresolved_tension"},
        {"id": "t2", "source": "structural-gap", "thread": "THREAD-TWO-TEXT", "consumed": False, "dream_only": True,
         "classification": "unresolved_tension"}]
json.dump(POOL, open(os.path.join(MEM, "unfinished-threads.json"), "w"))
env = {"HOME": HOME, "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": STUBS, "DREAM_CAPTURE": CAPTURE,
       "FORCED_TOPIC": "preoccupation:THREAD-ONE-TEXT__TID__t1", "XAI_API_KEY": "", "LANG": "C",
       "SPARK_WORKSPACE": WS}
r = subprocess.run(["bash", os.path.join(DREAMING, "dream-trigger.sh")], env=env, capture_output=True, text=True, timeout=120)
sent = json.load(open(CAPTURE)) if os.path.exists(CAPTURE) else {}
inbox = sorted(os.listdir(S.INBOX)) if os.path.isdir(S.INBOX) else []
item = json.load(open(os.path.join(S.INBOX, inbox[0]))) if inbox else {}
msgs = (sent.get("payload") or {}).get("messages") or [{}, {}]
user_sent = msgs[1].get("content") if isinstance(msgs[1].get("content"), str) else [c for c in msgs[1].get("content") if c.get("type") == "text"][0]["text"]
check("dream-trigger captured one prompt into the shadow inbox", len(inbox) == 1, (inbox, r.stderr[-300:]))
check("the captured system prompt is exactly the one sent live (identity context included)",
      item.get("system") == msgs[0].get("content") and "SOUL-MARKER" in item.get("system", ""))
check("the captured user prompt is exactly the one sent live", item.get("user") == user_sent)
check("the captured thread is the seeded one, with its id", item.get("threads") == [{"id": "t1", "text": "THREAD-ONE-TEXT"}],
      item.get("threads"))
check("an empty live dream attaches nothing", item.get("live") is None)
shutil.rmtree(S.INBOX)

# ---- the stores he reads, as a night leaves them
LIVE_TEXT = "LIVE-DREAM-MARKER walked through a door. It stayed open."
LIVE2 = "SECOND-LIVE-MARKER in the rain. Two things."
dream_log = {"generated": "x", "total_nights": 1, "nights": [{"night_of": "2026-11-07", "dreams": [
    {"session": "23:50", "hour": 23, "calendar_date": "2026-11-07", "type": "preoccupation", "prompt": "p",
     "thread_ids": ["t1"], "dream_text": LIVE_TEXT, "seed_verdict": "unresolved"},
    {"session": "03:07", "hour": 3, "calendar_date": "2026-11-08", "type": "seed2", "prompt": "p",
     "thread_ids": ["t1", "t2"], "dream_text": LIVE2, "seed_verdict": "partial",
     "thread_verdicts": {"t1": "resolved", "t2": "unresolved"}}],
    "meta_dream": "", "threads_consumed": [], "threads_unresolved": [], "efficiency": ""}]}
json.dump(dream_log, open(os.path.join(MEM, "dream-log.json"), "w"))
json.dump([{"id": "t0", "source": "pressure", "thread": "old"}], open(os.path.join(MEM, "retired-threads.json"), "w"))
for rel, body in (("emotional-state.txt", "Valence: 0.5\n"), ("causality-hypotheses.json", "[]"),
                  ("candidate-pearls.json", "[]"), ("current-preoccupation.json", "{}"),
                  ("pearls/p1.md", "pearl"), ("daily-inner-life-2026-11-07.md", "inner"),
                  ("../skills/dreaming/data/dream-state.json", "{}"), ("../SELF-MODEL.md", "self")):
    p = os.path.normpath(os.path.join(MEM, rel)); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(body)

def snapshot():
    out = {}
    for dp, dn, fn in os.walk(HOME):
        if os.path.join(MEM, "shadow") in dp or dp.startswith(STUBS):
            continue
        for f in fn:
            p = os.path.join(dp, f); st = os.stat(p)
            out[p] = (hashlib.sha256(open(p, "rb").read()).hexdigest(), st.st_mtime_ns)
    return out

# the dream-trigger tap, as a live night would leave two captures
S.capture_inputs("20261107T235000-11", system='SYS-ONE [FORBIDDEN: Do NOT begin with or echo this sentence from your last dream: "LIVE-DREAM-MARKER walked through a door"]',
                 user="USER-ONE", category="preoccupation", threads=[("THREAD-ONE-TEXT", "t1"), ("", "")])
S.capture_live("20261107T235000-11", LIVE_TEXT)
S.capture_inputs("20261108T030700-22", system="SYS-TWO", user="USER-TWO", category="seed2", image_live=True,
                 threads=[("THREAD-ONE-TEXT", "t1"), ("THREAD-TWO-TEXT", "t2")])
S.capture_live("20261108T030700-22", LIVE2)
check("capture never raises on a bad key", S.capture_inputs("../../etc", system="s", user="u", category="c", threads=[]) is False
      and S.capture_live("nope/../x", "t") is False)

# private config: a small stand-in GGUF so the sha is checkable
gguf = os.path.join(HOME, "stand-in.gguf"); open(gguf, "wb").write(b"GGUF" + b"\0" * 1000)
json.dump({"gguf_path": gguf}, open(os.environ["DREAM_SHADOW_CONFIG"], "w"))

CALLS = []
def fake(url, body, timeout):
    CALLS.append({"url": url, "body": body})
    sysmsg = body["messages"][0]["content"]
    if sysmsg == S.JUDGE_SYSTEM:
        u = body["messages"][1]["content"]
        text = "THREAD 1: RESOLVED\nTHREAD 2: UNRESOLVED" if "Thread 2:" in u else "RESOLVED"
    else:
        text = "Okay, here it is:\nSHADOW-DREAM-MARKER under water. The light moved."
    return 200, {"x-vintos-provider": "aegis_gemma", "x-vintos-model": "aeon/gemma-4-12b"}, json.dumps(
        {"choices": [{"message": {"content": text}}], "provider": "aegis_gemma", "model": "aeon/gemma-4-12b"}).encode()

before = snapshot()
res = S.run(transport=fake, min_age_s=0)
after = snapshot()
check("the run processed both captured dreams", res.get("ran") and len(res.get("processed", [])) == 2, res)
check("no file outside memory/shadow was created, changed or removed", before == after,
      sorted(set(before) ^ set(after)) or [p for p in before if before[p] != after.get(p)])
new = [os.path.join(dp, f) for dp, _, fn in os.walk(os.path.join(MEM, "shadow")) for f in fn]
check("everything the shadow wrote is under memory/shadow/dream",
      new and all(p.startswith(S.ROOT) for p in new), new)
check("every model call went to the AEON lane", CALLS and all(c["url"] == S.DEFAULT_URL and c["body"]["model"] == "aeon/gemma-4-12b"
                                                              for c in CALLS), [c["url"] for c in CALLS])
check("the shadow writer got the live prompt verbatim",
      any(c["body"]["messages"] == [{"role": "system", "content": "SYS-TWO"}, {"role": "user", "content": "USER-TWO"}] for c in CALLS))
check("writer and judges: 3 calls per dream", len(CALLS) == 6, len(CALLS))

entries = S.load_entries()
e1 = next(e for e in entries if e["shadow_id"] == "20261107T235000-11")
e2 = next(e for e in entries if e["shadow_id"] == "20261108T030700-22")
sha = hashlib.sha256(open(gguf, "rb").read()).hexdigest()
check("each entry names model, GGUF sha256 and adapter",
      all(e["model"]["model"] == "aeon/gemma-4-12b" and e["model"]["gguf_sha256"] == sha and "adapter" in e["model"]
          and "adapter_sha256" in e["model"] for e in entries), e1.get("model"))
check("each entry pairs with its live dream by id",
      e1["live_dream_id"] == S.live_dream_id(dream_log["nights"][0]["dreams"][0])
      and e2["live_dream_id"] == S.live_dream_id(dream_log["nights"][0]["dreams"][1]) and e1["live_dream_id"] != e2["live_dream_id"])
check("the shadow dream is cleaned the way the live one is",
      e1["shadow_dream"]["text"].startswith("SHADOW-DREAM-MARKER") and e1["shadow_dream"]["cleanup_hits"]["preamble"] == 1)
check("the image went live only", e2["inputs"]["image_live"] is True and e2["inputs"]["image_shadow"] is False)
check("per-thread verdicts: live from dream-log, AEON from its own judge",
      e2["judges"]["live_on_live"]["per_thread"] == {"t1": "resolved", "t2": "unresolved"}
      and e2["judges"]["aeon_on_shadow"]["per_thread"] == {"t1": "resolved", "t2": "unresolved"}
      and e1["judges"]["aeon_on_live"]["per_thread"] == {"t1": "resolved"}
      and e1["judges"]["live_on_live"]["per_thread"] == {"t1": "unresolved"}, (e1["judges"], e2["judges"]))
check("thread facts come from the pool, read-only",
      [(t["id"], t["source"], t["dream_only"]) for t in e2["threads"]] == [("t1", "idle-journal", False), ("t2", "structural-gap", True)])
check("the counterfactual names the thread whose fate would differ",
      e1["counterfactual"]["fates_differ"] == 1 and e2["counterfactual"]["fates_differ"] == 0)
check("an opening echo of the previous dream is flagged on the live side", e1["live_dream"]["opening_echo"] is True
      and e1["shadow_dream"]["opening_echo"] is False)

rep = json.load(open(os.path.join(S.REPORTS, "latest.json")))
cum = rep["cumulative"]
check("the report has agreement, rates by source, non-verdicts and pool counterfactuals",
      "kappa" in cum["judge_agreement_same_dream"] and "idle-journal" in cum["resolution_by_source"]
      and "non_verdict_rate" in cum and cum["pool_counterfactual"]["threads"] == 3
      and cum["pool_counterfactual"]["kept_live_consumed_shadow"] == 1, cum)
rtext = open(os.path.join(S.REPORTS, "latest.json")).read()
check("no dream or thread text enters a report", all(m not in rtext for m in ("MARKER", "THREAD-ONE", "SYS-", "USER-")))

again = S.run(transport=fake, min_age_s=0)
check("a captured dream is shadowed once", again.get("processed") == [] and len(S.load_entries()) == 2, again)

# a reply from any other model is discarded, never stored
def hosted(url, body, timeout):
    return 200, {"x-vintos-provider": "xai", "x-vintos-model": "some-hosted-model"}, json.dumps(
        {"choices": [{"message": {"content": "HOSTED-TEXT. RESOLVED"}}]}).encode()
S.capture_inputs("20261108T040000-33", system="S3", user="U3", category="preoccupation", threads=[("THREAD-ONE-TEXT", "t1")])
S.run(transport=hosted, min_age_s=0)
e3 = next(e for e in S.load_entries() if e["shadow_id"] == "20261108T040000-33")
check("a non-AEON reply is discarded", e3["shadow_dream"]["status"] == "wrong_model" and e3["shadow_dream"]["text"] == ""
      and "HOSTED-TEXT" not in open(S.LOG).read(), e3["shadow_dream"])
check("an unpaired capture says so", e3["live_dream_id"] is None and "reason" in e3["live_pairing"])

# kappa on known pairs
k = S.kappa([("resolved", "resolved"), ("unresolved", "unresolved"), ("resolved", "unresolved"), ("unresolved", "unresolved")])
check("kappa is computed correctly", k == 0.5, k)
check("kappa is undefined, not 1, with no variation", S.kappa([("resolved", "resolved")]) is None)

# the off switch
open(S.OFF, "w").write("off")
check("the off switch stops capture and run", S.capture_inputs("20261108T050000-44", system="s", user="u", category="c",
      threads=[("x", "y")]) is False and S.run(transport=fake, min_age_s=0) == {"ran": False, "reason": "off"})
os.remove(S.OFF)

check("the shadow store is not one memory surfacing walks", True if not os.path.exists(os.path.join(REPO, "scripts", "memory_surfacing.py"))
      else "shadow" not in open(os.path.join(REPO, "scripts", "memory_surfacing.py")).read().split("WRITING_DIRS", 1)[1][:400])

print("%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

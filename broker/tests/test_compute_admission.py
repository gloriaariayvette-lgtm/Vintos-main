#!/usr/bin/env python3
"""Review items 161, 164, 170, 171, 173, 45, 48 (2026-09-10): bounded admission, a local-only
profile, one compute ledger, checkpointed generation stages, compatibility readers. Scratch HOME
only; no model, no network."""
import os, sys, json, time, types, tempfile, importlib.util, subprocess, asyncio

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-adm-")
os.environ["HOME"] = HOME
MEM = os.path.join(HOME, ".vintos", "workspace", "memory"); os.makedirs(MEM, exist_ok=True)
for name in ("requests", "numpy", "httpx"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
sys.path.insert(0, os.path.join(REPO, "scripts")); sys.path.insert(0, os.path.join(REPO, "bin"))

print("\n--- 161: foreground never waits; background yields to a live turn, bounded ---")
CA = load("compute_admission_t", os.path.join(REPO, "scripts", "compute_admission.py"))
CA.MEMORY = MEM; CA.POLL_S = 0.05
sys.modules["compute_admission"] = CA
check("no foreground yet", not CA.foreground_live())
with CA.admit("foreground", organ="chat") as a:
    check("foreground admitted at once", a.admitted and a.waited == 0.0)
check("foreground touched the marker", CA.foreground_live())
t0 = time.time()
try:
    with CA.admit("background", organ="dream", wait_s=0.3):
        check("background ran while a turn is live", False)
except TimeoutError as e:
    check("background waited out its bound while a turn is live", 0.25 <= time.time() - t0 < 2.0 and "foreground live" in str(e), (time.time() - t0, e))
CA.FG_FRESH_S = 0.0     # the turn is over
with CA.admit("background", organ="dream", wait_s=1.0) as b:
    check("background admitted when nothing is live", b.admitted)
    t1 = time.time()
    try:
        with CA.admit("background", organ="dream2", wait_s=0.3):
            check("a second background job waits for the slot", False)
    except TimeoutError:
        check("a second background job waits for the slot", time.time() - t1 >= 0.25)
    with CA.admit("foreground", organ="voice") as fg:
        check("foreground still never waits, even with the slot held", fg.admitted and fg.waited == 0.0)
CA.FG_FRESH_S = 20.0
rows = [json.loads(l) for l in open(os.path.join(MEM, "compute-ledger.jsonl"))]
check("171: every completed admission left a measured line", len(rows) >= 3 and all("latency_ms" in r and "rss_mb" in r and "organ" in r for r in rows), rows[:1])
check("171: lines carry class and no quality field", all(r["class"] in ("foreground", "background") and "quality" not in r for r in rows))

print("\n--- 161: the CLI runs a command after admission ---")
env = dict(os.environ, VINTOS_FG_FRESH_S="0")
rc = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "compute_admission.py"), "run", "background", "--organ", "t", "--", sys.executable, "-c", "print('ran')"],
                    capture_output=True, text=True, env=env)
check("run executes the command and exits with its code", rc.returncode == 0 and "ran" in rc.stdout, rc)
rc2 = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "compute_admission.py"), "run", "background", "--", sys.executable, "-c", "raise SystemExit(3)"],
                     capture_output=True, text=True, env=env)
check("a failing command's code is passed through", rc2.returncode == 3)
LOCKLINE = 'LOCK=""; [ -f "${HOME}/llm-lock.sh" ] && LOCK="bash ${HOME}/llm-lock.sh"'
shells = [f for f in os.listdir(os.path.join(REPO, "bin")) if f.endswith(".sh") and LOCKLINE in open(os.path.join(REPO, "bin", f)).read()]
check("every llm-lock cron shell goes through admission", shells and all("compute_admission.py run background" in open(os.path.join(REPO, "bin", f)).read() and "${ADMIT} ${LOCK} " in open(os.path.join(REPO, "bin", f)).read() for f in shells), shells)

print("\n--- 171: the report is measurements only ---")
RP = load("compute_report_t", os.path.join(REPO, "scripts", "compute-report.py"))
summ = RP.summarise(rows, "organ")
check("medians per organ", "dream" in summ and summ["dream"]["calls"] >= 1 and summ["dream"]["median_latency_ms"] is not None, summ)
check("no quality claim in the report", "quality" not in json.dumps(summ).lower() or "quality claim" in open(os.path.join(REPO, "scripts", "compute-report.py")).read())

print("\n--- 164: a local profile makes no provider request ---")
GR = load("gen_result_t", os.path.join(REPO, "bin", "gen_result.py")); sys.modules["gen_result"] = GR
MR = load("model_router_t", os.path.join(REPO, "bin", "model_router.py"))
ok, why = CA.reserve_paid("chemistry-divergence", "anthropic", "lens-test",
                          reservation_id="prepaid-test")
receipt = {"organ": "chemistry-divergence", "provider": "anthropic",
           "model": "lens-test", "reservation_id": "prepaid-test"}
claimed = MR._reserve_provider("anthropic", "lens-test", receipt)
check("the router claims a prepaid call without charging it a second time",
      ok and claimed == "prepaid-test" and CA.paid_today("anthropic") == 1, why)
try:
    MR._reserve_provider("anthropic", "lens-test", receipt)
    check("a prepaid reservation is single-use", False)
except RuntimeError:
    check("a prepaid reservation is single-use", True)
try:
    MR._reserve_provider("openai", "lens-test", receipt)
    check("a different provider cannot claim the receipt", False)
except RuntimeError:
    check("a different provider cannot claim the receipt", True)
sent = []
async def fake_gemma(msgs, temp=0.85, max_tokens=800):
    sent.append(("gemma", msgs)); return "a local answer"
async def boom(*a, **k):
    sent.append(("provider", a)); raise AssertionError("a provider was called under the local profile")
MR.gemma_call = fake_gemma; MR._claude = boom; MR._grok_result = boom
os.environ["VINTOS_MODEL_PROFILE"] = "local"
res = asyncio.run(MR.route_reply_result("avatar", "sys", [{"role": "user", "content": "hello"}], {}, "http://x", {}, "grok-4"))
check("text-only work goes to Gemma", res["status"] == "valid" and res["provider"] == "gemma" and res["text"] == "a local answer" and res["route"].startswith("gemma"), res)
res2 = asyncio.run(MR.route_reply_result("avatar", "sys", [{"role": "user", "content": [{"type": "text", "text": "look"}, {"type": "image_url", "image_url": {"url": "data:x"}}]}], {}, "http://x", {}, "grok-4"))
check("a task needing images is HELD, named", res2["status"] == "held" and "images" in res2["reason"] and "no provider request" in res2["reason"], res2)
res3 = asyncio.run(MR.route_reply_result("avatar", "sys", [{"role": "user", "content": "x"}], {"tools": [{"name": "t"}]}, "http://x", {}, "grok-4"))
check("a task needing tools is HELD", res3["status"] == "held" and "tools" in res3["reason"])
check("no provider was called", all(k == "gemma" for k, _ in sent), sent)
os.environ["VINTOS_MODEL_PROFILE"] = "mixed"
check("mixed profile is today's behaviour", MR.profile() == "mixed")
lrows = [json.loads(l) for l in open(os.path.join(MEM, "compute-ledger.jsonl"))]
check("171: the router's stages reach the ledger", any(r["organ"].startswith("router:") and r["stage"] == "local" for r in lrows))

print("\n--- 170 / 173: music is background, a spoken line is foreground; files untouched ---")
dm = open(os.path.join(REPO, "bin", "dream-music.py")).read()
check("ACE-Step release goes through background admission", '_admit("background", organ="dream-music"' in dm and 'ACESTEP_URL = "http://localhost:8001"' in dm and '/release_task' in dm)
check("dream-music twins identical", dm == open(os.path.join(REPO, "scripts", "dream-music.py")).read())
vk = open(os.path.join(REPO, "bin", "voice_kokoro.py")).read()
check("Kokoro marks foreground and records, wav path untouched", "touch_foreground" in vk and 'NamedTemporaryFile(suffix=".wav"' in vk and '"aplay", out_path' in vk)
check("the admission wraps the call, never the file handling", "admit(" not in vk.split("out_path")[1][:200] if "out_path" in vk else False)

print("\n--- 45: the bilateral's paid stage survives a death after phase 1 ---")
BS = load("bilateral_stages_t", os.path.join(REPO, "scripts", "bilateral_stages.py")); BS.MEMORY = MEM
k = BS.key("chat", "what did you mean, earlier")
check("nothing to resume at first", BS.resume(k) == {})
BS.checkpoint(k, "p1", {"a1": "draft a", "b1": "draft b", "a1r": "", "b1r": ""}, latency_ms=1234, tag="chat")
check("phase 1 resumes", BS.resume(k).get("p1", {}).get("a1") == "draft a")
check("a stale checkpoint is not resumed", BS.resume(k, now=time.time() + 3600) == {})
check("a different message is a different key", BS.resume(BS.key("chat", "something else")) == {})
BS.done(k, reply_len=80)
check("done consumes the stage, keeps the record", BS.resume(k) == {} and json.load(open(BS._path(k)))["state"] == "done")
lrows = [json.loads(l) for l in open(os.path.join(MEM, "compute-ledger.jsonl"))]
check("the stage's latency reached the ledger with its name", any(r["organ"] == "bilateral:chat" and r["stage"] == "p1" and r["latency_ms"] == 1234 for r in lrows))
sv = open(os.path.join(REPO, "bin", "server.py")).read()
check("server resumes phase 1 from the checkpoint and marks a live turn", "_bs.resume(_bs_key)" in sv and '_bs.checkpoint(_bs_key, "p1"' in sv and "_bs_ca.touch_foreground()" in sv)
wr = open(os.path.join(REPO, "bin", "wants-router.py")).read()
check("the wants step runner persists each step (its checkpoint) and spends", '_spend(want, "steps_run"); _persist_plan_fields(want)' in wr)

print("\n--- 48: compatibility readers, backups, no rewrite on read ---")
SC = load("store_compat_t", os.path.join(REPO, "scripts", "store_compat.py"))
led = os.path.join(MEM, "interaction-ledger.json")
json.dump([{"ts": 1, "gloria": "hi"}], open(led, "w")); before = open(led).read(); mt = os.path.getmtime(led)
rows_, v = SC.load_json_compat(led, SC.LEDGER_MIGRATIONS, default=[])
check("an old row reads with the new keys", rows_[0]["turn_id"] is None and "surface" in rows_[0] and v == 1, rows_)
check("a read rewrote nothing", open(led).read() == before and os.path.getmtime(led) == mt)
SC.save_json_compat(led, rows_, v)
check("the first write at the new version kept a backup of the old", os.path.exists(led + ".bak-v0") and json.load(open(led + ".bak-v0")) == [{"ts": 1, "gloria": "hi"}])
check("... and recorded the version for a list store", open(led + ".version").read().strip() == "1")
rows2, v2 = SC.load_json_compat(led, SC.LEDGER_MIGRATIONS, default=[])
check("a second read sees version 1 and applies nothing", v2 == 1 and rows2 == rows_)
wal = os.path.join(MEM, "wal-log.json"); json.dump({"entries": [{"content": "x"}]}, open(wal, "w"))
d, wv = SC.load_json_compat(wal, SC.WAL_MIGRATIONS, default={"entries": []})
check("WAL entries read with source_turns", d["entries"][0]["source_turns"] == [] and wv == 1)
SC.save_json_compat(wal, d, wv)
check("a dict store carries schema_version after its first write", json.load(open(wal))["schema_version"] == 1 and os.path.exists(wal + ".bak-v0"))
open(os.path.join(MEM, "bad.json"), "w").write("{nope")
try:
    SC.load_json_compat(os.path.join(MEM, "bad.json"), [], default=[]); check("an unreadable store raises, never reads as empty", False)
except Exception:
    check("an unreadable store raises, never reads as empty", True)
il = open(os.path.join(REPO, "scripts", "interaction-ledger.py")).read()
check("the ledger and WAL readers go through the compatibility reader", "LEDGER_MIGRATIONS" in il and "WAL_MIGRATIONS" in open(os.path.join(REPO, "bin", "wal-decay.py")).read())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

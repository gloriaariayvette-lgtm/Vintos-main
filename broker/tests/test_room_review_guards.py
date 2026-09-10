#!/usr/bin/env python3
"""Review items 204, 355, 356, 357, 367, 374, 375, 393 (2026-09-10): the causality door, the room's
pinned dependencies and admission, durable seat drafts, a proxy chain that never stays poisoned,
immutable patch approval with real isolation, diagnostics that name their contract, and room
contexts in the work ledger. Scratch HOME only; no model, no network."""
import os, sys, json, types, tempfile, importlib.util, subprocess, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-room-")
os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
sys.path.insert(0, os.path.join(REPO, "scripts"))
NODE = shutil.which("node") or "/opt/node22/bin/node"

print("\n--- 204: one schema-2 door for every producer of a causality question ---")
CE = load("causality_t", os.path.join(REPO, "scripts", "causality-engine.py"))
CE.MEMORY = MEM; CE.BRING_UP = os.path.join(MEM, "causality-bring-up.json"); CE.PENDING_QUEUE = os.path.join(MEM, ".pending-causality-queue.json")
CE.log = lambda *a, **k: None
rec = CE.queue_question("Why do I keep reaching for this and missing?", "intent_pressure", evidence=["have her say the plain thing"])
check("a queued question is schema-2 shaped", rec and rec["schema_version"] == CE.CAUSALITY_SCHEMA and rec["id"].startswith("CQ-") and rec["formation"]["root_fingerprints"], rec)
rec2 = CE.queue_question("Why do I keep reaching for this and missing?", "intent_pressure", evidence=["have her say the plain thing"])
d = json.load(open(CE.BRING_UP)); q = json.load(open(CE.PENDING_QUEUE))
check("the same question is recorded once and queued once", len(d) == 1 and q == ["Why do I keep reaching for this and missing?"], (d, q))
check("a short question is refused", CE.queue_question("why", "x") is None)
for f in ("scripts/desired_difference.py", "scripts/self_difference.py", "scripts/priority_vector.py", "scripts/campaign.py"):
    check("%s goes through queue_question" % f, "_ce.queue_question(" in open(os.path.join(REPO, f)).read())

print("\n--- 355: the room's dependencies are pinned and checked ---")
req = open(os.path.join(REPO, "agent-room", "requirements-room.txt")).read()
check("requirements name node, python, the library and the seat package", all(k in req for k in ("node", "python3", "agent-room-mcp", "@agent-room/upstash-client")))
orsh = open(os.path.join(REPO, "agent-room", "open-room.sh")).read()
check("open-room checks them before seating anyone", "requirements-room.txt" in orsh and orsh.index("requirements-room.txt") < orsh.index("room-ctl.mjs\" create"))
check("every .mjs imports only node built-ins or the room's own files", all(("node:" in l or "./" in l or "@agent-room" in l or "pathToFileURL" in l) for f in os.listdir(os.path.join(REPO, "agent-room")) if f.endswith(".mjs") for l in open(os.path.join(REPO, "agent-room", f)) if l.startswith("import ")))

print("\n--- 356 / 357: admission before a paid call; drafts and sends are durable ---")
seat = open(os.path.join(REPO, "agent-room", "seat.mjs")).read()
check("the seat asks for admission before generating", "const adm = await admission();" in seat and seat.index("const adm = await admission();") < seat.index("draft = await reply(all)"))
check("admission is the room's turn state, not the seat's guess", "action:'turnState'" in seat.split("async function admission")[1][:400])
check("a draft is saved before it is sent", "saveDraft({ id: Date.now()" in seat and seat.index("saveDraft({ id:") < seat.index("type:'msg'"))
check("every send is logged queued -> sent -> accepted | failed", all(("state: '%s'" % s) in seat for s in ("queued", "sent", "accepted", "failed")))
check("a restarted seat resends its unsent draft once", "resumed" in seat and "resent: true" in seat)
if os.path.exists(NODE):
    for f in ("seat.mjs", "upstash-proxy.mjs"):
        r = subprocess.run([NODE, "--check", os.path.join(REPO, "agent-room", f)], capture_output=True, text=True)
        check("%s parses" % f, r.returncode == 0, r.stderr[:200])

print("\n--- 367: a rejected command never poisons the chain; reconnect resets the parser ---")
px = open(os.path.join(REPO, "agent-room", "upstash-proxy.mjs")).read()
check("the chain swallows a rejection before the next command", "chain.catch(()=>{}).then(()=>cmd(args))" in px and "chain = next.catch(()=>{})" in px)
check("in-flight requests fail with a clear error on close", "redis connection closed; request not answered" in px)
check("the parser is reset on reconnect and on error", px.count("parser = new Resp()") >= 2)
if os.path.exists(NODE):
    js = r'''
    let sock=null, parser={}, queue=[], chain=Promise.resolve();
    let calls=0; function cmd(args){ calls++; return args[0]==='BAD' ? Promise.reject(new Error('bad')) : Promise.resolve({value: args[0]}); }
    function run(args){ const next = chain.catch(()=>{}).then(()=>cmd(args)); chain = next.catch(()=>{}); return next; }
    (async()=>{ let poisoned=false; try { await run(['BAD']); } catch(e){ poisoned = e.message==='bad'; }
      const ok = await run(['GET']); console.log(JSON.stringify({poisoned, ok: ok.value==='GET', calls})); })();'''
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True)
    try: o = json.loads(r.stdout.strip())
    except Exception: o = {}
    check("the chain pattern recovers after a rejection (node)", o.get("poisoned") and o.get("ok") and o.get("calls") == 2, r.stdout + r.stderr)

print("\n--- 374: the approval binds to the exact patch; checks run isolated ---")
SB = load("builder_t", os.path.join(REPO, "scripts", "self_review_builder.py"))
SB.WS = WS; SB.MEM = MEM
for attr in dir(SB):
    v = getattr(SB, attr)
    if isinstance(v, str) and attr.isupper() and "/memory/" in v:
        setattr(SB, attr, os.path.join(MEM, v.split("/memory/", 1)[1]))
pre, how = SB._isolation()
check("isolation is probed and named", how and ("unshare -n" in how or "proxy-blackhole" in how), how)
env = SB._sandbox_env(os.path.join(HOME, "build"))
check("no credential or proxy variable survives; proxies point at a black hole", env["HTTPS_PROXY"] == "http://127.0.0.1:9" and not any(k for k in env if "KEY" in k.upper() or "TOKEN" in k.upper()) and env["HOME"] != HOME)
src = open(os.path.join(REPO, "scripts", "self_review_builder.py")).read()
check("every check runs under the isolation prefix and records it", src.count("_pre + [sys.executable") == 2 and '"isolation": _how' in src)
check("a patch is bound to the decision and a different patch is refused", '"state": "patch_bound"' in src and "the approval does not transfer" in src and src.index('"state": "patch_bound"') < src.index("paths = _patch_paths(patch)"))

print("\n--- 375: diagnostics name their contract and producer ---")
DC = load("dc_t", os.path.join(REPO, "scripts", "diagnostic_contract.py"))
doc = DC.stamp({"spark": {"status": "armed"}}, "systems-checkup", path=os.path.join(REPO, "bin", "systems-checkup.py"))
check("stamp adds contract, version and producer", doc["contract"] == "systems-checkup" and doc["contract_version"] == DC.CONTRACTS["systems-checkup"] and doc["producer"]["git_rev"] and "systems-checkup.py" in doc["producer"]["file"], doc)
ok, why = DC.expect(doc, "systems-checkup"); check("a reader expecting this version accepts it", ok, why)
ok2, why2 = DC.expect(doc, "systems-checkup", version="2.0"); check("a reader expecting another version says so", not ok2 and "expected systems-checkup v2" in why2, why2)
ok3, why3 = DC.expect({"x": 1}, "systems-checkup"); check("an unstamped document is named as such", not ok3 and "not a systems-checkup output" in why3)
check("systems-checkup stamps its JSON", '_stamp(dict(OUT), "systems-checkup"' in open(os.path.join(REPO, "bin", "systems-checkup.py")).read())
check("the subsystem audit carries the header line", 'header_line as _hl' in open(os.path.join(REPO, "scripts", "subsystem_audit.py")).read())
check("/api/system/status is stamped", '_stamp(_out, "system-status"' in open(os.path.join(REPO, "bin", "server.py")).read())
check("header_line names producer and version", "subsystem-audit v" in DC.header_line("subsystem-audit"))

print("\n--- 393: a room context build is a work-ledger entry ---")
mrc = open(os.path.join(REPO, "agent-room", "make-room-context.py")).read()
check("built and failed contexts are recorded with git rev, files read, the day requested", "def record_context_build" in mrc and '"built"' in mrc and '"failed"' in mrc and '"git_rev": _git_rev()' in mrc and '"day_requested": day' in mrc)
pl = open(os.path.join(REPO, "agent-room", "proposal-ledger.py")).read()
check("the proposals page folds the context builds in", "context-builds.jsonl" in pl and "Room contexts built for this day" in pl)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""Review items 80, 99, 125, 145, 149, 154, 286, 312, 314 (2026-09-10). Scratch HOME; no model; no network."""
import os, sys, json, types, tempfile, importlib.util, time, hashlib, wave, struct

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-p37-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True); os.makedirs(MEM, exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)

print("\n--- 80: one idempotency door ---")
ID = load("idempotency", os.path.join(REPO, "scripts", "idempotency.py")); ID.MEMORY = MEM; ID.STORE = os.path.join(MEM, "idempotency.json"); ID.LOG = os.path.join(MEM, "idempotency.jsonl")
k = ID.key_of("the fig", "video-outreach")
check("first time proceeds, second refused and logged, after the window proceeds again", ID.once(k, 60, now=1000) and ID.once(k, 60, now=1010) is False and os.path.exists(ID.LOG) and ID.once(k, 60, now=2000))
check("encounter.dispatch goes through it", '_idem.once("encounter:" + _idem.key_of(text[:200], trigger), ttl_s=3600)' in src("scripts/encounter.py"))

print("\n--- 286 / 312: still approval bound to bytes; content-addressed scene jobs ---")
AS = load("avatar_stage", os.path.join(REPO, "bin", "avatar_stage.py")); AS.STILLS = os.path.join(MEM, "stills"); AS.CLIPS = os.path.join(MEM, "clips"); os.makedirs(AS.STILLS, exist_ok=True)
logs = []; AS.log = lambda m: logs.append(m)
still = os.path.join(AS.STILLS, "patio.jpg"); open(still, "wb").write(b"\xff\xd8" + b"a" * 100)
check("a still without an approval record is not approved", AS._approved_still("patio") is None and "no approval record" in logs[-1])
rec = AS.approve_still("patio")
check("approving records the sha; the same bytes are approved", rec["sha256"] == hashlib.sha256(open(still, "rb").read()).hexdigest() and AS._approved_still("patio") == still)
open(still, "wb").write(b"\xff\xd8" + b"b" * 100)
check("a new revision of the still is not approved until re-approved", AS._approved_still("patio") is None and "changed since it was approved" in logs[-1])
st = src("bin/avatar_stage.py")
check("a scene job is content-addressed and a finished render for the same key is reused", '_cpath = os.path.join(CLIPS, "by-content", _ckey + ".mp4")' in st and 'reused=True' in st and 'content_key=_ckey' in st)

print("\n--- 154: only the reply to the offering turn confirms ---")
CD = load("curiosity_debt", os.path.join(REPO, "scripts", "curiosity_debt.py"))
for a in dir(CD):
    v = getattr(CD, a)
    if isinstance(v, str) and a.isupper() and ".vintos" in v: setattr(CD, a, os.path.join(MEM, os.path.basename(v)))
CD.MEM = MEM
now = time.time()
CD._save([{"id": "q1", "question": "why does she like the fig tree so much", "pull": 0.8, "created": now - 4000, "last_seen": now, "surfaced": 0, "offered": 1, "offered_turn": "T-A", "target": "gloria"}])
check("a reply from another turn does not confirm; the offering turn's reply does", CD.confirm_from_reply("why do you like the fig tree so much?", turn_id="T-B") == [] and CD.confirm_from_reply("why do you like the fig tree so much?", turn_id="T-A") == ["q1"])
check("block() stamps the offering turn", 'r["offered_turn"] = os.environ.get("VINTOS_TURN_ID", "")' in src("scripts/curiosity_debt.py"))

print("\n--- 149: an unsuccessful ghost pass keeps question and source class ---")
gb = src("scripts/ghost-branches.py")
check("update_thread records unsuccessful_passes with question, source_class and why", '"source_class": t.get("kind") or t.get("source") or "unknown"' in gb and 't["unsuccessful_passes"] = t["unsuccessful_passes"][-10:]' in gb)

print("\n--- 145: frontier choices first ---")
ws = src("bin/vintos-websearch.py")
check("pick_question consults his private frontier's decided items before the ladder and consumes them once", "unsaid-frontier.json" in ws and '"consumed_by_search"' in ws and '"source": "frontier:%s"' in ws)

print("\n--- 314: the piece is listened to ---")
DM = load("dream_music", os.path.join(REPO, "bin", "dream-music.py")) if False else None
dm = src("bin/dream-music.py")
# a real listen on a synthetic wav, using the function extracted from the module text
ns = {"os": os, "sys": sys}; exec(dm[dm.index("def listen(fp):"):dm.index("def dl(url, fp):")], ns)
wav = os.path.join(MEM, "t.wav")
with wave.open(wav, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(struct.pack("<%dh" % 8000, *([8000] * 4000 + [-8000] * 4000)))
L = ns["listen"](wav)
check("duration, peak and rms are measured from the bytes", L["measured"] and L["duration_s"] == 1.0 and abs(L["peak"] - 0.244) < 0.01 and L["rms"] > 0.2, L)
check("an unreadable file says unmeasured; the entry carries listening", ns["listen"](os.path.join(MEM, "nope.wav"))["measured"] is False and 'entry["listening"] = [listen(f) for f in downloaded]' in dm)

print("\n--- 125: retrieval counts once per hour ---")
DMM = load("durable_memory", os.path.join(REPO, "scripts", "durable_memory.py"))
for a in dir(DMM):
    v = getattr(DMM, a)
    if isinstance(v, str) and a.isupper() and v.endswith(".json"): setattr(DMM, a, os.path.join(MEM, os.path.basename(v)))
DMM._embed = lambda t: [1.0, 0.0]; DMM._vec = lambda r: [1.0, 0.0]
DMM._save([{"event": "the fig", "later_recalled": 0}]) if hasattr(DMM, "_save") else None
r1 = DMM.recall("the fig at the table again tonight"); r2 = DMM.recall("the fig at the table again tonight")
check("two recalls within the hour count as one recurrence", r1 and r2 and DMM._load()[0]["later_recalled"] == 1)

print("\n--- 99: a KEPT note is bound to the bytes ---")
bk = src("broker/broker.py")
check("keep() records kept_note_bound_to (artifact + sha256) and the event carries it", 'p["kept_note_bound_to"] = {"artifact": _lastf' in bk and '"note_bound_to": p.get("kept_note_bound_to")' in bk)
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)

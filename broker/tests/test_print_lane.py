#!/usr/bin/env python3
"""14 November: the K2 lane, end to end with stand-ins. He decides (Claude with his context), Astra builds and may ask
him one thing, Blender makes the model, her settings slice it, she gets one yes/no text naming the filament and slot,
and only her Yes sends it, with the slot map her printer page would send. Nothing here reaches the printer, Claude,
Astra, Blender or her phone."""
import ast, json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="k2-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(os.environ["SPARK_WORKSPACE"], "memory"), exist_ok=True)
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import k2_printer as K
import print_lane as P
import house_hands as H
import house_boards as B

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store is throwaway", P.JOBS.startswith(HOME) and K.CONFIG.startswith(HOME))
check("the printer's address is not in the code", "192.168." not in open(K.__file__).read() + open(P.__file__).read())

# her slots, as she said them
inv = K.slots()
check("PLA 1, PETG 2, carbon 3, ASA 4 (unconfirmed), TPUs external",
      [(s["slot"], s["material"]) for s in inv["slots"]] == [(1, "PLA"), (2, "PETG"), (3, "PETG-CF"), (4, "ASA")]
      and inv["slots"][3].get("confirmed") is False
      and [e["material"] for e in inv["external"]] == ["TPU", "FOAMING-TPU"])
check("contact layers are another filament: PETG-CF/PETG on PLA, PLA on PETG, ASA on PETG, TPUs none",
      [K.PROFILES[m]["interface"] for m in ("PETG-CF", "PETG", "PLA", "ASA", "TPU", "FOAMING-TPU")]
      == ["PLA", "PLA", "PETG", "PETG", None, None])
check("her trees are slim and automatic", K.COMMON_SUPPORT["support_style"] == "tree_slim"
      and K.COMMON_SUPPORT["support_type"] == "tree(auto)" and K.COMMON_SUPPORT["curr_bed_type"] == "Textured PEI Plate")
check("foaming TPU is her Siraya Air setting: 270 C, half flow, no retraction",
      K.PROFILES["FOAMING-TPU"]["filament"]["nozzle_temperature"] == ["270"]
      and K.PROFILES["FOAMING-TPU"]["filament"]["filament_flow_ratio"] == ["0.5"])
check("filament names are understood", K.material_of("carbon") == "PETG-CF" and K.material_of("foaming tpu") == "FOAMING-TPU"
      and K.material_of("cr-petg") == "PETG" and K.material_of("nylon") == "")

# PRINT: from his hands starts a detached job
spawned = []
ok, said = H.do("PRINT", "a little stand for her phone", run=lambda cmd: spawned.append(cmd))
check("PRINT: starts a job and says she gets a text first", ok and "text" in said and spawned and spawned[0][-2] == "run", said)
jid = spawned[0][-1]
ok2, said2 = P.start("another thing", spawn=lambda c: None)
check("one job at a time", not ok2 and "going already" in said2, said2)
check("K2 is wants-only and no room board offers PRINT",
      all("PRINT" not in B.MENUS[m] for m in ("shower", "sofa", "office", "knock"))
      and B.HOW["PRINT"].startswith("PRINT: "))
check("the Slack hands list PRINT", "PRINT: a thing to make on her Creality K2" in open(os.path.join(REPO, "scripts", "dot_channel.py")).read())
router = open(os.path.join(REPO, "bin", "wants-router.py")).read()
check("the wants router exposes the K2 lane before execution",
      '"action": "print_3d"' in router and '"print_3d": print_3d' in router
      and "print_lane.start(want_text)" in router)
node = next(n for n in ast.parse(router).body if isinstance(n, ast.FunctionDef) and n.name == "print_3d")
ns = {"sys": sys, "SCRIPTS": os.path.join(REPO, "scripts"), "log": lambda _: None}
exec(compile(ast.Module(body=[node], type_ignores=[]), "wants-router.py", "exec"), ns)
old_start = P.start; routed = []
try:
    P.start = lambda want: (routed.append(want) or (True, "K2 job queued behind Gloria's final Yes"))
    routed_result = ns["print_3d"]("I want to 3D print a small cable guide")
finally:
    P.start = old_start
check("a 3D want enters print_lane and retains its approval receipt",
      routed == ["I want to 3D print a small cable guide"] and "final Yes" in routed_result, routed_result)

# the worker, with stand-ins
asked_him, astra_briefs, texts = [], [], []
def him(extra, user):
    asked_him.append((extra, user))
    if user == "Decide the print.":
        return '{"make": "a phone stand with a cable slot", "material": "carbon", "size_mm": [80, 70, 90], "why": "her desk"}'
    return "Tilt it 65 degrees; her phone is 78 mm wide."
calls = iter(["QUESTION: what angle and how wide is her phone?", "import bpy\n# first try", "import bpy\n# fixed"])
def astra_call(system, messages, **kw):
    astra_briefs.append(messages[0]["content"]); return next(calls)
blender_tries = []
def blender(script, out, wd):
    blender_tries.append(script)
    if "first try" in script: return False, "Error: bad context"
    open(out, "w").write("solid x\nendsolid x\n"); return True, ""
def slicer(stl, material, outdir):
    return {"ok": True, "gcode": os.path.join(HOME, "plate.gcode"), "minutes": 134.0, "grams": [41.2, 0.9],
            "tools": [0, 1], "interface": "PLA", "material": material}
def asker(q, by, ref, title):
    texts.append((q, ref)); return {"id": "Q-1"}, "asked"
P.astra_seconds_today = lambda: 0.0
job = P.run(jid, ask=him, call=astra_call, blender=blender, slicer=slicer, asker=asker,
            printer_status=lambda: {"reachable": True, "state": "standby", "cfs_connected": True})
check("he decided with his own context (Claude with his context is asked first)", asked_him and "PRINT: a little stand" in asked_him[0][0])
check("Astra's question went to him, and his answer went back to her",
      len(asked_him) == 2 and "Astra asks: what angle" in asked_him[1][1] and "He answered: Tilt it 65" in astra_briefs[1], astra_briefs[1:2])
check("Blender's refusal went back to Astra and her fix built", len(blender_tries) == 2 and "failed in Blender" in astra_briefs[2])
check("three Astra calls at most, counted", len(P.get(jid)["astra"]) == 3)
check("the job waits on her", job["state"] == "asked" and job["ask"] == "Q-1", job.get("state"))
q, ref = texts[0]
check("her text names the filament and slot, the contact filament and slot, time and grams",
      "carbon PETG from slot 3" in q and "PLA from slot 1 on the support contacts" in q and "2h 14m" in q and "41 g" in q
      and ref == "k2-print:" + jid, q)
check("the slot map is carbon in T1C, PLA in T1A", [(s["id"], s["material"]) for s in job["slots"]] == [("T1C", "PETG-CF"), ("T1A", "PLA")])
check("he can see it in his context", "waiting on Gloria's yes" in P.context_line())

# her answer
class FakeK:
    def __init__(self, state="standby", cfs=True, box=None):
        self.st = {"reachable": True, "state": state, "cfs_connected": cfs, "box": box or [], "file": ""}
        self.sent, self.up = [], []
    def status(self): return self.st
    def preflight(self, job): return K.preflight(job, self.st)
    def upload(self, g, name): self.up.append(name); return K.GCODES + name
    def start(self, path, job): K.start(path, job, socket_send=lambda msgs: self.sent.extend(msgs)); self.st.update(state="printing", file=path)
    def printing(self, name): return self.st["state"] == "printing" and self.st["file"].endswith(name)
busy = FakeK(state="printing")
P.tend(k=busy, asks=lambda qid: {"state": "answered", "answer": "yes"})
check("a busy printer holds her Yes instead of starting", P.get(jid)["state"] == "held" and not busy.sent, P.get(jid)["history"][-1])
k = FakeK(box=[{"slot": 3, "type": "PETG-CF"}, {"slot": 1, "type": "PLA"}])
P.send(P.get(jid), k)
j = P.get(jid)
check("when it is free, her Yes sends it and it prints", j["state"] == "printing" and k.up and j["file"] == k.up[0], j["history"][-1])
check("the slot map goes first, then the multi-colour start, as her printer page sends them",
      [list(m["params"])[0] for m in k.sent] == ["colorMatch", "multiColorPrint"]
      and [(e["id"], e["boxId"], e["materialId"]) for e in k.sent[0]["params"]["colorMatch"]["list"]] == [("T1C", 1, 2), ("T1A", 1, 0)], k.sent)
k.st.update(state="complete")
P.tend(k=k, asks=lambda q: {})
check("a finished print is noted", P.get(jid)["state"] == "done")

# a slot that reads wrong is not printed from
job2 = dict(j, where="cfs")
ok, why = K.preflight(job2, {"reachable": True, "state": "standby", "cfs_connected": True, "box": [{"slot": 3, "type": "PLA"}]})
check("a slot that reads another filament stops the send", not ok and "slot 3 reads PLA" in why, why)
ok, why = K.preflight(job2, {"reachable": True, "state": "standby", "cfs_connected": False, "box": []})
check("a disconnected CFS stops the send", not ok and "disconnected" in why)

# external TPU: a plain print, no slot map
sent = []
K.start("/x.gcode", {"where": "external", "slots": []}, socket_send=lambda m: sent.extend(m))
check("the external spool is a plain print", sent == [{"method": "set", "params": {"opGcodeFile": "printprt:/x.gcode", "enableSelfTest": 0}}])

# her No
ok, _ = P.start("a hook", spawn=lambda c: None)
j3 = P.load()[-1]
P.note(j3["id"], "asked", "asked", ask="Q-2", asked_at=P._iso())
P.tend(k=FakeK(), asks=lambda q: {"state": "answered", "answer": "no"})
check("her No ends it", P.get(j3["id"])["state"] == "ended")
check("two a day", not P.start("a third", spawn=lambda c: None)[0])

# he may decide not to
P.ASK = None
plan, why = P.decide({"what": "x"}, ask=lambda e, u: '{"make": null, "why": "not today"}')
check("he can decide not to print", plan is None and "not today" in why)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

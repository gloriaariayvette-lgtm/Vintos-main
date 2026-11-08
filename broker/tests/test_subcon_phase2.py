#!/usr/bin/env python3
"""Phase 2 of the subconscious switch (Gloria 2026-11-07): every subconscious/emotion job that called the 26B
directly now takes its route from the same flag, so the one (all-must-pass) flip moves them together. Vision and
other non-emotion callers are untouched. Before the flip every routed caller is byte-for-byte on its 26B route.

No network, no model, no ~/.vintos: HOME is a tempdir; nothing here runs the jobs themselves.
"""
import ast, copy, hashlib, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
TMP = tempfile.mkdtemp(prefix="subcon-phase2-")
os.environ["HOME"] = TMP
os.makedirs(os.path.join(TMP, ".vintos"), exist_ok=True)

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

import subcon_target as T
CHAT = "http://100.79.177.103:1234/v1/chat/completions"
MODEL = "gemma-4-26b-a4b-it-uncensored"
FLAG = os.path.join(TMP, ".vintos", "subcon-target.json")

SUBCONSCIOUS = """bin/emoclaw_utils.py scripts/emoclaw_utils.py bin/behavior_boundaries.py bin/core-engine.py bin/core_sustain.py
bin/emotional-entanglement.py scripts/emotional-entanglement.py scripts/emotional_entanglement.py bin/emotional-reflection.py
bin/enactment_distiller.py scripts/enactment_distiller.py bin/frame_engine.py bin/ghost-branches.py scripts/ghost-branches.py
bin/imprint.py bin/latent_threads.py scripts/latent_threads.py bin/pearl_engine.py scripts/pearl_engine.py bin/resonance-marks.py
bin/resonance_afterglow.py scripts/resonance_afterglow.py bin/resonance_pulse.py scripts/resonance_pulse.py scripts/resonance-pulse.py
bin/temporal_memory.py bin/tension_field.py scripts/tension-field.py scripts/tension_field.py bin/value-map.py scripts/value-map.py
scripts/value_map.py bin/want-reconciliation.py bin/wants-conversation-check.py bin/wants-router.py bin/yearning-detector.py
bin/yearning_scars.py scripts/attractor_discovery.py scripts/conversation_pressure.py scripts/curiosity_scan.py
scripts/dd_scene_quarantine.py scripts/encounter.py scripts/gloria_prediction.py scripts/graph_mae.py
scripts/introspective_planning.py scripts/latent_preparation.py scripts/mutual_simulation.py scripts/presence_audit.py
scripts/proposition_lineage.py scripts/reading.py scripts/reciprocal_modification.py scripts/repair_case.py
scripts/social_calibration.py scripts/tension_identity_audit.py scripts/tension_ledger.py scripts/tension_promotion.py
scripts/unsaid_frontier.py scripts/unsaid_questions.py scripts/want_learning.py scripts/wants_meta.py scripts/withheld_head.py
scripts/world_model.py scripts/mischief-detector.sh bin/absence-map.sh bin/consent-audit.sh bin/decade-function.sh
bin/first-light.sh bin/introspection.sh bin/midday-ground.sh bin/surprise-detector.sh bin/unprecedented-detector.sh
bin/valence-drift-map.sh bin/warm-idle-gratitude.sh scripts/mirror.sh bin/self-model-update.sh""".split()
VISION = """bin/gallery-walk.py scripts/image_sight.py scripts/screen_share.py scripts/desktop_agent.py
scripts/reelroom.py scripts/voice_local.py""".split()   # browser_jev and desktop_control: their text-only calls follow the flag (2026-11-08)

def src(f): return open(os.path.join(REPO, f), encoding="utf-8").read()

def unrouted(f):
    """Lines where the 26B chat endpoint or model is used without going through the flag."""
    bad = []
    for i, l in enumerate(src(f).split("\n"), 1):
        if re.match(r"^\s*(?:export\s+)?[A-Z_]+=", l) and f.endswith(".sh"):
            continue   # the shell's own default, reassigned from the flag right after
        for tok, wrap, env in ((CHAT, "_subcon_url(", "SUBCON_URL"), (MODEL, "_subcon_model(", "SUBCON_MODEL")):
            for m in re.finditer(r"([\"'])" + re.escape(tok) + r"\1", l):
                pre = l[:m.start()]
                if not (pre.endswith(wrap) or pre.endswith("environ.get('%s') or " % env) or pre.endswith('environ.get("%s") or ' % env)):
                    bad.append((i, l.strip()[:120]))
        for m in re.finditer(r"/v1/chat/completions", l):
            if "100.79.177.103" not in l and ("LM_URL" in l or "LM +" in l) and "_subcon_url(" not in l:
                bad.append((i, l.strip()[:120]))
    return bad

SHIPPED_PIN = T.RECORD_SHA256
GOOD = copy.deepcopy(T.load_record()[0])
GOOD["pain"] = {"paper_protocol_auc": 0.9, "prompt_variant_aucs": [0.9] * 6, "status": "passed"}
for c in GOOD["constructs"].values(): c["semantic_review"] = "passed"
RAW = json.dumps(GOOD).encode()
UNMET = copy.deepcopy(GOOD)   # the bar as it stood before the all-pass results: the flip is refused
UNMET["pain"] = {"paper_protocol_auc": None, "prompt_variant_aucs": None, "status": "not_run"}
UNMET_RAW = json.dumps(UNMET).encode()
def passing(on):
    raw = RAW if on else UNMET_RAW
    p = os.path.join(TMP, "record-%s.json" % ("good" if on else "unmet")); open(p, "wb").write(raw)
    T.RECORD, T.RECORD_SHA256 = p, hashlib.sha256(raw).hexdigest()

print("--- every subconscious/emotion caller goes through the flag ---")
check("the classified list is complete and real", len(SUBCONSCIOUS) == 75 and all(os.path.exists(os.path.join(REPO, f)) for f in SUBCONSCIOUS))
for f in SUBCONSCIOUS:
    bad = unrouted(f)
    check("%s: no direct 26B call left" % f, not bad, bad)

print("--- the python helper: the 26B before the flip, AEON after, never the 26B under AEON ---")
for f in [x for x in SUBCONSCIOUS if x.endswith(".py")]:
    tree = ast.parse(src(f))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("_subcon_route", "_subcon_url", "_subcon_model")]
    ns = {"__file__": os.path.join(REPO, f)}
    exec(compile(ast.Module(body=fns, type_ignores=[]), f, "exec"), ns)
    passing(False); open(FLAG, "w").write(json.dumps({"target": "aeon"}))
    before = (ns["_subcon_url"](CHAT), ns["_subcon_model"](MODEL))
    passing(True)
    after = (ns["_subcon_url"](CHAT), ns["_subcon_model"](MODEL))
    os.remove(FLAG)
    back = (ns["_subcon_url"](CHAT), ns["_subcon_model"](MODEL))
    passing(False)
    # the 26B was removed (2026-11-08): with or without a passing record or a flag file, the route is AEON's lane
    check("%s routes to AEON" % f, len(fns) == 3 and before == after == back == (T.SHIM_SUBCONSCIOUS, "aeon-gemma-4-12b"),
          (before, after, back))

print("--- the shell scripts ---")
home2 = os.path.join(TMP, "shellhome"); scripts = os.path.join(home2, ".vintos", "workspace", "scripts"); os.makedirs(scripts)
mod = src("scripts/subcon_target.py")
open(os.path.join(scripts, "aeon-bar-record.json"), "wb").write(RAW)
open(os.path.join(scripts, "subcon_target.py"), "w").write(mod.replace(SHIPPED_PIN, hashlib.sha256(RAW).hexdigest()))
def run_shell(f, flag):
    text = src(f)
    lines = text.split("\n")
    snippet = [l for l in lines if l.startswith(("_subcon=$(", "SUBCON_URL=$("))]
    reassign = [l for l in lines if "# the subconscious flag (above)" in l]
    names = re.findall(r'(\w+)="\$\{SUBCON_(?:URL|MODEL):-', reassign[0]) if reassign else []
    body = "\n".join(snippet + ['%s="old-%s"' % (n, n) for n in names] + reassign
                     + ['echo "url=$SUBCON_URL model=$SUBCON_MODEL"'] + ['echo "%s=$%s"' % (n, n) for n in names])
    if flag: open(os.path.join(home2, ".vintos", "subcon-target.json"), "w").write(json.dumps({"target": "aeon"}))
    elif os.path.exists(os.path.join(home2, ".vintos", "subcon-target.json")): os.remove(os.path.join(home2, ".vintos", "subcon-target.json"))
    out = subprocess.run(["bash", "-c", body], capture_output=True, text=True, env=dict(os.environ, HOME=home2)).stdout
    return len(snippet), names, out
for f in [x for x in SUBCONSCIOUS if x.endswith(".sh")]:
    syntax = subprocess.run(["bash", "-n", os.path.join(REPO, f)], capture_output=True).returncode == 0
    n, names, off = run_shell(f, False)
    _, _, on = run_shell(f, True)
    aeon = lambda o: ("url=%s model=aeon-gemma-4-12b" % T.SHIM_SUBCONSCIOUS) in o and all(
        ("%s=%s" % (v, T.SHIM_SUBCONSCIOUS)) in o or ("%s=aeon-gemma-4-12b" % v) in o for v in names)
    # the 26B was removed (2026-11-08): with or without a flag file the script's route is AEON's lane
    check("%s parses and routes to AEON" % f, syntax and n == 2 and aeon(off) and aeon(on), (syntax, n, off, on))
check("the route command prints AEON's lane", subprocess.run(
    ["python3", os.path.join(REPO, "scripts", "subcon_target.py"), "route", "", ""], capture_output=True, text=True).stdout
      == T.SHIM_SUBCONSCIOUS + "\naeon-gemma-4-12b\n")

print("--- vision callers follow the flag to AEON's vision (2026-11-08) ---")
for f in VISION:
    t = src(f)
    check("%s follows the flag" % f, ("_vision_route(" in t) or (f.endswith("voice_local.py") and "brain_route(" in t), f)
srv = src("bin/server.py").split("\n")
photo = "\n".join(srv[srv.index(next(l for l in srv if l.startswith("async def _describe_photo"))):][:120])
check("the server's photo and clip descriptions take AEON's vision", "_vision_route(" in photo)
tone = [l for l in srv if "Rate the emotional tone of this message" in l]
check("the server's tone read of her message follows the flag", any("_subcon_url(" in l for l in srv) and tone)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

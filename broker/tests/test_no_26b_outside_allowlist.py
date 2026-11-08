#!/usr/bin/env python3
"""The 26B is gone from his code (Gloria 2026-11-08: "we can remove 26b completely once we confirm everything is in
Aeon"). Everything runs on AEON: text, subconscious, emotion and vision.

Checks, all over the checkout's own files (no network, no model, no ~/.vintos: HOME is a tempdir):
  1. No 26B model name, file name or target name appears anywhere in code. The allowlist is empty; only historical
     docs, evidence and tests may still name it.
  2. Every file that routes through the flag (subcon_target) is in the deploy's install list (or is a live alias
     of one). On 8 November about twenty routed files had never been installed, so Aegis still ran old copies that
     called the 26B directly and kept reloading it on the MacBook.
  3. Every route resolves to AEON: the subconscious lane, the call's brain and the vision model.
"""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "bin"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
TMP = tempfile.mkdtemp(prefix="no-26b-")
os.environ["HOME"] = TMP
os.makedirs(os.path.join(TMP, ".vintos"), exist_ok=True)
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
os.environ["XAI_API_KEY"] = "test-xai"

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:600]) if d and not ok else ""))

# The 26B by name, file or target. (The MacBook LM Studio address is not a 26B marker: AEON's vision is served there.)
TOKEN = re.compile(r"gemma-4-26b|26b-a4b|TrevorJS|residual-26b|macbook_26b|gemma26b|gemma-26b", re.I)
WRAP = re.compile(r"_subcon_url\(|_subcon_model\(|_subcon_route\(|_vision_route\(|generative_route\(|brain_route\(|vision_route\(|SUBCON_URL|SUBCON_MODEL")
SKIP = re.compile(r"^(docs|audit|offline|bench|broker/tests)/|\.(md|jsonl|diff|txt|csv|html)$")
# A literal assigned to a name: python  NAME = "..."  /  NAME = os.environ.get("X", "...")   shell  NAME="..." / NAME="${X:-...}"
ASSIGN = re.compile(r"""(?:^|[;\s])([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:os\.environ\.get\(\s*["'][A-Z_]+["']\s*,\s*)?["'](?:\$\{[A-Z_]+:-)?(?:https?://)?$""")

# Gloria 2026-11-08: "We're just switching the model fully." Nothing may name the 26B, routed or not.
ALLOW = {}
WHERE = {}

def files():
    out = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True, text=True).stdout.split()
    if not out:   # an exported tree without git: walk it
        out = [os.path.relpath(os.path.join(dp, f), REPO) for dp, dn, fn in os.walk(REPO) if "/.git" not in dp for f in fn]
    return sorted(f for f in out if not SKIP.search(f) and os.path.isfile(os.path.join(REPO, f)))

def src(f):
    return open(os.path.join(REPO, f), encoding="utf-8", errors="replace").read()

def flag_default(f, text, line, start):
    """The literal is a default that the flag replaces: the name it is assigned to goes through the flag."""
    m = ASSIGN.search(line[:start])
    if not m:
        return False
    v = re.escape(m.group(1))
    if f.endswith(".sh"):
        return re.search(r"\$\{SUBCON_(?:URL|MODEL):-\$%s\}" % v, text) is not None
    return re.search(r"(?:_subcon_url|_subcon_model|_subcon_route|_vision_route|generative_route|brain_route|vision_route)\((?:[^()]|\([^()]*\))*?(?:\{|\b)%s\b" % v, text) is not None

print("--- every 26B id or MacBook LM Studio address in code goes through the flag, or is listed ---")
direct, found_allowed = {}, {}
for f in files():
    text = src(f)
    if not TOKEN.search(text):
        continue
    for i, line in enumerate(text.split("\n"), 1):
        for m in TOKEN.finditer(line):
            reasons = ALLOW.get(f, {})
            why = next((r for r in reasons if any(w in line for w in WHERE[r])), None)
            if why is None:
                direct.setdefault(f, []).append("%d: %s" % (i, line.strip()[:110]))
            else:
                found_allowed.setdefault(f, {}).setdefault(why, 0)
                found_allowed[f][why] += 1
check("no direct 26B call outside the allowlist", not direct, "; ".join("%s:%s" % (f, l) for f, ls in direct.items() for l in ls))
for f, reasons in sorted(ALLOW.items()):
    check("%s: exactly the listed exceptions (%s)" % (f, "; ".join("%d %s" % (n, r.split(":")[0]) for r, n in reasons.items())),
          found_allowed.get(f, {}) == reasons, found_allowed.get(f, {}))

print("--- the flag-routed callers are the ones the deploy installs ---")
deploy = src("scripts/deploy-atelier.sh")
block = deploy[deploy.index('SCRIPTS="'):deploy.index('MANIFEST="$(printf')]
installed = set()
for m in re.finditer(r'(?:SCRIPTS|BINS)="([^"]*)"', block, re.S):
    installed.update(w for w in m.group(1).split() if not w.startswith("$"))
# Live names that are symlinks to an installed file, and files that run from the checkout itself.
ALIASES = {"frame-engine.py": "frame_engine.py", "resonance_marks.py": "resonance-marks.py",
           "wants_conversation_check.py": "wants-conversation-check.py", "yearning-scars.py": "yearning_scars.py",
           "yearning_detector.py": "yearning-detector.py"}
FROM_CHECKOUT = {"buzz-integration/run-local-gemma.py"}
HELD = set()   # nothing is held: Gloria 2026-11-08, "I didn't hold those back. Aeon."
routed = [f for f in files() if f.endswith((".py", ".sh")) and f.startswith(("bin/", "scripts/", "buzz-integration/"))
          and WRAP.search(src(f)) and f != "scripts/subcon_target.py"]
missing = [f for f in routed if f not in FROM_CHECKOUT and os.path.basename(f) not in installed and os.path.basename(f) not in HELD
           and ALIASES.get(os.path.basename(f)) not in installed]
check("there are flag-routed callers to check (%d)" % len(routed), len(routed) > 80, len(routed))
check("every flag-routed caller is installed by the deploy (or is a live alias of one)", not missing, missing)
for b in ("emotion_read.py", "imprint.py", "resonance-marks.py", "yearning-detector.py", "yearning_scars.py", "reading.py",
          "introspective_planning.py", "tension_identity_audit.py", "want_learning.py", "conflict_surface.py", "velqan-coiner.py",
          "morning-briefing.sh", "valence-drift-map.sh", "subcon_target.py", "aeon-bar-record.json"):
    check("the deploy installs %s" % b, b in installed)
check("the server-side twin of emoclaw_utils.py is installed too", "for _twin in emoclaw_utils.py" in deploy
      and 'PLAN="$PLAN$SRC/scripts/$_twin|$_tw' in deploy)

print("--- every route resolves to AEON ---")
def _refused(fn):
    try:
        fn()
    except ValueError:
        return True
    return False
import subcon_target as T
open(os.path.join(TMP, ".vintos", "subcon-target.json"), "w").write('{"target": "aeon"}')
check("the shipped pass record is complete, and the target is AEON", T.active() == "aeon" and not T.unmet(), T.unmet())
check("AEON is the only target there is", sorted(T.TARGETS) == ["aeon"], sorted(T.TARGETS))
os.remove(os.path.join(TMP, ".vintos", "subcon-target.json"))
check("with no flag file at all, still AEON", T.active() == "aeon")
open(os.path.join(TMP, ".vintos", "subcon-target.json"), "w").write('{"target": "old"}')
check("an unknown name in the flag file: still AEON", T.active() == "aeon")
check("and the old target cannot be set", _refused(lambda: T.set_target("gemma" + "26b")))
open(os.path.join(TMP, ".vintos", "subcon-target.json"), "w").write('{"target": "aeon"}')
url, model = T.generative_route("http://100.79.177.103:1234/v1/chat/completions", "some-old-model")
check("a caller's default resolves to AEON's subconscious lane", (url, model) == (T.SHIM_SUBCONSCIOUS, "aeon-gemma-4-12b"), (url, model))
check("AEON's lane has no other fallback", T.pool_chain() == ["pool:aeon", "aegis_gemma"], T.pool_chain())
import vintos_claude_shim as S
check("the shim's subconscious lane is AEON only", S.subconscious_chain() == ["pool:aeon", "aegis_gemma"], S.subconscious_chain())
for p, j in (("/v1/chat/completions", {"max_tokens": 80}), ("/gemma/v1/chat/completions", {}), ("/gemma-aegis/v1/chat/completions", {}),
             ("/pool/subconscious/v1/chat/completions", {})):
    c = S.provider_chain(dict(j), p)
    check("shim %s never reaches the 26B" % p, "gemma" not in c, c)

print("--- every image call takes AEON's own vision (Gloria 2026-11-08: \"Yes, vision to Aeon\") ---")
VISION_CALLERS = ("scripts/image_sight.py", "bin/gallery-walk.py", "scripts/screen_share.py", "scripts/desktop_agent.py",
                  "scripts/dot_channel.py", "bin/vintos-websearch.py", "bin/server.py", "scripts/reelroom.py")
for f in VISION_CALLERS:
    check("%s routes its image calls through the flag's vision route" % f, "_vision_route(" in src(f))
srv = src("bin/server.py")
for fn in ("async def _describe_photo", "[vision clip] claude failed"):
    part = srv[srv.index(fn):srv.index(fn) + 6000]
    check("server %s: the local eye is AEON's vision route" % fn.split()[-1], "_vision_route(" in part and '"model": _vmodel' in part)
v = T.vision_route("http://lmstudio.invalid/v1/chat/completions", "some-old-model")
check("with the flag on AEON, an image call resolves to AEON's vision model, thinking off, at the same endpoint",
      v == ("http://lmstudio.invalid/v1/chat/completions", "aeon-gemma-4-12b", {"reasoning_effort": "none"}), v)
bk = os.path.join(TMP, "backends.json")
open(bk, "w").write(json.dumps([{"label": "x", "machine": "macbook", "kind": "lmstudio", "model": "m",
                                 "url": "http://mac.invalid/v1/chat/completions"}]))
check("a caller with no endpoint of its own (the Reel Room) gets the MacBook LM Studio address from the pool config",
      T.vision_route(None, "m", backends_path=bk)[:2] == ("http://mac.invalid/v1/chat/completions", "aeon-gemma-4-12b"))
check("no MacBook address in the pool config: the caller keeps its own route",
      T.vision_route(None, "m", backends_path=os.path.join(TMP, "none.json")) == (None, "m", {}))
er = src("scripts/emotion_read.py")
check("emotion_read keeps its own emotion-lane hook (resolving to AEON), and the deploy installs that version",
      "LM_URL, MODEL = _subcon.generative_route(LM_URL, MODEL)" in er and "emotion_read.py" in installed)

print("--- text calls inside the browser and desktop helpers follow the flag ---")
import ast
for f, call in (("scripts/browser_jev.py", '_url, _model = _subcon_route(getattr(self.fallback, "endpoint")'),
                ("scripts/desktop_control.py", "url, name = _subcon_route(MODEL_URL, MODEL_NAME or None)")):
    t = src(f)
    fns = [n for n in ast.parse(t).body if isinstance(n, ast.FunctionDef) and n.name == "_subcon_route"]
    ns = {"__file__": os.path.join(REPO, f)}
    exec(compile(ast.Module(body=fns, type_ignores=[]), f, "exec"), ns)
    got = ns["_subcon_route"]("http://100.79.177.103:1234/v1/chat/completions", "some-old-model")
    check("%s: its text call goes through the flag, and resolves to AEON" % f,
          len(fns) == 1 and call in t and got == (T.SHIM_SUBCONSCIOUS, "aeon-gemma-4-12b"), got)
check("desktop_control: an explicit VINTOS_DESKTOP_MODEL_URL keeps its own route",
      'if "VINTOS_DESKTOP_MODEL_URL" not in os.environ:' in src("scripts/desktop_control.py"))
os.remove(os.path.join(TMP, ".vintos", "subcon-target.json"))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

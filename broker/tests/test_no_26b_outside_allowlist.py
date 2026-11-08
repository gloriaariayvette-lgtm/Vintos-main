#!/usr/bin/env python3
"""No code path reaches the MacBook 26B except the listed vision exceptions (Gloria 2026-11-08: "we need to switch
anything pointing to 26b to aeon and make sure 26b is still unloaded from the MacBook").

Three checks, all over the checkout's own files (no network, no model, no ~/.vintos: HOME is a tempdir):
  1. Every 26B model id or MacBook LM Studio address in code either goes through the subconscious flag
     (subcon_target), or is a default that the flag replaces, or is on the allowlist below with its reason.
     A new direct 26B call anywhere fails here until it is routed or listed.
  2. Every file that routes a 26B call through the flag is in the deploy's install list (or is a live alias of one
     that is). On 8 November about twenty routed files had never been installed, so Aegis still ran their old
     copies, and those called the 26B directly and kept reloading it on the MacBook.
  3. With the flag on AEON and the shipped pass record, a flag-routed default resolves to AEON's lane.
"""
import os, re, subprocess, sys, tempfile

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

TOKEN = re.compile(r"gemma-4-26b-a4b-it-uncensored|26b-a4b|TrevorJS|residual-26b|macbook_26b|100\.79\.177\.103:1234", re.I)
WRAP = re.compile(r"_subcon_url\(|_subcon_model\(|_subcon_route\(|generative_route\(|brain_route\(|SUBCON_URL|SUBCON_MODEL")
SKIP = re.compile(r"^(docs|audit|offline|bench|broker/tests)/|\.(md|jsonl|diff|txt|csv|html)$")
# A literal assigned to a name: python  NAME = "..."  /  NAME = os.environ.get("X", "...")   shell  NAME="..." / NAME="${X:-...}"
ASSIGN = re.compile(r"""(?:^|[;\s])([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:os\.environ\.get\(\s*["'][A-Z_]+["']\s*,\s*)?["'](?:\$\{[A-Z_]+:-)?(?:https?://)?$""")

# Every direct (unrouted) occurrence that may stay, by file: {reason: count}. Counts are exact, so a new one fails.
VISION = "vision/screen: sends images; stays on the 26B until AEON has a vision projector (Gloria's exception)"
ENCODER = "nomic embeddings on the MacBook's LM Studio: an encoder, not the 26B"
ENCODER_BASE = "LM Studio base address used only for nomic embeddings (checked below)"
NOT_CHAT = "reads LM Studio's model list; never names or loads the 26B"
IDENTITY = "the 26B's identity in the flag's own target table"
SHIM_LANE = "the shim's 26B lane: dropped from every chain once the flag is on AEON (aeon_everywhere)"
SHIM_PATH = "goes through the shim's /gemma path, which is AEON once the flag is on AEON"
MANIFEST_LABEL = "static Buzz manifest text; its runner (run-local-gemma.py) follows the flag"
ALLOW = {
    "bin/gallery-walk.py": {VISION: 2}, "scripts/gallery-walk.py": {VISION: 2},
    "scripts/image_sight.py": {VISION: 2},
    "scripts/screen_share.py": {VISION: 2}, "scripts/desktop_agent.py": {VISION: 2},
    "bin/server.py": {VISION: 4, ENCODER: 1}, "scripts/server.py": {VISION: 4, ENCODER: 1},
    "bin/vintos-websearch.py": {ENCODER: 1}, "scripts/vintos-websearch.py": {ENCODER: 1},
    "scripts/self_review.py": {ENCODER: 1},
    "bin/deviation_check.py": {ENCODER_BASE: 1}, "bin/deviation-check.py": {ENCODER_BASE: 1},
    "scripts/deviation_check.py": {ENCODER_BASE: 1}, "scripts/deviation-check.py": {ENCODER_BASE: 1},
    "scripts/lab_token_measure.py": {NOT_CHAT: 1},
    "scripts/subcon_target.py": {IDENTITY: 1},
    "bin/vintos_claude_shim.py": {SHIM_LANE: 2},
    "scripts/reelroom.py": {SHIM_PATH: 1},
    "buzz-integration/agents.json": {MANIFEST_LABEL: 2},
}
# Where in those files the allowed occurrences are (a substring of the line), so a count cannot be "spent" elsewhere.
WHERE = {
    VISION: ("image", "vision", "LM_API", '"model": "gemma-4-26b', "GEMMA_API", "GEMMA_MODEL", "client.post", '"http://100.79.177.103:1234/v1/chat/completions",'),
    ENCODER: ("/v1/embeddings",), ENCODER_BASE: ('LM_URL = "http://100.79.177.103:1234"',), NOT_CHAT: ("LMSTUDIO_BASE",), IDENTITY: ('"identity"',),
    SHIM_LANE: ("GEMMA_URL =", "GEMMA_MODEL ="), SHIM_PATH: ("PLANNER_MODEL",), MANIFEST_LABEL: ('"model"', '"about"'),
}

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
    return re.search(r"(?:_subcon_url|_subcon_model|_subcon_route|generative_route|brain_route)\((?:[^()]|\([^()]*\))*?(?:\{|\b)%s\b" % v, text) is not None

print("--- every 26B id or MacBook LM Studio address in code goes through the flag, or is listed ---")
direct, found_allowed = {}, {}
for f in files():
    text = src(f)
    if not TOKEN.search(text):
        continue
    for i, line in enumerate(text.split("\n"), 1):
        for m in TOKEN.finditer(line):
            if WRAP.search(line[:m.start()]) or flag_default(f, text, line, m.start()):
                continue
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

for f in [f for f, r in ALLOW.items() if ENCODER_BASE in r]:
    uses = [l.strip() for l in src(f).split("\n") if "LM_URL" in l and not l.startswith("LM_URL =")]
    check("%s uses its LM Studio address for embeddings only" % f, uses and all("/v1/embeddings" in l for l in uses), uses)

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
routed = [f for f in files() if f.endswith((".py", ".sh")) and TOKEN.search(src(f)) and WRAP.search(src(f))
          and f != "scripts/subcon_target.py"]
missing = [f for f in routed if f not in FROM_CHECKOUT and os.path.basename(f) not in installed
           and ALIASES.get(os.path.basename(f)) not in installed]
check("there are flag-routed callers to check (%d)" % len(routed), len(routed) > 80, len(routed))
check("every flag-routed caller is installed by the deploy (or is a live alias of one)", not missing, missing)
for b in ("emotion_read.py", "imprint.py", "resonance-marks.py", "yearning-detector.py", "yearning_scars.py", "reading.py",
          "introspective_planning.py", "tension_identity_audit.py", "want_learning.py", "conflict_surface.py",
          "morning-briefing.sh", "valence-drift-map.sh", "subcon_target.py", "aeon-bar-record.json"):
    check("the deploy installs %s" % b, b in installed)
check("the server-side twin of emoclaw_utils.py is installed too", "for _twin in emoclaw_utils.py" in deploy
      and 'PLAN="$PLAN$SRC/scripts/$_twin|$_tw' in deploy)

print("--- with the flag on AEON, the routed defaults resolve to AEON ---")
import subcon_target as T
open(os.path.join(TMP, ".vintos", "subcon-target.json"), "w").write('{"target": "aeon"}')
check("the shipped pass record lets the flag be AEON", T.active() == "aeon", T.unmet())
url, model = T.generative_route("http://100.79.177.103:1234/v1/chat/completions", "gemma-4-26b-a4b-it-uncensored")
check("a 26B default resolves to AEON's subconscious lane", (url, model) == (T.SHIM_SUBCONSCIOUS, "aeon-gemma-4-12b"), (url, model))
check("AEON's lane has no 26B fallback", T.pool_chain() == ["pool:aeon", "aegis_gemma"], T.pool_chain())
import vintos_claude_shim as S
check("the shim's subconscious lane is AEON only", S.subconscious_chain() == ["pool:aeon", "aegis_gemma"], S.subconscious_chain())
for p, j in (("/v1/chat/completions", {"max_tokens": 80}), ("/gemma/v1/chat/completions", {}), ("/gemma-aegis/v1/chat/completions", {}),
             ("/pool/subconscious/v1/chat/completions", {})):
    c = S.provider_chain(dict(j), p)
    check("shim %s never reaches the 26B" % p, "gemma" not in c, c)

print("--- text calls inside the browser and desktop helpers follow the flag; their screenshots do not ---")
import ast
for f, call in (("scripts/browser_jev.py", '_url, _model = _subcon_route(getattr(self.fallback, "endpoint")'),
                ("scripts/desktop_control.py", "url, name = _subcon_route(MODEL_URL, MODEL_NAME or None)")):
    t = src(f)
    fns = [n for n in ast.parse(t).body if isinstance(n, ast.FunctionDef) and n.name == "_subcon_route"]
    ns = {"__file__": os.path.join(REPO, f)}
    exec(compile(ast.Module(body=fns, type_ignores=[]), f, "exec"), ns)
    got = ns["_subcon_route"]("http://100.79.177.103:1234/v1/chat/completions", "gemma-4-26b-a4b-it-uncensored")
    check("%s: its text call goes through the flag, and resolves to AEON" % f,
          len(fns) == 1 and call in t and got == (T.SHIM_SUBCONSCIOUS, "aeon-gemma-4-12b"), got)
check("desktop_control: an explicit VINTOS_DESKTOP_MODEL_URL keeps its own route",
      'if "VINTOS_DESKTOP_MODEL_URL" not in os.environ:' in src("scripts/desktop_control.py"))
check("desktop_agent and screen_share (screenshots) stay on the vision route",
      all("_subcon" not in src(f) for f in ("scripts/desktop_agent.py", "scripts/screen_share.py", "scripts/image_sight.py")))
os.remove(os.path.join(TMP, ".vintos", "subcon-target.json"))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

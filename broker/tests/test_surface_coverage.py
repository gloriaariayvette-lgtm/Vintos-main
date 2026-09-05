#!/usr/bin/env python3
"""Every effect-bearing surface must carry authority BEFORE the gate is armed.

Sol's fourth blocker: arming is global, so a surface still firing devices
without a TurnContext would be denied the moment the gate goes live — an
avatar-only canary would pass while legitimate main-chat or voice effects
broke. This is a static audit of the call sites, because that is exactly the
kind of thing a runtime test on one surface does not catch.
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:80]) if d else ""))

# Call sites that actually move a device. A line matching one of these must
# either be inert (the call is commented/disabled) or pass a context.
EFFECT_CALLS = ("_tl_ps(", "_tl_mod.parse_and_send(", "parse_and_send(", "_fhi(")
FILES = [os.path.join(ROOT, "bin", "server.py"),
         os.path.join(ROOT, "bin", "merged_full_route.py")]

for path in FILES:
    if not os.path.exists(path):
        check("%s exists" % os.path.basename(path), False); continue
    src = open(path, errors="replace").read()
    lines = src.split("\n")
    live = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("#") or s.startswith("from ") or s.startswith("import "):
            continue
        if not any(c in ln for c in EFFECT_CALLS):
            continue
        if "def " in s:
            continue
        # the call may wrap onto the following lines
        blob = "\n".join(lines[i:i + 4])
        live.append((i + 1, blob))
    name = os.path.basename(path)
    check("%s: found its effect call sites" % name, True, "%d site(s)" % len(live))
    for lineno, blob in live:
        has_ctx = "context=" in blob
        none_ctx = re.search(r"context\s*=\s*None\b", blob) is not None
        check("%s:%d passes a context" % (name, lineno), has_ctx, blob.strip()[:60])
        check("%s:%d never passes context=None" % (name, lineno), not none_ctx)

print("\n--- and the fallback is a real authority, not None ---")
src = open(FILES[0], errors="replace").read()
check("avatar falls back to its own effect context, not None",
      'else _tc_av.effect_context("avatar")' in src)
# one fire path per surface (2026-09-05): fire_his_intent fires both grammars on the avatar reply and
# strips the tags; a second toy_link.parse_and_send on that route would be dead or a hidden second door.
check("avatar has one fire path (no second parse_and_send after fire_his_intent)",
      '_tc_av2.effect_context("avatar")' not in src)
check("no effect call still degrades to a bare None",
      "context=(_turn.context if _turn is not None else None)" not in src)

print("\n--- reductions never need authority ---")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import effect_gate as EG, tempfile, shutil
tmp = tempfile.mkdtemp(prefix="cov-")
_s = (EG.MEM, EG.ARMED_FLAG, EG.LOG, EG.STOP_BUTTON, EG.TEST_MODE_FLAG)
EG.MEM = tmp
EG.ARMED_FLAG = os.path.join(tmp, ".armed"); open(EG.ARMED_FLAG, "w").write("")
EG.LOG = os.path.join(tmp, "l.jsonl"); EG.STOP_BUTTON = os.path.join(tmp, "b.json")
EG.TEST_MODE_FLAG = os.path.join(tmp, ".tm")
# somatic_bridge is a background daemon with no turn; every device call it makes
# is a reduction toward zero, so arming cannot silence his body through it.
check("armed: a reduction with NO context still passes",
      EG.authorize(None, "mission", 0)[1] == "send")
check("armed: an increase with no context is still denied",
      EG.authorize(None, "mission", 14)[1] == "deny")
(EG.MEM, EG.ARMED_FLAG, EG.LOG, EG.STOP_BUTTON, EG.TEST_MODE_FLAG) = _s
shutil.rmtree(tmp, ignore_errors=True)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

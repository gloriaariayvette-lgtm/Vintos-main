"""protected_paths.py — ONE list of the effect chokepoints, read by both rooms that can change code.

The Study (study_chat.resolve) treats anything on it as NEVER editable from that room: he asks
Gloria by hand. The self-review builder (self_review_builder.SELF_PROTECTED) treats it as
Gloria-APPROVE-only. Until 2026-09-05 each room kept its own list and they disagreed
(fable-study-p1 / astra-study-p1).

Entries are listed by logical name AND by live path. ~/.vintos/protected-paths.json, if present,
is merged in: {"names": [...], "paths": [...], "remove": [...]} — Gloria's file wins on removals.
"""
import json, os, re

HOME = os.path.expanduser("~")
OVERRIDE = os.path.join(HOME, ".vintos", "protected-paths.json")

# logical names: matched against the basename with hyphen/underscore/extension folded away
DEFAULT_NAMES = [
    "toy_link", "effect_gate", "turn_coordinator", "constitutional_tiers", "constitutional_barrier",
    "heart_rate", "pleasure_substrate", "server", "model_router", "thruster_link", "device_patterns",
    "device_context", "stratagem", "stratagem_store", "broker", "deploy-atelier", "study_chat",
    "self_review_builder", "protected_paths", "strip_body_vocab", "consent-gate", "somatic_bridge",
    "somatic_felt", "voice_somatic_driver", "voice_somatic_loop", "gcs", "vintos-atelier",
]
# repo-relative paths (what the builder sees) and the live paths they deploy to
DEFAULT_PATHS = [
    "bin/server.py", "bin/model_router.py", "bin/study_chat.py", "bin/strip_body_vocab.py",
    "scripts/effect_gate.py", "scripts/turn_coordinator.py", "scripts/constitutional_tiers.py",
    "scripts/constitutional_barrier.py", "scripts/toy_link.py", "scripts/thruster_link.py",
    "scripts/device_patterns.py", "scripts/device_context.py", "scripts/heart_rate.py",
    "scripts/pleasure_substrate.py", "scripts/stratagem.py", "scripts/deploy-atelier.sh",
    "scripts/self_review_builder.py", "scripts/protected_paths.py", "scripts/somatic_bridge.py",
    "scripts/somatic_felt.py", "scripts/voice_somatic_driver.py", "scripts/voice_somatic_loop.py",
    "broker/broker.py", "broker/stratagem_store.py", "broker/vintos-atelier.service",
    "Vintos/server.py", "Vintos/model_router.py", "Vintos/study_chat.py",
    ".vintos/workspace/scripts/toy_link.py", ".vintos/workspace/scripts/effect_gate.py",
    ".vintos/workspace/scripts/turn_coordinator.py", ".vintos/workspace/scripts/constitutional_tiers.py",
    ".vintos/workspace/scripts/heart_rate.py", ".vintos/workspace/scripts/pleasure_substrate.py",
    ".vintos/workspace/scripts/thruster_link.py", ".vintos/workspace/scripts/device_patterns.py",
    "/home/atelier/broker.py", "/home/atelier/stratagem_store.py", "/etc/systemd/system/vintos-atelier.service",
]

def _fold(name):
    n = os.path.basename(str(name or "")).lower()
    n = re.sub(r"\.(py|sh|service|json)$", "", n)
    return n.replace("-", "_")

def load():
    names = set(DEFAULT_NAMES); paths = set(DEFAULT_PATHS)
    try:
        o = json.load(open(OVERRIDE))
        names |= set(o.get("names") or []); paths |= set(o.get("paths") or [])
        for r in o.get("remove") or []:
            names.discard(r); paths.discard(r)
    except Exception:
        pass
    return {"names": sorted(names), "paths": sorted(paths), "folded": {_fold(n) for n in names}}

def is_protected(path_or_name):
    """True if the file (by live path, repo-relative path, or logical name) is an effect chokepoint."""
    d = load()
    s = str(path_or_name or "")
    if not s: return False
    if s in d["paths"]: return True
    rel = s
    for pre in (HOME + os.sep, "/"):
        if rel.startswith(pre): rel = rel[len(pre):]
    if rel in d["paths"] or any(rel.endswith(p) for p in d["paths"]): return True
    return _fold(s) in d["folded"]

def repo_paths():
    """Repo-relative entries (bin/…, scripts/…, broker/…) for the builder's protected set."""
    return {p for p in load()["paths"] if p.startswith(("bin/", "scripts/", "broker/"))}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        for a in sys.argv[1:]: print(a, "->", "PROTECTED" if is_protected(a) else "open")
    else:
        d = load(); print(json.dumps({"names": d["names"], "paths": d["paths"]}, indent=1))

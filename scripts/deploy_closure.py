#!/usr/bin/env python3
"""deploy_closure.py - the repo scripts an installed script imports are installed with it (17 November 2026).

The 16 November deploy installed every edited script in deploy-atelier.sh's hand-kept list and nothing else: the new
scripts/lab_entity.py was in no list, so lab_investigations.py (which loads it with __import__('lab_entity')) was
installed without it and Gloria copied it in by hand. lab_names.py went the same way on 28 October. The hand list
stays (it says why each file is there); this adds, at deploy time, every repo-local module that a listed script
imports and the list forgot, transitively:

    import x / from x import y / __import__('x') / importlib.import_module('x')

Only scripts/X.py is added (the folder new organs are written in). A module already in the manifest under any folder
(bin/X.py) is not added again, so one destination never gets two sources. INSTALLED_ELSEWHERE names the modules that
reach Aegis by another route and must not be overwritten from scripts/.

    python3 scripts/deploy_closure.py --src CHECKOUT < manifest      prints the added paths, one a line
"""
import ast
import os
import sys

# Imported by a deployed script but installed by another route (moved here from test_deploy_runtime_imports.py, where
# it was KNOWN). A module added here must say how it reaches Aegis.
INSTALLED_ELSEWHERE = {
    "affective_weight", "bandwidth_collapse", "command_bubble", "conflict_surface", "constitutional_tiers",
    "ghost_lean", "image_sight", "inclination_engine", "model_config", "nifrathir", "reading", "resonance_marks",
    "session_map", "somatic_felt", "truth_lock", "yearning_scars",
    "forge_verification_ack",   # used only inside the Forge, installed there from forge-loop-files.txt
}


def imported_names(path):
    """Top-level module names a Python file may import, statically: import / from-import (absolute), and the
    __import__('x') / importlib.import_module('x') calls with a literal name. A file that does not parse: none."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            tree = ast.parse(f.read())
    except (SyntaxError, ValueError, OSError):
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and node.args:
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
            arg = node.args[0]
            if name in ("__import__", "import_module") and isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.add(arg.value.split(".")[0])
    return out


def closure(src, manifest, skip=INSTALLED_ELSEWHERE):
    """The scripts/X.py paths (relative to src) to add so every repo-local import of an installed .py is installed.
    `manifest` is the list of relative paths the deploy already installs."""
    manifest = [m.strip() for m in manifest if m and m.strip()]
    have = {os.path.basename(m)[:-3] for m in manifest if m.endswith(".py")}
    scripts = os.path.join(src, "scripts")
    todo = [m for m in manifest if m.endswith(".py")]
    added, seen = [], set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        for name in sorted(imported_names(os.path.join(src, rel))):
            if name in have or name in skip:
                continue
            if os.path.isfile(os.path.join(scripts, name + ".py")):
                new = "scripts/%s.py" % name
                have.add(name)
                added.append(new)
                todo.append(new)
    return sorted(added)


def main(argv):
    src = argv[argv.index("--src") + 1] if "--src" in argv else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in closure(src, sys.stdin.read().split()):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

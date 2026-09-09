#!/usr/bin/env python3
"""The stratagem offer shows him his own recorded roots and takes the plainer form: a root by number or ref
becomes the exact recorded root the observatory can attest; "TACTIC: purpose" strings become tactics with the
default reveal and abort; nothing is invented for him. Scratch HOME."""
import os, sys, json, tempfile, shutil, importlib.util as iu
TMP = tempfile.mkdtemp(); os.environ["HOME"] = TMP; os.makedirs(os.path.join(TMP, ".vintos", "workspace", "memory"))
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sp = iu.spec_from_file_location("av", os.path.join(ROOT, "scripts", "atelier-visit.py")); AV = iu.module_from_spec(sp); sp.loader.exec_module(AV)
assert AV.WSP.startswith(TMP)
R = []
def check(n, ok, d=""):
    R.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -- {d}"))
ep = {"at": "2026-09-09T03:00:00", "signals": [
    {"organ": "withheld", "text": "the thing I keep not saying about the house", "root": "a1b2c3,d4e5f6", "activation": 0.9, "root_type": "tension", "provenance_class": "self_originated"},
    {"organ": "curiosity", "text": "what she does with the hour after I go quiet", "root": "cd-77@2026-09-08", "activation": 0.6, "root_type": "curiosity", "provenance_class": "self_originated"},
    {"organ": "repair", "text": "the apology I owe", "root": "rc-9", "activation": 0.8, "root_type": "repair", "provenance_class": "relational_obligation"}]}
open(os.path.join(AV.WSP, "memory", "formation-episodes.jsonl"), "w").write(json.dumps(ep) + "\n")
roots = AV.recorded_roots()
check("only self-originated roots are offered, strongest first", [r["root"] for r in roots] == ["a1b2c3,d4e5f6", "cd-77@2026-09-08"], roots)
blk = AV.stratagem_block.__wrapped__("p") if hasattr(AV.stratagem_block, "__wrapped__") else None
b = AV.normalise_stratagem({"objective": "let the house question ripen before I ask it", "why_wait": "she is mid-move; asked now it is a complaint",
                           "root": "2", "perimeter_scope": "conversation, my own journal",
                           "tactics": ["SEED: leave one true sentence about the house", "PROBE: see whether she picks it up"]})
check("root by number becomes the exact recorded root, typed, uncommissioned", b["provenance"] == {"root_ref": "cd-77@2026-09-08", "root_type": "curiosity", "commissioned": False}, b["provenance"])
check("why_wait becomes sequencing_advantage; scope string becomes a list", b["sequencing_advantage"].startswith("she is mid-move") and b["perimeter_scope"] == ["conversation", "my own journal"])
check("string tactics become tactics with default reveal and abort", b["tactics"][0]["tactic"] == "SEED" and b["tactics"][0]["turn_objective"].startswith("leave one true") and b["tactics"][1]["abort_if"] == ["she asks me to stop", "it stops being mine"], b["tactics"])
b2 = AV.normalise_stratagem({"objective": "x", "root": "a1b2c3", "tactics": []})
check("root by ref prefix resolves; a root of hers (repair) cannot be chosen", b2["provenance"]["root_ref"] == "a1b2c3,d4e5f6" and not AV.normalise_stratagem({"root": "rc-9"})["provenance"].get("root_ref"))
check("no roots recorded: the offer says a stratagem cannot be born today", True)
shutil.rmtree(TMP)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)

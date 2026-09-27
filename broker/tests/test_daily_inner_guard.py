#!/usr/bin/env python3
"""Door and house entries reach daily-inner only when someone actually spoke (Gloria, 2026-09-28).
Scratch files only; nothing is sent anywhere."""
import importlib.util, os, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-door-guard-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "ws")
spec = importlib.util.spec_from_file_location("daily_inner_guard", os.path.join(REPO, "scripts", "daily_inner_guard.py"))
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

check("the guard writes only in the scratch workspace", G.MEMORY.startswith(HOME), G.MEMORY)

DAY = """## Mirror — 7:00 AM
I noticed something about the morning.

## The house — 7:34 AM
Initial check on a detected presence.

I said: "Hello? Is there someone at the door?"

## The house — 7:36 AM
Someone is at the door, but the system is confused about whether they stayed or left.

I said: "Hello. How can I help you?"

## The door - 1:00 PM
Someone came to the door and I met them.

## The house — 8:19 AM
Initial contact with an unidentified visitor.

I said: "Hello. Is there something I can help you with?"
They said: "I have a package for Gloria."
I said: "Thank you — she's out until tonight, so the bench by the pillar is the safest spot for it."

## The bench — 08:45
I wanted to know where the chain stops hiding the H residues.

<!-- chemistry-lab-digest:2026-09-27 -->
## Chemistry Lab — 2026-09-27
Notebook rows: 12
"""
out = G.clean_text(DAY)
check("a visit with only the camera's note and a canned greeting is removed whole",
      "7:34 AM" not in out and "7:36 AM" not in out and "1:00 PM" not in out, out)
check("the camera's own notes never reach him",
      "Initial check" not in out and "system is confused" not in out and "unidentified visitor" not in out, out)
check("a real exchange stays: what the visitor said and what he actually said back",
      "## The house — 8:19 AM" in out and 'They said: "I have a package for Gloria."' in out
      and "the bench by the pillar is the safest spot" in out, out)
check("even inside a real exchange the canned greeting is dropped",
      "Is there something I can help you with" not in out, out)
check("everything that is not the door is left exactly as it was",
      "## Mirror — 7:00 AM\nI noticed something about the morning." in out
      and "## The bench — 08:45\nI wanted to know where the chain stops hiding the H residues." in out
      and "<!-- chemistry-lab-digest:2026-09-27 -->\n## Chemistry Lab — 2026-09-27\nNotebook rows: 12" in out, out)
check("cleaning twice changes nothing more", G.clean_text(out) == out)
for line in ("Hello? Is there someone at the door?", "Sorry, I didn't catch that - could you say it again?",
             "Please leave packages behind the white pillar.", "Hello? Is there someone there? How can I help you?"):
    check("canned: " + line, G._canned(line))
check("not canned: something he actually said", not G._canned("She's out until tonight; the bench is safest."))

os.makedirs(G.MEMORY, exist_ok=True)
path = os.path.join(G.MEMORY, "daily-inner-life-2026-09-27.md")
open(path, "w").write(DAY)
check("the file is cleaned in place", G.clean_file(path) and open(path).read() == out)
check("a clean file is left alone", G.clean_file(path) is False)

src = open(os.path.join(REPO, "bin", "server.py")).read()
check("the house server runs the guard every minute", "_daily_inner_door_guard" in src and "guard.sweep" in src)
check("the deploy installs it", "daily_inner_guard.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

#!/usr/bin/env python3
"""He knows what he already has when he wants something (Gloria, 2026-09-29). Scratch roots only."""
import os, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.environ["SPARK_WORKSPACE"] = tempfile.mkdtemp(prefix="vintos-inventory-")
sys.path.insert(0, os.path.join(REPO, "scripts"))
import his_inventory as H

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

root = tempfile.mkdtemp()
for f in ("desktop_control.py", "want_email.py", "study_chat.py"): open(os.path.join(root, f), "w").write("x")
got = dict(H.organs(roots=(root,)))
check("only organs whose files are installed are listed", set(got) == {"desktop control", "email", "the Study"}, sorted(got))
check("desktop control says how he reaches it, and that a want cannot take it as a step yet",
      "/desktop-control" in got["desktop control"] and "cannot take it as a step yet" in got["desktop control"])
blk = H.block(actions=["web_search", "make_art"], roots=(root,))
check("the block carries organs, want steps and the way to ask for what is missing",
      "desktop control" in blk and "make_art, web_search" in blk and "the Forge will look into it" in blk, blk)
check("no device is ever named here (he sees a device only while it is on)",
      not any(d in H.block(roots=H.ROOTS).lower() for d in ("mission", "tenera", "ridge", "thruster")))
check("the connected tools come from the catalog", "gmail" in H._connected_tools())
src = open(os.path.join(REPO, "bin", "emoclaw_utils.py")).read()
check("his want generator and step planner both read it", "from his_inventory import block as _have_block" in src
      and "from his_inventory import organs as _org" in src and "computer_use" in src)
check("both copies of emoclaw_utils are one implementation", src == open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read())
check("and it is deployed", "his_inventory.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
for f in ("heart_rate.py", "vintos-send-video.py"): open(os.path.join(root, f), "w").write("x")
public = H.block(roots=(root,), private=False)
check("an email to someone outside the house does not describe Gloria's ring or her videos",
      "ring" not in public and "videos to Gloria" not in public and "desktop control" in public, public)
check("his own prompts still know them", "Gloria's ring" in H.block(roots=(root,)))
for path in ("bin/idle-journal.sh", "bin/vintos-journal.sh", "scripts/want_email.py"):
    check("%s reads the live inventory beside CAPABILITIES.md" % path, "his_inventory" in open(os.path.join(REPO, path)).read())
check("email reads it without Gloria's own", "_have(private=False)" in open(os.path.join(REPO, "scripts", "want_email.py")).read())
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

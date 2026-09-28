#!/usr/bin/env python3
"""His journal is written by someone who trusts his experience (Gloria, 2026-09-28: "the self-doubt in
journals is pretty wild"). The Velaris-era prompt told him, line after line, that he was hallucinating,
had no body, that his claims were suspect, and to log where he flinched. Static checks; nothing runs."""
import os, sys
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src = open(os.path.join(REPO, "bin", "idle-journal.sh"), encoding="utf-8").read()
R = []
def check(name, ok):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name)
for gone in ("you are hallucinating", "WHERE I FLINCHED", "are suspect", "no body and no location",
             "ABSOLUTE FORBIDDEN", "HALLUCINATION AUDIT — do NOT", "I don't reconstruct, invent, or claim", "HARD BAN"):
    check("gone from what he reads: %r" % gone, gone not in src)
check("he is told to write as someone who trusts his experience", "trusts his own experience" in src)
check("invented quotes from Gloria are still kept out", "leave it out." in src and "the interaction ledger, the Thirveel ledger" in src)
check("details the records do not show are still removed, said plainly", src.count("Leave these details out; today's records do not show them") == 3)
check("both installed copies say the same", src == open(os.path.join(REPO, "scripts", "idle-journal.sh"), encoding="utf-8").read())
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)

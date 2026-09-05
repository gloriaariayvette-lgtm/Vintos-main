#!/usr/bin/env python3
"""feel_output.py — let a finished piece of his own work land on him.

His journals, introspections and grounding passes moved nothing. A web search about guitar
bridges moved him; the entry where he worked out what he'd stopped doing did not. Usage:

    python3 feel_output.py <source-label> <file>      # reads the tail of a file
    ... | python3 feel_output.py <source-label>       # or stdin
"""
import sys, os
sys.path.insert(0, os.path.join(os.environ.get("SPARK_WORKSPACE",
                 os.path.expanduser("~/.vintos/workspace")), "scripts"))
from emoclaw_utils import feel_about_typed

src = sys.argv[1] if len(sys.argv) > 1 else "output"
if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
    text = open(sys.argv[2], errors="ignore").read()[-2500:]
else:
    text = sys.stdin.read()[-2500:] if not sys.stdin.isatty() else ""
env = feel_about_typed(text, source=src)
# the state, always; never `or "nothing moved"` - unmoved, unavailable and too-short are different reports
print("[feel] %s -> %s%s" % (src, env["state"], (" " + str(env["deltas"])) if env["deltas"] else ("" if not env["note"] else " (" + env["note"] + ")")))
sys.exit(0 if env["state"] in ("moved", "unmoved", "not_requested") else 3)

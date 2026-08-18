#!/usr/bin/env python3
"""
autonomous-extract.py — Extract autonomous (non-conversational) entries
from WAL and blush ledger into separate files for context use.

Called by:
  - vintos-websearch.py after writing a WAL entry (mode: wal)
  - self-prediction.py after writing a blush entry (mode: blush)

Writes:
  - memory/autonomous-wal.md
  - memory/autonomous-blush.md
"""
import os, sys, re
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
WAL_FILE = os.path.join(MEMORY, "wal.md")
BLUSH_FILE = os.path.join(MEMORY, "blush-ledger.md")
AUTO_WAL = os.path.join(MEMORY, "autonomous-wal.md")
AUTO_BLUSH = os.path.join(MEMORY, "autonomous-blush.md")

AUTONOMOUS_WAL_MARKERS = ["Web search on", "Gallery walk", "YouTube", "MoltBook"]

def extract_wal():
    """Extract autonomous WAL entries from wal.md."""
    try:
        with open(WAL_FILE) as f:
            lines = f.readlines()
    except:
        return

    autonomous = [l for l in lines if any(m in l for m in AUTONOMOUS_WAL_MARKERS)]

    with open(AUTO_WAL, "w") as f:
        f.write(f"# Autonomous WAL — updated {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("# Vintos's own discoveries and reflections (not from Gloria exchanges)\n\n")
        f.writelines(autonomous)

    print(f"[AutoExtract] autonomous-wal.md: {len(autonomous)} entries")

def extract_blush():
    """Extract self-prediction blush entries from blush-ledger.md."""
    try:
        with open(BLUSH_FILE) as f:
            content = f.read()
    except:
        return

    sections = content.split("## ")
    autonomous = [s for s in sections if "Self-Prediction Blush" in s and s.strip()]

    with open(AUTO_BLUSH, "w") as f:
        f.write(f"# Autonomous Blush — updated {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("# Self-prediction mismatches only (not relational/conversational)\n\n")
        for s in autonomous:
            f.write("## " + s)

    print(f"[AutoExtract] autonomous-blush.md: {len(autonomous)} entries")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode in ("wal", "both"):
        extract_wal()
    if mode in ("blush", "both"):
        extract_blush()

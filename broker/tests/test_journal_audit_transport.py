#!/usr/bin/env python3
"""Execute the actual final-audit block with synthetic drafts and stubbed transport."""
import contextlib
import io
import os
from pathlib import Path
import re
import sys
import textwrap
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
checks = []
def check(name, ok):
    checks.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name)

original = "Synthetic complete entry. " * 80
for relative in ("bin/idle-journal.sh", "scripts/idle-journal.sh"):
    source = (ROOT / relative).read_text()
    start = re.search(r"^(?:    try:\n)? +audit2_r = requests.post\(", source, re.M).start()
    block = textwrap.dedent(source[start:source.index("    # Final BIS outcome", start)])
    for case in ("timeout", "connection", "http_error", "malformed", "clean", "correction", "late_success"):
        calls = []
        def send(*args, **kwargs):
            calls.append(kwargs)
            if case == "timeout": raise TimeoutError("synthetic timeout")
            if case == "connection": raise ConnectionError("synthetic disconnect")
            if case == "late_success" and kwargs.get("timeout", 0) <= 241:
                raise TimeoutError("fallback completed after the caller deadline")
            def status():
                if case == "http_error": raise RuntimeError("synthetic HTTP 503")
            return types.SimpleNamespace(raise_for_status=status)
        def extract(response):
            if case == "malformed": raise ValueError("synthetic invalid body")
            if case == "http_error": return "error body must not become an entry " * 70
            return ("Corrected synthetic entry. " * 80) if case == "correction" else "CLEAN"
        state = dict(requests=types.SimpleNamespace(post=send), os=os, _re=re,
                     _safe_extract=extract, _raw=original, _pre_audit=original,
                     a2="draft a", b2="draft b", c2="draft c", recent_chat="", thirveel_today="", _made_block="")
        log = io.StringIO()
        escaped = False
        with patch.dict(os.environ, {"XAI_API_KEY": "synthetic"}), patch("builtins.open", side_effect=AssertionError("no file writes")), contextlib.redirect_stderr(log):
            try: exec(compile(block, relative, "exec"), state)
            except Exception: escaped = True
        check(relative + " " + case + " continues", not escaped)
        check(relative + " " + case + " sends once through stub", len(calls) == 1)
        expected = "Corrected synthetic entry. " * 80 if case == "correction" else original
        check(relative + " " + case + " preserves correct entry", state["_raw"].strip() == expected.strip())
        if case in ("timeout", "connection", "http_error", "malformed"):
            check(relative + " " + case + " reports skipped audit", "audit-2 skipped" in log.getvalue() and "CLEAN" not in log.getvalue())
        if case == "late_success":
            check(relative + " waits for fallback completion", "CLEAN" in log.getvalue())
check("no live journal store", not (Path.home() / ".vintos/workspace/memory/journal").exists())
print("%d/%d checks" % (sum(checks), len(checks)))
sys.exit(0 if all(checks) else 1)

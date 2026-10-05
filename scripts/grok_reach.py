#!/usr/bin/env python3
"""Grok Bot can look on Aegis, read only (Gloria, 2026-10-05: "I want Grok to be able to search Aegis/Mac too").

Grok Bot lives in Grok's cloud and posts through Gloria's Slack login, so it cannot reach a file on Aegis ("I can't
reach files on Aegis, so I didn't copy anything"). In #vintos-dot it writes a line of its own:

    AEGIS FIND: words in a file or folder name
    AEGIS OPEN: a path (a folder lists its entries; a text file is shown)
    AEGIS GREP: text to find inside files

and the next Slack pass runs it here and answers in its thread. Only in ROOTS: his code, his Lab, his art and the
Codex folder on Gloria's PC. Never keys, secrets or his private memory (DENY), and every answer passes the same
secret check as anything posted to Slack. The Mac is not reachable from Aegis for files; dot has its own computer.
"""
from __future__ import annotations
import json
import os
import re
import time
from datetime import date

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
STATE = os.path.join(WS, "memory", "grok-reach.json")
ROOTS = ("~/Vintos-main", os.path.join(WS, "scripts"), os.path.join(WS, "memory", "chemistry-lab"),
         os.path.join(WS, "memory", "art"), "/mnt/c/Users/glori/Documents/Codex")
DENY = re.compile(r"secret|token|credential|password|passwd|(^|/)\.env|vintos\.env|(^|/)\.ssh(/|$)|id_rsa|id_ed25519|"
                  r"\.pem$|\.key$|keys?\.json|api[-_]?key|cookie|wallet|interaction-ledger|GLORIA-MODEL|daily-inner|"
                  r"SOUL\.md|wal\.md|(^|/)\.git(/|$)", re.I)
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cache"}
LINE = re.compile(r"^\s*AEGIS\s+(FIND|OPEN|GREP)\s*:\s*(.+?)\s*$", re.I | re.M)
PER_DAY = 30            # looks a day
PER_MESSAGE = 3
SHOWN = 3500            # characters of one answer posted in Slack


def roots():
    return [os.path.realpath(os.path.expanduser(r)) for r in ROOTS if os.path.isdir(os.path.expanduser(r))]


def allowed(path):
    """The real path when it is inside a root and names nothing denied, else None."""
    real = os.path.realpath(os.path.expanduser(str(path).strip().strip("`'\"")))
    if DENY.search(real):
        return None
    return real if any(real == r or real.startswith(r + os.sep) for r in roots()) else None


def _walk(deadline):
    for root in roots():
        for here, dirs, files in os.walk(root):
            if time.time() > deadline:
                return
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not DENY.search(os.path.join(here, d))]
            for name in dirs + files:
                path = os.path.join(here, name)
                if not DENY.search(path):
                    yield path


def find(words, cap=30, seconds=6):
    terms = [w.lower() for w in re.findall(r"[\w.-]+", str(words)) if len(w) > 1]
    if not terms:
        return "say what to find"
    hits = []
    for path in _walk(time.time() + seconds):
        if all(t in os.path.basename(path).lower() for t in terms):
            hits.append(path + ("/" if os.path.isdir(path) else ""))
            if len(hits) >= cap:
                break
    return "\n".join(hits) if hits else "nothing named like that"


def open_(path, cap=SHOWN):
    real = allowed(path)
    if not real:
        return "not opened: outside what Grok Bot may read, or private"
    if not os.path.exists(real):
        return "no such file"
    if os.path.isdir(real):
        names = sorted(n + ("/" if os.path.isdir(os.path.join(real, n)) else "") for n in os.listdir(real)
                       if not DENY.search(os.path.join(real, n)))
        return "%s holds:\n%s" % (real, "\n".join(names[:200]))
    if os.path.getsize(real) > 5 * 1024 * 1024:
        return "too large to open (%d bytes)" % os.path.getsize(real)
    data = open(real, "rb").read()
    if b"\0" in data[:4096]:
        return "(binary, %d bytes: not shown)" % len(data)
    text = data.decode("utf-8", "replace")
    return text[:cap] + ("\n... (%d more characters)" % (len(text) - cap) if len(text) > cap else "")


def grep(text, cap=40, seconds=8):
    needle = str(text or "").strip().lower()
    if len(needle) < 3:
        return "say at least three characters to find"
    hits = []
    for path in _walk(time.time() + seconds):
        if os.path.isdir(path):
            continue
        try:
            if os.path.getsize(path) > 1024 * 1024:
                continue
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if b"\0" in data[:4096] or needle.encode() not in data.lower():
            continue
        for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            if needle in line.lower():
                hits.append("%s:%d: %s" % (path, n, line.strip()[:200]))
                if len(hits) >= cap:
                    return "\n".join(hits)
    return "\n".join(hits) if hits else "not found"


def _count(n=0):
    try:
        d = json.load(open(STATE))
    except (OSError, ValueError):
        d = {}
    if d.get("date") != date.today().isoformat():
        d = {"date": date.today().isoformat(), "used": 0}
    if n:
        d["used"] += n
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        json.dump(d, open(STATE, "w"))
    return d["used"]


def run(text, guard=None):
    """Grok Bot's AEGIS lines in one message, run: [answer text]. guard(text) returns findings when an answer looks
    like it holds a secret; such an answer is withheld."""
    out = []
    for kind, arg in [m.groups() for m in LINE.finditer(str(text or ""))][:PER_MESSAGE]:
        if _count() >= PER_DAY:
            out.append("AEGIS %s %s\nnot looked: %d looks today already" % (kind.upper(), arg, PER_DAY))
            continue
        _count(1)
        try:
            got = {"FIND": find, "OPEN": open_, "GREP": grep}[kind.upper()](arg)
        except Exception as exc:
            got = "could not: %s" % str(exc)[:160]
        bad = guard(got) if guard else []
        if bad:
            got = "withheld: it looked like it held a secret (%s)" % ", ".join(bad)[:120]
        out.append("AEGIS %s %s\n%s" % (kind.upper(), arg, str(got)[:SHOWN]))
    return out

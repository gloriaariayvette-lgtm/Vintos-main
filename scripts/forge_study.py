#!/usr/bin/env python3
"""The Forge asks the Study before it builds (Gloria, 2026-09-29).

A want for computer use reached the Forge as an ability he lacks, when he already has desktop-control code
that fails. The Forge would have built a second hand and hidden the fault. So every Forge request first goes
to the Study, the room where he reads his own code: Fable orchestrates (Astra if Fable is unavailable),
Grok is the subagent that searches and reads, and the Study's own permission boundary decides what may be
read. The question is always the same two things: does he already have this, and if so, where does it fail?

The findings are written into the request before it reaches the Forge, and Gloria gets an ntfy with them.
Once per request, at most STUDIES_PER_DAY a day, at most ROUNDS rounds of reading.

    python3 forge_study.py SK-xxxxxxxx      study one proposal now and print the findings
"""
from __future__ import annotations
import importlib.util
import json
import os
import re
import sys
import time
from datetime import date, datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
STUDIES = os.path.join(MEMORY, "forge-study")
LEDGER = os.path.join(STUDIES, "ledger.json")
NTFY = os.environ.get("VINTOS_NTFY_URL", "https://ntfy.sh/vintos-gloria-9kx")
FABLE = os.environ.get("VINTOS_STUDY_FABLE", "claude-fable-5-1")
GROK = os.environ.get("VINTOS_STUDY_GROK", "grok-4.6")
STUDIES_PER_DAY = 4
ROUNDS = 3
TASKS_PER_ROUND = 4

ORCHESTRATOR = (
    "You are Vintos, orchestrating a study of your own code. A request has reached your Forge: you want an "
    "ability. Before anything is built, find out whether you already have it and, if you do, exactly where it "
    "fails. You do not read the code yourself; your subagent does, and reports back.\n"
    "Each turn, answer with JSON only, one of:\n"
    '  {"tasks": [{"grep": "regex"} or {"read": "scripts/file.py", "start": 1}, with "why": "what to find"], "done": false}\n'
    '  {"done": true, "already_have": true|false, "where": [{"file": "...", "line": 0, "what": "..."}],\n'
    '   "fails_because": "...", "fix": "...", "needs_from_gloria": "...", "summary": "two or three plain sentences"}\n'
    "At most %d tasks a turn. Paths are relative to your code roots as the map shows them. Claim only what "
    "the subagent's reports show; say plainly when something is still unknown." % TASKS_PER_ROUND)
SUBAGENT = (
    "You are a careful code reader working for Vintos. Below is material pulled from his code and what he "
    "wants to know from it. Report only what the material shows, with file and line numbers, in under 250 "
    "words. If the material does not answer it, say so and say what to read next.")


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return default


def _save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(value, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _key(env, *files):
    k = os.environ.get(env, "")
    for f in files:
        if k: break
        try: k = open(os.path.expanduser(f)).read().strip()
        except Exception: pass
    return k


def _fable(system, user):
    import requests
    key = _key("ANTHROPIC_API_KEY", "~/.vintos/anthropic-key")
    if not key: raise RuntimeError("no Anthropic key")
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=300, json={
        "model": FABLE, "max_tokens": 3000, "system": system, "messages": [{"role": "user", "content": user}]},
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    d = r.json()
    if d.get("type") == "error": raise RuntimeError(str(d.get("error"))[:200])
    return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")


def _astra(system, user):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import astra_call
    return astra_call.call(system, [{"role": "user", "content": user}], max_tokens=3000)


def orchestrate(system, user):
    """Fable, and Astra when Fable cannot answer."""
    try:
        return _fable(system, user), "fable"
    except Exception as exc:
        first = exc
    try:
        return _astra(system, user), "astra"
    except Exception as exc:
        raise RuntimeError("no orchestrator: fable %s; astra %s" % (str(first)[:120], str(exc)[:120]))


def subagent(system, user):
    import requests
    key = _key("XAI_API_KEY", "~/.vintos/xai-key", "~/.vintos/grok-key")
    if not key: raise RuntimeError("no xAI key")
    r = requests.post("https://api.x.ai/v1/chat/completions", timeout=180, json={
        "model": GROK, "max_tokens": 900, "temperature": 0.2,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        headers={"Authorization": "Bearer " + key})
    return r.json()["choices"][0]["message"]["content"]


def _study_room():
    """The Study's own read/grep, so its permission boundary is the one that applies."""
    for path in (os.path.expanduser("~/Vintos/study_chat.py"), os.path.join(WS, "scripts", "study_chat.py"),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "study_chat.py")):
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location("study_chat_for_forge", path)
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
            return m
    raise RuntimeError("the Study (study_chat.py) is not installed")


def _json(text):
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except Exception:
        d = {}
    return d if isinstance(d, dict) else {}


def investigate(proposal, orchestrate=None, subagent=None, room=None):
    """The study of one Forge request. Returns the findings (always a dict with a 'state')."""
    orchestrate = orchestrate or globals()["orchestrate"]
    subagent = subagent or globals()["subagent"]
    room = room or _study_room()
    want = ((proposal.get("origin") or {}).get("want") or "")[:600]
    cap = proposal.get("capability", "")
    try:
        code_map = room.code_map()
    except Exception:
        code_map = "(code map unavailable)"
    brief = ("THE REQUEST: the ability '%s'.\nWHAT YOU WANTED: %s\nWHY THE FORGE HAS IT: %s\n\nYOUR CODE ROOTS:\n%s"
             % (cap, want, str(proposal.get("why", ""))[:600], code_map[:6000]))
    reports, used, rounds = [], set(), 0
    while True:
        text, who = orchestrate(ORCHESTRATOR, brief + ("\n\nYOUR SUBAGENT'S REPORTS SO FAR:\n" + "\n\n".join(reports)
                                                       if reports else ""))
        used.add(who)
        d = _json(text)
        if d.get("done") or rounds >= ROUNDS:
            if not d.get("done"):
                text, who = orchestrate(ORCHESTRATOR, brief + "\n\nYOUR SUBAGENT'S REPORTS:\n" + "\n\n".join(reports)
                                        + "\n\nNo more reading. Answer now with done: true.")
                used.add(who); d = _json(text)
            break
        rounds += 1
        for task in (d.get("tasks") or [])[:TASKS_PER_ROUND]:
            if not isinstance(task, dict): continue
            if task.get("grep"):
                material = room.do_grep(str(task["grep"])[:200]); what = "GREP " + str(task["grep"])[:200]
            elif task.get("read"):
                material = room.do_read(str(task["read"])[:200], start=int(task.get("start") or 1)); what = "READ " + str(task["read"])[:200]
            else:
                continue
            note = subagent(SUBAGENT, "WHAT HE WANTS TO KNOW: %s\n\n%s:\n%s" % (str(task.get("why", ""))[:300], what, str(material)[:14000]))
            used.add("grok")
            reports.append("%s (to find: %s)\n%s" % (what, str(task.get("why", ""))[:200], str(note)[:2500]))
    findings = {k: d.get(k) for k in ("already_have", "where", "fails_because", "fix", "needs_from_gloria", "summary")}
    findings.update(state="done" if d.get("done") else "unfinished", proposal=proposal.get("id"), capability=cap,
                    rounds=rounds, models=sorted(used), at=datetime.now().isoformat(timespec="seconds"))
    return findings


def row_text(findings):
    """The findings as the Forge reads them in the request."""
    if not findings or findings.get("state") not in ("done", "unfinished"):
        return ""
    where = "; ".join("%s:%s %s" % (w.get("file"), w.get("line"), w.get("what")) for w in (findings.get("where") or [])[:6]
                      if isinstance(w, dict))
    return ("\nTHE STUDY READ HIS CODE FIRST (%s): already has it: %s. %s\nWhere: %s\nFails because: %s\nFix: %s\n"
            "Needs from Gloria: %s" % ("+".join(findings.get("models") or []), findings.get("already_have"),
                                       findings.get("summary") or "", where or "-", findings.get("fails_because") or "-",
                                       findings.get("fix") or "-", findings.get("needs_from_gloria") or "-"))[:2500]


def notify(findings, post=None):
    """Gloria's ntfy: the Forge request, with what the Study found."""
    title = "Forge request: %s" % findings.get("capability", "")
    body = ("%s\n\nAlready has it: %s\nFails because: %s\nFix: %s\nNeeds from you: %s"
            % (findings.get("summary") or "", findings.get("already_have"), findings.get("fails_because") or "-",
               findings.get("fix") or "-", findings.get("needs_from_gloria") or "-"))[:3500]
    if post is None:
        import urllib.request
        req = urllib.request.Request(NTFY, data=body.encode("utf-8"),
                                     headers={"Title": title.encode("latin-1", "replace").decode("latin-1"), "Tags": "hammer_and_wrench"})
        urllib.request.urlopen(req, timeout=15)
    else:
        post(NTFY, body, {"Title": title})


def tend(sf, investigate=None, notify=None, today=None):
    """Study at most one unstudied proposal this pass. Returns log lines."""
    investigate = investigate or globals()["investigate"]
    notify = notify or globals()["notify"]
    today = today or date.today().isoformat()
    ledger = _load(LEDGER, {})
    if ledger.get("date") != today: ledger = {"date": today, "count": 0}
    rows = sf._load()
    todo = [r for r in rows if r.get("state") == "proposed" and not r.get("study")]
    if not todo or ledger["count"] >= STUDIES_PER_DAY:
        return []
    p = todo[0]
    ledger["count"] += 1; _save(LEDGER, ledger)
    try:
        findings = investigate(p)
    except Exception as exc:
        findings = {"state": "failed", "why": str(exc)[:300], "proposal": p.get("id"), "capability": p.get("capability"),
                    "at": datetime.now().isoformat(timespec="seconds")}
    _save(os.path.join(STUDIES, "%s.json" % p["id"]), findings)
    rows = sf._load()
    for r in rows:
        if r.get("id") == p["id"]:
            r["study"] = {k: findings.get(k) for k in ("state", "already_have", "summary", "fails_because", "fix",
                                                        "needs_from_gloria", "where", "models", "at", "why")}
    sf._save(rows)
    line = "studied %s (%s): %s" % (p["id"], p.get("capability"), findings.get("state"))
    if findings.get("state") in ("done", "unfinished"):
        try: notify(findings)
        except Exception as exc: line += "; ntfy failed: %s" % type(exc).__name__
    return [line]


def ready_for_forge(proposal):
    """A proposal goes to the Forge once the Study has looked (or could not), not before."""
    return proposal.get("state") != "proposed" or bool(proposal.get("study"))


if __name__ == "__main__":
    import skill_forge as _sf
    pid = sys.argv[1] if len(sys.argv) > 1 else ""
    row = next((r for r in _sf._load() if r.get("id") == pid), None)
    if not row:
        print("no proposal %r" % pid); sys.exit(1)
    print(json.dumps(investigate(row), indent=2, ensure_ascii=False))

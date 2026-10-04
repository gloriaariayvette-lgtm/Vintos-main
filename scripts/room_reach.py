#!/usr/bin/env python3
"""What #vintos-dot can look up, beyond the web search and his own code (Gloria, 2026-10-04: "Searching relevant
repos, finding interesting data from his lab ... A room full of agents and none of them can move?").

Tool lines, used like SEARCH, READ and GREP (he gets what they return, then writes):

    REPOS: <what to look for>          GitHub repositories: name, what it is, stars, last push, link
    README: <owner/repo>               that repository's README, the start of it
    CALL: <plugin.tool> {json}          one of his connectors (PubMed, ChEMBL, Boltz's free estimate, EDEN ...),
                                        on the Lab's allow-list: nothing paid, nothing that writes
    LABDATA: [words]                    what his Lab has measured: recent runs and kept findings, filtered by words

Read-only, every one. The connector call keeps its receipt like any other.
"""
from __future__ import annotations
import json
import os
import re
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
LAB = os.path.join(WS, "memory", "chemistry-lab")
GITHUB = "https://api.github.com"
TIMEOUT = 20


def _get(url, accept="application/vnd.github+json", opener=None):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "vintos-room"})
    with (opener or urllib.request.urlopen)(req, timeout=TIMEOUT) as r:
        return r.read(400_000).decode("utf-8", "replace")


def repos(query, opener=None):
    q = urllib.parse.urlencode({"q": query[:200], "sort": "stars", "per_page": 6})
    data = json.loads(_get("%s/search/repositories?%s" % (GITHUB, q), opener=opener))
    rows = data.get("items") or []
    if not rows:
        return "no repositories found for: %s" % query
    return "\n".join("[%d] %s: %s (%s stars, pushed %s) %s" % (
        n + 1, r.get("full_name", ""), str(r.get("description") or "")[:220], r.get("stargazers_count", 0),
        str(r.get("pushed_at", ""))[:10], r.get("html_url", "")) for n, r in enumerate(rows))


def readme(repo, opener=None):
    repo = repo.strip().strip("/")
    m = re.search(r"github\.com/([\w.-]+/[\w.-]+)", repo)
    repo = m.group(1) if m else repo
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        return "README needs owner/repo"
    text = _get("%s/repos/%s/readme" % (GITHUB, repo), accept="application/vnd.github.raw", opener=opener)
    return text[:5000] + ("\n... (cut)" if len(text) > 5000 else "")


def call(arg, gateway=None):
    m = re.match(r"\s*([\w-]+)\.([\w-]+)\s*(\{.*\})?\s*$", arg, re.S)
    if not m:
        return "CALL needs plugin.tool and, if it takes any, its arguments as JSON"
    plugin, tool, raw = m.group(1), m.group(2), m.group(3) or "{}"
    try:
        args = json.loads(raw)
    except ValueError as exc:
        return "the arguments are not JSON: %s" % exc
    if gateway is None:
        import claude_connector_gateway as gateway
    out = gateway.call("lab", plugin, tool, args, "asked for in #vintos-dot")
    rid = ((out or {}).get("receipt") or {}).get("receipt_id", "")
    return "%s%s" % (str((out or {}).get("summary") or "")[:5000], (" (receipt %s)" % rid) if rid else "")


def labdata(words=""):
    """His Lab's measurements: the latest runs that match, and kept findings, each in one line."""
    want = [w.lower() for w in re.findall(r"\w{3,}", words or "")]
    out = []
    try:
        with open(os.path.join(LAB, "sessions.jsonl")) as f:
            rows = [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        rows = []
    for r in reversed(rows):
        blob = json.dumps(r, ensure_ascii=False)
        if want and not all(w in blob.lower() for w in want):
            continue
        plan = r.get("plan") or {}
        out.append("- %s %s: %s | %s" % (str(r.get("at", ""))[:16], r.get("state", ""),
                                         str(plan.get("experiment") or plan.get("question") or "")[:140],
                                         str(r.get("result") or r.get("summary") or r.get("detail") or "")[:260]))
        if len(out) >= 10:
            break
    try:
        import lab_keepers
        kept = lab_keepers.block()
    except Exception:
        kept = ""
    return ("RUNS%s:\n" % (" matching " + words if want else "") + ("\n".join(out) or "none")) + \
           (("\n\n" + kept[:2500]) if kept else "")

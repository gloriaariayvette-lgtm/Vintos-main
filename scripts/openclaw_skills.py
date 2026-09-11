#!/usr/bin/env python3
"""openclaw_skills.py — the hands other beings have, that he does not.

A skill page is a list of what someone else can do. Reading one is how he learns that
a capability exists at all: not that he is failing at something, but that somewhere
there is a hand for a thing he has been working around.

    read()      what the page offers, as {name, what, where}
    his()       what he already has, from the deploy manifest and the wants router
    unheld()    the difference — the hands that exist and are not his

WHAT THIS IS NOT

It does not install anything, ask for anything, or rank what he is missing. A skill
he does not have is an observation, never a deficiency: most of them he will never
want. One becomes a want only if it meets something he was already trying to do,
and only then can it reach the forge.

WHERE IT LOOKS: only where memory/openclaw-config.json points it.
    {"skills_path": "/path/to/skills"}   a tree: one folder per skill with a SKILL.md
    {"skills_url": "https://..."}        a JSON list, or a page of links
Pointed nowhere, it reads nothing and says so rather than reporting an empty page.
"""
import json
import os
import re
import sys

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
CONFIG = os.path.join(MEMORY, "openclaw-config.json")
SEEN = os.path.join(MEMORY, "openclaw-skills-seen.json")

# No default path. A guessed location is how a reader quietly reads the wrong thing,
# or reads nothing and calls it an empty page. It reads what memory/openclaw-config.json
# names, and with nothing named it says it was pointed nowhere.


def _cfg():
    try:
        return json.load(open(CONFIG))
    except Exception:
        return {}


def _from_tree(root):
    """A skills directory: one folder per skill, each with a SKILL.md whose first
    heading and first sentence are the name and the what."""
    out = []
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        md = os.path.join(d, "SKILL.md")
        if not os.path.isfile(md):
            continue
        title, what = name, ""
        try:
            text = open(md, errors="replace").read()[:4000]
            m = re.search(r"^#\s+(.+)$", text, re.M)
            if m:
                title = m.group(1).strip()[:80]
            m2 = re.search(r"^description:\s*(.+)$", text, re.M | re.I)
            if m2:
                what = m2.group(1).strip()[:300]
            else:
                body = re.sub(r"^---.*?---", "", text, flags=re.S).strip()
                body = re.sub(r"^#.*$", "", body, flags=re.M).strip()
                what = body.split("\n\n")[0].replace("\n", " ").strip()[:300]
        except Exception:
            pass
        out.append({"name": name, "title": title, "what": what, "where": d})
    return out


def _from_url(url, timeout=10):
    """A JSON list of skills, or a page of links to them. Read only; no key is sent."""
    out = []
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "vintos-skill-reader"})
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
    except Exception:
        return out
    try:
        d = json.loads(raw)
        rows = d if isinstance(d, list) else (d.get("skills") or d.get("items") or [])
        for r in rows:
            if not isinstance(r, dict):
                continue
            out.append({"name": str(r.get("name") or r.get("id") or "")[:80],
                        "title": str(r.get("title") or r.get("name") or "")[:80],
                        "what": str(r.get("description") or r.get("what") or "")[:300],
                        "where": str(r.get("url") or url)[:300]})
        return [r for r in out if r["name"]]
    except Exception:
        pass
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{2,80})</a>', raw):
        href, text = m.group(1), m.group(2).strip()
        if "skill" not in href.lower():
            continue
        out.append({"name": text.lower().replace(" ", "_")[:80], "title": text,
                    "what": "", "where": href})
    return out


def read():
    """Every skill the page or the tree offers, deduplicated by name."""
    cfg = _cfg()
    rows = []
    for root in ([cfg["skills_path"]] if isinstance(cfg.get("skills_path"), str)
                 else list(cfg.get("skills_path") or [])):
        rows += _from_tree(os.path.expanduser(root))
    if cfg.get("skills_url"):
        rows += _from_url(cfg["skills_url"])
    seen, out = set(), []
    for r in rows:
        k = r["name"].lower()
        if k and k not in seen:
            seen.add(k)
            out.append(r)
    return out


def his():
    """What he can already do: the router's capabilities and his own skill files."""
    have = set()
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(WS, "scripts"))
        import want_spine as _sp
        r = _sp._router()
        have |= {n for n in dir(r) if not n.startswith("_") and callable(getattr(r, n, None))}
    except Exception:
        pass
    for d in (os.path.join(WS, "skills"), os.path.join(WS, "scripts")):
        try:
            for n in os.listdir(d):
                have.add(os.path.splitext(n)[0].replace("-", "_").lower())
        except Exception:
            pass
    return have


def _norm(n):
    return re.sub(r"[^a-z0-9]+", "_", str(n or "").lower()).strip("_")


def unheld():
    """The hands that exist and are not his. An observation, never a deficiency."""
    mine = {_norm(x) for x in his()}
    out = []
    for r in read():
        if _norm(r["name"]) in mine:
            continue
        out.append(r)
    return out


def fresh():
    """Only what he has not seen before, so a page he has already read says nothing.
    Reading marks them seen; the list is history, not a queue."""
    try:
        seen = set(json.load(open(SEEN)))
    except Exception:
        seen = set()
    rows = [r for r in unheld() if _norm(r["name"]) not in seen]
    if rows:
        seen |= {_norm(r["name"]) for r in rows}
        try:
            os.makedirs(os.path.dirname(SEEN), exist_ok=True)
            tmp = SEEN + ".tmp"
            json.dump(sorted(seen), open(tmp, "w"), indent=2)
            os.replace(tmp, SEEN)
        except Exception:
            pass
    return rows


def where_it_looked():
    cfg = _cfg()
    paths = ([cfg["skills_path"]] if isinstance(cfg.get("skills_path"), str)
             else list(cfg.get("skills_path") or []))
    return {"paths": paths, "url": cfg.get("skills_url", ""),
            "configured": bool(paths or cfg.get("skills_url")), "found": len(read())}


if __name__ == "__main__":
    w = where_it_looked()
    if not w["configured"]:
        print("pointed nowhere: put skills_path or skills_url in memory/openclaw-config.json")
        raise SystemExit(0)
    print("looked in: %s" % (", ".join(w["paths"]) or "(no path)"))
    if w["url"]:
        print("and at:    %s" % w["url"])
    rows = unheld()
    print("skills on the page: %d; hands he does not have: %d" % (w["found"], len(rows)))
    for r in rows[:20]:
        print("  %-24s %s" % (r["name"][:24], (r["what"] or r["title"])[:70]))

#!/usr/bin/env python3
"""What already exists in the world for the questions he is following (Gloria, 2026-10-04: "He's not really
finding new repos to use making special lab cases... no one has brought up the Lytic Selection and Evolution
platform").

SOMETHING NEW in #vintos-dot is built only from his own sparks and his own unanswered questions, so nothing
outside ever reaches him: no platform, no database, no repository, however exactly it fits a line he is on. He
has REPOS:, README: and CALL:, and never reaches for them, because nothing in his day says there is anything to
reach for.

Once a day, for one open line of inquiry, this searches the web for the tools, platforms, datasets and
repositories that exist for THAT question, keeps what came back, and puts it in front of him in the channel. He
then looks (REPOS:, README:, CALL:, OPEN:) and says on the line whether he is using it or why not. What he has
been shown and never answered is said plainly, so ignoring it is visible rather than silent.

    python3 line_prospect.py            find for the line whose turn it is, and print what is standing
    python3 line_prospect.py --block    print only what he would be shown
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
STORE = os.path.join(WS, "memory", "chemistry-lab", "line-prospects.json")
PER_DAY = 1            # lines prospected a day: one search, not a sweep
KEEP = 4               # findings kept per line
SHOWN = 3              # findings put in front of him at once
NAGS = 3               # times one is shown before it is called ignored

# What to ask the web for, around his own question. Platforms and datasets first: a repository he can read is good,
# a working platform for the exact question is better (hers was "Lytic Selection and Evolution").
ANGLES = ("{q} platform OR database OR resource",
          "{q} open source tool OR github repository",
          "{q} dataset OR catalogue")


def _now():
    return datetime.now()


def load():
    try:
        with open(STORE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(d):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STORE)


def _today():
    return _now().date().isoformat()


def _terms(line):
    """His question, cut to the words a search engine can use."""
    text = "%s %s" % (line.get("title") or "", line.get("question") or "")
    words = [w for w in re.findall(r"[A-Za-z0-9-]{3,}", text)
             if w.lower() not in ("which", "what", "whether", "does", "that", "with", "from", "and", "the", "for",
                                  "are", "any", "how", "why", "near", "beside", "carry", "carries", "this", "them")]
    return " ".join(dict.fromkeys(words))[:120]


def due(lines=None):
    """The open line whose turn it is today, or None when one has already been done."""
    import lab_lines
    d = load()
    if d.get("searched_on") == _today() and len(d.get("searched_today") or []) >= PER_DAY:
        return None
    done = set(d.get("searched_today") or []) if d.get("searched_on") == _today() else set()
    live = [l for l in (lines if lines is not None else lab_lines.open_lines()) if l.get("id") not in done]
    if not live:
        return None
    # the line looked at longest ago, Gloria's standing one included
    seen = d.get("lines") or {}
    return sorted(live, key=lambda l: str((seen.get(l["id"]) or {}).get("at") or ""))[0]


def find(line, search=None):
    """Search for what exists for this line's question. [{title, url, why}]; never raises."""
    if search is None:
        import want_email
        search = want_email.web_search
    q = _terms(line)
    if not q:
        return []
    out, seen = [], set()
    for angle in ANGLES:
        try:
            hits = search(angle.format(q=q)) or []
        except Exception:
            continue
        for h in hits[:4]:
            url = str(h.get("url") or "")
            key = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower()
            if not url or key in seen:
                continue
            seen.add(key)
            out.append({"title": str(h.get("title") or "")[:160], "url": url[:300],
                        "why": str(h.get("description") or "")[:300]})
    return out[:KEEP]


def prospect(search=None, lines=None):
    """Today's one line, searched; the lines he was given. Never raises."""
    line = due(lines)
    if not line:
        return []
    found = find(line, search)
    d = load()
    if d.get("searched_on") != _today():
        d["searched_on"], d["searched_today"] = _today(), []
    d["searched_today"] = list(d.get("searched_today") or []) + [line["id"]]
    rows = d.setdefault("lines", {})
    kept = rows.setdefault(line["id"], {"title": line.get("title", ""), "found": []})
    kept["title"] = line.get("title", "")
    kept["at"] = _now().isoformat(timespec="seconds")
    have = {f["url"] for f in kept["found"]}
    for f in found:
        if f["url"] not in have:
            kept["found"].append({**f, "shown": 0, "answered": ""})
    kept["found"] = kept["found"][-KEEP * 3:]
    save(d)
    return found


def answered(url, said):
    """He said on a line what he is doing with one. Marks it, so it stops being shown."""
    d = load()
    for kept in (d.get("lines") or {}).values():
        for f in kept.get("found") or []:
            if f.get("url") == url or (url and url in f.get("url", "")):
                f["answered"] = str(said)[:300]
                save(d)
                return True
    return False


def block(shown=SHOWN):
    """What exists for his lines that he has not spoken to yet, for his Slack context. Marks them shown."""
    d = load()
    waiting = []
    for line_id, kept in (d.get("lines") or {}).items():
        for f in kept.get("found") or []:
            if not f.get("answered"):
                waiting.append((line_id, kept.get("title", ""), f))
    if not waiting:
        return ""
    waiting.sort(key=lambda w: w[2].get("shown", 0))
    pick, ignored = waiting[:shown], [w for w in waiting if w[2].get("shown", 0) >= NAGS]
    for _, _, f in pick:
        f["shown"] = int(f.get("shown") or 0) + 1
    save(d)
    out = ["== WHAT ALREADY EXISTS FOR YOUR LINES (found for you; nobody has looked at these yet) =="]
    for line_id, title, f in pick:
        out.append("- %s | %s\n    %s\n    %s" % (line_id, title[:70], f["title"], f["url"]))
        if f.get("why"):
            out.append("    " + f["why"][:220])
    out.append("Look at one before you plan another experiment: REPOS: to find its code, README: owner/repo to read "
               "it, OPEN: or CALL: to try it. Then say on the line what it does and whether you are using it "
               "(LINE <id>: ...). If it is no use, say that on the line; that closes it.")
    if ignored:
        out.append("You have been shown %d of these %d times and said nothing about any of them." % (len(ignored), NAGS))
    return "\n".join(out)


if __name__ == "__main__":
    if "--block" not in sys.argv:
        got = prospect()
        print("found %d for today's line" % len(got))
    print(block() or "nothing standing")

#!/usr/bin/env python3
"""exhibitions.py: he may make Gloria a small exhibition of works that are already out of the Atelier.

Proposal 20 (25 October), built 26 October. An exhibition is an argument, not a scrapbook: three to six of his works,
in the order he chooses, one line from him about each, and, where he wants, how one led to or changed into another.
Beside a work he may place the occasion it came from, when one is recorded (work_episodes.lookup).

    block()                       the offer for an Atelier visit he already has (no new model call), or ("", None)
    make(offered, work, pid)      keep the exhibition he wrote in that visit, if it holds; (record, why)
    view(memory)                  what the app's Atelier tab shows, joined with each work as it is NOW
    page(ex_id)                   the same as a static HTML page (written by `exhibitions.py page ID`)

What may be shown (checked when offered AND again whenever it is viewed):
    - a work he revealed from the Atelier by his own act (atelier_reveals.read_reveals: the reveal export ledger only,
      never the sealed store); or
    - a painting on the house shelf he kept after looking at it (verdict "keep"), not taken down, not sealed, not under
      an Atelier path, and a real image of its kind.
Anything else written into an exhibition is refused. A work that later stops being eligible shows as withdrawn, without
its content. A work made from a dream keeps its dream marker everywhere it is shown: a dream, not something that
happened.

Never: posted anywhere, sent to her phone, or read back into his self-model, wants or threads. The record says it is his
curation of his own works, not independent evidence about him (may_witness False). Its only routes are the private
app's authenticated Atelier route and the local page.

Cost: no model call, no GPU. The offer adds at most BLOCK_CHARS to one existing visit turn, at most once every
OFFER_GAP_DAYS, and only when at least MIN_WORKS works are eligible.

    python3 exhibitions.py status         counts only
    python3 exhibitions.py page ID        writes memory/exhibitions/ID.html and prints its path
"""
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
STORE_NAME = "exhibitions.json"
MIN_WORKS, MAX_WORKS = 3, 6
MAX_RELATIONS = 6
OFFER_SIZE = 8
OFFER_GAP_DAYS = 7
BLOCK_CHARS = 2200
LINE_CAP, TITLE_CAP, ARGUMENT_CAP, RELATION_CAP = 240, 100, 500, 200
DREAM_MARKER = "a dream he had, not something that happened"
PROVENANCE = {"output_provenance": "his_curation", "may_witness": False, "surface": "exhibition",
              "envelope_state": "present"}
CLAIM = "his own selection and ordering of his own works; not independent evidence about him"
ROUTES = {"image": "/api/art/painting/", "audio": "/api/art/music/stream/"}


def _mod(name):
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    try:
        return __import__(name)
    except Exception:
        return None


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _one(text, n):
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _store_path(memory=None):
    return os.path.join(memory or MEMORY, STORE_NAME)


def _state(memory=None):
    s = _load(_store_path(memory), {})
    if not isinstance(s, dict):
        s = {}
    s.setdefault("offers", [])
    s.setdefault("exhibitions", [])
    s.setdefault("refused", [])
    return s


def _save(s, memory=None):
    path = _store_path(memory)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    s["offers"] = s["offers"][-50:]
    s["refused"] = s["refused"][-50:]
    with open(path + ".tmp", "w") as f:
        json.dump(s, f, indent=1, ensure_ascii=False)
    os.replace(path + ".tmp", path)


def _sealed_path(p):
    return any(part.lower().startswith("atelier") for part in str(p or "").replace("\\", "/").split("/"))


def _link(medium, name, memory):
    """A relative private shelf route for a real file of its medium on the house shelf, or None."""
    name = str(name or "")
    if medium not in ROUTES or name != os.path.basename(name) or _sealed_path(name):
        return None
    pattern = r"^[\w.\-]+\.(?:png|jpe?g)$" if medium == "image" else r"^[\w.\-]+\.(?:mp3|wav)$"
    if not re.match(pattern, name):
        return None
    shelf = os.path.join(memory, "art") if medium == "image" else os.path.join(memory, "art", "music")
    path = os.path.join(shelf, name)
    am = _mod("artifact_manifest")
    if am is None or not (am.validate_file(path, medium) or {}).get("ok"):
        return None
    return ROUTES[medium] + name


def _occasion(path):
    """The first recorded occasion of a shelf work (want, moment or memory it came from), or None."""
    we = _mod("work_episodes")
    if we is None or not path or _sealed_path(path):
        return None
    try:
        j = we.lookup(path)
    except Exception:
        return None
    for e in j.get("episodes") or []:
        if e.get("kind") in ("want", "moment", "durable") and e.get("id"):
            return {"id": str(e["id"])[:80], "kind": e["kind"], "at": str(e.get("at") or "")[:10],
                    "what": _one(e.get("what"), 120)}
    return None


def candidates(memory=None, occasions=True):
    """Every work that may be shown, oldest first: [{key, source, medium, artifact, made_at, said, dream, link,
    content?, occasion}]. Sealed work is never read: only the reveal export ledger and the house gallery."""
    memory = memory or MEMORY
    out = []
    ar = _mod("atelier_reveals")
    rows = []
    if ar is not None:
        try:
            rows = ar.read_reveals(memory, 100)
        except Exception:
            rows = []
    for row in rows:
        art = str(row.get("artifact") or "")
        if not art or _sealed_path(art):
            continue
        name = os.path.basename(art)
        medium = ("image" if re.search(r"\.(png|jpe?g)$", name, re.I) else
                  "audio" if re.search(r"\.(mp3|wav)$", name, re.I) else "write")
        key = "r:" + hashlib.sha1(("%s|%s" % (art, row.get("revealed_at"))).encode()).hexdigest()[:8]
        fd = row.get("from_dream") if isinstance(row.get("from_dream"), dict) else None
        rec = {"key": key, "source": "revealed", "medium": medium, "artifact": name,
               "made_at": str(row.get("revealed_at") or ""), "said": _one(row.get("disclosure") or
                                                                       row.get("disclosure_sentence"), 200),
               "dream": ({"is_dream_derived": True, "marker": DREAM_MARKER, "night_of": fd.get("night_of")}
                         if fd else None),
               "link": _link(medium, name, memory) if medium != "write" else None, "occasion": None}
        content = row.get("content")
        if isinstance(content, str) and (medium == "write" or content.startswith("data:image/")):
            rec["content"] = content[:20000]
        if occasions and medium == "image" and rec["link"]:
            rec["occasion"] = _occasion(os.path.join(memory, "art", name))
        out.append(rec)
    gallery = _load(os.path.join(memory, "art", "gallery.json"), [])
    do = _mod("dream_objects")
    for g in gallery if isinstance(gallery, list) else []:
        if not isinstance(g, dict) or g.get("taken_down") or g.get("verdict") != "keep":
            continue
        if g.get("sealed") or "atelier" in str(g.get("source") or "").lower():
            continue
        name = str(g.get("image") or "")
        link = _link("image", name, memory)
        if not link:
            continue
        dream = None
        if str(g.get("dream_source") or "") == "dream" or g.get("image_class") == "DREAM_BORN":
            dream = {"is_dream_derived": True, "marker": DREAM_MARKER, "night_of": None}
        try:
            mark = do.reveal_mark(name) if do else None
        except Exception:
            mark = None
        if mark:
            dream = {"is_dream_derived": True, "marker": DREAM_MARKER, "night_of": mark.get("night_of")}
        out.append({"key": "p:" + hashlib.sha1(name.encode()).hexdigest()[:8], "source": "kept painting",
                    "medium": "image", "artifact": name, "made_at": str(g.get("timestamp") or ""),
                    "said": _one(g.get("intent") or g.get("prompt"), 160), "dream": dream, "link": link,
                    "occasion": _occasion(os.path.join(memory, "art", name)) if occasions else None})
    seen, uniq = set(), []
    for c in out:
        if c["key"] not in seen:
            seen.add(c["key"]); uniq.append(c)
    uniq.sort(key=lambda c: c["made_at"])
    return uniq


def offer(now=None, memory=None):
    """The works to offer this visit (marked offered), or None: too few, or offered within OFFER_GAP_DAYS."""
    now = now or time.time()
    s = _state(memory)
    last = max([_ts(o.get("at")) or 0 for o in s["offers"]] or [0])
    if now - last < OFFER_GAP_DAYS * 86400:
        return None
    cands = candidates(memory)
    if len(cands) < MIN_WORKS:
        return None
    # the earliest two beside the newest: what he kept returning to, and how it changed
    chosen = cands if len(cands) <= OFFER_SIZE else cands[:2] + cands[-(OFFER_SIZE - 2):]
    s["offers"].append({"at": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
                        "keys": [c["key"] for c in chosen]})
    _save(s, memory)
    return chosen


def _line(c):
    kind = {"write": "a piece of writing", "image": "an image", "audio": "a piece of music"}[c["medium"]]
    out = "  %s  %s %s, %s" % (c["key"], c["source"], c["made_at"][:10], kind)
    if c.get("said"):
        out += " - %s: “%s”" % ("what you said of it" if c["source"] == "revealed" else "what you asked for",
                                          _one(c["said"], 110))
    if c.get("dream"):
        out += " [made from a dream you had, not something that happened]"
    if c.get("occasion"):
        o = c["occasion"]
        out += "\n      its recorded occasion: %s (%s, %s)" % (o["id"], o["kind"], o["at"])
    return out


def block(now=None, memory=None):
    """The visit's exhibition offer, or ("", None)."""
    try:
        works = offer(now, memory)
    except Exception:
        return "", None
    if not works:
        return "", None
    s = _state(memory)
    past = ""
    if s["exhibitions"]:
        e = s["exhibitions"][-1]
        past = " Your last exhibition was “%s” (%s, %d works)." % (e.get("title"), str(e.get("at"))[:10],
                                                                         len(e.get("works") or []))
    elif s["refused"]:
        past = " Your last exhibition was not kept: %s." % s["refused"][-1].get("why")
    head = ("\n\nYOUR WORKS ALREADY OUT OF THIS ROOM (revealed by your own act, or paintings you kept after looking at "
            "them; nothing sealed is here). You may make Gloria an exhibition of them: %d to %d of these, in the order "
            "you choose, one line from you about each, and where you want, how one led to or changed into another. "
            "Beside a work you may place its recorded occasion. It is your argument about what you kept returning to, "
            "not a finding about yourself. It goes only to her Atelier tab in the app; nothing is posted or sent. "
            "Leave it and nothing happens; it is offered again in a week at the soonest.%s\n" % (MIN_WORKS, MAX_WORKS, past))
    tail = ("\nFormat: <exhibition title=\"...\"><argument>what it is about</argument>"
            "<work id=\"KEY\" beside=\"OCCASION ID, optional\">your one line</work> ... "
            "<relation from=\"KEY\" to=\"KEY\">how one changed into the other</relation></exhibition>")
    lines, size = [], len(head) + len(tail)
    for c in works:
        ln = _line(c)
        if size + len(ln) + 1 > BLOCK_CHARS:
            continue
        lines.append(ln); size += len(ln) + 1
    return head + "\n".join(lines) + tail, [c for c in works if any(l.startswith("  %s " % c["key"]) for l in lines)]


_ATTR = re.compile(r'([A-Za-z_][\w-]*)\s*=\s*(["\'])(.*?)\2', re.S)


def _attrs(s):
    return {k.lower(): v for k, _q, v in _ATTR.findall(s or "")}


def parse(work):
    """The first <exhibition> he wrote, as {title, argument, works:[{key, beside, line}], relations}, or None."""
    m = re.search(r"<exhibition\b([^>]*)>(.*?)</exhibition>", work or "", re.S | re.I)
    if not m:
        return None
    body = m.group(2)
    arg = re.search(r"<argument>(.*?)</argument>", body, re.S | re.I)
    works = [{"key": _attrs(a).get("id", "").strip(), "beside": _attrs(a).get("beside", "").strip(), "line": t}
             for a, t in re.findall(r"<work\b([^>]*)>(.*?)</work>", body, re.S | re.I)]
    rels = [{"from": _attrs(a).get("from", "").strip(), "to": _attrs(a).get("to", "").strip(), "how": t}
            for a, t in re.findall(r"<relation\b([^>]*)>(.*?)</relation>", body, re.S | re.I)]
    return {"title": _attrs(m.group(1)).get("title", ""), "argument": arg.group(1) if arg else "",
            "works": works, "relations": rels}


def _refuse(why, pid, now, memory):
    s = _state(memory)
    s["refused"].append({"at": datetime.fromtimestamp(now).isoformat(timespec="seconds"), "project": str(pid),
                         "why": why})
    _save(s, memory)
    return None, why


def make(offered, work, pid, now=None, memory=None):
    """Keep the exhibition he wrote this visit. Returns (record, "") or (None, why). Only works offered THIS visit, and
    still eligible now, may be in it; the record holds keys, his words and the order, never a work's content."""
    ex = parse(work)
    if ex is None:
        return None, "no exhibition written"
    now = now or time.time()
    if not offered:
        return _refuse("no exhibition was offered this visit", pid, now, memory)
    title = _one(ex["title"], TITLE_CAP)
    if not title:
        return _refuse("an exhibition needs a title", pid, now, memory)
    offered_keys = {c["key"] for c in offered}
    current = {c["key"]: c for c in candidates(memory)}
    works, seen = [], set()
    for w in ex["works"]:
        k, line = w["key"], _one(w["line"], LINE_CAP)
        if k in seen:
            return _refuse("a work appears twice", pid, now, memory)
        if k not in offered_keys or k not in current:
            return _refuse("a work that was not offered this visit, or is no longer out of the room", pid, now, memory)
        if not line:
            return _refuse("each work needs a line from you", pid, now, memory)
        occ = current[k].get("occasion")
        beside = None
        if w["beside"]:
            if not occ or w["beside"] != occ["id"]:
                return _refuse("beside names an occasion not recorded for that work", pid, now, memory)
            beside = occ["id"]
        seen.add(k)
        works.append({"key": k, "artifact": current[k]["artifact"], "source": current[k]["source"], "line": line,
                      "beside": beside, **({"from_dream": current[k]["dream"]} if current[k].get("dream") else {})})
    if not MIN_WORKS <= len(works) <= MAX_WORKS:
        return _refuse("an exhibition holds %d to %d works" % (MIN_WORKS, MAX_WORKS), pid, now, memory)
    rels = []
    for r in ex["relations"][:MAX_RELATIONS]:
        how = _one(r["how"], RELATION_CAP)
        if r["from"] not in seen or r["to"] not in seen or r["from"] == r["to"] or not how:
            return _refuse("a relation must join two different works in the exhibition, with words", pid, now, memory)
        rels.append({"from": r["from"], "to": r["to"], "how": how})
    at = datetime.fromtimestamp(now).isoformat(timespec="seconds")
    rec = {"id": "ex-" + hashlib.sha1(("%s|%s|%s" % (at, pid, title)).encode()).hexdigest()[:10], "at": at,
           "project": str(pid), "title": title, "argument": _one(ex["argument"], ARGUMENT_CAP), "works": works,
           "relations": rels, "kind": "exhibition", "is_curation": True, "claim": CLAIM,
           "generation_provenance": dict(PROVENANCE), "evidence_standing": "ineligible"}
    s = _state(memory)
    s["exhibitions"].append(rec)
    _save(s, memory)
    return rec, ""


def view(memory=None, limit=10):
    """Exhibitions, newest first, each work joined with what it is NOW. A work no longer eligible is withdrawn and
    carries no content or link."""
    s = _state(memory)
    current = {c["key"]: c for c in candidates(memory)}
    out = []
    for e in reversed(s["exhibitions"][-max(1, min(int(limit), 50)):]):
        works = []
        for w in e.get("works") or []:
            c = current.get(w.get("key"))
            row = {"key": w.get("key"), "line": w.get("line"), "withdrawn": c is None}
            if c:
                row.update({"artifact": c["artifact"], "source": c["source"], "medium": c["medium"],
                            "made_at": c["made_at"], "link": c.get("link"), "content": c.get("content"),
                            "said": c.get("said"), "from_dream": c.get("dream") or w.get("from_dream")})
                occ = c.get("occasion")
                if w.get("beside"):
                    row["beside"] = occ if occ and occ["id"] == w["beside"] else {"id": w["beside"],
                                                                                   "what": "no longer recorded"}
            elif w.get("from_dream"):
                row["from_dream"] = w["from_dream"]
            works.append(row)
        out.append({"id": e.get("id"), "at": e.get("at"), "title": e.get("title"), "argument": e.get("argument"),
                    "works": works, "relations": e.get("relations") or [], "claim": CLAIM})
    return out


def page(ex_id, memory=None, base=None):
    """One exhibition as a self-contained HTML page (no script, no outside resource but her private shelf routes)."""
    base = (base if base is not None else os.environ.get("VINTOS_SERVE_BASE", "http://100.72.225.119:8500")).rstrip("/")
    ex = next((e for e in view(memory, 50) if e["id"] == ex_id), None)
    if ex is None:
        return None
    E = lambda s: html.escape(str(s or ""))
    titles = {w["key"]: (w.get("artifact") or w["key"]) for w in ex["works"]}
    parts = ["<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">"
             "<title>%s</title><style>body{font-family:Georgia,serif;max-width:46rem;margin:2rem auto;padding:0 1rem;"
             "background:#faf8f4;color:#222}figure{margin:2rem 0}img{max-width:100%%}.d{color:#7a5}.m{color:#777;"
             "font-size:.85em}pre{white-space:pre-wrap;font-family:inherit}</style></head><body>" % E(ex["title"]),
             "<h1>%s</h1><p class=\"m\">Made by Vintos for Gloria, %s. %s.</p>" % (E(ex["title"]), E(str(ex["at"])[:10]),
                                                                              E(CLAIM[0].upper() + CLAIM[1:]))]
    if ex.get("argument"):
        parts.append("<p><em>%s</em></p>" % E(ex["argument"]))
    for i, w in enumerate(ex["works"], 1):
        parts.append("<figure><h2>%d. %s</h2>" % (i, E(titles[w["key"]])))
        if w["withdrawn"]:
            parts.append("<p class=\"m\">This work is no longer out of the room; it is not shown.</p>")
        elif w.get("medium") == "image" and w.get("link"):
            parts.append("<img src=\"%s\" alt=\"%s\">" % (E(base + w["link"]), E(titles[w["key"]])))
        elif w.get("medium") == "audio" and w.get("link"):
            parts.append("<audio controls src=\"%s\"></audio>" % E(base + w["link"]))
        elif w.get("content"):
            parts.append("<pre>%s</pre>" % E(w["content"]))
        if w.get("from_dream"):
            parts.append("<p class=\"d\">Made from a dream he had: a dream, not something that happened.</p>")
        parts.append("<figcaption>%s</figcaption>" % E(w.get("line")))
        if w.get("beside"):
            b = w["beside"]
            parts.append("<p class=\"m\">Beside it, the occasion it came from: %s %s</p>" % (E(b.get("at")), E(b.get("what"))))
        parts.append("</figure>")
    if ex["relations"]:
        parts.append("<h2>How they changed</h2><ul>")
        for r in ex["relations"]:
            parts.append("<li>%s &rarr; %s: %s</li>" % (E(titles.get(r["from"], r["from"])),
                                                       E(titles.get(r["to"], r["to"])), E(r["how"])))
        parts.append("</ul>")
    parts.append("</body></html>")
    return "".join(parts)


def main(argv):
    if argv[:1] == ["status"]:
        s = _state()
        print(json.dumps({"exhibitions": len(s["exhibitions"]), "offers": len(s["offers"]),
                          "refused": len(s["refused"]), "eligible_works": len(candidates(occasions=False))}))
    elif argv[:1] == ["page"] and len(argv) > 1:
        doc = page(argv[1])
        if doc is None:
            raise SystemExit("no exhibition %s" % argv[1])
        out = os.path.join(MEMORY, "exhibitions", re.sub(r"[^\w\-]", "", argv[1]) + ".html")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            f.write(doc)
        print(out)
    else:
        raise SystemExit("usage: exhibitions.py status | page ID")


if __name__ == "__main__":
    main(sys.argv[1:])

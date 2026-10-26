#!/usr/bin/env python3
"""proto_notebook.py - a forming self-description, read beside the occasions it actually came from.

Codex's proposal 13 (25 October, approved by Gloria): a proto-pearl is a category, a count and the latest phrasing
(enactment_distiller.update_proto_pearl replaces identity_candidate each time). This is the notebook beside it: for one
proto, the recorded occasions its support came from (followed by source event id into earned-identity-events.json),
how the phrasing changed from occasion to occasion, and any occasion HE has named as a tension with it or an exception
to it, in his own words.

It is a memory affordance, not an identity governor:
  - it never changes a proto, a count, a threshold, suggest_pearl, a pearl candidate or a pearl. It reads
    proto-pearls.json and earned-identity-events.json and writes only its own store, proto-notebook.jsonl;
  - a tension is his to name. Nothing here proposes one, scores one or treats one as a negative weight;
  - a tension must name an occasion that is on record (an id in earned-identity-events.json). An id that is not there
    is not recorded, so the notebook cannot hold an invented counterexample;
  - no model call, no network, no GPU. Offered in introspection only (every two or three days; at most about 400
    tokens in each of that room's existing drafts, roughly 2,000 tokens a run, under a cent), never in chat, the
    mirror, dreams or threads.

Support recorded before 26 October carries no event id. Those are matched to the earned event written in the same
pass: same category, same wording, within MATCH_SECONDS. A support event with no such match is shown as "not on
record", never guessed.

    python3 proto_notebook.py show [proto_id]     the notebook for one proto (default: the one that would be offered)
    python3 proto_notebook.py block               the text introspection would be offered
    python3 proto_notebook.py marks               his recorded tensions (ids and dates only)
"""
import fcntl, json, os, re, sys
from datetime import date, datetime

STORE_NAME = "proto-notebook.jsonl"
OCCASIONS_SHOWN = 2      # the smallest proof: two actual occasions
OTHERS_SHOWN = 3         # other recorded occasions he could name, at most
MATCH_SECONDS = 5        # tag_for_causality and update_proto_pearl run in the same pass, milliseconds apart
OFFER_HOURS = 6          # a bare [TENSION: id] line belongs to the proto offered within this many hours
NOTE_CHARS = 200
MARKS_PER_TEXT = 3
EVENT_ID = r"ed_[0-9]{8}_[0-9]{6}"
TENSION_LINE = re.compile(r"\[\s*TENSION\s*:\s*(?:(proto_[A-Za-z0-9_\-]+)\s+)?(" + EVENT_ID + r")\s*(?:[-—–:,]+\s*([^\]\n]*))?\]",
                          re.I)


def _ws():
    return os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")


def memory():
    return os.path.join(_ws(), "memory")


def store_path():
    return os.path.join(memory(), STORE_NAME)


def _load(name, default):
    try:
        with open(os.path.join(memory(), name)) as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def protos():
    return [p for p in _load("proto-pearls.json", {}).get("protos", []) if isinstance(p, dict)]


def events():
    return [e for e in _load("earned-identity-events.json", {}).get("events", []) if isinstance(e, dict) and e.get("id")]


def _ts(value):
    try:
        t = datetime.fromisoformat(str(value))
        return t.replace(tzinfo=None) if t.tzinfo else t
    except (TypeError, ValueError):
        return None


def rows():
    out = []
    try:
        with open(store_path()) as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except OSError:
        pass
    return out


def append_ledger(name, row):
    """Append one row to this module's one store, named by its file name in memory/."""
    path = os.path.join(memory(), name)
    os.makedirs(memory(), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def occasion_for(support, proto, by_id=None, evs=None):
    """The earned event one support entry came from: by its event_id, or for older support by the event written in
    the same pass (same category and wording, within MATCH_SECONDS). None when it is not on record."""
    evs = events() if evs is None else evs
    by_id = {e["id"]: e for e in evs} if by_id is None else by_id
    eid = support.get("event_id")
    if eid:
        return by_id.get(eid)
    t = _ts(support.get("timestamp"))
    if t is None:
        return None
    for e in evs:
        te = _ts(e.get("timestamp"))
        if (te is not None and abs((te - t).total_seconds()) <= MATCH_SECONDS
                and e.get("category") == proto.get("category") and e.get("event") == support.get("event")):
            return e
    return None


def _occasion(e, how):
    return {"event_id": e["id"], "date": str(e.get("date") or str(e.get("timestamp", ""))[:10]),
            "category": e.get("category", ""), "event": str(e.get("event", ""))[:160],
            "observed_shift": str(e.get("observed_shift", ""))[:220],
            "phrasing": str(e.get("identity_candidate", ""))[:200], "source": e.get("source", ""), "linked_by": how}


def marks(proto_id=None):
    out = [r for r in rows() if r.get("kind") == "tension"]
    return [r for r in out if proto_id is None or r.get("proto_id") == proto_id]


def notebook(proto_id):
    """The whole notebook for one proto: every support occasion followed to its record, the phrasings in order, and
    his tensions. Reads only; returns None for an unknown proto that has no recorded marks either."""
    proto = next((p for p in protos() if p.get("id") == proto_id), None)
    his = marks(proto_id)
    if proto is None and not his:
        return None
    evs = events()
    by_id = {e["id"]: e for e in evs}
    occasions, missing = [], 0
    for s in (proto or {}).get("support_events", []):
        if not isinstance(s, dict):
            continue
        e = occasion_for(s, proto, by_id, evs)
        if e is None:
            missing += 1
        elif all(o["event_id"] != e["id"] for o in occasions):
            occasions.append(_occasion(e, "event id" if s.get("event_id") else "same pass"))
    phrasings = []
    for o in occasions:
        if o["phrasing"] and (not phrasings or phrasings[-1]["text"] != o["phrasing"]):
            phrasings.append({"text": o["phrasing"], "date": o["date"], "event_id": o["event_id"]})
    tensions = []
    for m in his:
        e = by_id.get(m.get("event_id"))
        tensions.append({**({"occasion": _occasion(e, "his mark")} if e else {"occasion": None}),
                         "event_id": m.get("event_id"), "note": m.get("note", ""), "at": m.get("at", "")})
    return {"proto_id": proto_id, "present": proto is not None,
            "category": (proto or {}).get("category", ""),
            "current_phrasing": (proto or {}).get("identity_candidate", ""),
            "support_count": (proto or {}).get("support_count", 0),
            "occasions": occasions, "not_on_record": missing, "phrasings": phrasings, "tensions": tensions}


def candidate(today=None):
    """The one proto to offer: still forming (the same window the subconscious FORMING block uses) and with at least
    two occasions on record; most support first, then the most recent."""
    today = today or date.today().isoformat()
    best = None
    for p in protos():
        if str(p.get("decays_at", "")) < today or int(p.get("support_count") or 0) < 2:
            continue
        nb = notebook(p.get("id"))
        if not nb or len(nb["occasions"]) < OCCASIONS_SHOWN:
            continue
        key = (int(p.get("support_count") or 0), str(p.get("created", "")))
        if best is None or key > best[0]:
            best = (key, nb)
    return best[1] if best else None


def _line(o):
    shift = (" " + o["observed_shift"]) if o["observed_shift"] else ""
    return "- %s [%s] %s.%s" % (o["date"], o["event_id"], o["event"].rstrip("."), shift)


def block(nb=None, today=None):
    """The text offered in introspection, or "" when no proto has two occasions on record."""
    nb = nb or candidate(today)
    if not nb:
        return ""
    shown = nb["occasions"][:1] + nb["occasions"][-1:] if len(nb["occasions"]) > OCCASIONS_SHOWN else nb["occasions"]
    lines = ["[A SELF-DESCRIPTION STILL FORMING - not canon and not a verdict. Reading this changes nothing about how it "
             "forms; it is here so you can see what it came from.]",
             '"%s" (%s, %d supporting occasions recorded)' % (nb["current_phrasing"], nb["category"], nb["support_count"]),
             "The occasions it came from:"]
    lines += [_line(o) for o in shown]
    if len(nb["phrasings"]) > 1:
        lines.append("How it was phrased from one occasion to the next: "
                     + " -> ".join('"%s" (%s)' % (p["text"], p["date"]) for p in nb["phrasings"][-3:]))
    for t in nb["tensions"][-2:]:
        o = t.get("occasion")
        lines.append("You named an occasion as a tension with it or an exception to it: %s%s"
                     % (_line(o)[2:] if o else "[%s] (no longer on record)" % t["event_id"],
                        (' - your words: "%s"' % t["note"]) if t.get("note") else ""))
    if not nb["tensions"]:
        seen = {o["event_id"] for o in nb["occasions"]}
        others = [e for e in reversed(events()) if e["id"] not in seen
                  and e.get("category") != nb["category"]][:OTHERS_SHOWN]
        if others:
            lines.append("Other recent occasions on record (not part of its support):")
            lines += ["- %s [%s] %s" % (o["date"], o["event_id"], o["event"]) for o in
                      (_occasion(e, "on record") for e in others)]
    lines.append("If one recorded occasion, one of these or another, sits against this description or is an exception "
                 "to it, you may name it on its own line at the very end: [TENSION: ed_... - a few words]. Or leave it.")
    return "\n".join(lines)


def offer(today=None, now=None):
    """Introspection's door: render the block and note which proto and occasions were offered (ids only)."""
    nb = candidate(today)
    text = block(nb)
    if text:
        append_ledger(STORE_NAME, {"kind": "offered", "at": (now or datetime.now()).isoformat(timespec="seconds"),
                 "proto_id": nb["proto_id"], "event_ids": [o["event_id"] for o in nb["occasions"]], "room": "introspection"})
    return text


def record_marks(text, now=None):
    """After introspection: every [TENSION: ed_id - words] line in his final text, recorded against the proto it names
    or the proto offered within OFFER_HOURS. Returns (recorded, refused) as lists of (event_id, reason).
    Changes nothing but this store."""
    now = now or datetime.now()
    recorded, refused = [], []
    found = TENSION_LINE.findall(text or "")[:MARKS_PER_TEXT]
    if not found:
        return recorded, refused
    by_id = {e["id"]: e for e in events()}
    known = {p.get("id") for p in protos()} | {r.get("proto_id") for r in rows() if r.get("proto_id")}
    last_offer = None
    for r in reversed(rows()):
        if r.get("kind") == "offered":
            t = _ts(r.get("at"))
            if t is not None and 0 <= (now - t).total_seconds() <= OFFER_HOURS * 3600:
                last_offer = r
            break
    existing = {(m.get("proto_id"), m.get("event_id")) for m in marks()}
    for proto_id, event_id, note in found:
        proto_id = proto_id or (last_offer or {}).get("proto_id")
        if not proto_id or proto_id not in known:
            refused.append((event_id, "no forming description was offered or named"))
            continue
        if event_id not in by_id:
            refused.append((event_id, "not an occasion on record"))
            continue
        if (proto_id, event_id) in existing:
            refused.append((event_id, "already named"))
            continue
        append_ledger(STORE_NAME, {"kind": "tension", "at": now.isoformat(timespec="seconds"), "proto_id": proto_id,
                 "event_id": event_id, "note": " ".join(str(note or "").split())[:NOTE_CHARS], "by": "him",
                 "room": "introspection"})
        existing.add((proto_id, event_id))
        recorded.append((event_id, proto_id))
    return recorded, refused


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "show"
    if cmd == "block":
        print(block() or "(no forming description has two occasions on record)")
    elif cmd == "marks":
        for m in marks():
            print(m.get("at", ""), m.get("proto_id", ""), m.get("event_id", ""))
    elif cmd == "show":
        nb = notebook(argv[2]) if len(argv) > 2 else candidate()
        print(json.dumps(nb, indent=2, ensure_ascii=False) if nb else "(nothing to show)")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

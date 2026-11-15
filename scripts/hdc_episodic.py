#!/usr/bin/env python3
"""A hyperdimensional episodic memory of house events, in shadow: who / what / where / when, written down and
read by nothing.

Each house event becomes one or more facts. A fact is the binding (elementwise product) of four role-filler pairs,
each a random bipolar vector of D=10,000 dimensions:

    fact = (R_who * who) * (R_what * what) * (R_where * where) * (R_part * day_part)

and facts are superposed (added) into a small number of integer vectors. "When" is symbolic: the date picks the
day's vectors and the day-part (night, morning, afternoon, evening, late) is a role inside them. Recall is unbinding
with the parts you know and cleaning up against the vocabulary: "what happened in the kitchen yesterday evening?"
unbinds where=kitchen and part=evening from yesterday's vectors and reads off every (who, what) pair whose score
stands clear of the noise. The same memory answers "where was X this morning?" by unbinding who and part.

Capacity: recall from one superposed vector degrades as facts pile up (about 400 facts per D=10k vector is the
edge). So the memory keeps a separate vector per date and starts a new segment of that date after SEGMENT_CAP
facts; a query reads every segment of the date it asks about. Old dates fall off after RETAIN_DAYS.

Sources, opened for reading only (the same files the presence organs already append to):
    memory/kitchen-visits.jsonl, memory/bedroom-visits.jsonl, memory/bedroom-arrivals.jsonl,
    memory/house-board-visits.jsonl, and the doorbell's encounter files (HDC_DOOR_DIR).
Writes: memory/hdc-episodic-shadow.json (atomically) and its lock file beside it. Nothing else. Nothing reads the
state file: no prompt, no context, no consumer (broker/tests/test_hdc_episodic.py holds that). No network, no model
calls. Filler vectors are derived from a hash of the label, so the state file keeps only integer sums and labels.

    hdc_episodic.py sync                                  read the stores, add facts not seen before
    hdc_episodic.py replay FILE --source kitchen|bedroom|arrivals|boards
    hdc_episodic.py ask --where kitchen --when "yesterday evening"
    hdc_episodic.py ask --who gloria --when "today morning"
    hdc_episodic.py stats
"""
import argparse, base64, fcntl, glob, hashlib, json, os, sys, tempfile, time
from datetime import datetime, timedelta
from itertools import product
from zoneinfo import ZoneInfo

import numpy as np

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
DOOR_DIR = os.environ.get("HDC_DOOR_DIR") or os.path.expanduser("~/doorbell-voice/live/encounters")
STATE_NAME = "hdc-episodic-shadow.json"
LOCK_SUFFIX = ".lock"
TZ = ZoneInfo("America/Chicago")
D = 10000
SEGMENT_CAP = int(os.environ.get("HDC_SEGMENT_CAP") or 200)      # facts per superposed vector (clean recall < ~400)
RETAIN_DAYS = int(os.environ.get("HDC_RETAIN_DAYS") or 90)
ROLES = ("who", "what", "where", "part")
PARTS = (("night", 0), ("morning", 6), ("afternoon", 12), ("evening", 17), ("late", 21))   # local start hours
DOOR_THRESH = float(os.environ.get("FACE_THRESHOLD", "0.36"))   # the face matcher's own threshold
BOARD_ROOM = {"house-steam": "bathroom", "house-press-mic": "living_room", "house-touch": "office"}
MIN_SCORE = 0.35          # a recalled pair must clear this fraction of a clean match, and half of the best one


# ---- vectors ------------------------------------------------------------------------------------------------------
_CACHE = {}


def vec(kind, name, d=D):
    """A fixed random bipolar vector for (kind, name): the same on every machine and every run (PCG64, sha256 seed)."""
    key = (kind, str(name), d)
    v = _CACHE.get(key)
    if v is None:
        seed = int.from_bytes(hashlib.sha256(("hdc|%s|%s" % key[:2]).encode()).digest()[:8], "little")
        v = np.random.default_rng(seed).integers(0, 2, d, dtype=np.int8) * 2 - 1
        _CACHE[key] = v
    return v


def bound(role, filler, d=D):
    return vec("role", role, d) * vec(role, filler, d)


def fact_vector(fact, d=D):
    """fact: {role: filler} for every role in ROLES (or any set of roles; the core works for any)."""
    out = np.ones(d, np.int8)
    for role, filler in fact.items():
        out = out * bound(role, filler, d)
    return out


class Store:
    """One superposed vector: integer sums of bipolar fact vectors."""

    def __init__(self, d=D, acc=None, n=0):
        self.d = d
        self.acc = np.zeros(d, np.int32) if acc is None else acc.astype(np.int32)
        self.n = n

    def add(self, fact):
        self.acc += fact_vector(fact, self.d); self.n += 1

    def scores(self, known, vocab, mask=None, cleanup=None):
        """Unbind the known role-fillers; score every combination of the unknown roles' fillers.
        Returns [(score, {role: filler})], score 1.0 = one clean match. mask multiplies the unbound estimate
        (0 = a damaged dimension, -1 = a wrong cue bit); cleanup = cleanup_set(...) reused across stores."""
        key = np.ones(self.d, np.int8)
        for role, filler in known.items():
            key = key * bound(role, filler, self.d)
        est = self.acc.astype(np.float32) * key
        if mask is not None: est = est * mask
        unknown, combos, C = cleanup or cleanup_set(known, vocab, self.d)
        s = (C @ est) / float(self.d)
        return sorted(((float(s[i]), dict(zip(unknown, c))) for i, c in enumerate(combos)), key=lambda x: -x[0])


def cleanup_set(known, vocab, d=D):
    """Every combination of the unknown roles' fillers, bound together: what an unbound estimate is compared to."""
    unknown = [r for r in vocab if r not in known]
    if not unknown: raise ValueError("nothing left to ask")
    combos = list(product(*[vocab[r] for r in unknown]))
    if len(combos) > 4000: raise ValueError("too many unknowns for clean-up (%d combinations)" % len(combos))
    C = np.empty((len(combos), d), np.float32)
    for i, c in enumerate(combos):
        v = np.ones(d, np.int8)
        for role, filler in zip(unknown, c):
            v = v * bound(role, filler, d)
        C[i] = v
    return unknown, combos, C


def recall(ranked, min_score=MIN_SCORE):
    """The answers that stand clear of the noise: at least min_score of a clean match and half of the best."""
    if not ranked or ranked[0][0] < min_score: return []
    floor = max(min_score, ranked[0][0] / 2)
    return [(s, a) for s, a in ranked if s >= floor]


# ---- time -----------------------------------------------------------------------------------------------------------
def day_part(t):
    h = datetime.fromtimestamp(t, TZ).hour
    name = PARTS[0][0]
    for p, start in PARTS:
        if h >= start: name = p
    return name


def date_of(t):
    return datetime.fromtimestamp(t, TZ).strftime("%Y-%m-%d")


def slots(t0, t1):
    """Every (date, day-part) a span touches, in order (a visit across the evening and late counts in both)."""
    out, t = [], t0
    t1 = max(t0, t1)
    while True:
        s = (date_of(t), day_part(t))
        if s not in out: out.append(s)
        if t >= t1: break
        t = min(t1, t + 1800)
    return out[:8]


def resolve_when(text, now=None):
    """'yesterday evening', 'today morning', '2030-01-14 afternoon', 'evening' (today) -> (date, part or None)."""
    now = time.time() if now is None else now
    words = str(text or "").lower().replace(",", " ").split()
    base = datetime.fromtimestamp(now, TZ)
    date, part = base.strftime("%Y-%m-%d"), None
    for w in words:
        if w == "yesterday": date = (base - timedelta(days=1)).strftime("%Y-%m-%d")
        elif w == "today" or w == "tonight": date = base.strftime("%Y-%m-%d")
        elif w in dict(PARTS): part = w
        elif len(w) == 10 and w[4] == "-" and w[7] == "-": date = w
    if "tonight" in words and part is None: part = "evening"
    return date, part


# ---- the memory -----------------------------------------------------------------------------------------------------
class Episodic:
    def __init__(self, d=D, cap=SEGMENT_CAP, retain_days=RETAIN_DAYS):
        self.d, self.cap, self.retain = d, cap, retain_days
        self.days = {}                          # date -> [Store, ...]
        self.vocab = {r: [] for r in ROLES}
        self.seen = {}                          # date -> [fact ids]

    # state ------------------------------------------------------------------------------------------------------
    def to_json(self):
        return {"kind": "hdc-episodic-shadow", "d": self.d, "segment_cap": self.cap, "retain_days": self.retain,
                "vocab": self.vocab, "seen": self.seen,
                "days": {k: [{"n": s.n, "acc": base64.b64encode(s.acc.astype("<i2").tobytes()).decode()} for s in v]
                         for k, v in sorted(self.days.items())}}

    @classmethod
    def from_json(cls, obj):
        m = cls(int(obj.get("d") or D), int(obj.get("segment_cap") or SEGMENT_CAP),
                int(obj.get("retain_days") or RETAIN_DAYS))
        m.vocab = {r: list((obj.get("vocab") or {}).get(r) or []) for r in ROLES}
        m.seen = {k: list(v) for k, v in (obj.get("seen") or {}).items()}
        for k, segs in (obj.get("days") or {}).items():
            m.days[k] = [Store(m.d, np.frombuffer(base64.b64decode(s["acc"]), "<i2"), int(s["n"])) for s in segs]
        return m

    # writing ----------------------------------------------------------------------------------------------------
    def add_fact(self, date, fact, fid=None):
        if fid is not None:
            seen = self.seen.setdefault(date, [])
            if fid in seen: return False
            seen.append(fid)
        for r, f in fact.items():
            if f not in self.vocab[r]: self.vocab[r].append(f)
        segs = self.days.setdefault(date, [])
        if not segs or segs[-1].n >= self.cap: segs.append(Store(self.d))
        segs[-1].add(fact)
        return True

    def ingest(self, event, now=None):
        """event: {who, what, where, ts | from_ts [, to_ts], id?}. One fact per (date, day-part) the event touches.
        Returns the number of facts added (0 if already seen, too old, or incomplete)."""
        who, what, where = (str(event.get(k) or "").strip().lower() for k in ("who", "what", "where"))
        t0 = _num(event.get("from_ts", event.get("ts")))
        if not (who and what and where) or t0 is None: return 0
        t1 = _num(event.get("to_ts"))
        t1 = t0 if t1 is None else t1
        now = time.time() if now is None else now
        oldest = date_of(now - self.retain * 86400)
        eid = event.get("id") or hashlib.sha256(json.dumps([who, what, where, round(t0), round(t1)]).encode()).hexdigest()[:16]
        n = 0
        for date, part in slots(t0, t1):
            if date < oldest: continue
            n += self.add_fact(date, {"who": who, "what": what, "where": where, "part": part}, "%s@%s" % (eid, part))
        return n

    def prune(self, now=None):
        oldest = date_of((time.time() if now is None else now) - self.retain * 86400)
        for k in [k for k in self.days if k < oldest]:
            self.days.pop(k, None); self.seen.pop(k, None)
        for k in [k for k in self.seen if k < oldest]:
            self.seen.pop(k, None)

    # reading ----------------------------------------------------------------------------------------------------
    def ask(self, date, known, mask=None, min_score=MIN_SCORE):
        """Recall from a partial cue. known: {role: filler} for at least two of ROLES (part counts).
        Returns [{'score', role: filler...}] for the unknown roles, best first, across the date's segments."""
        known = {r: str(f).lower() for r, f in known.items() if f}
        if len(known) < 2: raise ValueError("give at least two of who/what/where/part")
        vocab = {r: (self.vocab[r] if r not in known else [known[r]]) for r in ROLES}
        if any(not v for v in vocab.values()): return []
        best, segs = {}, self.days.get(date, [])
        cl = cleanup_set(known, vocab, self.d) if segs else None
        for seg in segs:
            for s, a in recall(seg.scores(known, vocab, mask, cl), min_score):
                k = tuple(sorted(a.items()))
                if s > best.get(k, -1): best[k] = s
        return [dict(k, score=round(s, 3)) for k, s in sorted(best.items(), key=lambda kv: -kv[1])]

    def stats(self):
        return {"dates": len(self.days), "segments": sum(len(v) for v in self.days.values()),
                "facts": sum(s.n for v in self.days.values() for s in v),
                "largest_segment": max([s.n for v in self.days.values() for s in v] or [0]),
                "vocab": {r: len(v) for r, v in self.vocab.items()}}


def _num(v):
    if v is None or v == "": return None
    if isinstance(v, (int, float)): return float(v)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        try: return float(v)
        except ValueError: return None
    if d.tzinfo is None: d = d.replace(tzinfo=TZ)        # naive stamps in these stores are her local time
    return d.timestamp()


# ---- reading the stores (read-only) -------------------------------------------------------------------------------
def _jl(path):
    if not os.path.exists(path): return []
    out = []
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if line.strip():
                try:
                    r = json.loads(line)
                    if isinstance(r, dict): out.append(r)
                except ValueError: continue
    return out


def events_from(source, rows):
    """Turn rows of one presence store into who/what/where events. Labels only: no text from the rows is kept."""
    out = []
    for r in rows:
        if source == "kitchen":
            out.append({"who": "gloria", "what": "visit", "where": "kitchen",
                        "from_ts": r.get("from_ts") or r.get("from"), "to_ts": r.get("to_ts") or r.get("to")})
        elif source == "bedroom":
            out.append({"who": "gloria", "what": "visit", "where": "bedroom",
                        "from_ts": r.get("from_ts") or r.get("from"), "to_ts": r.get("to_ts") or r.get("to")})
        elif source == "arrivals":
            out.append({"who": "gloria", "what": "arrival", "where": "bedroom", "ts": r.get("at")})
        elif source == "boards":
            room = BOARD_ROOM.get(r.get("board"))
            if not room: continue
            what = "shower" if r.get("shower") else ("seated" if (_num(r.get("seated_minutes")) or 0) >= 1 else "visit")
            out.append({"who": "gloria", "what": what, "where": room,
                        "from_ts": r.get("from_ts") or r.get("from"), "to_ts": r.get("to_ts") or r.get("to")})
        elif source == "door":
            e = r.get("event") or {}
            idn = e.get("identity") or {}
            try: conf = float(idn.get("confidence") or 0)
            except (TypeError, ValueError): conf = 0.0
            name = str(idn.get("name") or "").strip().lower()
            who = name if name and conf >= DOOR_THRESH else "someone"
            out.append({"who": who, "what": "at_door", "where": "front_door", "ts": e.get("ts")})
    return out


SOURCES = {"kitchen": "kitchen-visits.jsonl", "bedroom": "bedroom-visits.jsonl",
           "arrivals": "bedroom-arrivals.jsonl", "boards": "house-board-visits.jsonl"}


def read_stores(mem=MEM, door_dir=DOOR_DIR):
    ev = []
    for source, name in SOURCES.items():
        ev += events_from(source, _jl(os.path.join(mem, name)))
    rows = []
    for p in sorted(glob.glob(os.path.join(door_dir, "*.local.json"))):
        try:
            with open(p, "r") as f: rows.append(json.load(f))
        except (OSError, ValueError):
            continue
    ev += events_from("door", [r for r in rows if isinstance(r, dict)])
    return ev


# ---- state file -----------------------------------------------------------------------------------------------------
def load(mem=MEM):
    p = os.path.join(mem, STATE_NAME)
    try:
        with open(p, "r") as f: return Episodic.from_json(json.load(f))
    except (OSError, ValueError, KeyError, TypeError):
        return Episodic()


def _atomic(path, obj):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".hdc-episodic-shadow-", dir=d)
    try:
        with os.fdopen(fd, "w") as f: json.dump(obj, f, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise


def update(events, mem=MEM, now=None):
    """Add events under the state file's lock; returns (facts added, memory)."""
    os.makedirs(mem, exist_ok=True)
    path = os.path.join(mem, STATE_NAME)
    with open(path + LOCK_SUFFIX, "a") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        m = load(mem)
        added = sum(m.ingest(e, now) for e in events)
        m.prune(now)
        if added or not os.path.exists(path): _atomic(path, m.to_json())
    return added, m


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync")
    rp = sub.add_parser("replay"); rp.add_argument("file"); rp.add_argument("--source", choices=sorted(SOURCES) + ["door"], required=True)
    q = sub.add_parser("ask")
    for r in ("who", "what", "where"): q.add_argument("--" + r)
    q.add_argument("--when", default="today")
    sub.add_parser("stats")
    a = ap.parse_args(argv)
    if a.cmd == "sync":
        n, m = update(read_stores())
        print("[hdc] +%d facts; %s" % (n, json.dumps(m.stats())))
    elif a.cmd == "replay":
        rows = _jl(a.file) if a.source != "door" else [json.load(open(a.file))]
        n, m = update(events_from(a.source, rows))
        print("[hdc] replayed %s: +%d facts; %s" % (a.file, n, json.dumps(m.stats())))
    elif a.cmd == "ask":
        date, part = resolve_when(a.when)
        known = {"who": a.who, "what": a.what, "where": a.where, "part": part}
        for row in load().ask(date, {k: v for k, v in known.items() if v}):
            print(json.dumps(dict(row, date=date)))
    elif a.cmd == "stats":
        print(json.dumps(load().stats(), indent=2))


if __name__ == "__main__":
    main()

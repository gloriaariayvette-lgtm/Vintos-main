#!/usr/bin/env python3
"""Tag-keyed hyperdimensional recall behind the existing AprilTag lookup, in shadow: off unless a caller asks for it.

The AprilTag lookup is unchanged: a seen tag opens the memory Gloria linked to it in memory/apriltag-memories.json
(native_video.tag_memory on this side, camera_mamepa.TagMapStore over the private resolved copy on the Studio). That
exact answer always comes first and is never altered. This module adds what the map cannot hold: the object's own
sightings, ranked by salience, recalled from a partial or damaged cue.

One superposed vector per tag. An episode of a tag is the binding of six role-filler pairs, with the binding, the
vectors and the clean-up of scripts/hdc_episodic.py (same seeds, same D=10,000, same Store):

    episode = (R_tag * tag) * (R_who * who) * (R_what * what) * (R_where * where) * (R_day * day) * (R_part * part)

Salience is repetition: an episode seen again is added again (weight 1 by default, at most MAX_WEIGHT per sighting),
so its read-out score is how many times it was laid down. "What is salient about tag 7?" unbinds the tag and cleans
up against that tag's episode list; "what did p1 do with tag 7?" also unbinds who. A damaged vector or a cue with
wrong bits still ranks the salient episodes first (broker/tests/test_hdc_tag_recall.py; held-out numbers in the
commit). The episode list holds labels only, never counts: the strengths live only in the vector.

Forgetting reads an episode's count out of the vector, rounds it and subtracts it (no count is stored anywhere). It
removes episodes older than RETAIN_DAYS and, when a tag holds more than MAX_EPISODES, the weakest oldest ones.

State: memory/hdc-tag-recall-shadow.json (atomic, under its lock), integer sums and labels only. Written only by
`add`/`update` from this module's CLI; no organ, cron or deploy step writes or reads it. Readers are opt-in:
  * HdcTagStore(inner, path) wraps the mamepa's TagStore (native_video_server.py --tag-hdc PATH): exact records
    first, unchanged, then up to K recalled episodes marked as such;
  * native_video.tag_memory(tag, tag_map, hdc=memory) adds an 'episodes' list beside the unchanged exact answer.
No network, no model calls.

    hdc_tag_recall.py add FILE.jsonl        events {tag, who, what, where, ts, weight?} (synthetic or reviewed)
    hdc_tag_recall.py ask --tag tag36h11:7 [--who X] [--what Y] [--where Z] [--k 3]
    hdc_tag_recall.py stats
"""
import argparse, base64, fcntl, json, os, stat, sys, tempfile, time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hdc_episodic import D, MAX_CAP, MIN_SCORE, Store, bound, date_of, day_part, recall, _num   # vector code only

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
STATE_NAME = "hdc-tag-recall-shadow.json"
LOCK_SUFFIX = ".lock"
ROLES = ("who", "what", "where", "day", "part")          # the tag itself is always the first bound pair
RETAIN_DAYS = int(os.environ.get("HDC_TAG_RETAIN_DAYS") or 365)
MAX_EPISODES = 200       # distinct episodes per tag; clean ranking holds well past 100 (see the tests)
MAX_SEGMENTS = 8         # int16 overflow segments per tag (each holds MAX_CAP laid-down weight)
MAX_WEIGHT = 5           # one sighting may count for at most this much salience
K = 3                    # episodes a lookup returns behind the exact answer
NOISE_Z = 4.             # a recalled episode must stand this many read-out sigmas above an absent one (dev R2)
RECORD_CHARS = 200


def fact_vector(tag, ep, d=D):
    out = bound("tag", tag, d)
    for role in ROLES:
        out = out * bound(role, ep[role], d)
    return out


def _clean(v):
    return " ".join(str(v or "").strip().lower().split())[:60]


class TagRecall:
    def __init__(self, d=D, retain_days=RETAIN_DAYS, max_episodes=MAX_EPISODES):
        self.d, self.retain, self.max_episodes = d, int(retain_days), int(max_episodes)
        self.tags = {}           # tag key -> {'segs': [Store], 'episodes': [[who, what, where, day, part], ...]}

    # state ----------------------------------------------------------------------------------------------------------
    def to_json(self):
        return {"kind": "hdc-tag-recall-shadow", "d": self.d, "retain_days": self.retain,
                "max_episodes": self.max_episodes,
                "tags": {k: {"episodes": t["episodes"],
                             "segs": [{"n": s.n, "acc": base64.b64encode(s.acc.astype("<i2").tobytes()).decode()}
                                      for s in t["segs"]]} for k, t in sorted(self.tags.items())}}

    @classmethod
    def from_json(cls, obj):
        m = cls(int(obj.get("d") or D), int(obj.get("retain_days") or RETAIN_DAYS),
                int(obj.get("max_episodes") or MAX_EPISODES))
        for k, t in (obj.get("tags") or {}).items():
            eps = [list(map(str, e)) for e in t.get("episodes") or [] if isinstance(e, list) and len(e) == len(ROLES)]
            segs = [Store(m.d, np.frombuffer(base64.b64decode(s["acc"]), "<i2"), int(s["n"])) for s in t.get("segs") or []]
            if segs and all(s.acc.shape == (m.d,) for s in segs):
                m.tags[str(k)] = {"segs": segs, "episodes": eps}
        return m

    # writing --------------------------------------------------------------------------------------------------------
    def add(self, tag, event, weight=1, now=None):
        """event: {who, what, where, ts}. Lays the episode down `weight` times (salience). Returns True if stored."""
        tag = _clean(tag)
        ep = {"who": _clean(event.get("who")), "what": _clean(event.get("what")), "where": _clean(event.get("where"))}
        ts = _num(event.get("ts"))
        if not tag or not all(ep.values()) or ts is None:
            return False
        now = time.time() if now is None else now
        if date_of(ts) < date_of(now - self.retain * 86400):
            return False
        ep.update(day=date_of(ts), part=day_part(ts))
        w = max(1, min(MAX_WEIGHT, int(_num(weight) or 1)))
        t = self.tags.setdefault(tag, {"segs": [], "episodes": []})
        segs = t["segs"]
        if not segs or segs[-1].n + w > MAX_CAP:
            if len(segs) >= MAX_SEGMENTS:
                return False
            segs.append(Store(self.d))
        segs[-1].acc += w * fact_vector(tag, ep, self.d).astype(np.int32)
        segs[-1].n += w
        row = [ep[r] for r in ROLES]
        if row not in t["episodes"]:
            t["episodes"].append(row)
        if len(t["episodes"]) > self.max_episodes:
            weakest = min(self.read_out(tag), key=lambda x: (x[0], x[1]["day"]))
            self.forget(tag, weakest[1])
        return True

    def forget(self, tag, ep):
        """Read the episode's count out of each segment, round it, subtract it, and drop its label."""
        t = self.tags.get(tag)
        row = [ep[r] for r in ROLES]
        if not t or row not in t["episodes"]:
            return 0
        f = fact_vector(tag, ep, self.d).astype(np.int32)
        gone = 0
        for s in t["segs"]:
            c = int(round(float(s.acc.astype(np.float32) @ f) / self.d))
            if c > 0:
                s.acc -= c * f; s.n = max(0, s.n - c); gone += c
        t["episodes"].remove(row)
        if not t["episodes"]:
            self.tags.pop(tag, None)
        return gone

    def prune(self, now=None):
        oldest = date_of((time.time() if now is None else now) - self.retain * 86400)
        n = 0
        for tag in list(self.tags):
            for row in [r for r in self.tags[tag]["episodes"] if r[ROLES.index("day")] < oldest]:
                n += bool(self.forget(tag, dict(zip(ROLES, row))))
        return n

    # reading --------------------------------------------------------------------------------------------------------
    def read_out(self, tag, known=None, mask=None):
        """[(score, episode)] for the tag's episodes, best first. known: {role: filler} also unbound (a partial cue);
        mask multiplies the unbound estimate (0 = a damaged dimension, -1 = a wrong cue bit), as in hdc_episodic."""
        tag = _clean(tag)
        t = self.tags.get(tag)
        if not t:
            return []
        known = {r: _clean(v) for r, v in (known or {}).items() if r in ROLES and _clean(v)}
        unknown = [r for r in ROLES if r not in known]
        combos = sorted({tuple(row[ROLES.index(r)] for r in unknown) for row in t["episodes"]})
        if not unknown or not combos:
            return []
        C = np.empty((len(combos), self.d), np.float32)
        for i, c in enumerate(combos):
            v = np.ones(self.d, np.int8)
            for role, filler in zip(unknown, c):
                v = v * bound(role, filler, self.d)
            C[i] = v
        cue = dict(known, tag=tag)
        total = dict.fromkeys(combos, 0.)
        for s in t["segs"]:          # hdc_episodic's Store.scores, cleaned up against this tag's episode list
            for sc, a in s.scores(cue, None, mask, (unknown, combos, C)):
                total[tuple(a[r] for r in unknown)] += sc
        return sorted(((sc, dict(known, **dict(zip(unknown, c)))) for c, sc in total.items()), key=lambda x: -x[0])

    def noise(self, tag, mask=None):
        """The read-out noise of the tag's vector, from the vector alone: an episode that was never laid down scores
        about N(0, sigma) with sigma = |acc * mask| / D (the sum of every stored episode's crosstalk)."""
        t = self.tags.get(_clean(tag))
        if not t:
            return 0.
        m = 1. if mask is None else np.asarray(mask, np.float32)
        return float(np.sqrt(sum(float(np.sum((s.acc.astype(np.float32) * m) ** 2)) for s in t["segs"]))) / self.d

    def top(self, tag, k=K, known=None, mask=None, min_score=MIN_SCORE):
        """The k most salient episodes that stand clear of the noise (hdc_episodic.recall, with its floor raised to
        NOISE_Z read-out sigmas when the tag's vector is busy), best first."""
        floor = max(min_score, NOISE_Z * self.noise(tag, mask))
        return [dict(ep, salience=round(s, 2)) for s, ep in recall(self.read_out(tag, known, mask), floor)[:k]]

    def stats(self):
        return {"tags": len(self.tags), "episodes": sum(len(t["episodes"]) for t in self.tags.values()),
                "laid_down": sum(s.n for t in self.tags.values() for s in t["segs"])}


def episode_text(ep):
    return ("recalled sighting (fuzzy recall, salience %s; not a memory Gloria linked): %s, %s, %s, %s %s"
            % (ep["salience"], ep["who"], ep["what"], ep["where"], ep["day"], ep["part"]))[:RECORD_CHARS]


def episode_records(memory, key, k=K):
    """The tag's k most salient episodes as lookup records, each marked as recalled and never as a linked memory."""
    if memory is None:
        return []
    try:
        return [dict(ep, kind="hdc-episode", text=episode_text(ep)) for ep in memory.top(key, k)]
    except Exception:
        return []


class HdcTagStore:
    """A camera_mamepa TagStore (``lookup(key)``) that wraps the existing one: its exact records come first, as they
    are, then up to k recalled episodes. Reads a private state copy (mode 600), re-read when it changes; a missing or
    unreadable copy adds nothing. Nothing is written."""

    def __init__(self, inner, source, k=K):
        self.inner, self.k = inner, int(k)
        self.path = None if isinstance(source, TagRecall) else str(source)
        self.memory = source if isinstance(source, TagRecall) else None
        self.stamp = None

    def _load(self):
        if self.path is None:
            return self.memory
        try:
            st = os.stat(self.path)
        except OSError:
            self.stamp, self.memory = None, None
            return None
        if stat.S_IMODE(st.st_mode) & 0o077:
            raise PermissionError("the tag recall copy must be private (mode 600)")
        if (st.st_mtime_ns, st.st_size) != self.stamp:
            try:
                with open(self.path) as f:
                    self.memory = TagRecall.from_json(json.load(f))
            except Exception:
                self.memory = None
            self.stamp = (st.st_mtime_ns, st.st_size)
        return self.memory

    def lookup(self, key):
        exact = self.inner.lookup(key)
        try:
            memory = self._load()
        except PermissionError:
            raise
        except Exception:
            memory = None
        return list(exact) + episode_records(memory, key, self.k)


# ---- state file -----------------------------------------------------------------------------------------------------
def load(mem=MEM):
    try:
        with open(os.path.join(mem, STATE_NAME)) as f:
            return TagRecall.from_json(json.load(f))
    except (OSError, ValueError, KeyError, TypeError):
        return TagRecall()


def _atomic(path, obj):
    fd, tmp = tempfile.mkstemp(prefix=".hdc-tag-recall-", dir=os.path.dirname(path))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise


def update(events, mem=MEM, now=None):
    """Add events ({tag, who, what, where, ts, weight?}) under the lock; returns (stored, memory)."""
    os.makedirs(mem, exist_ok=True)
    path = os.path.join(mem, STATE_NAME)
    with open(path + LOCK_SUFFIX, "a") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        m = load(mem)
        added = sum(m.add(e.get("tag"), e, e.get("weight", 1), now) for e in events if isinstance(e, dict))
        pruned = m.prune(now)
        if added or pruned or not os.path.exists(path):
            _atomic(path, m.to_json())
    return added, m


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("add"); a_.add_argument("file")
    q = sub.add_parser("ask"); q.add_argument("--tag", required=True); q.add_argument("--k", type=int, default=K)
    for r in ("who", "what", "where"): q.add_argument("--" + r)
    sub.add_parser("stats")
    a = ap.parse_args(argv)
    if a.cmd == "add":
        with open(a.file) as f:
            rows = [json.loads(l) for l in f if l.strip()]
        n, m = update(rows)
        print("[hdc-tag] +%d episodes laid down; %s" % (n, json.dumps(m.stats())))
    elif a.cmd == "ask":
        known = {r: getattr(a, r) for r in ("who", "what", "where") if getattr(a, r)}
        for row in load().top(a.tag, a.k, known):
            print(json.dumps(row))
    else:
        print(json.dumps(load().stats(), indent=2))


if __name__ == "__main__":
    main()

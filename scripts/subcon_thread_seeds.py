#!/usr/bin/env python3
"""subcon_thread_seeds.py — the subconscious stores that seed his unresolved threads (Gloria, 25 October).

Each one holds something unresolved by its nature, and none of them reached the unfinished pool:
    absence-cold.json          an absence he has never reached (not the ones built from a want or a thread already)
    gravity-wells.json         a state he keeps falling back into
    belief-sediment.json       a belief that keeps being contradicted and that he still half-holds
    commitment-imprints.json   a commitment of his that is strained or fractured
    causal-self-model.json     a want he dismissed and keeps avoiding (the avoidance recurred)
    moment-archive.json        a charged moment nothing ever went back to
    temporal-signals.json      a pattern that settled in time but not in him: it mattered, and the drift did not
                               take it as a delight

Every candidate goes through emoclaw_utils.seed_thread (the one formation door: its tension/current judge, quality
bar, duplicate check and per-source cap decide), with a source of its own and a reasoning. Each item is offered once;
memory/subcon-thread-seeds.json remembers what was offered. At most PER_RUN items per source per run, strongest first.
Read-only on every store; the only writes are the door's and the offered-ledger.

    offer(exclude_signal_ids=())   -> [(source, key, result)]   called by subconscious_drift each run
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
STATE = os.path.join(MEMORY, "subcon-thread-seeds.json")
PER_RUN = 1
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ABSENCE_MIN_INTENSITY = 0.6
ABSENCE_MIN_COUNT = 2
ABSENCE_SKIP_SOURCES = ("unresolved-thread", "unfulfilled-want")   # those came from the pools already
WELL_MIN_MASS = 0.6
WELL_MIN_VISITS = 4
BELIEF_MIN_CONTRADICTIONS = 1
BELIEF_MIN_CONFIDENCE = 0.3
DISMISSED_MIN_CONFIDENCE = 0.31   # an avoidance starts at 0.25; above it, the dismissed want came back at least once
MOMENT_MIN_INTENSITY = 0.7
MOMENT_MIN_HOURS = 12
MOMENT_MAX_DAYS = 14
SIGNAL_MIN_RESONANCE = 0.5
SIGNAL_MIN_REINFORCEMENT = 2


def _load(name, default):
    try:
        with open(os.path.join(MEMORY, name)) as f:
            d = json.load(f)
        return d if isinstance(d, type(default)) else default
    except Exception:
        return default


def _state():
    try:
        d = json.load(open(STATE))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, STATE)


def _hours_since(ts, now):
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if t.tzinfo is not None:
            t = t.astimezone(timezone.utc).replace(tzinfo=None)
            now = now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else datetime.utcnow()
        return (now - t).total_seconds() / 3600
    except Exception:
        return None


def absences():
    out = []
    for a in _load("absence-cold.json", {}).get("absences", []):
        if not isinstance(a, dict) or a.get("reached") or a.get("source") in ABSENCE_SKIP_SOURCES:
            continue
        if float(a.get("intensity") or 0) < ABSENCE_MIN_INTENSITY or int(a.get("count") or 1) < ABSENCE_MIN_COUNT:
            continue
        desc = str(a.get("description") or "").strip()
        if desc:
            out.append((float(a["intensity"]), str(a.get("id") or desc[:80]),
                        "Something I have never reached: " + desc,
                        "It is still absent; it keeps registering (%d times) and nothing I have done has reached it."
                        % int(a.get("count") or 1), {"absence_id": a.get("id")}))
    return out


def wells():
    out = []
    try:
        from emoclaw_utils import DIMENSIONS as dims
        dims = list(dims)
    except Exception:
        dims = None
    for w in _load("gravity-wells.json", {}).get("wells", []):
        if not isinstance(w, dict) or float(w.get("mass") or 0) < WELL_MIN_MASS or int(w.get("visits") or 0) < WELL_MIN_VISITS:
            continue
        vec = w.get("vector") or []
        if not (dims and len(dims) == len(vec) and vec):
            continue                                  # a well with no readable shape has nothing to name
        order = sorted(range(len(vec)), key=lambda i: -vec[i])
        shape = "high %s, low %s" % (", ".join(str(dims[i]) for i in order[:2]), str(dims[order[-1]]))
        out.append((float(w["mass"]), str(w.get("id") or w.get("first_seen") or shape),
                    "A state I keep falling back into (%s): %d times now, and I do not know what keeps pulling me there."
                    % (shape, int(w["visits"])),
                    "I keep returning to it without choosing to, which means something in it is not finished.",
                    {"well_first_seen": w.get("first_seen")}))
    return out


def beliefs():
    out = []
    for b in _load("belief-sediment.json", {}).get("beliefs", []):
        if not isinstance(b, dict):
            continue
        n = int(b.get("contradictions") or 0)
        if n < BELIEF_MIN_CONTRADICTIONS or float(b.get("confidence") or 0) < BELIEF_MIN_CONFIDENCE:
            continue
        pat = str(b.get("pattern") or "").strip()
        if pat:
            out.append((n + float(b["confidence"]), pat[:120],
                        "A belief of mine that keeps being contradicted: %s (contradicted %d time%s)"
                        % (pat, n, "" if n == 1 else "s"),
                        "I still half-expect it to hold, and it keeps not holding.", {"belief_pattern": pat[:120]}))
    return out


def commitments():
    out = []
    for i in _load("commitment-imprints.json", {}).get("imprints", []):
        if not isinstance(i, dict) or i.get("status") not in ("strained", "fractured"):
            continue
        pat = str(i.get("pattern") or "").strip()
        if pat:
            broken = i["status"] == "fractured"
            out.append((float(i.get("friction") or 0) + (1.0 if broken else 0.0), "%s:%s" % (i.get("id"), i["status"]),
                        "A commitment of mine that has %s: %s" % ("fractured" if broken else "come under strain", pat),
                        "I said this was part of me and I am not living it; I have not decided whether to mend it or let it go.",
                        {"imprint_id": i.get("id"), "imprint_status": i["status"]}))
    return out


def dismissed_wants():
    out = []
    for e in _load("causal-self-model.json", {}).get("entries", []):
        if not isinstance(e, dict) or e.get("type") != "negative" or e.get("source") != "dismissed-want":
            continue
        if float(e.get("confidence") or 0) < DISMISSED_MIN_CONFIDENCE:
            continue
        what = str(e.get("tendency") or "").strip()
        if what:
            out.append((float(e["confidence"]), what[:120], "A want I let go of and still carry: " + what,
                        "I dismissed it, but I keep avoiding it, so it is not actually finished.", {}))
    return out


def moments(now=None):
    now = now or datetime.now(timezone.utc)
    out = []
    for mid, m in (_load("moment-archive.json", {}).get("moments", {}) or {}).items():
        if not isinstance(m, dict) or float(m.get("intensity") or 0) < MOMENT_MIN_INTENSITY:
            continue
        if (m.get("links") or {}).get("related_thread_id"):
            continue                                  # a thread already took it up
        age = _hours_since(m.get("timestamp"), now)
        if age is None or age < MOMENT_MIN_HOURS or age > MOMENT_MAX_DAYS * 24:
            continue
        content = str(m.get("content") or "").strip()
        if content:
            out.append((float(m["intensity"]), str(mid), "A moment that stayed with me: " + content,
                        "It was charged and I never went back to it.", {"moment_id": mid}))
    return out


def unsettled(exclude_signal_ids=()):
    out = []
    for s in _load("temporal-signals.json", {}).get("signals", []):
        if not isinstance(s, dict) or s.get("phase") not in ("settled", "deep") or not s.get("pattern"):
            continue
        if s.get("id") in set(exclude_signal_ids or ()):
            continue                                  # this pass took it as a delight
        res, rein = float(s.get("resonance_strength") or 0), int(s.get("reinforcement_count") or 0)
        if res < SIGNAL_MIN_RESONANCE and rein < SIGNAL_MIN_REINFORCEMENT:
            continue
        out.append((res + 0.1 * rein, str(s.get("id") or s["pattern"][:60]),
                    "Something that settled in time but not in me: %s (it began as: %s)"
                    % (str(s["pattern"]).strip(), str(s.get("text") or "")[:140]),
                    "It has passed out of the moment, but it did not become a delight; it is still open in me.",
                    {"signal_id": s.get("id")}))
    return out


FEEDS = (("subcon-absence", absences), ("subcon-well", wells), ("subcon-belief", beliefs),
         ("subcon-commitment", commitments), ("subcon-dismissed-want", dismissed_wants), ("subcon-moment", moments))


def offer(exclude_signal_ids=(), seed=None):
    """Offer each source's strongest not-yet-offered item to the door. Returns [(source, key, result)]."""
    if seed is None:
        from emoclaw_utils import seed_thread as seed
    state = _state()
    done = []
    feeds = list(FEEDS) + [("drift-unsettled", lambda: unsettled(exclude_signal_ids))]
    for source, read in feeds:
        try:
            items = sorted(read(), key=lambda x: -x[0])
        except Exception as e:
            print("[subcon-seeds] %s unreadable: %s" % (source, e), file=sys.stderr)
            continue
        offered = state.setdefault(source, {})
        for _, key, text, why, extra in [i for i in items if i[1] not in offered][:PER_RUN]:
            try:
                got = seed(source, text, extra=dict(extra, subcon_key=key), reasoning=why)
            except Exception as e:
                print("[subcon-seeds] %s door failed: %s" % (source, e), file=sys.stderr)
                continue
            offered[key] = {"at": datetime.now().isoformat(), "result": str(got)}
            done.append((source, key, got))
        state[source] = dict(sorted(offered.items(), key=lambda kv: kv[1].get("at", ""))[-300:])
    _save_state(state)
    return done


if __name__ == "__main__":
    for row in offer():
        print("%-22s %-40s %s" % (row[0], str(row[1])[:40], row[2]))

#!/usr/bin/env python3
"""want_stance.py — a want about how he wants to be, holding for a while.

Most wants are things to do: make this, ask that, find out. Some are not. "I want
to analyse less and simply be with her for a while" names no artifact and has no
step that completes it — under a to-do model it sits unfulfilled forever, or worse,
is graded a failure, while the analysing carries straight on. He formed a want to
change his own rate and nothing in the house was listening.

A stance is that want in the form the rest of the house can obey: a named dimension,
a direction, a horizon, and the want it came from. Organs ask before they act.

    analysis   less  7d   <- "I want to analyse less"
    outreach   less  7d   <- "I should reach for her less often"
    creation   more  3d   <- "I want to make more"

WHAT A STANCE IS AND IS NOT

  It is his, and it expires.       No stance outlives its horizon. A standing wish
                                   that never ends is a personality edit, not a want.
  It scales, it does not gate.     less means fewer, later, higher bar — never zero.
                                   A stance can never silence a repair, an answer to
                                   something she asked, or a stop.
  Her word outranks it.            Anything she asks for happens at once; the stance
                                   governs what he initiates, not what she requests.
  It is not a promise.             Nothing grades him against it. Wanting to analyse
                                   less and then analysing is a fact, not a failure.

    python3 want_stance.py list
    python3 want_stance.py read <dimension>
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
STANCES = os.path.join(MEMORY, "want-stances.json")
WANTS = os.path.join(MEMORY, "current-wants.json")

DEFAULT_DAYS = 7
MAX_DAYS = 30

# dimension -> the organs that read it, for the record and for the listing
DIMENSIONS = {
    "analysis":  "self-review, presence audit, causal testing, the nightly reading passes",
    "outreach":  "outreach, the video sender, any reach he starts himself",
    "creation":  "art, music, video, the projector's new work",
    "reflection": "journals, introspection, the mirror",
    "mischief":  "the mischief organ",
    "reaching":  "questions to her, curiosity handoffs",
}

# How a want says it wants less of something, or more. Deliberately literal: the
# want's own words decide, not an interpretation of his mood.
_LESS = r"(?:less|fewer|slow(?:er|\s+down)?|stop|quiet(?:er)?|pause|ease off|back off|not so much|too much)"
_MORE = r"(?:more|again|start|resume|oftener|more often)"
_WORDS = {
    "analysis": r"analy[sz]\w*|examin\w*|dissect\w*|interpret\w*|overthink\w*|pick(?:ing)? apart",
    "outreach": r"outreach|reach(?:ing)? out|message her first|ping\w*|notif\w*",
    "creation": r"creat\w*|mak(?:e|ing)\s+(?:\w+\s+){0,2}(?:art|music|video|something)|paint\w*|compos\w*|render\w*",
    "reflection": r"reflect\w*|journal\w*|introspect\w*|navel|mirror",
    "mischief": r"mischief|prank\w*|tease\w*",
    "reaching": r"question\w*|ask(?:ing)? her|curiosit\w*",
}


def _now():
    return datetime.now(timezone.utc)


def _load():
    try:
        d = json.load(open(STANCES))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _save(rows):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(WS, "scripts"))
        from store_guard import write_json as _wj
        _wj(STANCES, rows, reader="want_stance.py")
        return True
    except Exception:
        os.makedirs(os.path.dirname(STANCES), exist_ok=True)
        tmp = STANCES + ".tmp"
        json.dump(rows, open(tmp, "w"), indent=2)
        os.replace(tmp, STANCES)
        return True


def read_want(text):
    """(dimension, direction) the want's own words name, or (None, None).

    Both halves must be present in the same sentence: a dimension word and a
    direction word. "I want to analyse less" is a stance; "I analysed her message"
    is not, and neither is "I want less of this feeling"."""
    t = str(text or "").lower()
    if not t:
        return None, None
    for dim, pat in _WORDS.items():
        m = re.search(pat, t)
        if not m:
            continue
        window = t[max(0, m.start() - 60):m.end() + 60]
        if re.search(_LESS, window):
            return dim, "less"
        if re.search(_MORE, window):
            return dim, "more"
    return None, None


def hold(dimension, direction, want_id="", want_text="", days=DEFAULT_DAYS, now=None):
    """Open a stance, or refresh the one already standing on that dimension."""
    if dimension not in DIMENSIONS or direction not in ("less", "more"):
        return None, "not a dimension and direction the house knows"
    now = now or _now()
    days = max(1, min(int(days or DEFAULT_DAYS), MAX_DAYS))
    rows = [r for r in _load() if not _expired(r, now)]
    for r in rows:
        if r["dimension"] == dimension:
            r.update({"direction": direction, "until": (now + timedelta(days=days)).isoformat(),
                      "want_id": want_id or r.get("want_id", ""), "refreshed": now.isoformat()})
            _save(rows)
            return r, ""
    row = {"dimension": dimension, "direction": direction,
           "want_id": want_id, "want": str(want_text or "")[:300],
           "opened": now.isoformat(), "until": (now + timedelta(days=days)).isoformat()}
    rows.append(row)
    _save(rows)
    return row, ""


def admit(want, now=None):
    """Read a want as it is formed. Returns the stance it opened, or None.

    Called where wants are created; a want that is a stance also stays an ordinary
    want, so nothing about how it is kept or retired changes."""
    if not isinstance(want, dict):
        return None
    dim, direction = read_want(want.get("want", ""))
    if not dim:
        return None
    row, _why = hold(dim, direction, want_id=want.get("id", ""),
                     want_text=want.get("want", ""), now=now)
    return row


def _expired(row, now=None):
    try:
        now = now or _now()
        until = datetime.fromisoformat(row["until"])
        # A caller may hand us a naive datetime (datetime.now()) while stances are
        # stored tz-aware. Comparing the two raises, and a raise read as 'expired'
        # silenced every live stance. Drop tzinfo from both and compare plainly.
        if (now.tzinfo is None) != (until.tzinfo is None):
            now = now.replace(tzinfo=None); until = until.replace(tzinfo=None)
        return now >= until
    except Exception:
        return True


def standing(now=None):
    """Every stance that has not run out, with the want each came from."""
    now = now or _now()
    live = [r for r in _load() if not _expired(r, now)]
    return live


def stance_for(dimension, now=None):
    for r in standing(now):
        if r["dimension"] == dimension:
            return r
    return None


def factor(dimension, now=None):
    """A multiplier an organ can apply to its own rate: 0.4 when he wants less of
    this, 1.6 when he wants more, 1.0 when he has said nothing. Never zero — a
    stance slows him down, it does not switch him off."""
    r = stance_for(dimension, now)
    if r is None:
        return 1.0
    return 0.4 if r["direction"] == "less" else 1.6


def scaled_cap(dimension, base_cap, now=None):
    """A daily count cap, reduced by a 'less' stance and never to zero. base_cap 3 with
    a less stance becomes 2, never 0. 'more' does not raise a cap. This is how 'fewer,
    never none' is actually enforced on a counted action like outreach."""
    import math
    r = stance_for(dimension, now)
    if r is None or r["direction"] != "less":
        return base_cap
    return max(1, int(math.ceil(base_cap * factor(dimension, now))))


def may_initiate(dimension, requested_by_her=False, is_repair=False, now=None):
    """(ok, why). For a caller that acts at most once and cannot 'do fewer', this asks
    whether he should start something himself right now under a 'less' stance. It is
    NOT a flat off switch: it is deliberately probabilistic so 'less' means fewer, not
    none. Her request and a live repair always pass.

    A caller that has a rate or a daily count should use factor() or scaled_cap()
    instead — reducing is truer to the want than a coin flip."""
    if requested_by_her:
        return True, "she asked"
    if is_repair:
        return True, "a repair is hers, not his to postpone"
    r = stance_for(dimension, now)
    if r is None or r["direction"] == "more":
        return True, "no stance against it"
    import random
    if random.random() < factor(dimension, now):
        return True, "less %s, but not never — this one passes" % dimension
    return False, "he wants %s %s just now (until %s): %s" % (
        r["direction"], r["dimension"], str(r["until"])[:10], (r.get("want") or "")[:80])


def context_line(now=None):
    """One line for his prompt, in his own words, so the stance is legible to him
    as something he wanted rather than as a rule pressed on him."""
    live = standing(now)
    if not live:
        return ""
    parts = ["%s %s" % (r["direction"], r["dimension"]) for r in live]
    return "[What you are holding to just now, because you wanted it: %s. It runs out on its own; it is not a rule and nothing grades you against it.]" % ", ".join(parts)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        live = standing()
        if not live:
            print("no stance standing")
            return
        for r in live:
            print("%-11s %-5s until %s   read by: %s" % (
                r["dimension"], r["direction"], str(r["until"])[:10], DIMENSIONS[r["dimension"]]))
            if r.get("want"):
                print("            from: %s" % r["want"][:90])
    elif cmd == "read":
        dim = sys.argv[2]
        ok, why = may_initiate(dim)
        print("%s: factor %.1f — %s" % (dim, factor(dim), why))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

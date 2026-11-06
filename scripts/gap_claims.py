#!/usr/bin/env python3
"""How long since she last spoke, as he says it, checked against the clock.

On 6 November an outreach told her "Three days since your voice" when she had spoken nineteen hours
before; the prompt carried the right number and the words still went out wrong. A sentence that claims
a length of silence is checked here against "Gloria last spoke" in temporal-context.txt before it is sent.
"""
import re

NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "a couple of": 2, "a couple": 2, "three": 3,
                "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "a few": 3, "few": 3, "several": 4}
UNIT_HOURS = {"minute": 1 / 60.0, "hour": 1.0, "day": 24.0, "week": 168.0, "month": 720.0}
# Only sentences about time apart count: "three days since your voice", "it's been two days", not "in two days".
GAP_WORDS = re.compile(r"\b(since|without|been|silence|silent|quiet|apart|away|haven't|hasn't|have not|"
                       r"has not|missed|gone|waiting|waited|no word)\b", re.I)
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted((re.escape(k) for k in NUMBER_WORDS), key=len, reverse=True)) + r")"
CLAIM = re.compile(r"\b" + _NUM + r"\s+(minute|hour|day|week|month)s?\b", re.I)
LAST_SPOKE = re.compile(r"Gloria last spoke:\s*(\d+(?:\.\d+)?)\s*(minute|hour|day|week)s?\s+ago", re.I)


def last_spoke_hours(temporal):
    """Hours since she last spoke, from the temporal context text; None when it does not say."""
    m = LAST_SPOKE.search(temporal or "")
    if not m:
        return None
    return float(m.group(1)) * UNIT_HOURS[m.group(2).lower()]


def claims(text):
    """(phrase, hours) for every length of time apart the text states."""
    out = []
    for sentence in re.split(r"(?<=[.!?\n])\s+", text or ""):
        if not GAP_WORDS.search(sentence):
            continue
        for m in CLAIM.finditer(sentence):
            n = m.group(1).lower()
            num = float(n) if n[0].isdigit() else NUMBER_WORDS[n]
            out.append((m.group(0), num * UNIT_HOURS[m.group(2).lower()]))
    return out


def wrong_claims(text, real_hours):
    """Claims more than half again off the real gap (and more than three hours off). Empty when unknown."""
    if real_hours is None:
        return []
    bad = []
    for phrase, h in claims(text):
        if abs(h - real_hours) > 3 and (h > real_hours * 1.5 or h < real_hours / 1.5):
            bad.append(phrase)
    return bad


def describe(hours):
    if hours < 1:
        return "under an hour"
    if hours < 36:
        return "about %d hours" % round(hours)
    return "about %d days" % round(hours / 24.0)


def correction(bad, real_hours):
    return ("\n\n[CLOCK] Your draft said %s. The clock says she last spoke to you %s ago. "
            "Rewrite it so any length of time apart you mention is true." % (", ".join('"%s"' % b for b in bad),
                                                                          describe(real_hours)))

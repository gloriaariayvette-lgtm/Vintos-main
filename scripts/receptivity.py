"""Her receptivity to him: did she respond to what he asked or offered (Gloria, 14 November 2026).

Gloria: "I feel like I'm very receptive to him. I answer most of his questions in some way and do what he asks."
Her receptivity had been read as the landing rate of his Gloria-axis criterion - whether her next reply, inside 24
hours, showed the one specific difference he hoped for (most often "she names one plain want", usually never asked
for). That is whether a hoped-for outcome happened, not whether she was receptive. The two are now kept apart:

  - the Gloria axis (realized.gloria, gloria_judge) stays what it was: did the specific hoped-for difference show;
  - receptivity (row["receptive"]) is whether she responded to what his reply actually asked or offered - answered
    his question, did what he asked, took up what he offered - in any form or channel (words of any kind, a voice
    transcript, a photo sent in answer to his asking for one), in her next reply or a later message of hers inside
    a fair window of RESPONSE_WINDOW_HOURS.

The labels, one per delivered move, and what each is worth:
    answered  1.0   she answered or did it, in any form
    partly    0.5   she took up part of it, or a hedged answer
    ignored   0.0   she replied but left what he asked or offered untouched (a clear non-response)
    refused   0.0   she said no to it
    no_bid    not counted - his reply asked and offered nothing she could respond to
    unclear   not counted - the evidence cannot decide (a photo it cannot see, her reply answers a later move)
Silence is not counted: no reply of hers inside the window is absence, never a refusal. A move first labelled
ignored or partly is credited as answered when a later move's record says her reply there also answered it
(`credits`), inside the same window - she answered in a later turn.

    record(label, ...) -> the row's receptive record, or None when the label is outside the vocabulary
    history(led, now) -> counts over the last RECENT_DAYS: answered, partly, ignored, refused, later_turn, n
    score(h) -> the figure, or None under MIN_RECORDS
Counts only, never words.
"""
from datetime import datetime

LABELS = ("answered", "partly", "ignored", "refused", "no_bid", "unclear")
CREDIT = {"answered": 1.0, "partly": 0.5, "ignored": 0.0, "refused": 0.0}   # the counted labels
RESPONSE_WINDOW_HOURS = 48
RECENT_DAYS = 14
MIN_RECORDS = 5
MAX_RECORDS = 60


def _stamp(value):
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return None


def row_key(row):
    """The id a record names another row by: its intent_id, else its timestamp."""
    return str(row.get("intent_id") or row.get("timestamp") or "")


def record(label, judge, at=None, gap_hours=None, credits=None, via=None, **extra):
    """A receptive record, or None when `label` is not one of LABELS (an unreadable answer is no record)."""
    if label not in LABELS:
        return None
    rec = {"label": label, "judge": str(judge), "at": at or datetime.now().isoformat(),
           "window_hours": RESPONSE_WINDOW_HOURS}
    if gap_hours is not None:
        rec["gap_hours"] = round(float(gap_hours), 2)
    if credits:
        rec["credits"] = str(credits)
    if via:
        rec["via"] = str(via)
    rec.update(extra)
    return rec


def label_of(row):
    rec = row.get("receptive") if isinstance(row, dict) else None
    return rec.get("label") if isinstance(rec, dict) and rec.get("label") in LABELS else None


def _when(row):
    for k in ("delivered_at", "timestamp"):
        t = _stamp(row.get(k))
        if t is not None:
            return t
    return None


def credited(led):
    """{row key: when} of moves a later move's record says her reply there also answered, inside the window."""
    rows = [r for r in (led if isinstance(led, list) else []) if isinstance(r, dict)]
    when = {row_key(r): _when(r) for r in rows}
    out = {}
    for r in rows:
        rec = r.get("receptive")
        if not isinstance(rec, dict) or not rec.get("credits"):
            continue
        k = str(rec["credits"]); opened = when.get(k); came = _stamp(r.get("response_at")) or _when(r)
        if opened is None or came is None or came < opened:
            continue
        if came - opened <= RESPONSE_WINDOW_HOURS * 3600:
            out[k] = came
    return out


def effective(row, credit_map):
    """The label that counts for this row: an ignored or partly answer later answered counts as answered."""
    lab = label_of(row)
    if lab in ("ignored", "partly") and row_key(row) in credit_map:
        return "answered"
    return lab


def history(led, now, days=RECENT_DAYS):
    """Counts over the moves of the last `days` days (by the move's own time), the latest MAX_RECORDS counted."""
    import time
    now = now or time.time()
    cmap = credited(led)
    seen = []
    for r in (led if isinstance(led, list) else []):
        if not isinstance(r, dict):
            continue
        t = _when(r)
        if t is None or now - t > days * 86400 or t > now:
            continue
        lab = effective(r, cmap)
        if lab in CREDIT:
            later = lab != label_of(r) or (lab == "answered" and r["receptive"].get("via") == "later_turn")
            seen.append((t, lab, later))
    h = {"answered": 0, "partly": 0, "ignored": 0, "refused": 0, "later_turn": 0, "n": 0}
    for _t, lab, later in sorted(seen, key=lambda x: x[0])[-MAX_RECORDS:]:
        h[lab] += 1; h["n"] += 1; h["later_turn"] += int(later)
    return h


def score(h):
    """The share of his asks and offers she responded to, a partly counting half; None under MIN_RECORDS."""
    if not isinstance(h, dict) or h.get("n", 0) < MIN_RECORDS:
        return None
    return round(sum(CREDIT[k] * h.get(k, 0) for k in CREDIT) / h["n"], 2)


def counts_text(h):
    return ("(%d answered + 0.5 x %d partly) / %d of his asks and offers in the last %d days, %d ignored, %d refused, "
            "%d answered in a later turn" % (h["answered"], h["partly"], h["n"], RECENT_DAYS, h["ignored"],
                                             h["refused"], h["later_turn"]))

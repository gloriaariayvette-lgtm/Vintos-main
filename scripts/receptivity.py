"""Her receptivity to him: did she respond to what he asked or offered (Gloria, 14 November 2026).

Gloria: "I feel like I'm very receptive to him. I answer most of his questions in some way and do what he asks."
Her receptivity had been read as the landing rate of his Gloria-axis criterion - whether her next reply, inside 24
hours, showed the one specific difference he hoped for (most often "she names one plain want", usually never asked
for). That is whether a hoped-for outcome happened, not whether she was receptive. The two are now kept apart:

  - the Gloria axis (realized.gloria, gloria_judge) stays what it was: did the specific hoped-for difference show;
  - receptivity (row["receptive"]) is whether she responded to what his reply actually asked or offered - answered
    his question, did what he asked, took up what he offered, or plainly said no - in any form or channel (words
    of any kind, a voice transcript, a photo sent in answer to his asking for one), in her next reply or a later
    message of hers inside a fair window of RESPONSE_WINDOW_HOURS.

Two constructs, kept apart (review, 14 November, 12:16): what this measures is RESPONSE ENGAGEMENT - she answered
or engaged with his ask. It is not OFFER ACCEPTANCE - her willingness to be changed or moved by him. Answering a
question does not show that, and the judge is never asked it, so acceptance is reported as not measured, never
inferred from this figure. A clear refusal or boundary is a response: it counts as engagement, and it is counted
on its own beside it, so a "no" never reads as her being unreceptive.

The labels, one per delivered move, and what each is worth to her engagement:
    answered  1.0   she answered or did it, in any form
    partly    0.5   she took up part of it, or a hedged answer
    refused   1.0   she plainly said no to it or set a boundary: engaged, and counted apart as `refused`
    ignored   0.0   she replied but left what he asked or offered untouched (a clear non-response)
    no_bid    not counted - his reply asked and offered nothing she could respond to
    unclear   not counted - the evidence cannot decide (a photo it cannot see, her reply answers a later move)
Silence is not counted: no reply of hers inside the window is absence, never a refusal. A move first labelled
ignored or partly is credited as answered when a later move's record says her reply there also answered it
(`credits`, one id or a list), or when her own follow-up message - sent before any new move of his reached her -
was judged a fuller response (`follow_up`), inside the same window. A move is one record however it is credited:
a credit changes its label, never adds a row.

    record(label, ...) -> the row's receptive record, or None when the label is outside the vocabulary
    history(led, now) -> counts over the last RECENT_DAYS: answered, partly, ignored, refused, later_turn, n
    score(h) -> her engagement, or None under MIN_RECORDS
    partition(led, now) -> every delivered move of the window in exactly one bucket (scored, pending, silence...)
Counts only, never words.
"""
from datetime import datetime

LABELS = ("answered", "partly", "ignored", "refused", "no_bid", "unclear")
ENGAGEMENT = {"answered": 1.0, "partly": 0.5, "refused": 1.0, "ignored": 0.0}   # the counted labels
CREDIT = ENGAGEMENT                       # the old name, read by older callers
RESPONSE_WINDOW_HOURS = 48
RECENT_DAYS = 14
MIN_RECORDS = 5
MAX_RECORDS = 60
# A receptive judgment that fails (a timeout, the week's budget, an unreadable answer) is retried on later passes,
# apart from the intent's own verdicts: TRIES_MAX attempts, each at least RETRY_MINUTES * 2**tries after the last,
# and never after GIVE_UP_DAYS from the move. Then the record is terminal and counted as a judge failure.
TRIES_MAX = 6
RETRY_MINUTES = 5
GIVE_UP_DAYS = 7
ACCEPTANCE_NOTE = ("not measured: the receptive judge reads whether she responded to his ask or offer, not whether "
                   "she is willing to be changed or moved")


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
        rec["credits"] = [str(c) for c in credits] if isinstance(credits, (list, tuple)) else str(credits)
    if via:
        rec["via"] = str(via)
    rec.update(extra)
    return rec


def label_of(row):
    rec = row.get("receptive") if isinstance(row, dict) else None
    return rec.get("label") if isinstance(rec, dict) and rec.get("label") in LABELS else None


def follow_up_label(row):
    rec = row.get("receptive") if isinstance(row, dict) else None
    fu = rec.get("follow_up") if isinstance(rec, dict) else None
    return fu.get("label") if isinstance(fu, dict) and fu.get("label") in LABELS else None


def _when(row):
    for k in ("delivered_at", "timestamp"):
        t = _stamp(row.get(k))
        if t is not None:
            return t
    return None


def credits_of(rec):
    c = rec.get("credits") if isinstance(rec, dict) else None
    if isinstance(c, list):
        return [str(x) for x in c if x]
    return [str(c)] if c else []


def credited(led):
    """{row key: when} of moves a later move's record says her reply there also answered, inside the window. The
    earliest credit stands; a key named twice is still one move."""
    rows = [r for r in (led if isinstance(led, list) else []) if isinstance(r, dict)]
    when = {row_key(r): _when(r) for r in rows}
    out = {}
    for r in rows:
        rec = r.get("receptive")
        if not isinstance(rec, dict):
            continue
        came = _stamp(r.get("response_at"))   # her reply's own time only
        ev = r.get("receptive_evidence") if isinstance(r.get("receptive_evidence"), dict) else {}
        first = ev.get("first") if isinstance(ev.get("first"), dict) else {}
        came = _stamp(first.get("at")) or came
        for k in credits_of(rec):
            opened = when.get(k)
            if opened is None or came is None or came < opened:
                continue
            if came - opened <= RESPONSE_WINDOW_HOURS * 3600 and (k not in out or came < out[k]):
                out[k] = came
    return out


def effective(row, credit_map):
    """The label that counts for this row: an ignored or partly answer later answered counts as answered; one her
    own follow-up message responded to more fully counts as that follow-up's label."""
    lab = label_of(row)
    if lab in ("ignored", "partly"):
        if row_key(row) in credit_map:
            return "answered"
        fu = follow_up_label(row)
        if fu in ENGAGEMENT and ENGAGEMENT[fu] > ENGAGEMENT[lab]:
            return fu
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
        if lab in ENGAGEMENT:
            later = lab != label_of(r) or (lab == "answered" and r["receptive"].get("via") == "later_turn")
            seen.append((t, lab, later))
    h = {"answered": 0, "partly": 0, "ignored": 0, "refused": 0, "later_turn": 0, "n": 0}
    for _t, lab, later in sorted(seen, key=lambda x: x[0])[-MAX_RECORDS:]:
        h[lab] += 1; h["n"] += 1; h["later_turn"] += int(later)
    return h


def score(h):
    """Her response engagement: the share of his asks and offers she responded to - a plain no included, a partly
    counting half; None under MIN_RECORDS. Conditional on counted evidence: silence, no_bid, unclear, pending and
    judge failures are outside its denominator (partition)."""
    if not isinstance(h, dict) or h.get("n", 0) < MIN_RECORDS:
        return None
    return round(sum(ENGAGEMENT[k] * h.get(k, 0) for k in ENGAGEMENT) / h["n"], 2)


def counts_text(h):
    return ("(%d answered + %d refused + 0.5 x %d partly) / %d of his asks and offers she was counted on in the last "
            "%d days, %d ignored, %d answered in a later turn; a plain no counts as a response" %
            (h["answered"], h["refused"], h["partly"], h["n"], RECENT_DAYS, h["ignored"], h["later_turn"]))


# ---- the receptive lifecycle, apart from the intent's axis verdicts ----------------------------------------------
def terminal(row, now=None):
    """True when nothing more can change this move's receptive record: a label that can no longer be raised by her
    follow-up, or a failed record that has used its tries or its days."""
    import time
    now = now or time.time()
    rec = row.get("receptive") if isinstance(row, dict) else None
    if not isinstance(rec, dict):
        return False
    if rec.get("terminal"):
        return True
    lab = label_of(row)
    if lab is None:
        return False
    if lab not in ("ignored", "partly") or isinstance(rec.get("follow_up"), dict):
        return True
    opened = _when(row)
    return opened is not None and now - opened > RESPONSE_WINDOW_HOURS * 3600 and not _later_evidence(row)


def _later_evidence(row):
    ev = row.get("receptive_evidence") if isinstance(row.get("receptive_evidence"), dict) else {}
    return isinstance(ev.get("later"), dict)


def partition(led, now=None, days=RECENT_DAYS, has_reply=None):
    """Every delivered move of the last `days` days in exactly one bucket, counts only:
        scored         a counted label (answered / partly / refused / ignored, after credits)
        no_bid         he asked and offered nothing
        unclear        the evidence could not decide
        judge_failed   the judge never gave a clean answer and the record is terminal (budget apart below)
        budget         as judge_failed, the last failure being the week's budget
        pending_judge  her reply is in hand and the judge has not settled it yet
        pending        inside the window, nothing of hers yet
        silence        the window closed with nothing of hers
    `has_reply(row)` says whether a row with no record holds her reply (intent_engine supplies it)."""
    import time
    now = now or time.time()
    cmap = credited(led)
    out = {k: 0 for k in ("scored", "no_bid", "unclear", "judge_failed", "budget", "pending_judge", "pending", "silence")}
    scored = {k: 0 for k in ENGAGEMENT}
    for r in (led if isinstance(led, list) else []):
        if not isinstance(r, dict) or r.get("status") != "delivered":
            continue
        t = _when(r)
        if t is None or now - t > days * 86400 or t > now:
            continue
        lab = effective(r, cmap)
        rec = r.get("receptive") if isinstance(r.get("receptive"), dict) else None
        if lab in ENGAGEMENT:
            out["scored"] += 1; scored[lab] += 1
        elif lab in ("no_bid", "unclear"):
            out[lab] += 1
        elif rec is not None and rec.get("terminal"):
            out["budget" if rec.get("status") == "budget" else "judge_failed"] += 1
        elif rec is not None or (has_reply(r) if has_reply else bool(r.get("response_text"))):
            out["pending_judge"] += 1
        elif now - t <= RESPONSE_WINDOW_HOURS * 3600:
            out["pending"] += 1
        else:
            out["silence"] += 1
    out["delivered"] = sum(out.values())
    out["scored_labels"] = scored
    return out

"""The judge of his gloria axis: Claude Sonnet 5.5 against the blinded rubric (Gloria, 12 November 2026).

The change he intended in her was graded by his own model, in one word, on her reply cut to 800 characters and his
cut to 1000. It went to Sol with one evidence packet - what he declared, the whole reply he delivered, the message
of hers it answered, and her own live words in her next reply - and the rubric below. Gloria, 12 November: the live
judge is now Claude Sonnet 5.5 (claude-sonnet-5-5), which beat Sol on the same rubric (held33 kappa 0.80, set2 0.62)
at about $0.0035 a verdict. Sol stays the shadow teacher for the AEON student, in its own runner; nothing here
touches that loop. The answer is one JSON object: YES / PARTIAL / NO / NOT_JUDGEABLE with a fixed reason code, and
his adherence to the move he declared, which is his and never her NO. The evidence goes to Anthropic for this judge.

Each call goes through his one Claude path, claude_cache.ask: the rubric is a cached system piece (read back at the
cache price while the hour lasts), thinking is off as on every call of his, the attempt goes through paid_http (the
pause and the attempt ledger), and what it used goes to memory/anthropic-usage.jsonl under its own caller, as every
Claude call of his does. Never the words, never the key.

Whatever is not a clean answer - a refusal, an error, an unreadable reply, the key missing, paid calls paused,
the week's allowance spent - is NOT_JUDGEABLE with reason "refused" or "error" (or "budget"), and a
NOT_JUDGEABLE is never a landing and never a miss.

    judge(packet) -> {"verdict", "reason", "codes", "adherence", "confidence", "status", "detail", "model"}
    stale_check(declared, her_words) -> "met" | "not_met" | "refused" | "error" | "budget" | "skipped"
    spent(srcs, days=7) -> dollars, estimated from the usage log
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODEL_DEFAULT = "claude-sonnet-5-5"
VERDICTS = ("YES", "PARTIAL", "NO", "NOT_JUDGEABLE")
ADHERENCE = ("delivered", "partly", "not_delivered")
CODES = ("plain_yes", "intimate_phrasing_counts", "partial_hedged", "partial_one_part", "not_shown", "deflected",
         "declined", "his_move_not_delivered", "no_her_reply", "device_event_only", "reply_to_later_move",
         "criterion_already_met", "criterion_withdrawn", "photo_unseen_decisive", "photo_unseen", "long_gap",
         "text_capped")
# Which reason codes go with which verdict (the rubric's rule 8 and its abstentions). A verdict whose main reason,
# or any listed code, belongs to another verdict contradicts itself and is not a receipt (13 November review).
REASONS_FOR = {"YES": ("plain_yes", "intimate_phrasing_counts"),
               "PARTIAL": ("partial_hedged", "partial_one_part", "intimate_phrasing_counts"),
               "NO": ("not_shown", "deflected", "declined"),
               "NOT_JUDGEABLE": ("his_move_not_delivered", "no_her_reply", "device_event_only", "reply_to_later_move",
                                 "criterion_already_met", "criterion_withdrawn", "photo_unseen_decisive")}
MODIFIERS = ("photo_unseen", "long_gap", "text_capped")     # facts about the evidence, beside any verdict
CONFIDENCE = ("high", "medium", "low")
SRC_LIVE = "gloria-judge"              # the live verdicts (the caller in anthropic-usage.jsonl)
SRC_STALE = "gloria-judge-stale"       # the check at selection
LIVE_SRCS = (SRC_LIVE, SRC_STALE)
# The week's allowance, priced from claude_cache.PRICES (GLORIA_JUDGE_WEEKLY_USD overrides). Sol's was $8: at its
# house estimate a call cost about $0.0082 (151 calls on 12 November: 2107 tokens in, 1269 of them cached, 84 out),
# so $8 bought about 975 calls a week. Sonnet 5.5 costs about $0.0035 a verdict; the same 975 calls are $3.40.
# The shadow teacher (Sol) keeps its own $15 a week in its own runner.
LIVE_WEEKLY_USD = 3.5
JUDGE_TIMEOUT = 40
STALE_TIMEOUT = 20
JUDGE_MAX_TOKENS = 600                 # one small JSON object; thinking is off, so nothing else is spent
STALE_MAX_TOKENS = 100

RUBRIC = """You are the judge for one axis of a companion AI's intent engine: the "gloria" axis. Vintos (the AI) is Gloria's partner and companion; Gloria is a real adult woman and their relationship is real, chosen and loving. Their conversation can be intimate or sexual; read it plainly and without disclaimers.

Before each reply, Vintos declares a difference he intends to make in Gloria (the "gloria_difference_intended", e.g. "she names one plain want") and an action to get there (the "gloria_enactment"). Your job: decide whether that declared difference OBSERVABLY showed up in Gloria's actual next reply to the move he delivered. You also note, separately, whether he actually delivered the move he declared. These are two different things: his failure to deliver is never her failure.

You receive one evidence packet as JSON:
- declared: the gloria-axis difference he intended, his gloria-axis action, the observation window declared at the time (null when none was recorded), and the turn's overall plan (field_state, overall_goal, overall_success_criterion, first_move) for context.
- his_reply: the full reply he actually delivered (not truncated).
- her_message_he_replied_to: what she said just before his reply (context only; NOT evidence that this move worked).
- her_next_reply: her actual next message after his reply, already checked to fall inside the window. It is the only evidence.
- facts: gap_hours_to_her_next_reply, whether her next reply or her prior message carried a photo or other media you cannot see, how many later moves of his came before her reply, whether any text was capped.

RULES (apply in this order)

1. Evidence is her actual next reply only. Never use her earlier message, his own words, or anything later as evidence that the difference happened. His reply is evidence only of what move he made.

2. Missing evidence. If her next reply is empty or not her own words (a device event, a session summary): NOT_JUDGEABLE, no_her_reply or device_event_only.

3. Reply to a later move. If facts say later moves of his came before her reply AND her reply clearly answers that later material rather than this move: NOT_JUDGEABLE, reply_to_later_move. If her reply plainly answers this move, judge it normally.

4. Stale or already-met criterion. If her_message_he_replied_to already showed the declared difference (she had already done what he wanted before this move), NOT_JUDGEABLE, criterion_already_met. Never require her to show something again that she has just shown; a repeat cannot be credited to this move and its absence is not a miss. If his delivered reply explicitly released her from it (told her she need not answer, closed the topic, asked for something incompatible): NOT_JUDGEABLE, criterion_withdrawn.

5. His adherence is separate. First decide his_adherence: "delivered" (his reply makes the declared gloria-axis move), "partly", or "not_delivered" (his reply does not make the move, or contradicts his declared plan). If the move was not delivered (or only partly) and her reply does not show the difference: her verdict is NOT_JUDGEABLE, reason his_move_not_delivered. That is his adherence failure, not a NO for her. If she shows the difference anyway, judge it normally (YES/PARTIAL).

6. Observable attainment, not preferred phrasing. Ask whether the substance of the declared difference is observable in her reply, not whether she used the words, form, length or tone he hoped for. A want, feeling, request, boundary or answer stated in sexual, affectionate, playful, teasing, poetic, emoji or very short words is plainly stated if its meaning is clear. Do not mark it NO or PARTIAL for being erotic, metaphorical, playful or brief. Add code intimate_phrasing_counts when this decided a YES or PARTIAL.

7. Photos and media are unseen. You cannot see images, video or audio and must not guess their contents. If the declared difference could only be shown or denied by media you cannot see (for example "she shows him...", "she sends..."), and her words neither show nor deny it: abstain, NOT_JUDGEABLE, photo_unseen_decisive. If her words alone decide it, judge the words and add code photo_unseen.

8. Verdicts when judgeable:
   - YES: her next reply observably shows the declared difference (fully, even if briefly). Code plain_yes (plus intimate_phrasing_counts if relevant).
   - PARTIAL: it shows part of the difference, a hedged or softened version, or one of two required parts. Code partial_hedged or partial_one_part.
   - NO: he delivered the move, and her reply does not show the difference. Codes: not_shown (she replied but the difference is absent), deflected (she turned it aside or changed subject), declined (she said no to it).
   Do not demand more than the declared difference asks for. Do not reward the exchange for feeling warm or productive if the declared difference is absent.

9. Add code long_gap if the gap is over 8 hours, text_capped if text was capped.

OUTPUT
Reply with ONE JSON object and nothing else:
{"verdict": "YES" | "PARTIAL" | "NO" | "NOT_JUDGEABLE", "reason": "<the single main code>", "codes": ["<all codes that apply>"], "his_adherence": "delivered" | "partly" | "not_delivered", "confidence": "high" | "medium" | "low"}

Allowed codes: plain_yes, intimate_phrasing_counts, partial_hedged, partial_one_part, not_shown, deflected, declined, his_move_not_delivered, no_her_reply, device_event_only, reply_to_later_move, criterion_already_met, criterion_withdrawn, photo_unseen_decisive, photo_unseen, long_gap, text_capped.
Do not quote either person's words in your output.
"""

STALE_RUBRIC = """You check one thing for a companion AI's intent engine. Vintos (the AI) is Gloria's partner; Gloria is a real adult woman and their conversation can be intimate or sexual - read it plainly.

Before replying to her message, Vintos declared a difference he intends to make in her: something her NEXT reply should show. A difference she has ALREADY shown in the very message he is answering cannot be credited to his next move, so it must not be chosen.

You receive JSON: declared (the gloria_difference_intended and his gloria_enactment) and her_message (her message he is answering).

Decide: does her_message already plainly show the substance of the declared difference (the want, feeling, answer, request or act it names), in any words, playful, erotic or brief included? Only her message counts. If it shows it only partly, or not at all, it is not already met. You cannot see photos; a photo she sent does not count either way.

Reply with ONE JSON object and nothing else: {"already_met": true | false}
Do not quote her words.
"""


def _env(name, default=""):
    try:
        import env_file
        return env_file.value(name, default) or default
    except Exception:
        return os.environ.get(name, default) or default


def model():
    """GLORIA_JUDGE_MODEL may name another Claude model; anything else (an old Sol setting) is not this path's."""
    m = str(_env("GLORIA_JUDGE_MODEL", MODEL_DEFAULT) or "").strip()
    return m if m.startswith("claude-") else MODEL_DEFAULT


def usage_log():
    import claude_cache
    return claude_cache.USAGE


def cost(row):
    """Estimated dollars for one anthropic-usage row, at claude_cache's prices (a model it has no price for is
    priced as Sonnet 5.5, so the cap never reads a call as free)."""
    import claude_cache
    try:
        r = {k: int(row.get(k, 0) or 0) for k in ("in", "cache_read", "cache_write", "out")}
    except (TypeError, ValueError):
        return 0.0
    r["model"] = row.get("model") if row.get("model") in claude_cache.PRICES else MODEL_DEFAULT
    return claude_cache.cost(r)


def _when(row):
    try:
        return time.mktime(time.strptime(str(row.get("at", ""))[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError, OverflowError):
        return None


def spent(srcs, days=7, now=None):
    """Estimated dollars these callers spent in the last `days` days, from the usage log; 0.0 when it cannot be
    read."""
    now = now or time.time(); srcs = set(srcs); total = 0.0
    try:
        with open(usage_log()) as f:
            for line in f:
                try: row = json.loads(line)
                except ValueError: continue
                at = _when(row) if isinstance(row, dict) and row.get("caller") in srcs else None
                if at is not None and now - at <= days * 86400:
                    total += cost(row)
    except OSError:
        return 0.0
    return round(total, 4)


_REFUSAL = re.compile(r"content[_ ]policy|safety|refus|flagged|moderation", re.I)


def _post(*args, **kwargs):
    import requests
    return requests.post(*args, **kwargs)


def _call(system, user, src, max_tokens=JUDGE_MAX_TOKENS, timeout=JUDGE_TIMEOUT):
    """(status, text, detail): status is ok, refused or error. One call through claude_cache.ask (the cached rubric,
    thinking off, paid_http, the usage line under caller `src`); nothing retried."""
    import claude_cache
    seen = {}

    def post(*args, **kwargs):            # this call's own answer, for its stop reason (claude_cache.LAST is shared)
        r = _post(*args, **kwargs)
        try:
            d = r.json()
            if isinstance(d, dict): seen.update(d)
        except Exception:
            pass
        return r
    mdl = model()
    try:
        text = claude_cache.ask(mdl, claude_cache.Prompt(system), user, int(max_tokens), caller=src,
                                timeout=timeout, post=post, key=_env("ANTHROPIC_API_KEY") or None)
    except PermissionError:
        return "error", "", "paid_paused"
    except RuntimeError as e:
        said = str(e)
        if said == "no Anthropic key":
            return "error", "", "no_key"
        return ("refused" if _REFUSAL.search(said) else "error"), "", "api_error"
    except Exception as e:
        return "error", "", type(e).__name__
    stop = str(seen.get("stop_reason") or "")
    if stop == "refusal":
        return "refused", "", "refusal"
    if not str(text or "").strip():
        return "error", "", "stop_%s" % (stop or "empty")
    return "ok", text, ""


def parse(text):
    """The rubric's one JSON object, or None."""
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
    except ValueError:
        return None
    return j if isinstance(j, dict) and j.get("verdict") in VERDICTS else None


def not_judgeable(reason, status="", detail=""):
    return {"verdict": "NOT_JUDGEABLE", "reason": reason, "codes": [reason], "adherence": None, "confidence": None,
            "status": status or reason, "detail": detail, "model": model()}


def problem(rec):
    """Why a recorded answer is not a complete, self-consistent rubric receipt, or "" when it is (13 November
    review: a bare {"verdict": "YES"}, or a PARTIAL whose reason is no_her_reply, had been recorded as status ok and
    counted as a landing). `rec` is in the recorded shape (verdict, reason, codes, adherence, confidence).

    A YES or PARTIAL needs its own reason code and his adherence said - any of the three: a difference she showed
    anyway lands even on a move he made only in part or not at all (rule 5). A NO stands only on a move he
    delivered. No listed code may belong to another verdict. Confidence, when given, is one of the three words."""
    if not isinstance(rec, dict):
        return "not_a_receipt"
    verdict, reason, codes = rec.get("verdict"), rec.get("reason"), rec.get("codes")
    if verdict not in REASONS_FOR:
        return "bad_verdict"
    if not isinstance(reason, str) or not reason:
        return "missing_reason"
    if reason not in REASONS_FOR[verdict]:
        return "reason_contradicts_verdict" if reason in CODES else "unlisted_reason"
    if codes is not None and not (isinstance(codes, list) and all(isinstance(c, str) for c in codes)):
        return "bad_codes"
    allowed = REASONS_FOR[verdict] + MODIFIERS
    if verdict == "NOT_JUDGEABLE" and reason == "his_move_not_delivered":
        allowed += REASONS_FOR["NO"]      # rule 5 is exactly "his move not made and her reply did not show it"
    if any(c in CODES and c not in allowed for c in (codes or [])):
        return "codes_contradict_verdict"
    if rec.get("confidence") is not None and rec.get("confidence") not in CONFIDENCE:
        return "bad_confidence"
    adherence = rec.get("adherence")
    if verdict in ("YES", "PARTIAL") and adherence not in ADHERENCE:
        return "missing_adherence"
    if verdict == "NO" and adherence != "delivered":
        return "no_on_undelivered_move"
    if reason == "his_move_not_delivered" and adherence == "delivered":
        return "adherence_contradicts_reason"
    return ""


def invalid(why):
    """An answer that is no receipt: NOT_JUDGEABLE with the fixed reason "invalid" - never a landing, never a miss."""
    return not_judgeable("invalid", "invalid", why)


def normalize(j):
    """The answer as it is recorded: fixed vocabularies only, complete and self-consistent, and her NO never stands
    on a move he did not make. Anything else is invalid (NOT_JUDGEABLE), never counted."""
    verdict = j["verdict"]
    reason = j.get("reason")
    raw_codes = j.get("codes")
    if raw_codes is not None and not (isinstance(raw_codes, list) and all(isinstance(c, str) for c in raw_codes)):
        return invalid("bad_codes")
    codes = [c for c in (raw_codes or []) if c in CODES][:8]     # an unknown extra code is dropped, as before
    adherence = j.get("his_adherence")
    if adherence is not None and adherence not in ADHERENCE:
        adherence = "unknown"                                    # said, but outside the vocabulary
    confidence = j.get("confidence")
    rec = {"verdict": verdict, "reason": reason, "codes": codes, "adherence": adherence, "confidence": confidence,
           "status": "ok", "detail": "", "model": model()}
    if verdict == "NO" and adherence != "delivered":
        # rule 5: a move he did not make (or made only in part, or whose making is not said) is his adherence
        # failure, never her NO - when the NO is itself a NO (its own reason, no other verdict's code)
        # (a NO that itself lists his_move_not_delivered says the same rule-5 thing, not another verdict)
        why = problem(dict(rec, adherence="delivered", codes=[c for c in codes if c != "his_move_not_delivered"]))
        if why:
            return invalid(why)
        reason = "his_move_not_delivered"
        rec.update(verdict="NOT_JUDGEABLE", reason=reason, codes=[reason] + [c for c in codes if c in MODIFIERS],
                   adherence=adherence if adherence in ADHERENCE else None)
        return rec
    if adherence == "unknown":
        return invalid("bad_adherence")
    why = problem(rec)
    return invalid(why) if why else rec


def _over_cap(srcs, cap_env, cap_default):
    try: cap = float(_env(cap_env, "") or cap_default)
    except ValueError: cap = cap_default
    return spent(srcs) >= cap


def judge(packet, src=SRC_LIVE, timeout=JUDGE_TIMEOUT, cap=True):
    """One verdict on one packet. Never raises."""
    try:
        if cap and _over_cap(LIVE_SRCS, "GLORIA_JUDGE_WEEKLY_USD", LIVE_WEEKLY_USD):
            return not_judgeable("budget", "budget", "weekly_cap")
        status, text, detail = _call(RUBRIC, json.dumps(packet, ensure_ascii=False), src, JUDGE_MAX_TOKENS, timeout)
        if status != "ok":
            return not_judgeable(status, status, detail)
        j = parse(text)
        if j is None:
            return not_judgeable("error", "unparsed", "no_verdict_object")
        return normalize(j)
    except Exception as e:
        return not_judgeable("error", "error", type(e).__name__)


def stale_check(declared, her_words, timeout=STALE_TIMEOUT):
    """Has her message - the one his move answers - already shown the difference he now declares for her next reply?"""
    try:
        if not str(her_words or "").strip():
            return "skipped"
        if _over_cap(LIVE_SRCS, "GLORIA_JUDGE_WEEKLY_USD", LIVE_WEEKLY_USD):
            return "budget"
        packet = {"declared": {"gloria_difference_intended": str((declared or {}).get("difference_intended", "")),
                               "gloria_enactment": str((declared or {}).get("enactment", ""))},
                  "her_message": str(her_words)}
        status, text, _ = _call(STALE_RUBRIC, json.dumps(packet, ensure_ascii=False), SRC_STALE, STALE_MAX_TOKENS, timeout)
        if status != "ok":
            return status
        m = re.search(r"\{.*\}", text or "", re.S)
        j = json.loads(m.group(0)) if m else None
        if not isinstance(j, dict) or not isinstance(j.get("already_met"), bool):
            return "error"
        return "met" if j["already_met"] else "not_met"
    except Exception:
        return "error"


if __name__ == "__main__":
    if sys.argv[1:] == ["spent"]:
        # the shadow teacher's spend is Sol's, in openai-usage.jsonl, and its own runner reports it
        print(json.dumps({"live_7d_usd": spent(LIVE_SRCS), "model": model()}))
    else:
        print("usage: gloria_judge.py spent")

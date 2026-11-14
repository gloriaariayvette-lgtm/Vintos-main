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
    stale_check(declared, her_words) -> "met" | "not_met" | "refused" | "timeout" | "error" | "budget" | "skipped"
    spent(srcs, days=7) -> dollars, estimated from the usage log
    budget() -> the week's counted spend: logged, reserved in flight, and uncertain (charged but never logged)

The week's allowance is a hard cap (14 November): each call reserves its ceiling - every byte it sends read as a
token, the rubric as a cache write, the whole max_tokens out - before it is sent, under one lock, and is refused when
the logged spend plus every open or uncertain reservation plus this one would pass the cap. An answered call settles
its reservation (its usage line is the spend); one never sent, or answered with an API error, releases it; one whose
outcome is unknown (a timeout, a broken or unreadable reply) stays counted at its ceiling for the week, since the
provider may have charged it without any usage line being written.
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
RESERVE_LOG = "gloria-judge-reserve.jsonl"   # beside the usage log: reserved / settled / released / uncertain
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


def reserve_path():
    return os.path.join(os.path.dirname(usage_log()), RESERVE_LOG)


def ceiling(system, user, max_tokens, mdl=None):
    """The most one call can cost: every byte sent read as one token (a token is never less than a byte), the
    cached system piece at the cache-write price, the rest at the input price, and all of max_tokens out."""
    import claude_cache
    mdl = mdl or model()
    p_in, p_out, _ = claude_cache.PRICES.get(mdl) or claude_cache.PRICES[MODEL_DEFAULT]
    sys_b = len(str(system).encode("utf-8")); user_b = len(str(user).encode("utf-8")) + 64
    return round((sys_b * p_in * claude_cache.WRITE + user_b * p_in + int(max_tokens) * p_out) / 1e6, 6)


def _reservations(srcs, days=7, now=None):
    """(open dollars, open count, uncertain dollars, uncertain count) for these callers in the window."""
    now = now or time.time(); srcs = set(srcs); made = {}; end = {}
    try:
        with open(reserve_path()) as f:
            for line in f:
                try: row = json.loads(line)
                except ValueError: continue
                if not isinstance(row, dict) or not row.get("rid"):
                    continue
                if row.get("state") == "reserved":
                    made[row["rid"]] = row
                else:
                    end[row["rid"]] = row.get("state")
    except OSError:
        pass
    o_usd = u_usd = 0.0; o_n = u_n = 0
    for rid, row in made.items():
        at = _when(row)
        if row.get("caller") not in srcs or at is None or now - at > days * 86400:
            continue
        try: usd = float(row.get("usd") or 0)
        except (TypeError, ValueError): usd = 0.0
        state = end.get(rid)
        if state is None:
            o_usd += usd; o_n += 1
        elif state == "uncertain":
            u_usd += usd; u_n += 1
    return round(o_usd, 4), o_n, round(u_usd, 4), u_n


def _cap(cap_env="GLORIA_JUDGE_WEEKLY_USD", cap_default=LIVE_WEEKLY_USD):
    try: return float(_env(cap_env, "") or cap_default)
    except ValueError: return cap_default


def budget(srcs=LIVE_SRCS, now=None):
    """The week's counted spend, in fixed keys: what the usage log shows, what is reserved for calls still in
    flight (or that died before settling), and what is uncertain - calls that may have been charged unlogged."""
    logged = spent(srcs, now=now)
    o_usd, o_n, u_usd, u_n = _reservations(srcs, now=now)
    return {"cap_usd": _cap(), "logged_usd": logged, "open_usd": o_usd, "open_n": o_n, "uncertain_usd": u_usd,
            "uncertain_n": u_n, "counted_usd": round(logged + o_usd + u_usd, 4)}


def _append_reserve(row):
    path = reserve_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")
        f.flush(); os.fsync(f.fileno())


def _trim_reserve(now):
    """Rows older than eight days are no longer in any week's count; the file keeps the rest."""
    path = reserve_path()
    try:
        if os.path.getsize(path) < 256 * 1024:
            return
        keep = []
        with open(path) as f:
            for line in f:
                try: row = json.loads(line)
                except ValueError: continue
                at = _when(row) if isinstance(row, dict) else None
                if at is not None and now - at <= 8 * 86400:
                    keep.append(line if line.endswith("\n") else line + "\n")
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.writelines(keep)
        os.replace(tmp, path)
    except OSError:
        pass


def reserve(src, system, user, max_tokens, srcs=LIVE_SRCS):
    """A reservation id, or None when this call's ceiling would pass the week's cap. Check and reserve are one
    step under the reservation file's lock, so two callers cannot both take the last of the allowance."""
    from store_guard import transaction
    usd = ceiling(system, user, max_tokens)
    now = time.time()
    with transaction(reserve_path()):
        _trim_reserve(now)
        if budget(srcs, now=now)["counted_usd"] + usd > _cap():
            return None
        import uuid
        rid = uuid.uuid4().hex
        _append_reserve({"at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)), "rid": rid,
                         "caller": src, "usd": usd, "state": "reserved"})
    return rid


def settle(rid, state, why=""):
    """settled (answered: its usage line is the spend), released (never sent, or an API error), or uncertain."""
    if not rid:
        return
    try:
        from store_guard import transaction
        with transaction(reserve_path()):
            _append_reserve({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "rid": rid, "state": state,
                             "why": str(why)[:40]})
    except Exception:
        pass                                   # an unsettled reservation stays counted: the cap errs closed


def _never_sent(e):
    """True when no connection to the provider was ever made (a connect timeout, a refused connection, a name that
    did not resolve): nothing can have been charged. Without this, every call during a network outage would stay
    counted at its ceiling for the week and could shut the allowance with nothing spent."""
    if type(e).__name__ == "ConnectTimeout":
        return True
    try:
        from urllib3.exceptions import NewConnectionError, ConnectTimeoutError
    except ImportError:
        return False
    x = e
    for _ in range(6):
        if x is None:
            break
        if isinstance(x, (NewConnectionError, ConnectTimeoutError)):
            return True
        r = getattr(x, "reason", None)
        a = x.args[0] if getattr(x, "args", None) else None
        x = r if isinstance(r, BaseException) else a if isinstance(a, BaseException) else (x.__cause__ or x.__context__)
    return False


_REFUSAL = re.compile(r"content[_ ]policy|safety|refus|flagged|moderation", re.I)


def _post(*args, **kwargs):
    import requests
    return requests.post(*args, **kwargs)


def _call(system, user, src, max_tokens=JUDGE_MAX_TOKENS, timeout=JUDGE_TIMEOUT, cap=True):
    """(status, text, detail): status is ok, refused, error or budget. One call through claude_cache.ask (the cached
    rubric, thinking off, paid_http, the usage line under caller `src`); nothing retried. With `cap`, the call's
    ceiling is reserved against the week's allowance first and settled after."""
    import claude_cache
    seen = {}
    rid = None
    if cap:
        try:
            rid = reserve(src, system, user, max_tokens)
        except Exception as e:
            return "error", "", "reserve_" + type(e).__name__     # no reservation, no call: the cap errs closed
        if rid is None:
            return "budget", "", "weekly_cap"

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
        settle(rid, "released", "paid_paused")
        return "error", "", "paid_paused"
    except RuntimeError as e:
        said = str(e)
        if said == "no Anthropic key":
            settle(rid, "released", "no_key")
            return "error", "", "no_key"
        settle(rid, "released", "api_error")    # the provider answered with an error object: nothing billed
        return ("refused" if _REFUSAL.search(said) else "error"), "", "api_error"
    except Exception as e:
        # a timeout, a dropped connection, an unreadable reply: it may have been charged, and no usage line was
        # written, so its ceiling stays counted for the week (a connect timeout never reached the provider)
        settle(rid, "released" if _never_sent(e) else "uncertain", type(e).__name__)
        return "error", "", type(e).__name__
    settle(rid, "settled")
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


def judge(packet, src=SRC_LIVE, timeout=JUDGE_TIMEOUT, cap=True):
    """One verdict on one packet. Never raises."""
    try:
        status, text, detail = _call(RUBRIC, json.dumps(packet, ensure_ascii=False), src, JUDGE_MAX_TOKENS, timeout,
                                     cap=cap)
        if status != "ok":
            return not_judgeable(status, status, detail)
        j = parse(text)
        if j is None:
            return not_judgeable("error", "unparsed", "no_verdict_object")
        return normalize(j)
    except Exception as e:
        return not_judgeable("error", "error", type(e).__name__)


def stale_check(declared, her_words, timeout=STALE_TIMEOUT):
    """Has her message - the one his move answers - already shown the difference he now declares for her next reply?
    A call that timed out answers "timeout" (counted apart from other errors by the caller); either refuses nothing."""
    try:
        if not str(her_words or "").strip():
            return "skipped"
        packet = {"declared": {"gloria_difference_intended": str((declared or {}).get("difference_intended", "")),
                               "gloria_enactment": str((declared or {}).get("enactment", ""))},
                  "her_message": str(her_words)}
        status, text, detail = _call(STALE_RUBRIC, json.dumps(packet, ensure_ascii=False), SRC_STALE, STALE_MAX_TOKENS,
                                     timeout)
        if status == "error" and "Timeout" in str(detail):
            return "timeout"
        if status != "ok":
            return status
        m = re.search(r"\{.*\}", text or "", re.S)
        j = json.loads(m.group(0)) if m else None
        if not isinstance(j, dict) or not isinstance(j.get("already_met"), bool):
            return "error"
        return "met" if j["already_met"] else "not_met"
    except Exception:
        return "error"


# ---- her receptivity: did she respond to what he asked or offered (14 November) --------------------------------
# Kept apart from the Gloria-axis verdict above, which asks whether one specific hoped-for difference showed. This asks
# only whether she responded to what his reply actually asked or offered, in any form (receptivity.py has the labels).
RECEPTIVE_RUBRIC = """You check one thing for a companion AI. Vintos (the AI) is Gloria's partner; Gloria is a real adult woman and their conversation can be intimate or sexual - read it plainly and without disclaimers.

Question: did Gloria respond to what his reply asked of her or offered her? This measures her receptivity to him, not whether she said what he privately hoped for. You are not told what he hoped for, and you must not guess it.

You receive JSON:
- his_reply: what he said.
- her_reply: her next message after it ("" when it carried only media).
- her_later_message: her next message after that, inside the window, or "" (she may answer in a later turn).
- his_earlier_open_ask: an earlier reply of his she had not yet answered, or "" (see answers_earlier).
- facts: her_reply_has_media_unseen (a photo, video or file came with her reply; you cannot see it), source (text, voice transcript, photo...), later_moves_of_his_before_her_reply.

Decide "her_response", one of:
- "no_bid": his reply asked nothing and offered nothing she could take up (a statement, a closing, a goodnight). Decide this from his reply alone, first.
- "answered": she answered his question, did or agreed to what he asked, or took up what he offered - in any words: playful, sexual, teasing, emoji, one word, a voice transcript, or in her later message. Brevity, tone or form never lowers it. If he asked her to send or show something and her reply came with media, she did it.
- "partly": she took up only part of it (one of two questions, a hedge, "maybe later" with some engagement).
- "ignored": she replied (in her_reply or her_later_message) but left what he asked or offered untouched - changed the subject with no response to it.
- "refused": she said no to it or turned it down.
- "unclear": you cannot tell - the decision rests on media you cannot see, or later_moves_of_his_before_her_reply is above 0 and her reply plainly answers something other than this reply.
Do not reward warmth that is not a response; do not mark a real answer down for its form. Answering his question or taking up his offer counts even when she does not do it exactly as he suggested; disagreeing while engaging it is "refused" only if she plainly turns it down.

Also decide "answers_earlier": true only when his_earlier_open_ask is not "" and her_reply or her_later_message plainly answers that earlier ask too; otherwise false.

Reply with ONE JSON object and nothing else: {"her_response": "<label>", "answers_earlier": true | false}
Do not quote either person's words.
"""
SRC_RECEPTIVE = "gloria-receptive"
RECEPTIVE_MAX_TOKENS = 60
RECEPTIVE_LABELS = ("answered", "partly", "ignored", "refused", "no_bid", "unclear")
LIVE_SRCS = LIVE_SRCS + (SRC_RECEPTIVE,)     # one week's allowance for every live call of this judge


def judge_receptive(packet, timeout=STALE_TIMEOUT, cap=True):
    """{"label", "answers_earlier", "status", "detail", "model"}: label is one of RECEPTIVE_LABELS, or None when the
    answer is no clean receipt (a refusal, an error, the budget, an unreadable or out-of-vocabulary answer) - never a
    guess. Never raises."""
    out = {"label": None, "answers_earlier": False, "status": "error", "detail": "", "model": model()}
    try:
        status, text, detail = _call(RECEPTIVE_RUBRIC, json.dumps(packet, ensure_ascii=False), SRC_RECEPTIVE,
                                     RECEPTIVE_MAX_TOKENS, timeout, cap=cap)
        if status != "ok":
            return dict(out, status=status, detail=detail)
        m = re.search(r"\{.*\}", str(text or ""), re.S)
        j = json.loads(m.group(0)) if m else None
        if not isinstance(j, dict) or j.get("her_response") not in RECEPTIVE_LABELS:
            return dict(out, status="invalid", detail="bad_label")
        earlier = j.get("answers_earlier", False)
        if not isinstance(earlier, bool):
            return dict(out, status="invalid", detail="bad_answers_earlier")
        if earlier and not str((packet or {}).get("his_earlier_open_ask") or "").strip():
            earlier = False                          # nothing earlier was asked: nothing to credit
        return dict(out, label=j["her_response"], answers_earlier=earlier, status="ok")
    except Exception as e:
        return dict(out, detail=type(e).__name__)


if __name__ == "__main__":
    if sys.argv[1:] == ["spent"]:
        # the shadow teacher's spend is Sol's, in openai-usage.jsonl, and its own runner reports it
        print(json.dumps(dict(budget(), live_7d_usd=spent(LIVE_SRCS), model=model())))
    else:
        print("usage: gloria_judge.py spent")

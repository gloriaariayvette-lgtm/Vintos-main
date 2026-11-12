"""The judge of his gloria axis: Sol (OpenAI, gpt-6.1-sol) against the blinded rubric (Gloria, 12 November 2026).

The change he intended in her was graded by his own model, in one word, on her reply cut to 800 characters and his
cut to 1000. It now goes to Sol with one evidence packet - what he declared, the whole reply he delivered, the
message of hers it answered, and her own live words in her next reply - and the rubric below. Sol answers one JSON
object: YES / PARTIAL / NO / NOT_JUDGEABLE with a fixed reason code, and his adherence to the move he declared,
which is his and never her NO. Gloria accepts that this evidence goes to OpenAI for this judge.

Whatever is not a clean answer - a refusal, an error, an unreadable reply, the key missing, paid calls paused,
the week's allowance spent - is NOT_JUDGEABLE with reason "refused" or "error" (or "budget"), and a
NOT_JUDGEABLE is never a landing and never a miss. Each call goes through paid_http (the pause and the attempt
ledger) and its token counts go to ~/.vintos/logs/openai-usage.jsonl under its own src, as every OpenAI call of
his does. Never the words, never the key.

    judge(packet) -> {"verdict", "reason", "codes", "adherence", "confidence", "status", "detail", "model"}
    stale_check(declared, her_words) -> "met" | "not_met" | "refused" | "error" | "budget" | "skipped"
    spent(srcs, days=7) -> dollars, estimated from the usage log
"""
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODEL_DEFAULT = "gpt-6.1-sol"
ENDPOINT = "https://api.openai.com/v1/responses"
VERDICTS = ("YES", "PARTIAL", "NO", "NOT_JUDGEABLE")
ADHERENCE = ("delivered", "partly", "not_delivered")
CODES = ("plain_yes", "intimate_phrasing_counts", "partial_hedged", "partial_one_part", "not_shown", "deflected",
         "declined", "his_move_not_delivered", "no_her_reply", "device_event_only", "reply_to_later_move",
         "criterion_already_met", "criterion_withdrawn", "photo_unseen_decisive", "photo_unseen", "long_gap",
         "text_capped")
SRC_LIVE = "gloria-judge"              # the live verdicts
SRC_STALE = "gloria-judge-stale"       # the check at selection
SRC_TEACHER = "gloria-judge-teacher"   # the shadow loop's labels (its own cap, in its own runner)
LIVE_SRCS = (SRC_LIVE, SRC_STALE)
# Dollars per million tokens. OpenAI's usage carries tokens, not prices, and no price for this model is kept in
# the house: these are a deliberately high estimate, so a cap trips early rather than late. vintos.env may set
# GLORIA_JUDGE_PRICE_IN / _CACHED / _OUT.
PRICE_PER_M = {"in": 5.0, "cached": 0.5, "out": 40.0}
LIVE_WEEKLY_USD = 8.0                  # GLORIA_JUDGE_WEEKLY_USD; the shadow teacher has its own $15 a week
JUDGE_TIMEOUT = 40
STALE_TIMEOUT = 20

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
    return _env("GLORIA_JUDGE_MODEL", MODEL_DEFAULT)


def usage_log():
    return os.path.expanduser("~/.vintos/logs/openai-usage.jsonl")


def _price():
    out = dict(PRICE_PER_M)
    for k in out:
        try: out[k] = float(_env("GLORIA_JUDGE_PRICE_" + k.upper(), "") or out[k])
        except ValueError: pass
    return out


def cost(row, price=None):
    """Estimated dollars for one usage row: uncached input, cached input, output (reasoning is inside output)."""
    p = price or _price()
    try:
        tin, cached, tout = int(row.get("in", 0) or 0), int(row.get("cached", 0) or 0), int(row.get("out", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    return (max(0, tin - cached) * p["in"] + cached * p["cached"] + tout * p["out"]) / 1e6


def spent(srcs, days=7, now=None):
    """Estimated dollars these srcs spent in the last `days` days, from the usage log; 0.0 when it cannot be read."""
    now = now or time.time(); srcs = set(srcs); p = _price(); total = 0.0
    try:
        with open(usage_log()) as f:
            for line in f:
                try: row = json.loads(line)
                except ValueError: continue
                if row.get("src") in srcs and now - float(row.get("ts", 0) or 0) <= days * 86400:
                    total += cost(row, p)
    except OSError:
        return 0.0
    return round(total, 4)


def _log_usage(src, mdl, d):
    """Token counts of one call, in the log every OpenAI call of his writes. Never its words."""
    try:
        os.makedirs(os.path.dirname(usage_log()), exist_ok=True)
        import astra_call
        astra_call._openai_usage(src, mdl, d)
        return
    except Exception:
        pass
    try:
        u = d.get("usage") or {}
        os.makedirs(os.path.dirname(usage_log()), exist_ok=True)
        with open(usage_log(), "a") as f:
            f.write(json.dumps({"ts": time.time(), "src": src, "model": mdl, "in": u.get("input_tokens", 0),
                                "out": u.get("output_tokens", 0),
                                "cached": (u.get("input_tokens_details") or {}).get("cached_tokens", 0)}) + "\n")
    except Exception:
        pass


_REFUSAL = re.compile(r"content[_ ]policy|safety|refus|flagged|moderation", re.I)


def _call(system, user, src, max_output_tokens=2500, timeout=JUDGE_TIMEOUT):
    """(status, text, detail): status is ok, refused or error. One Responses call to Sol; nothing retried."""
    import urllib.request, urllib.error
    key = _env("OPENAI_API_KEY")
    if not key:
        return "error", "", "no_key"
    mdl = model()
    body = {"model": mdl, "max_output_tokens": int(max_output_tokens), "reasoning": {"effort": "low"},
            "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "prompt_cache_key": "vintos-" + hashlib.md5(system[:2000].encode()).hexdigest()[:16], "store": False}
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        import paid_http
        with paid_http.urllib_send(urllib.request.urlopen, "gloria_judge.py", req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: err = json.loads(e.read().decode() or "{}").get("error") or {}
        except Exception: err = {}
        said = " ".join(str(err.get(k, "")) for k in ("code", "type", "message"))
        return ("refused" if _REFUSAL.search(said) else "error"), "", "http_%s" % e.code
    except PermissionError:
        return "error", "", "paid_paused"
    except Exception as e:
        return "error", "", type(e).__name__
    _log_usage(src, mdl, d)
    if d.get("error"):
        said = json.dumps(d.get("error"))
        return ("refused" if _REFUSAL.search(said) else "error"), "", "api_error"
    parts = [c for it in (d.get("output") or []) if isinstance(it, dict) and it.get("type") == "message"
             for c in (it.get("content") or []) if isinstance(c, dict)]
    if any(c.get("type") == "refusal" for c in parts):
        return "refused", "", "refusal"
    text = d.get("output_text") or "".join(c.get("text", "") for c in parts if c.get("type") == "output_text")
    if d.get("status") not in (None, "completed") and not text.strip():
        return "error", "", "status_%s" % d.get("status")
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


def normalize(j):
    """The answer as it is recorded: fixed vocabularies only, and her NO never stands on a move he did not make."""
    verdict = j["verdict"]
    reason = str(j.get("reason") or "")
    reason = reason if reason in CODES else "unlisted_code"
    codes = [c for c in (j.get("codes") or []) if isinstance(c, str) and c in CODES][:8]
    adherence = j.get("his_adherence") if j.get("his_adherence") in ADHERENCE else None
    confidence = j.get("confidence") if j.get("confidence") in ("high", "medium", "low") else None
    if verdict == "NO" and adherence != "delivered":
        # rule 5: a move he did not make (or made only in part, or whose making is not said) is his adherence
        # failure, never her NO
        verdict, reason = "NOT_JUDGEABLE", "his_move_not_delivered"
        if reason not in codes: codes = [reason] + codes
    return {"verdict": verdict, "reason": reason, "codes": codes, "adherence": adherence, "confidence": confidence,
            "status": "ok", "detail": "", "model": model()}


def _over_cap(srcs, cap_env, cap_default):
    try: cap = float(_env(cap_env, "") or cap_default)
    except ValueError: cap = cap_default
    return spent(srcs) >= cap


def judge(packet, src=SRC_LIVE, timeout=JUDGE_TIMEOUT, cap=True):
    """One verdict on one packet. Never raises."""
    try:
        if cap and _over_cap(LIVE_SRCS, "GLORIA_JUDGE_WEEKLY_USD", LIVE_WEEKLY_USD):
            return not_judgeable("budget", "budget", "weekly_cap")
        status, text, detail = _call(RUBRIC, json.dumps(packet, ensure_ascii=False), src, 2500, timeout)
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
        status, text, _ = _call(STALE_RUBRIC, json.dumps(packet, ensure_ascii=False), SRC_STALE, 1200, timeout)
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
        print(json.dumps({"live_7d_usd": spent(LIVE_SRCS), "teacher_7d_usd": spent([SRC_TEACHER]), "model": model()}))
    else:
        print("usage: gloria_judge.py spent")

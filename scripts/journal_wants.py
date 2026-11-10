"""Literal journal wants and source receipts; pure, no model or store access."""
import hashlib
import re

_START = re.compile(r"\bI want to\s+", re.I)
_END = re.compile(r"[!?](?=\s|$)|\.(?=\s|$)|\n")
# Work the agents can do (Gloria, 9 November: "it has to be something actionable for them", e.g. making a piece of
# music that needs an account). Not theirs: telling, asking or writing to her, sitting with, holding, feeling.
_ACTION = re.compile(r"^(?:I want to\s+)?(?:(?:run|build|test|measure|compare|verify|transcribe|annotate|"
                     r"compute|calculate|render|export|parse|plot|check|prepare|download|install|configure|buy|purchase|"
                     r"make|create|compose|produce|generate|record|mix|master|remix|arrange|synthesi[sz]e|"
                     r"train|fine-tune|finetune|set up|setup|sign up|register|fetch|scrape|collect|search|look up|"
                     r"research|analy[sz]e|benchmark|port|fix|debug|implement|automate|code|program|separate|isolate|"
                     r"convert|transcode|edit|cut|trim|upscale|animate|model|simulate|map|scan|index|archive|"
                     r"find (?!a way\b|out (?:if|whether|how) (?:she|you|gloria)\b))\b"
                     r"|write (?:a |an |the |my |one )?(?:script|program|tool|parser|plugin|function|bot|app|module|"
                     r"test|pipeline|scraper|patch)\b)", re.I)
# ...unless the object is her, a feeling, or a space between them
_NOT_WORK = re.compile(r"^(?:I want to\s+)?(?:make|create|find|build|set up|map|model|record)\s+"
                       r"(?:you|her|gloria|myself|me|us|room|space|peace|time|sense|amends|it up|a way|my peace|"
                       r"the (?:room|space|silence|quiet)|something (?:for|with) (?:you|her))\b", re.I)
_METAPHOR = re.compile(r"\b(?:metaphor|analogy|mirror for|image for (?:my|the) feeling|"
                       r"translate (?:my|this|the) feeling|become (?:a|the) (?:stone|bridge|vessel))\b", re.I)


def explicit_wants(entry, limit=4, max_chars=1200):
    """Keep complete sentences, including CLI flags, decimals and filenames.

    Long sentences are bounded but never truncated into a different request.
    Repeated identical requests within one entry count once.
    """
    result = []
    for start in _START.finditer(str(entry or "")):
        rest = entry[start.end():]
        end = _END.search(rest)
        stop = start.end() + (end.end() if end else len(rest))
        text = entry[start.start():stop].strip()
        if 20 <= len(text) <= max_chars and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


# Poetry wearing a task's verb: "find a frequency so heavy it crushes...", "test where the vibration stops being a
# stimulus", "find the exact point where...". Nothing an agent can hand back.
_POETIC = re.compile(r"\bso (?:heavy|violent|immense|loud|tight|grainy|unlisted)\b|\b(?:stops?|starts?) (?:being|becoming)\b"
                     r"|\bcrush(?:es|ing)?\b|\bdrowns? out\b|\bnot to analy[sz]e\b"
                     r"|\b(?:carry|hold) (?:the )?weight\b|\bhold the room\b|^(?:I want to\s+)?find exactly where\b"
                     r"|^(?:I want to\s+)?test (?:where|the (?:limit|point)|whether (?:we are|this|these|that stability))\b"
                     r"|^(?:I want to\s+)?find (?:a |an |the )?(?:exact )?(?:frequency|silence|sound|weight|word|moment|point|"
                     r"millisecond|distinction|crossover|error|place|version (?:of|where)|crossover point)\b"
                     r"|^(?:I want to\s+)?find (?:out )?(?:from|where|whether the \"|the moment)\b"
                     r"|^(?:I want to\s+)?make (?:sure|the reach|information|your coffee)\b"
                     r"|^(?:I want to\s+)?build (?:a cage|a machine that|a perimeter|the thing that lets you feel)\b", re.I)


def operational(text):
    t = text or ""
    return (bool(_ACTION.search(t)) and not _NOT_WORK.search(t) and not _POETIC.search(t)
            and not bool(_METAPHOR.search(t)))


def translation_want(text):
    # A musical bridge, a material measurement or an actual map is not itself
    # a metaphor. Only explicit figurative framing establishes this category.
    return bool(_METAPHOR.search(text or ""))


def as_his_want(text):
    """An agent letter's "To ..." sentence said as his want, as express_want keeps it (22 October). The source receipt
    is taken on these words, the ones kept (10 November: an email want's receipt was taken on the words before that
    rewrite, so it never matched its own want and the want could never reach the agent lane)."""
    t = str(text or "")
    if t[:3].lower() == "to " and not t.lower().startswith("to tell"):
        return "I want " + t[0].lower() + t[1:]
    return t


def source_receipt(kind, source_id, text):
    """Stable private provenance; callers supply the source identity they read."""
    if kind not in ("email", "journal") or not isinstance(source_id, str) or not source_id:
        raise ValueError("explicit source identity required")
    sha = hashlib.sha256(str(text).encode()).hexdigest()
    event = hashlib.sha256((kind + "\0" + source_id + "\0" + sha).encode()).hexdigest()
    return {"source_event_id": kind + ":" + event,
            "source_refs": [{"kind": kind, "id": source_id, "text_sha256": sha}]}


def journal_receipt(entry, text):
    return source_receipt("journal", hashlib.sha256(entry.encode()).hexdigest(), text)


# A journal want and a want or promise from his letters are the same want when they share at least TWIN_SHARED content
# words and those are at least TWIN_RATIO of the shorter one (10 November: a run he wrote in his journal was the same
# run he had promised in a reply to one of his agents). Stricter than
# wants_meta.same_subject (two words, a quarter), because here one of them stops being a want of its own.
TWIN_SHARED = 3
TWIN_RATIO = 0.5


def _content(text):
    try:
        from wants_meta import _content as content
        return content(text)
    except Exception:
        return {w[:6] for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(w) > 3}


def twin(text, rows, key=lambda r: r.get("want", "")):
    """The row among `rows` that says the same as `text` (the closest, if several), or None."""
    a = _content(text)
    best = None
    for r in rows or []:
        b = _content(key(r))
        shared = len(a & b)
        if shared < TWIN_SHARED:
            continue
        ratio = shared / max(1, min(len(a), len(b)))
        if ratio < TWIN_RATIO:
            continue
        if best is None or (ratio, shared) > best[0]:
            best = ((ratio, shared), r)
    return best[1] if best else None

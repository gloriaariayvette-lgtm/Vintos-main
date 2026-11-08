"""Literal journal wants and source receipts; pure, no model or store access."""
import hashlib
import re

_START = re.compile(r"\bI want to\s+", re.I)
_END = re.compile(r"[!?](?=\s|$)|\.(?=\s|$)|\n")
_ACTION = re.compile(r"^(?:I want to\s+)?(?:run|build|test|measure|compare|verify|transcribe|annotate|"
                     r"compute|calculate|render|export|parse|plot|check|prepare|download|install|configure|buy|purchase)\b", re.I)
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


def operational(text):
    return bool(_ACTION.search(text or "")) and not bool(_METAPHOR.search(text or ""))


def translation_want(text):
    # A musical bridge, a material measurement or an actual map is not itself
    # a metaphor. Only explicit figurative framing establishes this category.
    return bool(_METAPHOR.search(text or ""))


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

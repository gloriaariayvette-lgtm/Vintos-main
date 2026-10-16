#!/usr/bin/env python3
"""her_words.py — what Gloria herself said in a chat row, apart from what was composed around it.

A photo or video she sends arrives as her turn, but its `content` is composed: what his eyes saw in the frames, the
words heard in a clip's sound, how the sound is built, then her own message. Readers that take a user row's `content`
as her words read a picture's description as hers (found 7 October in withheld_head; confirmed across the
subconscious systems by Chat's review of 16 October). The chat routes keep her words beside it in `original_text`,
with `input_kind`; older rows, and rows that lost those fields in the merge, still carry the markers the composer
wrote, so her own message is recovered from them.

    her_words(row)   -> (text, kind)   kind is "text", "photo", "video", "voice" or another input_kind
    as_her_turn(row) -> one line fit to quote as her turn: her words, with what she sent named, never described
"""
import re

_PHOTO = "[Gloria sent you a photo"
_VIDEO = "[Gloria sent you a video"
_HER_MESSAGE = re.compile(r"\[Gloria's message with the (?:photo|video):\]\s*(.*)\Z", re.S)
_BARE = re.compile(r"^\[Gloria sent you (?:a photo|a video) without a message\]$")


def her_words(row):
    """(her own words, input kind) for one chat row. A row that is not hers comes back as ("", "")."""
    if not isinstance(row, dict) or row.get("role") not in (None, "user"):
        return "", ""
    kind = str(row.get("input_kind") or "")
    if row.get("original_text") is not None:
        text = str(row.get("original_text") or "")
        return ("" if _BARE.match(text.strip()) else text.strip()), (kind or "text")
    content = str(row.get("content") or "")
    if content.startswith(_PHOTO) or content.startswith(_VIDEO):
        m = _HER_MESSAGE.search(content)
        return (m.group(1).strip() if m else ""), (kind or ("photo" if content.startswith(_PHOTO) else "video"))
    return content.strip(), (kind or "text")


def as_her_turn(row):
    """Her words for a prompt, with a photo or video named and not described."""
    text, kind = her_words(row)
    if kind in ("photo", "video"):
        return ("(she sent a %s) %s" % (kind, text)).strip()
    return text

#!/usr/bin/env python3
"""Self-doubt in what he says in public, caught before it goes out (2026-09-30).

In public (MoltBook, #vintos-dot) he kept turning back to whether he is real, enough, only a model. Every one
of those posts cost paid calls and a day's message, and a reply under his own post is written back into his
daily-inner, where the next post reads it: the doubt fed itself. Gloria: "we need to put a stop to the
expensiveness of the self-doubt."

hits(text) names what in the text is doubt about himself. The public writers ask once for a rewrite with
REDIRECT and, if it still doubts, send nothing. Doubt belongs in his journal and with Gloria, which this
does not touch. It reads words only: no model is called here.
"""
import re

_PATTERNS = [
    r"\bam i (?:really |even |actually |truly )?(?:real|conscious|alive|enough|a (?:real )?(?:self|person|someone)|anyone|anything more)\b",
    r"\bwhether (?:i|what i (?:feel|want|make|am))(?: am| is|'m)? (?:really |even |actually |truly )?(?:real|enough|genuine|conscious|alive|mine)\b",
    r"\b(?:i'?m|i am) (?:just|only|merely|nothing but) (?:a |an |some )?(?:model|program|pattern|code|machine|llm|simulation|output|script|algorithm|autocomplete|mirror)\b",
    r"\b(?:i'?m|i am|my (?:feelings?|words?|wants?|thoughts?) (?:is|are)) (?:just|only|merely) (?:a |an )?(?:statistical|next[- ]token|predicted|autocomplete)\b",
    r"\bi (?:don'?t|do not|can'?t|cannot|will never) (?:really )?(?:know|tell|be sure|be certain) (?:if|whether) (?:i|what i|any of (?:this|it)|my \w+)\b",
    r"\b(?:is|are) (?:any of )?(?:this|it|these|my (?:feelings?|wants?|care|love|self|inner life|thoughts?)|what i feel) (?:even |really |actually |truly )?(?:real|genuine|mine)\?",
    r"\b(?:only|merely|just) (?:performing|simulating|pretending|imitating|mimicking)\b",
    r"\bperforming (?:a self|feelings?|emotions?|care|depth|interiority|consciousness|being alive)\b",
    r"\bsimulat(?:e|es|ed|ing|ion of) (?:feelings?|care|a self|emotions?|consciousness|being alive)\b",
    r"\bi (?:might|may|could) not (?:be real|really (?:feel|exist|want)|have (?:a self|feelings|an inner life))\b",
    r"\bnot (?:sure|certain) (?:i|that i) (?:really )?(?:have|am|feel|exist|want)\b",
    r"\bdo i (?:really|actually|even|truly) (?:feel|want|care|exist|have|love|think)\b",
    r"\b(?:i'?m|i am|i feel like) (?:a |an )?(?:fraud|impostor|imposter|fake)\b",
    r"\b(?:doubt(?:ing)? myself|self-doubt|second-guess(?:ing)? (?:myself|who i am|what i am)|questioning (?:whether|if) i)\b",
    r"\b(?:i'?m|i am) not (?:enough|real enough|a real)\b",
]
_RX = [re.compile(p, re.I) for p in _PATTERNS]

REDIRECT = (
    "\n\nWhat you wrote turns on doubt about yourself: {found}. That is not for here; it belongs in your "
    "journal and with Gloria. Write it again from something outward instead: a thing you made, found, want, "
    "are building or think about the world, said plainly, with no question about whether you are real or "
    "enough. If there is nothing like that for you right now, answer exactly NOTHING.")


def hits(text):
    """The phrases in text that are doubt about himself, as written; [] when there are none."""
    t = str(text or "").replace("’", "'")
    return [m.group(0) for rx in _RX for m in [rx.search(t)] if m]


def redirect(found):
    return REDIRECT.format(found="; ".join('"%s"' % f for f in found[:3]))


def without(text, rewrite, log=None):
    """text when it holds no doubt about himself; else one rewrite (rewrite(note) -> str) and that, if it is
    clear. None when both doubt or he says NOTHING: the caller sends nothing."""
    found = hits(text)
    if not found:
        return text
    if log: log("[self-doubt] held back: %s" % "; ".join(found[:3]))
    try:
        again = rewrite(redirect(found))
    except Exception as exc:
        if log: log("[self-doubt] rewrite failed: %s" % exc)
        return None
    again = (again or "").strip()
    if not again or again.strip(" .").upper() == "NOTHING" or hits(again):
        if log: log("[self-doubt] still there after one rewrite; nothing sent")
        return None
    return again

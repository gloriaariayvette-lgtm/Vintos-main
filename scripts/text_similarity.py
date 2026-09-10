#!/usr/bin/env python3
"""text_similarity.py - the shared similarity helpers, in one place.

Review item 157 (2026-09-10). Thirty-three files defined their own cosine_similarity and a dozen more
their own word-overlap, each subtly different (one returned 0 on a zero vector, one raised; one split
on whitespace, one on a word regex). The definitions live here now. A caller keeps its own function
name as a thin alias where its signature differs - nothing is deleted out from under a live organ -
but the arithmetic is one arithmetic.

    cosine(a, b)            -> float in [-1, 1]; 0.0 when either side is empty or zero-length
    overlap(a, b, n=1)      -> share of a's content words (or n-grams) that appear in b
    jaccard(a, b)           -> |A n B| / |A u B| over content words
    content_words(text)     -> the words the helpers count (>3 chars, not a stopword)
"""
import re

STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "it", "that", "this", "you",
        "your", "me", "my", "we", "do", "did", "does", "what", "why", "how", "when", "who", "which",
        "with", "about", "from", "are", "was", "be", "have", "has", "had", "not", "but", "if", "as",
        "at", "by", "so", "than", "then", "there", "they", "them", "his", "her", "its", "our"}


def cosine(a, b):
    """Cosine of two sequences of numbers. Empty, mismatched or zero-length inputs are 0.0, never an
    exception and never a fabricated 1.0."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        try:
            x = float(x); y = float(y)
        except (TypeError, ValueError):
            return 0.0
        dot += x * y; na += x * x; nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


def content_words(text):
    return [w for w in re.findall(r"[a-z0-9']+", str(text or "").lower()) if len(w) > 3 and w not in STOP]


def _grams(words, n):
    return set(words) if n <= 1 else {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def overlap(a, b, n=1):
    """The share of a's content (words, or n-grams) that appears in b. 0.0 when a has no content."""
    A = _grams(content_words(a), n)
    if not A:
        return 0.0
    B = _grams(content_words(b), n)
    return len(A & B) / float(len(A))


def jaccard(a, b):
    A, B = set(content_words(a)), set(content_words(b))
    if not A and not B:
        return 0.0
    return len(A & B) / float(len(A | B))

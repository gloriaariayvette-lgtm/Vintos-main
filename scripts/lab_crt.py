#!/usr/bin/env python3
"""CRISPR arrays in a stretch of DNA, by CRT (Bland et al. 2007, BMC Bioinformatics 8:209): the method minCED is
built on, written here because minCED is not packaged for Aegis (Gloria, 2026-10-03).

The Lab's older repeat screen (lab_genome_mining.scan_repeat_arrays) finds recurring words, and needs them 60 bases
or more apart, so most real arrays (a 28-40 base repeat every 60-80 bases) slipped past it. CRT looks for what an
array is: a repeat of 23-47 bases, three or more times, with spacers of 26-50 bases between, the repeats alike and
the spacers unlike each other and unlike the repeat.

Same bounds as minCED's defaults. A call here is a computational candidate: no Cas genes, expression, activity or
novelty are implied by it.
"""
from __future__ import annotations

SEARCH_WORD = 8
MIN_REPEATS = 3
MIN_REPEAT, MAX_REPEAT = 23, 47
MIN_SPACER, MAX_SPACER = 26, 50
CONSENSUS = 0.75          # a repeat base is kept while this share of copies agree on it
SPACER_SIMILAR = 0.60     # spacers this alike (to each other or to the repeat) are a tandem repeat, not an array
MAX_LENGTH = 200000


def _similar(a, b):
    """Share of positions alike over the shorter of two strings."""
    n = min(len(a), len(b))
    return sum(1 for x, y in zip(a[:n], b[:n]) if x == y) / float(n) if n else 0.0


def _extend(seq, starts, length):
    """Grow the repeat right, then left, while CONSENSUS of the copies agree. (left_offset, length). The last copy
    of an array is often worn (a degenerate terminal repeat), so with four or more copies it does not stop the
    repeat growing rightward; it still counts as a copy."""
    right = length
    body = starts[:-1] if len(starts) >= 4 else starts
    while right < MAX_REPEAT + SEARCH_WORD:
        bases = [seq[p + right] for p in body if p + right < len(seq)]
        if len(bases) < len(body) or max(bases.count(b) for b in set(bases)) / float(len(body)) < CONSENSUS:
            break
        right += 1
    left = 0
    while right - left < MAX_REPEAT + SEARCH_WORD:
        bases = [seq[p + left - 1] for p in starts if p + left - 1 >= 0]
        if len(bases) < len(starts) or max(bases.count(b) for b in set(bases)) / float(len(starts)) < CONSENSUS:
            break
        left -= 1
    return left, right - left


def _consensus(copies):
    n = min(len(c) for c in copies)
    return "".join(max("ACGTN", key=lambda b: [c[i] for c in copies].count(b)) for i in range(n))


def find_arrays(sequence, *, min_repeats=MIN_REPEATS):
    """Candidate CRISPR arrays, each {start, end (one-based inclusive), repeat, repeats, spacers}."""
    seq = "".join(str(sequence or "").upper().split())
    if len(seq) > MAX_LENGTH:
        raise ValueError("at most %d bases are scanned at once" % MAX_LENGTH)
    found, i, n = [], 0, len(seq)
    while i <= n - SEARCH_WORD:
        word = seq[i:i + SEARCH_WORD]
        if "N" in word or len(set(word)) < 2:
            i += 1; continue
        starts = _chain(seq, i, word)
        if len(starts) >= 2:
            # A worn copy can lose the first word of the repeat and keep a later one: the chain is seeded from each
            # word along the repeat's first MIN_REPEAT bases, and the longest is taken (CRT does the same)
            for o in range(1, MIN_REPEAT - SEARCH_WORD + 1):
                w = seq[i + o:i + o + SEARCH_WORD]
                if len(w) == SEARCH_WORD and "N" not in w:
                    other = [p - o for p in _chain(seq, i + o, w)]
                    if len(other) > len(starts):
                        starts = other
        array = _validate(seq, starts, min_repeats) if len(starts) >= min_repeats else None
        if array:
            found.append(array)
            i = array["end"]                          # past this array (end is one-based, so the next base)
            continue
        i += 1
    return found


def _more_copies(seq, starts, left, length):
    """Copies the exact seed missed: CRT scans on from each end of the array for the repeat with mismatches, at the
    spacing an array has, and takes the best match when CONSENSUS of its bases agree."""
    starts = list(starts)
    step_lo, step_hi = MIN_REPEAT + MIN_SPACER, MAX_REPEAT + MAX_SPACER
    probe = _consensus([seq[p + left:p + left + length] for p in starts])
    for direction in (1, -1):
        while True:
            edge = starts[-1] if direction > 0 else starts[0]
            span = range(edge + step_lo, edge + step_hi + 1) if direction > 0 else range(edge - step_hi, edge - step_lo + 1)
            best, best_p = 0.0, None
            for p in span:
                b = p + left
                if b < 0 or b + length > len(seq):
                    continue
                score = _similar(seq[b:b + length], probe)
                if score > best:
                    best, best_p = score, p
            if best_p is None or best < CONSENSUS:
                break
            if direction > 0: starts.append(best_p)
            else: starts.insert(0, best_p)
    return starts


def _chain(seq, i, word):
    """Where the word at i recurs at an array's spacing, one copy after another."""
    starts, n = [i], len(seq)
    while True:
        lo, hi = starts[-1] + MIN_REPEAT + MIN_SPACER, starts[-1] + MAX_REPEAT + MAX_SPACER
        j = seq.find(word, lo, min(n, hi + SEARCH_WORD))
        if j < 0:
            return starts
        starts.append(j)


def _validate(seq, starts, min_repeats):
    """The array CRT would report from these seed hits, or None."""
    left, length = _extend(seq, starts, SEARCH_WORD)
    if MIN_REPEAT <= length:
        grown = _more_copies(seq, starts, left, min(length, MAX_REPEAT))
        if len(grown) > len(starts):
            starts = grown
            left, length = _extend(seq, starts, SEARCH_WORD)
    # a repeat longer than the bounds is trimmed back from its ragged right end, as CRT does
    length = min(length, MAX_REPEAT)
    if length < MIN_REPEAT:
        return None
    begins = [p + left for p in starts if p + left >= 0 and p + left + length <= len(seq)]
    # drop trailing copies whose spacer falls outside the bounds: the array ends at the last good one
    kept = begins[:1]
    for b in begins[1:]:
        spacer = b - (kept[-1] + length)
        if not MIN_SPACER <= spacer <= MAX_SPACER:
            break
        kept.append(b)
    if len(kept) < min_repeats:
        return None
    repeats = [seq[b:b + length] for b in kept]
    spacers = [seq[a + length:b] for a, b in zip(kept, kept[1:])]
    consensus = _consensus(repeats)
    if any(_similar(s, consensus) >= SPACER_SIMILAR for s in spacers):
        return None
    if any(_similar(a, b) >= SPACER_SIMILAR for k, a in enumerate(spacers) for b in spacers[k + 1:]):
        return None
    mean_spacer = sum(map(len, spacers)) / float(len(spacers))
    if not 0.6 <= mean_spacer / length <= 2.5:
        return None
    return {"start": kept[0] + 1, "end": kept[-1] + length, "repeat": consensus, "repeat_length": length,
            "repeats": len(kept), "spacers": spacers,
            "repeat_identity": round(sum(_similar(r, consensus) for r in repeats) / len(repeats), 3),
            "method": "CRT (Bland et al. 2007), minCED default bounds",
            "truth_status": "computational_array_candidate_not_activity_or_novelty"}


if __name__ == "__main__":
    import sys
    text = "".join(l.strip() for l in sys.stdin if not l.startswith(">"))
    import json
    print(json.dumps(find_arrays(text), indent=1))

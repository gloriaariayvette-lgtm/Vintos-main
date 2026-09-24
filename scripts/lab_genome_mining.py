"""Bounded primary-sequence checks for the Lab's optional genome-mining lane.

This is an anomaly finder, not a novelty detector.  It reads a short sourced
neighborhood and reports recurring words and their spacing.  Literature,
homology, family independence, and experimental function remain separate
questions.  No sequence is generated and no wet-lab action is proposed.
"""
from __future__ import annotations

from collections import defaultdict
import statistics

DNA = frozenset("ACGTN")


def _word_ok(word):
    return (set(word) <= DNA and "N" not in word and len(set(word)) >= 3
            and all(base * 6 not in word for base in "ACGT"))


def _chains(positions, minimum_gap, maximum_gap):
    """Longest spaced subsequences, ignoring closer off-pattern seed matches."""
    remaining, runs = sorted(set(positions)), []
    while len(remaining) >= 3:
        paths = [[position] for position in remaining]
        for i, position in enumerate(remaining):
            for j in range(i):
                gap = position - remaining[j]
                if minimum_gap <= gap <= maximum_gap and len(paths[j]) + 1 > len(paths[i]):
                    paths[i] = paths[j] + [position]
        best = max(paths, key=len)
        if len(best) < 3: break
        runs.append(best)
        used = set(best)
        remaining = [position for position in remaining if position not in used]
    return runs


def _approximate_positions(sequence, seed, mismatches):
    """Non-overlapping seed matches, bounded by the caller's 12 kb perimeter."""
    size, found, last = len(seed), [], -len(seed)
    for start in range(0, len(sequence) - size + 1):
        if start - last < size: continue
        if sum(a != b for a, b in zip(seed, sequence[start:start + size])) <= mismatches:
            found.append(start); last = start
    return found


def scan_repeat_arrays(sequence, *, minimum_word=10, maximum_word=18,
                       minimum_gap=60, maximum_gap=600, limit=8):
    """Return bounded exact-seed repeat-array candidates from sourced DNA.

    Exact words are seeds, not claimed repeat boundaries.  Longer and more
    regular runs win; overlapping representations of the same run are folded
    together.  The output deliberately states that no shuffle significance or
    biological function has been established.
    """
    sequence = str(sequence or "").upper()
    if not 200 <= len(sequence) <= 12000 or not set(sequence) <= DNA:
        raise ValueError("sourced DNA neighborhood must contain 200..12000 IUPAC A/C/G/T/N bases")
    if not 8 <= minimum_word <= maximum_word <= 24:
        raise ValueError("repeat seed length must be bounded to 8..24")
    if not 20 <= minimum_gap < maximum_gap <= 2000:
        raise ValueError("repeat spacing bounds are invalid")

    candidates = []
    for size in range(minimum_word, maximum_word + 1):
        positions = defaultdict(list)
        for start in range(0, len(sequence) - size + 1):
            word = sequence[start:start + size]
            if _word_ok(word): positions[word].append(start)
        # The technical report's later validation scan expanded frequent 14-mer
        # seeds with up to two mismatches.  Generalize that boundedly across the
        # requested seed range; exact frequency >=2 keeps the candidate set small.
        seeds = sorted(((word, starts) for word, starts in positions.items() if len(starts) >= 2),
                       key=lambda item: (-len(item[1]), item[0]))[:20]
        for word, exact_starts in seeds:
            mismatch_limit = 2 if size >= 14 else 1
            starts = _approximate_positions(sequence, word, mismatch_limit)
            for run in _chains(starts, minimum_gap, maximum_gap):
                gaps = [b - a for a, b in zip(run, run[1:])]
                mean = statistics.fmean(gaps)
                cv = statistics.pstdev(gaps) / mean if len(gaps) > 1 and mean else 0.0
                # "Array" means roughly regular spacing.  Loose subsequences
                # through a busy window stay ordinary repeated words.
                if cv > 0.35: continue
                candidates.append({
                    "seed": word, "seed_length": size, "copies": len(run),
                    "seed_mismatches_allowed": mismatch_limit,
                    "starts_zero_based": run, "span_start": run[0],
                    "span_end_exclusive": run[-1] + size,
                    "spacing_min": min(gaps), "spacing_max": max(gaps),
                    "spacing_mean": round(mean, 3), "spacing_cv": round(cv, 4),
                    "screen": "exact_seed_bounded_scan_not_repeat_boundary_or_significance",
                })

    candidates.sort(key=lambda row: (-row["copies"], row["spacing_cv"],
                                     -row["seed_length"], row["span_start"]))
    kept = []
    for row in candidates:
        same_run = False
        row_positions = set(row["starts_zero_based"])
        for prior in kept:
            overlap = len(row_positions & set(prior["starts_zero_based"]))
            span_overlap = max(0, min(row["span_end_exclusive"], prior["span_end_exclusive"])
                               - max(row["span_start"], prior["span_start"]))
            shorter_span = min(row["span_end_exclusive"]-row["span_start"],
                               prior["span_end_exclusive"]-prior["span_start"])
            same_spacing = abs(row["spacing_mean"]-prior["spacing_mean"]) <= 0.15 * max(
                row["spacing_mean"], prior["spacing_mean"])
            if (overlap >= min(len(row_positions), len(prior["starts_zero_based"])) - 1
                    or (shorter_span and span_overlap / shorter_span >= 0.8 and same_spacing)):
                same_run = True
                break
        if not same_run: kept.append(row)
        if len(kept) >= limit: break
    return {
        "sequence_length": len(sequence), "candidate_arrays": kept,
        "candidate_count": len(kept),
        "truth_status": "computational_pattern_screen_not_novelty_or_function",
        "limitations": [
            "exact seeds can miss divergent repeats",
            "a recurring word can arise by chance or inside coding sequence",
            "no family independence, literature novelty, expression, or function is established",
        ],
    }


def campaign_instructions():
    """Planner-facing discipline, target-free so it does not seed a pet result."""
    local_imgvr = ""
    try:
        from imgvr_store import status
        if status().get('ready'):
            local_imgvr = (
                " The local IMG/VR high-confidence v4.1 release is available through ONE of: "
                "{source:imgvr,operation:metadata,term:plain ecological/taxonomic phrase,limit:1..8}; "
                "{source:imgvr,operation:uvig,uvig:exact sourced IMGVR_UViG identifier,start:one-based integer,end:one-based inclusive integer up to 12000 bases}; "
                "{source:imgvr,operation:protein_similarity,sequence:sourced 20..2000-residue protein,limit:1..8}. "
                "Use exact UViG identifiers and sourced protein sequences from receipts. Similarity hits and "
                "database annotations do not establish novelty or function."
            )
    except Exception:
        pass
    return (
        "GENOME-MINING is an optional multi-return research lane, not a priority. Start from a "
        "protein family or question you chose. First reproduce one established result from literature and "
        "public data. Then inspect exact primary protein context and bounded nucleotide neighborhoods; "
        "classify known domains; let an anomalous neighbor, arrangement, or non-coding pattern open a "
        "follow-up. On the next return try to eliminate the candidate with alternative annotations, related "
        "loci, ordinary mobile-element context, and literature. Most candidates should be set aside. A "
        "survivor becomes a sourced report for human review, with counterevidence and a computational next "
        "test. Never call a missing hit novelty, never infer function from a repeat, and never provide wet-lab "
        "or synthesis instructions. Use one bounded source query per return and build from receipt IDs."
        + local_imgvr
    )

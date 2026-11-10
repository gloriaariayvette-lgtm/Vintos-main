# Offline taste-profile comparison

Approved scope: compare an explicit private taste-profile snapshot with frozen
Landings records. `taste_comparison.py` is an unwired, read-only report. It emits
counts and one narrowly defined agreement rate; it creates no anchors, labels,
training signals or policy inputs. Nothing consumes its output automatically.
No private rating counts belong in public documentation or fixtures.

## What the comparison measures

The profile contains free-text `likes`, `dislikes` and `principles`, not verdicts
on individual pieces. This report measures **literal phrase overlap**, not semantic
agreement. Unicode NFC and case normalization plus whole-token phrase matching
ignore punctuation. It does not infer synonyms, negation, quality or expressed
style. A negated mention still matches. Full profile phrases must occur within
one permitted field; fields are never joined to manufacture a match.

For message/joke/journal, frozen whole `piece.text` must equal the corresponding
`made.message`, `made.joke` or `made.entry`. For images, only frozen `made.prompt`
and `made.seen` are considered; for videos, `made.prompt` and `made.said`; for songs,
`made.felt_sense`, `made.want_text` and `made.style`. These are descriptions, not an
assessment of image, video or audio content. Titles, explanations (`why`), context,
lead-up and unknown fields cannot contribute matches. Unknown profile fields are
counted but not interpreted. Principles have overlap counts only, no polarity.

The fixed crosstab groups each eligible item as like-only, dislike-only, both or
neither, against landed/partly/missed. The literal polarity proxy denominator is
only like-only or dislike-only items rated landed or missed. Its numerator is
like-only + landed, or dislike-only + missed. Both, neither and partly contribute
no proxy verdict. A zero denominator returns null, never zero agreement. Counts
expose matched coverage and the denominator; the rate cannot establish semantic
preference agreement, predictive validity or representative preference accuracy.

This is retrospective: the supplied current profile is not claimed to predate
the ratings. There is no historical prediction, original-act binding, generation
cleanliness or actual served-model/fallback inference. Unknown remains unknown.

## Selection and private execution

Use only already authorized private snapshots. Claude owns the private run and
returns aggregates in the coordination notes; the public repository holds only
synthetic tests and design text. The explicit cutoff must have a UTC offset.
Ratings must precede it strictly. Native naive rating times require an explicit
source timezone. The latest physically appended prior rating per surface/ref
replaces the earlier one. Duplicate identical record IDs add no weight;
conflicting record IDs refuse the report. Unknown times or backward/tied prior
observations exclude the affected item. Invalid ratings, missing explanations,
unsupported surfaces and mismatched frozen text are counted and excluded.
No identities or historical snapshots are invented or backfilled.

```sh
python3 experiments/nonllm-judges/taste_comparison.py \
  --scratch "$SCRATCH" \
  --profile "$SCRATCH/taste-profile.json" \
  --landings "$SCRATCH/landings.jsonl" \
  --cutoff "<timestamp with explicit UTC offset>" \
  --source-timezone America/Chicago
```

The scratch root must be private (0700), outside a repository and live workspace;
input files must be private (0600), owned regular files, not symlinks. Inputs are
bounded to 4 MiB each and 4096 rating records. Each supported profile category is
bounded to 500 phrases of 2048 characters; compared fields to 10000 characters.
Duplicate JSON keys, nonfinite JSON, unsafe paths or malformed input refuse with
only `taste_comparison_refused`. There are no automatic live paths, output files,
network calls, subprocesses, writes, encoders or providers. Original fields and
provenance stay untouched in the private snapshots. Stdout contains fixed keys,
counts, the proxy rate and explicit measurement limitations, never source text,
titles, paths, IDs, hashes, vectors or arbitrary field names.

`broker/tests/test_taste_comparison.py` uses only synthetic fixtures to cover
selection, phrase boundaries, denominator and abstention, excluded context,
media-description limits, privacy, unchanged inputs and CLI refusals. Independent
review and the full isolated integration suite remain Claude's responsibility.

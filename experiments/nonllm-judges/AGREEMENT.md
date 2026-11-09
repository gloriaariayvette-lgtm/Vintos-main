# Retained judgment agreement

This is an offline comparison of recorded decisions and descriptive numerical
proxies. It does not establish that either judge is correct, authorize replacement,
or change a loop. It makes no calls to an encoder, provider or live service.

## Supported pairs and bands

| Recorded judge | Numerical counterpart | Recorded bands | Limits |
|---|---|---|---|
| Voice coherence | Per-reply voice familiarity | Native retained Score 1–3 with a note → flag | Writer logs selected flags only; missing entry is not pass. Judges at most 500 characters. |
| Deviation check | Per-reply voice familiarity | Native Deviation score > .30 → flag; Aligned → abstain | Persisted score is 60% classifier plus 40% identity similarity, not a pure LLM verdict. Aligned also labels commitment friction. Judges at most 400 reply characters. |
| Presence audit | Per-reply voice familiarity | Explicit current `flag` true/false → flag/pass; requested-work exemption → abstain | Presence rubric and familiarity differ. Historical archive omits flag/exemption; its scores remain abstentions. |
| Humor detector, his reply | Humor familiarity, message kind only | Retained `source=vintos`, signal >= .5 → pass | Positive-selected material, not evidence the joke landed. Incoming and social moments excluded; practice jokes never pooled with reply messages. Judges at most 600 reply characters. |

The numerical pipeline's existing `below_band`, `abstain`, `above_band` map to
flag, abstain, pass. Those are *descriptive comparison labels*, not accuracy or
quality labels. Existing voice calibration uses the inclusive [.2, .8] abstention
interval. Humor uses its existing empirical calibration; similarity-only or
insufficient-reference receipts stay abstentions. Missing numerical receipts are
missing, not an abstention vote. The tool re-evaluates `run_private.evaluate` on the
supplied cached evidence and preserves all lineage, indirect-influence, freeze,
mode, attribution, reference-day and outcome-anchor gates. It accepts no supplied
numerical verdict override and does not create embeddings.

Daily sustained drift has a different observation unit from a reply verdict; it
is listed as unavailable for this comparison. No invented daily aggregation or
new threshold makes it equivalent to deviation. Taste, recurrence and grouping
lack an equivalent retained reply rubric/adapter. Other inventory entries below
are explicitly unavailable, with null agreement rather than fabricated zeros.

## Read-only projection contract

Use a private copy of the existing numerical input bundle and optional Landings
projection, plus `judge-verdict-projection-v1`:

```json
{
  "schema": "judge-verdict-projection-v1",
  "cutoff_at": "2020-02-01T00:00:00Z",
  "records": [{
    "judge": "presence_audit",
    "store": "memory/presence-audit.json",
    "record": {"id": "synthetic-audit", "composite": 0.6, "flag": false},
    "recorded_at": "2020-01-20T12:00:01Z",
    "clock_order": "known",
    "binding": null,
    "served_model": null,
    "fallback": null
  }]
}
```

The example deliberately has no binding and cannot join. `record` is the original
retained JSON object, or the complete Markdown entry for voice/deviation. Do not
rewrite source fields, strip exemptions, normalize an unknown into a pass, or
feed generated prose through another model. Store names are exact inventory
labels, never filesystem paths the program opens. Retain any original provenance,
served-model and fallback fields in the private projection; additional private
metadata is never copied to public output. `served_model` and boolean `fallback`
may be copied to the envelope only from actual recorded serving evidence. A
configured/requested model is not proof; absent values stay null. The report
counts known/unknown metadata without publishing names.

A non-null binding must contain `kind=recorded_full_reply`, `turn_id`,
`content_sha256`, offset-bearing `finalized_at`, `mode` (everyday/intimate) and
`surface`. These must all exactly match an admitted reply; recorded time must be
at or after finalization and strictly before the common cutoff, with known clock
order. Bindings must come from an independently retained exact reply relation,
not reconstructed from a minute timestamp, excerpt, current mutable state,
nearest neighbor or the note's topic. Source-native audit IDs may require an
exact ledger relation; they must not be assumed to equal capture turn IDs.

The legacy Markdown logs do not themselves supply this relation. When it was
never retained, leave `binding` null and count missing coverage. The tool verifies
internal consistency, not the authenticity of caller-supplied binding/serving
claims. It does not certify that the judge saw the full reply merely because a
full reply can be identified: the truncation limits above still apply. Do not
retroactively manufacture receipts to increase agreement.

Identical copies count once. Conflicting copies or multiple distinct verdicts for
the same judge/reply exclude that reply from the joined population, rather than
choosing the most favorable or latest verdict. Project one canonical source row;
including both current and historical presence rows may make that reply ambiguous.
The raw copies and all fields remain unchanged outside this read-only program.

CLI (stdout counts only; no automatic discovery, writes or notifications):

```sh
python3 experiments/nonllm-judges/agreement.py \
  --scratch "$SCRATCH" --input "$SCRATCH/numerical-input.json" \
  --landings "$SCRATCH/landings.json" --verdicts "$SCRATCH/recorded-verdicts.json" \
  --cutoff 2020-02-01T00:00:00Z
```

Use the same actual cutoff in the verdict projection and CLI. Scratch must be
outside a repository/live workspace, owned and 0700, files 0600, no symlinks.
Inputs are bounded at 4 MiB each and 4096 projected verdicts; the existing numerical
admission bound remains 512 replies. Omit `--landings` when unavailable. The
process blocks writes, networking and subprocesses after loading its local modules;
malformed inputs produce only `judge_agreement_refused`. No source text, IDs,
hashes, vectors, scores, model names or arbitrary metadata enter its output.

## Denominators and interpretation

For each pair and each attribution view, independently, the report gives the
admitted population, recorded judgment coverage, numerical receipt coverage,
intersection, each unmatched side, neither, a 3×3 confusion matrix, agreement
rate and the two flag/pass disagreement directions. It also separates numerical
and recorded abstention disagreements. Missing data never enters the matrix.
Three-band agreement includes abstain/abstain; decisive agreement excludes all
abstentions and reports its denominator. A zero denominator gives null, not 100%.
Mode/surface cells remain separate. The primary 10-second view and overlapping
30-second sensitivity view are never summed or treated as independent samples.
Humor's denominator is explicit message attempts, not every admitted reply.
Source coverage is over the supplied projection, not a claim of complete live
history. Identical source snapshots are not independent observations.

Agreement can reveal directional disagreements worth private review and quantify
coverage gaps. It cannot establish truth, authenticity, feelings, causal benefit,
calibration, or equivalence of these constructs. Sparse flags and selected positive
moments create selection bias; repeated replies/days are correlated. There are no
confidence intervals pretending every reply is independent, no tuning on these
results, and no automatic replace/keep/run-both recommendation. Replacement would
need a reviewed common task, independently labeled outcomes, held-out evaluation,
adequate coverage by scope, and cost/error tradeoffs. For now all live judges and
feeds remain in place. Unknown data can accumulate through ordinary use; no test
messages are requested.

## Source persistence census (33 entries)

Paths below are relative to the workspace. These are writer-code destinations,
not a statement that private files exist or retain complete history. Authored
output/effect state is not automatically a verdict record. The README's source
links identify each writer. Only the four supported rows have reply-band adapters.
The others can contribute projected-record counts with their exact inventory
labels, but have no comparable agreement denominator.

| Entry / projection label | Retained output or effect store | Why comparison is limited |
|---|---|---|
| A `voice_coherence` | `memory/voice-coherence.md` | Selected flags, excerpt and minute stamp; no native exact binding. |
| B `deviation_check` | `memory/voice-coherence.md`; effects also `resolution-state.json`, `pending-nudges.json`, `core-vectors.json`, `held-ledger.json` under memory | Mixed scores and selective effects; effect stores are not complete verdict histories. |
| 1 `thread_triage` | `memory/thread-triage.md`, `memory/unfinished-threads.json` | Thread actions, not reply labels; recurrence component not a triage verdict. |
| 2 `thread_weaver` | `memory/unfinished-threads.json` | Mutable grouped threads; no retained grouping adapter. |
| 3 `thread_resolution` | `memory/retired-threads.json`, `memory/unfinished-threads.json` | Resolution/retirement is not familiarity. |
| 4 `wonder` | `memory/wonder-log.json` | Selected wonder entries; novelty component has no matching reply rubric. |
| 5 `hallucination` | `memory/hallucination-flags.json` | Selected claim flags; similarity cannot adjudicate truth. |
| 6 `surprise` | `memory/surprise-log.md` | Selected narrative; chat innovation is a residual, not a surprise verdict. |
| 7 `self_prediction` | `memory/self-blind-spots.jsonl`, `memory/.self-prediction-history.json`, `memory/self-prediction-held.jsonl` | Forecast/outcome unit; no common reply-band threshold. |
| 8 `self_model_update` | `SELF-MODEL.md`, `memory/self-model-refusals.jsonl` | Authored revisions/refusals, not a reply classification. |
| 9 `soul_review` | `memory/soul-proposals/`, `SOUL.md` | Authored proposal or rewrite; not numerical certification. |
| 10 `pride_mirror` | `memory/pride-reflections.md` | Authored reflection. |
| 11 `value_map` | `memory/value-map.md` | Authored value description; frequencies cannot replace it. |
| 12 `introspection` | `memory/introspection/` | Authored reflection. |
| 13 `mirror` | `memory/mirror/` | Authored dialogue and thread effects. |
| 14 `conversation_review` | `memory/conversation-insights.json` | Conversation/day review, not an exact reply verdict. |
| 15 `emotion_read` | No durable verdict store identified in this writer; applied nudges printed to stdout | Effects are not outcome labels. |
| 16 `emotional_reflection` | `memory/emotional-reflections.md`, `memory/reflection-history.json` | Bias/reflection summaries, different unit and construct. |
| 17 `presence_audit` | `memory/presence-audit.json`, `memory/presence-audit-history.jsonl` | Explicit current flag usable; historical exemption absent. |
| 18 `owner_prediction` | `memory/gloria-prediction.json`, `memory/gloria-prediction-history.json` | Forecast/next-turn outcome, not his reply quality. |
| 19 `withheld` | `memory/withheld.json`, `memory/withheld-history.json` | Inferred intention cannot be certified by topic coverage. |
| 20 `causality` | `memory/causality-hypotheses.json`, `memory/causality-retired.jsonl` | Hypothesis evidence, not a per-reply causal truth label. |
| 21 `world_model` | `memory/world-state.json` | Mutable state predictions; no matched sensor claim adapter here. |
| 22 `yearning_scars` | `memory/current-yearning.json`, `memory/yearning-scars.json` | Recurrence counts cannot decide yearning/scars. |
| 23 `humor_detector` | `memory/humor-moments.json` | Last 100 selected mixed-source moments; only his message rows eligible. |
| 24 `pearl` | `memory/candidate-pearls.json` | Declaration-specific verification; not generic familiarity. |
| 25 `reality_anchor` | `memory/reality-anchor.json` | Claim facts/physical evidence; no truth surrogate. |
| 26 `unprecedented` | `memory/unprecedented-states.md` | Selected narrative; first recorded is not first ever. |
| 27 `search_question` | `memory/web-search-log.json`, `memory/web-discoveries.md` | Selected queries/results; novelty does not grade their value. |
| 28 `creative_search` | `memory/creative-discoveries.md`; curiosity scan seeds existing threads | Authored discoveries/topic suggestions, no equivalent retained verdict. |
| 29 `social_score` | `memory/moltbook-replies.txt` | Chosen engagement log, not a complete candidate-score history. |
| 30 `social_members` | `memory/moltbook-members.json` | Encounter/member summaries; counts not social judgment. |
| 31 `social_post_check` | `memory/moltbook-post-log.md` | Post/action log, not complete rejected-and-accepted verdict history. |

The evidence bundle has a separate 64 MiB read limit, matching run_private; verdict and Landings projections retain the 4 MiB limit. Private ownership, parent permissions, regular-file, symlink, duplicate-key and finite-value checks apply at either bound.

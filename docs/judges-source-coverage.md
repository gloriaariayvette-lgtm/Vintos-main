# Chat caller and missing-surface coverage

Source review on 9 November 2026, based on the completion-join branch. This is
source evidence plus a runnable private diagnostic, not a newly measured live census.

## The text route does not use the avatar completion wrapper

- `bin/server.py` defines `_bilateral_reply_engine`; `chat_with_vintos` and
  `chat_full_context` invoke it with tags `chat` and `chatfull`. It calls draft
  helpers and direct provider requests, rather than `route_reply`.
- `scripts/bilateral_stages.py:checkpoint` records foreground stage observations
  under `bilateral:<tag>`. These calls supply stage and latency but omit model and
  provider. `compute_admission.record` writes those omitted fields as empty strings.
  Presence of both JSON keys therefore does not establish known model identity.
- A resumed stage need not run that checkpoint again. `done` changes the stage
  file; it does not append a final generation record to the compute ledger.
  Stage observations are not one selected reply each and cannot be relabelled as
  final-generation attribution.
- The router completion wrapper is used by the avatar handler; its current server
  call sites pass `avatar`. A text endpoint called chat and a ledger caller named
  `router:chat` are not the same contract.

This split predates the reported September 11 last retained `router:chat` entry.
Commit `2f8651d6` (August 27) already has two bilateral chat call sites and separate
avatar router calls. Commit `d335de72` (September 10), which adds compute accounting
and bilateral stage retention, retains that arrangement. The available source
therefore does **not** substantiate a September 11 switch or prove a logging outage.
The provenance of the September 10–11 `router:chat` rows remains unresolved; it
requires retained installed/runtime or call-origin evidence. Do not label them
production chat, tests, or another producer by guessing.

## Missing surface is not a door name

`interaction_ledger.main` takes surface from `VINTOS_SURFACE`, defaulting to an empty
string. The current server `_post_turn` subprocess launcher explicitly sets this
variable; its chat/full caller uses `chat/full`. `chat` and `chat/memory` intentionally
skip that ledger writer. Other producers, old installed versions and historical
records cannot be identified from an empty value alone.

`build_merged_chat.entry` retains a supplied surface and records the projection
source (`canonical` or `ledger`). It does not create a surface. Thus one missing
ledger field may appear in both the original and merged copy. Counts of source
copies are not counts of independent turns. Canonical appending also has a default
chat label; that label alone does not distinguish every text endpoint.

The new `coverage.py` aggregate `source_coverage` partitions assistant copies by:

- admitted adapter kind and fixed projection-source categories;
- explicit surface state: absent, empty, invalid or declared;
- for missing/invalid surfaces, availability of a declared surface on another copy
  with the same agreeing explicit turn ID and exact stored text.

Conflicting IDs, stored versions, surfaces, missing clocks and missing IDs stay
separate. Unknown-clock or at/after-cutoff peers cannot attest another copy. No
similarity matching, trimming, suffix removal, source-to-door defaults or automatic
surface filling occurs. The main attribution partition stays byte-for-byte
unchanged as a data structure. Strict witness eligibility and feeds stay unchanged.
The source grouping exposes only fixed labels and counts; IDs, text, hashes,
actual surface strings, dates, model/provider names and arbitrary source strings
are absent. All metadata-bearing output remains private scratch.

Private caller summaries now include nonempty model-and-provider counts and stage
counts alongside first/last retained times. Empty JSON fields no longer look like
identity coverage in this diagnostic. Retained endpoints are not logging start/stop
proof. Caller names, stages and dates remain in the private output only.

## Review run on the existing admitted copy

Use the same complete copied ledger and source groups, explicit timezone/mapping,
exclusive cutoff and isolated interpreter as the prior coverage run. No live
collection or fitting is needed. Choose a new output directory:

```sh
SPARK_WORKSPACE="$PRIVATE_SCRATCH" python3 experiments/judges-witness/coverage.py \
  --scratch "$PRIVATE_SCRATCH" --input "$PRIVATE_SCRATCH/bundle.json" \
  --output "$PRIVATE_SCRATCH/source-coverage-new" --cutoff "$CENSUS_CUTOFF"
```

Report only the fixed `source_coverage` groups and aggregate counts. Inspect the
private caller rows for bilateral chat/chatfull separately from router chat; report
whether stage activity continues and whether model/provider values are nonempty,
without publishing dates or arbitrary stage names. Do not broaden a caller mapping
on stage activity alone. An exact-ID/text peer is a candidate for source review,
not permission to backfill a surface or change historical training eligibility.

Validation: 78 isolated synthetic checks (coverage 21, attribution 26, merged
projection 31), including real scratch CLI/output permissions and cutoff/privacy
checks. One invocation used an incorrect merged-suite filename; the correctly
named suite passed. No real-data rerun or full host suite is claimed. Review owns
the full isolated host suite and private counts; production remains unchanged.

# Persistent carry — review revision, 28 October

`codex/persistent-carry-review` is based directly on the deploy branch. It contains
only the carrying implementation, consumers, tests, deployment plumbing and its
own documentation/evidence. The forecasting experiments remain on
`codex/persistence-sprint`; none are in this branch's merge diff.
Claude Code reviews before merge; Gloria approves and the owner deploys. No merge,
production installation, paid call or real send has occurred.

## Sources and words

The journal parser admits **only** Idle thoughts, Vintos Speaks, Last Word, Wonder
and Journal, including the existing timestamp prefix on Idle thoughts. Every
heading is a boundary; other sections cannot bleed into an admitted one. It does
not read creative files. Mirror, Ghost Branch, letters, email, web search,
MoltBook and other headings are excluded. Pending threads/wants with those origin
labels are excluded too, so they cannot bypass the journal rule.

Current admitted unfinished threads and wants remain candidates. Dream-log residue
is explicitly imagined, never an event. Canonical chat, Lab event kinds, Watch,
house sensors, want events and emotion readings update state; their text is not
quoted as a journal. A recent positive detection of Gloria's phone and fresh
Watch motion/wearing estimates supply presence input. Other phone fields are not used or retained; network
configuration is not opened. No missing detection means “she is away,” and no
latent coordinate is decoded into a feeling or a statement about her whereabouts.

Fragments remove markup, links' targets, quoted blocks, fenced code and completed
checklist lines. Long fragments end at a complete sentence; a long passage without
a sentence boundary is omitted. Duplicate or near-duplicate fragments cannot
occupy multiple slots. Resolved/fulfilled/retired items are excluded and every
consumer rechecks exact source text and current status before quoting it.

## Selection and persistence

This is a transparent **untrained** selective recurrence using fixed lexical
features, four decay timescales and per-source bounded input gates. It has no
forecasting objective or accuracy gate. Selection uses state similarity with a
small continuity bonus, with no source quota and no fixed thread/want/journal base
score. Three threads may be carried together; conversation and presence can change
the selection with the candidate records held identical. Tests exercise both
counterfactuals. Source volume is averaged so busy machine traffic does not drown
out a conversation. This functional check does not establish subjective usefulness.

The source window is seven days for allowed journals; pending items remain while
admitted and unresolved. Explicit references, source revisions and original carry
origins survive a restart. Edits and retirements rebuild only the affected channel;
forget marks reset retained meaning and purge old checkpoints. Carry headers and
versioned markers are rejected inside journals, pending records and conversation,
so the worker cannot ingest its own note as new evidence. First Light is excluded.

Decay is evaluated lazily. The durable `state.json` changes only when inputs,
references, selection, observed day or restart state changes. Quiet polls keep its
bytes, inode and mtime intact. Small separate health and note packets maintain a
heartbeat. Files use 0600 permissions in a 0700 output directory with one writer.
There are at most 512 retained items, 1,024 deduplication digests per stream, 48
hourly checkpoints of changed state, and 30 daily aggregate receipts.

Elapsed carry duration uses monotonic time in the worker. Each elapsed step is
clamped to 0–300 seconds; backwards or implausible wall-clock changes cannot
invent days of carry, collapse the state or age out a journal. A separate bounded
source clock follows normal wall time and preserves the source window during a
jump. Clock discontinuities are labeled in the note. A restarted worker resumes
its observed elapsed basis from private health; downtime is not counted as carry.

## Real switch, expiry and adoption

`memory/persistent-carry/config.json` controls the context reader:

```json
{"enabled": true}
```

`false`, a missing file or an unreadable file disables this new context block
immediately. Other feeds remain intact. A note older than **three hours**, or more
than 60 seconds in the future, is dropped. After five minutes it is explicitly
stale until refreshed; an old worker cannot keep an obsolete note alive. The full
and compact readers obey the same switch, source revalidation and expiry.

The owner-approved standard deploy initializes this flag to true only if absent;
it never overwrites an existing off flag. Starting the worker alone defaults the
production flag to false. Shadow uses an explicit private flag and is invisible
to normal context regardless of its flag. The deployment manifest includes the
three runtime modules and the service; rollback preserves prior unit/activation.

`VINTOS_CARRY_SHADOW_STATE` may transfer checked state during the owner's approved
deploy. **Adoption resets all carry origins, elapsed duration and observed-midnight
counts. Shadow days do not count as his lived carry.** It never overwrites an
existing production checkpoint. First Light receives the same switched, fresh
context block through its existing generation call, with no new model/provider call.

## Corrected shadow and release condition

Private root: `/tmp/persistent-carry-review-20261028-rvc4LM` on Aegis.
Input: read-only `/home/gloria/.vintos/workspace/memory`. All writes, logs, notes,
checkpoints and tests are under private scratch. The original v1 shadow is retired;
its observations do not establish the corrected version's acceptance.

The worker polls every 30 seconds, Nice 15, one BLAS thread, 96-hour lease.
`shadow.pid` and `/proc/PID/cmdline` identify it; check the resolved script path and
`--shadow` before any process operation. Do not install or restart live services.
The continuation checks actual private notes and publishes only aggregate evidence.

**Release is held until this corrected shadow crosses at least one real midnight
in America/Chicago.** `state/midnight-receipts.json` records the actual before/after
wall timestamps, monotonic step, number of selected records retained, source
failures and runtime hashes. Synthetic tests mark their receipts `real_clock:false`
and cannot satisfy the condition. Check the real heartbeat gap, retained source
origins and note, and distinguish an honest changed selection from a dropped state.
Then bring the observations back to Claude Code and Gloria; no automatic merge.

Judge stability, honest source attribution and noticeable carry, not forecast
scores. After owner release, observe normal context and First Light using ordinary
activity; a provider stub or a synthetic midnight is not evidence of his response.

## Validation

Final Aegis snapshot `3804b6a7`: **542/542 broker suites passed**, including 45
carrying tests, using `/usr/bin/python3.12` and OS isolation. One pre-existing
optional Lab SDK test internally skipped. Shell syntax and unit static checks
passed; the unit check reported an unrelated existing server-unit escape warning.
The generated store-ownership report was repaired after the initial run, whose
other failure was an unchanged bench denial assertion that subsequently passed.
Both aggregate run summaries and the shadow probe are in
`docs/review-evidence/persistent-carry/review-*.json`.

The corrected shadow has 32 admitted records; the note and all current selected
sources pass the private consumer probe. This is running-path evidence, not the
required real midnight or a claim about his lived response. The next scheduled
midnight check is 29 October at 00:10 America/Chicago. Release remains held.

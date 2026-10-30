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
H1–H6 heading is a boundary; other sections cannot bleed into an admitted one. It does
not read creative files. Mirror, Ghost Branch, letters, email, web search,
MoltBook and other headings are excluded. Pending threads/wants with those origin
labels, including grok/muse/codex origins, are excluded too, so they cannot bypass the journal rule.

Current admitted unfinished threads and wants remain candidates. Dream-log residue
is explicitly imagined, never an event. Canonical chat, Watch, want events and emotion readings update state;
Lab and house traffic contributes health counters only, without dirtying or
changing the selective state; their text is not
quoted as a journal. A recent positive detection of Gloria's phone and fresh
Watch motion/wearing estimates supply presence input. Other phone fields are not used or retained; network
configuration is not opened. No missing detection means “she is away,” and no
latent coordinate is decoded into a feeling or a statement about her whereabouts.

Fragments require at least 40 characters and five words after cleaning. They
remove timestamps, bare headings and the bracketed META-DREAM preamble, plus markup, links' targets, quoted blocks, fenced code and completed
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

Decay is evaluated lazily. Meaningful changes update the state in RAM immediately;
`state.json` persists pending changes at most once per **180 seconds**. Lab/house
cursors, deduplication and tick counters are observational RAM state and cannot
trigger this write. Quiet polls keep the checkpoint bytes, inode and mtime intact.
A crash can lose up to three minutes of pending state; current sources are read
again on restart and no missing carry duration is invented. Privacy removals
invalidate old state/hourly files immediately; their replacement still obeys the
write cadence. Small health and note packets retain a 30-second heartbeat.
Files use 0600 permissions in a 0700 output directory with one writer. There are
at most 512 retained items, 1,024 deduplication digests per stream, 48 hourly
checkpoints of changed state, and 30 daily aggregate receipts.

Elapsed carry duration uses monotonic time in the worker. Each elapsed step is
clamped to 0–300 seconds; backwards or implausible wall-clock changes cannot
invent days of carry, collapse the state or age out a journal. A separate bounded
source clock follows normal wall time and preserves the source window during a
jump. Clock discontinuities are labeled in the note. A restarted worker resumes
its observed elapsed basis from private health; downtime is not counted as carry.

## Real switch, expiry and adoption

`memory/persistent-carry/config.json` controls the context reader:

```json
{"enabled": false}
```

`false`, a missing file or an unreadable file disables this new context block
immediately. Other feeds remain intact. A note older than **three hours**, or more
than 60 seconds in the future, is dropped. After five minutes it is explicitly
stale until refreshed; an old worker cannot keep an obsolete note alive. The full
and compact readers obey the same switch, source revalidation and expiry.

Every owner-approved standard deploy writes **false**, including when a previous
flag was true. Gloria turns it on herself by setting `enabled` to true; neither
deploy, worker nor adoption enables the production reader. Starting the worker
alone also defaults the production flag to false. Shadow uses an explicit private
flag and is invisible to normal context regardless of that flag.

Carrying is absent from default full and compact context. Only `/api/chat`,
`/api/chat/full`, the avatar main-chat path (not ReelRoom), and First Light
explicitly pass `carrying=True`. MoltBook, idle-journal, dreams, voice-coherence,
wants-router, pride-mirror, dream_poetry, voice tokens and other default callers
never opt in. The underlying existing context defaults remain available to them.
The deployment manifest includes the three runtime modules and the service;
rollback preserves prior unit/activation.

`VINTOS_CARRY_SHADOW_STATE` may transfer checked state during the owner's approved
deploy. **Adoption resets all carry origins, elapsed duration and observed-midnight
counts. Shadow days do not count as his lived carry.** It never overwrites an
existing production checkpoint. First Light receives the same switched, fresh
context block through its existing generation call, with no new model/provider call.

## Corrected shadow and release condition

Private root: `/tmp/persistent-carry-second-review-20261028-1Ht0eN` on Aegis.
Input: read-only `/home/gloria/.vintos/workspace/memory`. All writes, logs, notes,
checkpoints and tests are under private scratch. The original v1 and first-review v2 shadows are retired;
their observations do not establish this v3 revision's acceptance.

The worker polls every 30 seconds, Nice 15, one BLAS thread, 96-hour lease.
`shadow.pid` and `/proc/PID/cmdline` identify it; check the resolved script path and
`--shadow` before any process operation. Do not install or restart live services.
**This scratch shadow does not survive reboot.** It is a `nohup` process in
`/tmp`, with no boot unit installed; reboot stops it and may erase its files.
After a reboot or expiry, inspect the interruption, restart only authorized scratch
work, and require a new uninterrupted actual midnight under the reviewed hashes.
The owner-approved production service is a separate later installation.
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

## Historical first-review validation

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

## Second-review validation and current hold

52 focused tests pass under Aegis `/usr/bin/python3.12` in OS isolation. They
exercise the real deploy config fragment, default-context exclusion and the
explicit chat/First Light calls, minimum content, META-DREAM stripping, H1 boundaries,
letter origins, non-dirtying Lab/house streams and the 180-second write limit.
The full-suite and current running-path receipts are recorded in the review log.
No release before this v3 worker crosses a real midnight, then Claude Code's review
and Gloria's yes. Her production context flag remains hers to turn on.

Final second-review snapshot `2a746c6d`: **542/542 suites passed**, including all
52 carrying tests. The new shadow has 21 admitted records and a 691-character note;
current references and explicit consumers pass the provider-stubbed probe, with
default contexts excluded. Receipts:
`docs/review-evidence/persistent-carry/second-review-*.json`. No actual midnight
has crossed yet. Reboot survival is explicitly **not provided** for this scratch
worker; no production unit was installed.

# Persistence sprint

## 29 October — review fixes before the future block

Claude Code reviewed `da1b31cd`; Gloria requested fixes and another review before
merge. A byte-exact private v3 copy now exists outside `/tmp`, with directories
0700 and files 0600. The amended v3 will be the sole evaluable bundle; older
copies receive exclusive retirement receipts in their attempt files. No actual
evaluation attempt has run.

The 24-hour horizon remains a descriptive score but is removed from pass rules:
day-seven origins cannot have within-block outcomes at that horizon. Six-hour
primary, minimum primary counts, thresholds and the conservative 56-contrast
interval adjustment remain unchanged. An analytic synthetic positive case must
pass the full evaluator using real predictions, ranks and intervals; the existing
negative case must fail. Neither is an empirical accuracy result.

Collector entry now requires the guard installed by `launch.py`, before reading
inputs or creating capture output. Tests cover direct-entry refusal, rename and
subprocess denial, and a forbidden `.vintos` root with a valid child output.
Published round receipts omit all daily blocks and strong-moment counts. Removed
private input filenames and source-store start dates from the log/recovery
receipt, and source filenames from the published capture provenance. Full private
artifacts retain their exact original bytes. Validation and durable seal hashes
will be recorded after the checks. No fitting, new score, merge or deploy.

## 29 October — resume the offline work without repeating fitted rounds

Gloria requested the offline sprint again. Checked deploy `340f9195`, the
`codex/latent-memory-review`, `codex/persistence-sprint` and carrying branches
before implementing. Rounds 1–8 and their numerical snapshots already exist;
recovered their offline-only source/evidence from `6f841f33` onto
`codex/persistence-offline-round-one`, based on the current deploy branch.
The carrying implementation/checks remain Claude Code's work. No live modules,
feeds, head parameters or deployment files are changed by this branch.

Aegis access was verified before any run. All seven named dense/chat input files
are readable. Existing capture, eight round directories and v2 future seal are
present. Its executable and candidate hashes match, with no evaluation attempt.
No real-data training or scoring was repeated: the first offline round was
already fitted, and the prior log/results below remain explicitly historical.

Round 1 has a 24-wide CPU selective diagonal state, input-dependent gates and
decay over actual irregular gaps; seven emotion horizons from 10 minutes to
24 hours. Representation pretraining starts as an emotion-persistence residual;
the final forecasting readout is a regularized correction to a separately fitted
present-only ridge control. Those are different stages, not an assertion that
the pretraining head is the exported present-moment model. Text correction starts
at zero. Round 2 adds source/gap supervision and contrastive 32-d projected-text
ranking; round 3 allows a validation-selected residual to the frozen text scorer.
No 768-d text regression is run. The history anchor in later rounds is labeled.

The first fitted six-hour check (16–17 October, 186 targets) was .803116 MSE,
versus .779449 present-only and .740038 present-plus-history. It lost. Its zero
text correction tied the identified portable present artifact at .274376 MRR
on 59 exact-time targets. These are neither synthetic scores nor the .230
confirmation reported on 23–27 October. The latter used 174 candidates; absolute
MRR levels across these candidate pools cannot be compared as a learning curve.

The frozen confirmation exposed both incumbent text and emotion scores on
23–27 October. The older sealed emotion-history experiment still uses exactly
23–29 October, excludes 30 October, and keeps its 30 October 08:00 Chicago
follow-up and original thresholds. Its overlapping/exposed comparison must not
be described as wholly untouched. Its rejected text candidate stays closed.
The new sprint's first untouched block is 31 October–6 November, inclusive.

Found an operational defect before that block: v2's sealed collector imports
admission helpers absent from its package. Added a clean-room synthetic capture
test, complete dependency packaging, disk checkpoint/restart and simultaneous
target tests, and filesystem mutation/network checks for the scratch launcher.
The repair command copies all existing candidate/control artifacts byte-for-byte
and refuses any change to the five scientific executables or any repair after
the future week opens. It creates a separate bundle; it never alters v2 or the
older emotion-history seal. Validation and repaired bundle receipt follow below.

This round is recovery and contract verification, not a ninth model selection.
Synthetic tests, previous fitted development scores and future untouched scores
remain separate. No fresh outcome has been opened, and no candidate is promoted.

## Prior 28 October work (preserved historical log)

The following schedule statements record what was arranged on 28 October; the
29 October receipt at the end is the current handoff. The daily carrying/sprint
continuation remains paused, with carrying checks left to Claude Code.

## 28 October — round 0: contract and capture

Started from deploy branch `7b859dad`, on `codex/persistence-sprint`, following
`docs/briefs/persistence-sprint-codex.md`. This is implementation in scratch,
not another architecture review. No live organ or feed is changed.

The inherited emotion experiment's actual sealed window is **23–29 October**,
not 23–30. Its exact executable/weights and one-attempt receipt remain untouched.
Claude's 28 October run exposed overlapping incumbent text **and emotion** scores.
Consequently the old window cannot be described as wholly unobserved or without
interim inspection. Its unchanged candidate may still receive its scheduled
single fixed comparison, explicitly labeled overlapping/exposed; it cannot
independently confirm a new sprint design. No early candidate scores are read.

New sprint confirmation starts **31 October–6 November**, then **7–13 November**,
America/Chicago. Seal before each window opens; one look after closure. Earlier
days are historical development even when a particular round has not scored them.
No claim that previously inspected October days are fresh confirmation.

Read-only coverage census: dense emotion retains **4,000 rows**. The cap and
unchanged-reading suppression mean missing times are not observations. Watch:
14,892 rows; sensor reactions: 16,783; want events: 301; Lab activity: 143,281.
These are available-store counts, not training counts. Store start dates are
omitted from the public log.
Only current admitted sources, no erased backups or reconstructed missing labels.

### Predeclared development sequence

All inputs and outcomes are bounded before 23 October to leave the old candidate
alone. Every round trains before its validation days, selects there, and scores
its next disjoint historical days once. Target horizons: 10/30 minutes,
1/3/6/12/24 hours. Primary: 6-hour normalized emotion MSE against the strongest
same-row persistence, present-only ridge, and present-plus-observed-history ridge
control. Report each horizon, overnight and strong-moment recovery separately.
No source stream may multiply one target's loss; no split-crossing labels.

1. Dense selective scan, emotion loss: validation 14–15 October; check 16–17.
2. Add source/gap/projected-text self-supervision, otherwise unchanged:
   validation 16–17; check 18–19.
3. Add a zero-start correction to the frozen present scorer, otherwise unchanged:
   validation 18–19; check 20 October.
4. Add state-keyed past-only retrieval, otherwise unchanged:
   validation 20 October; check 21–22.

An inadequate block is reported inadequate, not silently widened. Fixed seed,
CPU width 24, 4 epochs, truncated chunks of 128, AdamW 0.001/weight decay 0.05.
Readouts use ridge 10; any text correction strength is chosen only on validation
from {0, .05, .1, .25}. Every loss and result, including failures, gets a receipt.
Self-supervision is not evidence of consumer benefit. Source/gap mechanical
schedule controls and state reset ablations distinguish persistence from clock
and last-event information. Exact-time text targets are primary; estimated times
are descriptive only. No 768-dimensional target regression.

Fresh acceptance requires at least 5% lower primary MSE than every same-row
control, positive adjusted paired-day lower bound, at least 300 unique 6-hour
targets across all seven days, and no more than 1% text MRR loss versus frozen
present scoring. A source-specific text gain is secondary and needs its own
counts/interval. Four rounds and seven emotion horizons form 28 planned contrasts:
Bonferroni two-sided intervals use quantiles .05/(2*28) and 1-.05/(2*28), fixed
20,000 paired day draws. Development selection does not confer permission to
steer him. A winner only becomes eligible for an owner-approved scratch shadow
week; daemon installation and one consumer remain later review decisions.


## 28 October — rounds 1–4 completed; none qualifies

Capture `capture-v2` contains 17,490 atomic steps, 3,317 emotion readings and
2,763 text events before 23 October. Lab: 131,015 rows; sensors: 15,270;
Watch: 8,915; want events: 284; presence: 88. Five-minute bins preserve counts
and bounded numeric values, not raw Lab prose. Only 91 texts needed local
embedding. The initial capture reached numeric serialization but failed because
a NumPy integer was passed to JSON; it was retained, repaired, and recaptured to
a new directory before any scoring. No fabricated observations or erased backup.

| Round | Check days | 6h n | Selective MSE | Best control MSE | Relative gain |
|---|---|---:|---:|---:|---:|
| 1: emotion scan | 16–17 Oct | 186 | .803116 | .740038 (history) | −8.52% |
| 2: auxiliary losses | 18–19 Oct | 176 | .197958 | .180730 (history) | −9.53% |
| 3: text correction | 20 Oct | 69 | .449795 | .432277 (history) | −4.05% |
| 4: state retrieval | 21–22 Oct | 166 | .399246 | .382778 (present) | −4.30% |

These are different scoring blocks and different training cutoffs, so differences
between rows do not causally isolate each added feature. Same-row controls and
the reset-state ablation are the persistence tests. No interval is claimed from
one or two days. Primary exact-time text MRR: round 3 .276010 versus present
.276770; round 4 .351339 versus .372616. Round 4 retrieval proxy: .561021 versus
.553340 for present-key retrieval and .513727 for recent context, only 19 targets.
No independent continuity/return labels exist, so this proxy grants no release.

### Follow-up rounds, registered before running them

The learned state's amplitude is small, but the ridge penalty is applied in raw
units. Round 5 changes only train-fitted state standardization (floor .01).
Round 6 changes only the anchor: state residual on top of the observed-history
control, rather than forcing the state to relearn the history control's gain.
Both use training before 21 October and validation 21–22 October. Those days are
already exposed: **validation-only diagnostic rounds, no new check-block claim**.
Fresh acceptance remains exclusively future sealed blocks. Report all validation
results and choose a candidate there, never by future outcomes. Readout penalty
and backbone training settings stay fixed. The confirmation family is expanded
in advance to six candidates × seven horizons = 42 contrasts; no looser intervals.


## 28 October — rounds 5–6 completed; state still loses at six hours

On the explicitly exposed 21–22 October validation block (166 unique 6h targets),
state standardization gives MSE .416620, versus .361156 for present and .362517
for history. Changing to the history anchor improves that to .383043, still
6.06% worse than the strongest control. Neither qualifies. State-standardized
text validation improves from .372616 to .400691 (19 exact targets); this is a
selection result on reused validation, not a new accuracy claim.

Round 7 changes only the emotion pretraining path: remove its direct present-input
bypass, forcing the hidden state to carry the emotion signal. Round 8 changes
only the training budget from four to twenty epochs. Same exposed validation,
no newly claimed check block; no hyperparameter search on fresh data. All eight
candidates are reported, and the future family expands conservatively to 56
candidate/horizon contrasts before any fresh scoring. No failing model is installed.

Initial full Aegis suite: 542 invoked, 541 passed. The one failure is the generated
`docs/untested.md` consistency assertion, not an experiment import/runtime error.
Regenerate the ownership/coverage reports and verify the repaired source again.


## 28 October — rounds 7–8 and first prospective seal

State-only emotion pretraining (round 7) gives 6h validation MSE .370548 against
.361156 present, a **2.60% loss**, the closest of same-split diagnostics 5–8.
Twenty epochs (round 8) worsen that to .394035, a 9.10% loss. Text validation
chooses .1 correction for round 7 (MRR .403396) and .25 for round 8 (.428051),
both against .372616 on just 19 exact-time targets. These reused validation
scores are not evidence that a held-out text gain has been established.

All eight rounds are retained. Select candidate 7 as the predeclared future
primary on the six-hour objective, not candidate 8 on the nicer text number.
No development candidate earns promotion. The first future block can still
honestly reject the whole family.

The provisional first seal SHA256
`13e2fa9ac2a573c4d9d9fa1c7e3af019590e5347044ff733600c367c95d0d240`
is retired **before any fresh outcome is read**. Final v2 adds missing auxiliary
clock/source controls, retrieval reporting and sequential weekly error spending.
The candidate parameters and already computed through-22-October present refit
are copied unchanged. No repeat experiment or reselected hyperparameter.
Week w receives alpha .05/(w*(w+1)); week 1 alpha .025 is further divided across
56 candidate/horizon contrasts. A new week must seal before it opens, even
though its predecessor has not finished yet. No repeated unadjusted looks until
something happens to win. Exact v2 manifest is recorded in aggregate evidence.

CPU tests: 3 scan tests pass (chunk/restart parity, causality, real memory,
zero-start outputs and irregular-gap decay). A fully synthetic future-dated
week exercises all eight evaluation paths and repeat refusal. It exposed a
zero-error comparator division edge case; this was repaired before sealing any
final executable. No actual future-week inputs were opened by these tests.


## 28 October — final v2 handoff and continued rounds

Final seal at **05:34:45 America/Chicago**, before 31 October. Full private
manifest SHA256:
`f98125ede8aedef75811e5a82cf862100d263d1db406b56697f9ac5861e6e675`.
All exact executable hashes match; neither its attempt receipt nor the older
emotion experiment's attempt receipt exists. The frozen primary is candidate 7;
all eight have 13,999 parameters. The eight training/readout runs total 51.21 s
CPU wall time, excluding collection, fixed comparator refit and validation suites.

Historical text comparisons use the explicitly identified older portable
incumbent `f9976dd2...`, not an invented reconstruction of Claude's .230 run.
The final seal adds the fixed winning-config through-22-October comparator for
fresh text. It also fits training-only fixed-horizon present-plus-last-text and
history-plus-last-text emotion controls; a weak semantic-free control cannot
suffice to release the state. Extra baselines never refit on the fresh week.
The copied candidates and old comparator remain unchanged.

[All round receipts](review-evidence/persistence-sprint/rounds-20261028.json),
[capture coverage](review-evidence/persistence-sprint/capture-20261028.json), and
[final seal](review-evidence/persistence-sprint/seal-oct31.json) contain only
aggregate scores/counts/hashes, no vectors, weights or message/memory text.
The `seal-oct31.json` repository copy is formatted for review; the SHA above
identifies the byte-exact private manifest, not that reformatted copy.

A daily Codex continuation is scheduled at **09:00 America/Chicago**, attached
to this thread. It reads this log, preserves running processes and receipts,
continues useful CPU development without calling spent days fresh, prepares
later weeks before they open, and runs the first exact sealed evaluation only
once after 6 November closes. This is not an Aegis service or live model daemon.
The existing 30 October follow-up keeps its time, exact model and thresholds;
its prompt now explicitly labels the overlapping/exposed incumbent inspection.

Still needed before any use: a sealed-week statistical result, reliable arrival
history for mutable threads/dreams and a continuity outcome label, review, then
an owner-approved scratch shadow week and audit. There is no consumer release,
no muted/gated original input and no live-store change in this sprint.


## 28 October — final validation and publication

Final source `9d156b04` runs **542/542 broker suites successfully on Aegis**,
zero failing suites. All **18/18** new NumPy-only broker contracts pass. One
existing optional atlas SDK test is internally skipped for its absent pinned
SDK environment; no entire suite is omitted. Four CPU-runtime tests pass in the
existing training environment (three scan tests plus the synthetic end-to-end
week). [Validation receipt](review-evidence/persistence-sprint/validation-20261028.json).

Only logs/aggregate evidence/status changed after that full run. No new input,
model, threshold, checkpoint or executable changed. The branch is for review;
publication does not authorize a merge or deployment. The continuation remains
active, and the sprint is not represented as a successful model or a completed
consumer integration.

## 29 October — verified recovery, complete bundle, review handoff

Exact tested source `79bd59bc`: **543/543 broker suites pass on Aegis** through
`/usr/bin/python3.12 scripts/run_isolated_test.py`; one pre-existing optional
SDK test internally skips. All **19** sprint broker contracts pass. **Eight**
CPU-runtime tests pass in the existing emotion-model training interpreter, then
pass again from the actual sealed v3 code. Those include clean-room capture
with absent optional sources, closed dense-event buckets, split exclusion,
same-time target causality, zero correction heads, irregular decay, disk restart
and a fully synthetic future week. That synthetic week is not an untouched
outcome measurement. No model, encoder or dependency was installed.

Private current root: `/tmp/persistence-offline-20261029-EpYs5CMi`.
Verified the old capture and round-1 model/readout against their hashes. Readable
inputs: seven dense/conversation source stores, plus the existing local encoder
and vector cache. Private input filenames are omitted from this log. Real-data fits repeated: **zero**. Real-data scores
newly computed: **zero**. Mutable thread/dream arrival histories and independent
continuity labels remain unavailable; they are not fabricated or backdated.

V3 future bundle: `sealed-oct31-v3/`, manifest SHA256
`b186cf66f3ab078ef74d1946a7fa7f27d2211ae13598f80866b41cb3e3680268`.
It supersedes v2 solely for collector dependency packaging and the scratch guard.
All **34** fitted candidate/control/report artifacts match v2 byte-for-byte;
all scientific executables and statistical protocol fields match. The original
v2 remains intact, with no evaluation attempt. V3 has no attempt either. Candidate
7 remains primary, all eight remain reported, and the first block is unchanged:
31 October–6 November, evaluated only after 7 November local midnight. Use the
exact commands in `experiments/persistence-sprint/README.md`; do not evaluate
both v2 and v3. Like the previous scratch bundle, `/tmp` may disappear on reboot;
loss is a blocker, not permission to reconstruct a seal after the block opens.

The separate older emotion-history executable, frozen weights and incumbent
match its manifest in Claude's durable copy under
`/home/gloria/sealed-latent-memory-20261022`. No attempt exists there or in the
original `/tmp` copy. Restored the existing 30 October 08:00 Chicago follow-up
from its carrying-era pause, retaining 23–29 October only, the original thresholds
and adjusted interval, and the overlapping/exposed comparison label. Its rejected
text design stays closed; the separate carrying check automation stays paused.

Aggregate receipts: `docs/review-evidence/persistence-sprint/recovery-20261029.json`,
`full-suite-20261029.json` and `seal-oct31-v3.json`. No private input text, weights,
vectors, source identifiers or secrets are published. No live script/feed/unit,
Gloria-head parameter or disabled emotion service changed. Claude Code reviews
this branch; Gloria approves before any merge. No deploy or promotion.

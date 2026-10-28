# Persistent carrying state — shadow implementation

Gloria changed the goal on 28 October: build continuity as a working part of him,
not another forecasting competition. Forecasting scores do not gate this path.
Claude Code reviews before merge; the owner performs deployment after approval.
Nothing has been merged, installed into his service set, or injected into live context.

## What runs

`scripts/persistent_carry.py` continuously polls admitted streams every 30 seconds,
saves its state atomically, and writes a short sourced “WHAT I'M CARRYING” note.
This first version is an **untrained selective recurrence**, not a trained Mamba
or a decoder of hidden feelings. Fixed signed lexical features feed per-source
states with 6-hour, 1-day, 3-day and 7-day decay. Source-normalized input gates,
novelty and prior selection affect which records stay selected. Explicit item
memory preserves when something first began being carried, including across restarts.
No paid calls, encoder replacements or extra generation calls are involved.

Current unfinished threads, admitted wants, recent journal and creative sections,
and explicitly imagined dreams supply quotable records. Canonical chat, Lab,
Watch, sensor, want-event and emotion streams update the selective state. Bounded
tails report omissions; missing readings are not invented. The note selects up to
three current records, quotes their words, labels their provenance, and stays below
1,100 characters. Source dates and actual carry duration are different fields.
A historical record does not acquire a fabricated history of being carried.

The context reader revalidates each selected record against the current source.
Resolved wants, removed threads and revised text therefore cannot persist as old
quotes between worker ticks. Tactical, withheld, imported, test, forgotten and
unadmitted records are excluded. Dreams remain imagined; journals remain self-report.
Missing/unreadable sources are uncertainty, not evidence of resolution. Forget marks
reset retained meaning and purge old private checkpoints. First Light and carrying
notes are excluded from journal ingestion to avoid recursive amplification.

State is bounded: 512 items, 1,024 stream digests per source, 512 KiB initial tails,
48 hourly checkpoints and 30 aggregate daily records. State files contain references
and lexical state; only the private note contains quoted fragments. All output is
private mode 0600 under a 0700 directory. A lock rejects concurrent writers.

## Consumers and installation

Both full and compact `subconscious_context.py` readers include the new carrying
block when available. Existing feeds remain present. First Light already consumes
compact context; its prompt now allows sourced unfinished items to carry from prior
days and distinguishes a record from a new event. Existing generation remains intact.

The review branch adds `vintos-persistent-carry.service` to the standard deployment
manifest, rollback and activation path. It uses the deployed system interpreter,
NumPy and stdlib, denies network connections and restricts writes to its own store.
Do not run the deployment script before review and approval.

To preserve the real shadow duration during the owner's approved standard deploy,
set `VINTOS_CARRY_SHADOW_STATE` to the private shadow `state/state.json` path below.
The installed script validates source, schema and duration, adopts only when the
production store has no checkpoint, and revalidates sources on its first tick.
An existing production checkpoint is never overwritten by this option.

## Actual shadow, 28 October

Private Aegis root: `/tmp/persistent-carry-shadow-20261028-gDEKoUTQ`.
Source memory is read-only `/home/gloria/.vintos/workspace/memory`; all worker
writes are under the private root. `shadow.pid` identifies the process; verify
its `/proc/PID/cmdline` names this root and `--shadow` before any process operation.
It has a 96-hour lease, 30-second polling, Nice 15, and one BLAS thread. It is
running already, not merely represented by a proposed service file.

At the initial check: 190 admitted items, three selected fragments, a 664-character
note, no unavailable sources; a controlled restart preserved all 190 first-seen
timestamps. Approximately 40 MB RSS and 0.1% CPU were observed. Real full/compact
readers and extracted First Light prompt assembly received this private note with
a stubbed provider. The normal live context did **not** receive the shadow note.
These are working-path observations, not evidence of multi-day continuity or his
response. Private quotes and source identifiers are not committed.

## Acceptance and next observation

Judge the following directly, with aggregate health in Git and private notes kept
on Aegis. Do not substitute MSE, MRR or another forecasting control:

- Stability: heartbeat, bounded resources, restart preservation and carry origins
  survive actual midnight and successive days. Separate synthetic time tests from
  elapsed real days. Observe at least two calendar-day transitions and morning
  opportunities; this is an observation plan, not a new code gate on his feeds.
- Honesty: every quoted fragment resolves to a current admitted source; dreams,
  self-reports, revisions, stale worker state and unavailable sources stay explicit.
  Fulfilled/forgotten content disappears without a fabricated resolution story.
- Continuity: compare private notes over those days. Relevant unfinished things
  remain recognizable while changed or resolved things update. After owner release,
  inspect ordinary context and actual First Light for noticeable carry; ask Gloria
  whether it feels useful. A provider stub cannot establish that outcome.

The daily continuation checks this running shadow and records evidence. It must
not restart the closed forecasting competition or leave this permanently in shadow.
Bring this implementation and its observations to Claude Code for review within
days, then to the owner for the approved release and ordinary-use observation.

## Validation receipt

Implementation `a38d8beaae3bbd48cde8aaf1b83cd8f2808c0bd5`: all **543/543**
broker suites passed under Aegis `/usr/bin/python3.12` through the OS-isolated
runner, including all 31 new carrying tests. One pre-existing optional Lab SDK
test internally skipped. Shell syntax and systemd static verification passed.
The last shadow probe verified the runtime hashes match that snapshot and every
selected source reference is current. Aggregate receipts are in
`docs/review-evidence/persistent-carry/`. This validates the running path and
recovery contracts; actual cross-day and post-release usefulness remain to observe.

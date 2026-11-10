# Proposal: capture the existing value-map cron

Prepared for Gloria's decision; **not applied**. No crontab, config, service or
model was read or changed on the serving host. Coordination note #62 reports the
missing capture pointer. The source census in `audit/aegis/discovery.json` confirms
`37 3,11,19 * * *`, but does not preserve the complete current cron command.
Times remain in cron's existing timezone.

## Exact change

On only the existing `value-map-update.sh` line at that schedule, prepend
`JUDGES_CAPTURE_CONFIG='<existing approved absolute capture-config path>' ` to
the complete existing command. Preserve every other byte, including any wrappers
and redirections. Use the same private enabled config already used by capture;
its actual path must be supplied from the reviewed configuration, never guessed.
The earlier `/absolute/private/judges-capture.json` example is only a placeholder.
Do not set a global crontab variable or add another scheduled invocation.

```text
37 3,11,19 * * * EXISTING_COMMAND
37 3,11,19 * * * JUDGES_CAPTURE_CONFIG='APPROVED_ABSOLUTE_CONFIG' EXISTING_COMMAND
```

To produce a concrete one-line diff, the reviewer can use the generator below on
a private export named `crontab.before`. It changes only that copy; it does not
read or install a crontab. Set `CAPTURE_CONFIG` to the actual reviewed path. Keep
the exported/proposed crontabs in private scratch, never Git. This refuses missing
or multiple matching jobs, existing capture assignments and shell/cron metacharacters.

```sh
python3 - "$CAPTURE_CONFIG" "$SCRATCH/crontab.before" "$SCRATCH/crontab.proposed" <<'PY'
from pathlib import Path
import os, re, sys
config, before, proposed = sys.argv[1:]
if not re.fullmatch(r'/[A-Za-z0-9_./-]+', config):
    raise SystemExit('supply the reviewed absolute config path')
lines = Path(before).read_text().splitlines(keepends=True)
pattern = re.compile(r'^(\s*37\s+3,11,19\s+\*\s+\*\s+\*\s+)(.*value-map-update\.sh\b.*?)(\n?)$')
matches = [(i, pattern.fullmatch(line)) for i, line in enumerate(lines)]
matches = [(i, m) for i, m in matches if m]
if len(matches) != 1: raise SystemExit('expected exactly one existing value-map job')
i, m = matches[0]
if 'JUDGES_CAPTURE_' in m[2]: raise SystemExit('capture environment already present; review it')
lines[i] = m[1] + "JUDGES_CAPTURE_CONFIG='" + config + "' " + m[2] + m[3]
fd = os.open(proposed, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f: f.write(''.join(lines))
PY
```

Gloria reviews the private diff and decides whether to install it. This branch
contains no cron installer, config enablement or restart. Reconfirm that the
installed wrapper and hooks are the reviewed versions. The wrapper retains its
compute admission and lock before its existing Python call
(`bin/value-map-update.sh`, also the script twin). Environment inheritance must
survive these wrappers; do not remove a wrapper to make capture work. Never set
`JUDGES_CAPTURE_SCRATCH` or repoint `SPARK_WORKSPACE` for the serving job.

## What it records

The existing `value_map.py` hooks observe reads, assembled context, auxiliary
materials and existing draft/synthesis calls. `witness_capture.py` can publish
call/build receipts containing input/context/resource hashes and bindings,
stage/dependency identities, timestamps, HTTP outcomes, response and returned-text
hashes, response-reported served identity when available, selected output binding,
and entry-write-close metadata. Configured identity is not actual serving proof;
unknown stays unknown. Internal attempts/fallback coverage remains incomplete.
Write close is not proof of fsync or whole-file durability. See
`begin_value_map_call`, `finish_value_map_call`, `finish_value_map_build`.

These call/build packets do not add raw context or generated value-map prose.
They do not make value-map effects independent original acts, backfill historical
lineage or add another prompt, embedding, replay, provider request or feed.
Only future observed runs can acquire receipts; failures/unknown clock order may
still leave gaps.

## Cost, acceptance and rollback

Incremental model/paid/GPU calls: **zero**. Three existing daily invocations and
their ordinary calls remain unchanged. Added work is hashing/serialization,
private publication, locks and retention scans, with several receipts possible
per run. Incremental host latency and bytes for this cron have **not** been
measured; a prior chat-path measurement is not a value-map measurement.

Existing sink configuration applies, with ceilings of 1 MiB per packet, 256 MiB
total, 4096 retained files and seven days. Shared capacity can reduce headroom for
other producers. At capacity it skips new packets rather than evicting unexpired
evidence. Expiry is opportunistic, not a timer. Missing/invalid/disabled config
leaves capture off; producer capture failures remain fail-open. See
`docs/judges-capture-enable-proposal.md` for the full storage contract.

After approval, observe the next ordinary scheduled run and privately check
call/build receipts and sink failure/capacity counts. Inspect known/unknown
fields; zero packets does not prove zero activity. Do not manually run value-map
or ask Gloria to send a message for a test. No installed-state claim is made here.

**Scoped rollback:** remove only the inserted capture assignment from that line,
preserving concurrent cron edits, the schedule, command, lock, admission and logs.
An already-running child may finish; later runs no longer inherit the pointer.
Existing private packets remain. Do not restore an old entire crontab over newer
edits. Disabling the shared config is a broader emergency kill switch affecting
all capture producers, not the preferred rollback for this one job. This
environment-only proposal requires no code rollback.

# Working in this checkout

## Subagents run on Opus. Always.

`.claude/settings.json` sets `CLAUDE_CODE_SUBAGENT_MODEL=opus`, which the CLI reads
before anything else — before an agent definition's own `model:`, before the parent's
model, before a `model` argument on the call. Every subagent spawned from this
checkout is an Opus subagent, whatever the prompt says.

This is here because it went wrong. A review pass spawned its parallel readers on
Fable and drained a week of her Fable credits in one afternoon. Nobody chose Fable;
it was inherited from an invocation default nobody had set. A fan-out multiplies
whatever default it starts from, so the default is pinned rather than remembered.

Do not override it. If a task genuinely needs a different model, say so and let
Gloria decide — do not pass `model:` to the Agent tool, and do not edit the setting
out of the way to get a run through.

**This is not the forge.** `scripts/forge_build.py` calls Fable 5.1 deliberately: one
review call per approved build, reviewing a capability Astra wrote before it may be
installed. That is a named, bounded, per-build cost she agreed to. It has nothing to
do with subagent defaults and the two must not be conflated when either is changed.

## A test never reaches the world

Every suite under `broker/tests/` runs on the host that serves her, with her real
`~/.vintos/workspace` beside it. Two rules follow, and both have been broken:

- **Repoint every path the module under test writes**, not just the obvious one.
  `test_skill_forge.py` repointed `print_3d.CONFIG` and left `JOBS` naming her live
  print-jobs store, so the suite opened real jobs in it.
- **Stub anything that sends.** `deliver`, `ntfy`, `requests`, any provider client.
  The reveal test fired real notifications at her phone during a deploy's suite
  phase. A test that can reach her is a test that eventually will.

Assert the isolation in the suite itself — a check that the store is throwaway and
the sender is a stub — so the next edit cannot quietly undo it.

## Where things live

- `scripts/`, `bin/` — his organs. `deploy-atelier.sh` installs a named manifest of
  them onto Aegis; a new module is not deployed until its name is in that manifest.
- `broker/*.service`, `broker/*.timer` — the units. Same rule: the deploy installs
  what it names.
- `docs/open-work.md` — the only to-do in the repository. Keep it honest: a thing
  that was not done is left written down as not done.

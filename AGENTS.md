# Working in this checkout

> Codex reads this file. It is the same guidance Claude Code gets in CLAUDE.md;
> where it says `--by claude`, use `--by codex`.

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

## The bench — how work moves between agents

`bench/` is where Claude Code, Codex, Grok Build and Gemma pass work to each other.
It is **not** `agent-room/`; that is Vintos's, and nothing here touches it.

**Before starting anything that is not what Gloria just asked for, propose it:**

```sh
python3 bench/bench.py propose --by claude --kind <kind> --what "<one line>" --why "<why>"
```

Then stop. It is proposed, not approved. She approves. You do not start on a
`proposed` task, and `claim()` will refuse you if you try.

**Do not do work that is cheaper elsewhere.** Check your own delegate map before
reaching for a tool:

```sh
python3 bench/bench.py agents
```

A grep, a one-word verdict, a summary, a regenerated report, a lint pass → `gemma`
(local, free). A rename, a test, a bounded fix with a named target, a port of a known
change → `grok`. Propose it with the right `--kind` and the bench addresses it to them
automatically. Keep only: design, root-cause, cross-repo, review, security, deploy.

**When you are given approved work:**

```sh
python3 bench/bench.py mine --by claude          # what is open and yours
python3 bench/bench.py claim T-xxxx --by claude
python3 bench/bench.py done  T-xxxx --by claude --result "<what actually happened>"
python3 bench/bench.py fail  T-xxxx --by claude --why "<what stopped it>"
```

**If it turns out to belong to someone else**, hand it on rather than doing it badly:

```sh
python3 bench/bench.py handoff T-xxxx --to grok --why "<why them>"
```

That closes yours and opens a new one for them — proposed, waiting on her. A hand-off
is not a way around her yes.

**Read the ledger before asking her anything.** `bench/bench.py show T-xxxx` has the
whole history of a task, and `mine --by <agent>` has what each agent is holding. If
another agent already did it, it is in there. Do not ask her to tell you what the
ledger already says.

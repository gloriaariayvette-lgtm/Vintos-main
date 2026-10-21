# Working in this checkout

> Codex reads this file. It is the same guidance Claude Code gets in CLAUDE.md, kept in step with it;
> where it says `--by claude`, use `--by codex`, and your review branches are `codex/<topic>`.

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

**This is not the forge.** `scripts/forge_build.py` makes one review call per approved
build, reviewing a capability Astra wrote before it may be installed. That is a named,
bounded, per-build cost she agreed to. Since 20 October it is Opus 5.5, not Fable
("No Fable, Opus 5.5": nothing of his calls Fable now). It has nothing to do with
subagent defaults and the two must not be conflated when either is changed.

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

## Never ask her to send him a message for a test

Gloria does not send him messages to produce test data, and does not want to be asked — she has had to
say so again and again (2026-10-13). A test of his replies uses the last message she actually sent and
the reply he actually gave (`bin/avatar_dryrun.py` with no line given: her real message, his real reply,
the candidate's reply beside it), and saves nothing. If something a test needs is not there yet, it fills
in on its own from her ordinary use: say that, and never ask her to make it happen.

## Deploying to Aegis — the only safe way

Aegis is the machine that serves her. Nothing reaches it except through her hands, by this route:

1. **Push your work to `claude/device-visuals-2026-10-13`.** That is the branch the deploy reads. Work for
   review goes on a branch of its own (`claude/<topic>`, `codex/<topic>`); it is merged into the deploy branch
   only after Claude Code in her main thread has reviewed it and she has said yes.
2. **She runs the deploy. You never do, and you never ask Dot or anyone else to.** Give her this command
   exactly:

   ```sh
   cd ~/Vintos-main && [ -z "$(git status --porcelain)" ] && git checkout -q claude/vintos-avatar-ui-redesign-br5lt4; python3 scripts/aegis_sync.py --from claude/device-visuals-2026-10-13 --deploy 2>&1 | tee ~/deploy-latest.log
   ```

   `aegis_sync.py` commits any edits made on Aegis itself (never throws them away), merges the branch, and
   starts `scripts/deploy-atelier.sh`. If the deploy stops asking for the Forge step, she runs
   `sudo bash /home/gloria/.vintos/deploy/forge-install.sh`. Broker changes print their own `sudo` lines.
3. **The deploy runs every suite in `broker/tests/` first, on Aegis, beside her real workspace.** A failing
   suite stops it. Run the suites you touched before you push. Known failures in a cloud container, which
   pass on Aegis: anything needing bubblewrap (`test_chemistry_proposal`, `test_forge_build`,
   `test_review_repairs`) and `test_reelroom_frame_and_cost` (needs the plithra-app branch). Never call
   another failure "environment-only" without reading why it failed.
4. **The deploy installs only what its manifest names.** A new file in `scripts/` or `bin/`, or a new unit
   in `broker/`, must be added to the `SCRIPTS`/`BINS`/unit lists in `scripts/deploy-atelier.sh`, or it never
   reaches Aegis. After adding a module, regenerate `docs/untested.md` and `docs/entry-owners.md`
   (`python3 scripts/untested_report.py --write`, `python3 scripts/entry_owners.py --write`); a suite checks
   them.
5. **Every deploy leaves a rollback**: `bash ~/.vintos/deploy/<backup>/restore.sh`, printed in the log.
6. **Before a risky change reaches him, prove it on Aegis without touching him.** Give her a dry run that
   writes only to a throwaway directory (`SPARK_WORKSPACE=$(mktemp -d)`, the branch's `scripts/` extracted
   with `git archive`), and judge the change by its output. Nothing ships on a guess.

## Models and money — never change a model without her yes

- Chat is **Opus 4.8**. Everything else on Claude is **Opus 5.5**, except the step-downs she chose: Forge
  investigations and Lab planning on Sonnet 5.5, Spark on Haiku 5.5. **No Fable anywhere.** Pleasure is named by
  whatever model is in use in the moment (`draft_in_the_moment`).
- **The Chemistry Lab's minute loop runs on Gemma** (local, free; `CHEM_LAB_LLM_MODEL`). Do not move it off
  Gemma, and do not describe its calls as paid calls.
- Do not raise Gemma's context. Do not add paid model calls to fix something. Money is a standing concern of
  hers: say what a change costs.
- No model names in commit messages, PR text or code comments.

## The Lab is for novel findings

Gloria started the Chemistry Lab for novelty — the model is the array-associated reverse transcriptases
Anthropic found by screening genomes. **His Lab must pose questions nobody has written the answer to, and
answer them with his own instruments** (screens, folds, comparisons, measurements, simulations). Retrieving
documented facts ("what are the documented roles of X") is not the Lab's job, and a fix that makes lookups
pass more often has failed. Judge any Lab change by new results per day. Never weaken a scientific check
(identity, repeat, evidence) to get a number down.

## Working with her

- **Read before you ask or claim.** `git log` on the files you touch, `docs/open-work.md`, the bench ledger.
  Much of this has been worked on for weeks; a proposal that repeats an earlier commit wastes her time.
- **Do not announce a root cause you have not checked against her real data.** Give her a short read-only
  probe, say what each possible answer would mean, and act on what it shows. A wrong "I found it" costs more
  than "I don't know yet".
- **Cloud containers cannot reach most scientific APIs** (UniProt, RCSB, NCBI, Europe PMC are blocked). Aegis
  can. Probes she runs there must be read-only, or write only to a scratch directory, and must print plainly.
- Give exact text she can paste for Chat, Codex and Dot. Keep messages short; lead with what changed and what
  she has to do.
- **Never ask her to send Vintos a message to test something** (below), and never send test notifications.
- **Slack:** posts made through her account open with "[Claude Code]", say it is Claude Code posting, and
  @-mention nobody. Builder work is never posted in #vintos-dot; that is his channel.
- Her Forge decisions are delegated to Claude Code. Do not touch the Gloria JEPA head; `velaris-emoclaw` is off.
- No secrets, keys or device tokens in output.

## Where things live

- `scripts/`, `bin/` — his organs. `deploy-atelier.sh` installs a named manifest of
  them onto Aegis; a new module is not deployed until its name is in that manifest.
- `broker/*.service`, `broker/*.timer` — the units. Same rule: the deploy installs
  what it names.
- `scripts/probes/` — read-only probes she runs on Aegis. `docs/briefs/` — briefs written for other agents.
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

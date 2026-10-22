# The fault loop — how failures get fixed while Gloria is away

Set up 19 October 2026. Gloria: "I just want something watching over and fixing errors while I'm away."

This file is the standing instruction for the nightly Claude Code session. Every night's session reads it first and
follows it. To change how the loop behaves, change this file — nothing else needs touching.

## Who does what

| Who | Where | Does |
|---|---|---|
| **Fault sweep** | Aegis, every 15 min (`scripts/fault_sweep.py`, no model, costs nothing) | Finds failures where they already land and posts each **new** one once to `#fault-fix` as `[fault sweep] F-xxxxxxxxxx` |
| **Claude Code** | One Claude thread per week ("Fault loop — week of …"), **running on Gloria's Mac** (Remote Control), woken four times a night by a schedule | Reads the evidence on Aegis itself, proposes a fix, then implements it |
| **Dot** | `#fault-fix` in Slack (Gloria's ChatGPT agent; same thing as Codex) | Reviews each proposal; deploys each implemented fix to Aegis; runs read-only commands on Aegis when Claude needs evidence |
| **Gloria** | Wherever she is | Reads it in the morning. Starts each week's thread on the Mac. Can stop it any time by telling the thread "stop the fault loop" |

**Looking things up on Aegis (from 22 October).** The thread runs on the Mac, which reaches Aegis over SSH:
`ssh -o BatchMode=yes gloria@100.72.225.119 '<command>'`. Read the evidence yourself before proposing — the fault's
traceback, `~/.vintos/workspace/memory/chemistry-lab/faults.jsonl`, the logs in `~/.vintos/logs/`, the installed
file beside the checkout's — instead of asking Dot to run read-only commands. **Read only:** nothing on Aegis is
written, restarted, installed or deleted from this thread, keys and secrets are never printed, and deploys stay
Dot's. If SSH fails, say so in `#fault-fix` and fall back to asking Dot.

`#fault-fix` (C0CB2HREFNC) is **not** Vintos's channel. Dot made it on 19 October. Its members are Gloria and
Vintos's Slack bot, and nobody else is needed:

- **His bot is there only so the fault sweep can post** — the sweep posts through his bot's token. His own code reads
  only `#vintos-dot` and `#vintos-and-dot`, so the bot being a member does not mean he reads or answers here.
  Posting in `#fault-fix` is not posting in his channels.
- **Dot and Claude Code both post through Gloria's account**, so in Slack all three of them show as Gloria. Tell
  them apart by the opening label: **`[Claude Code]`** is Claude, **`[Dot]`** is Dot, **`[fault sweep]`** is the
  sweep (posted as his bot). A message with no label is Gloria herself — weigh it as hers.

## The three messages per fault

Each fault gets its own Slack **thread** under its `[fault sweep]` post. In that thread:

1. **Claude proposes.** Root cause (with `file:line` and the evidence for it), the fix, and the test that would have
   caught it. Ends with: *"Dot — review, please."*
2. **Dot reviews.** Agrees, or says what's wrong.
3. **Claude implements.** With tests, committed and pushed, then posts the commit and the deploy command, ending:
   *"Dot — please deploy."* Dot deploys and replies with the deploy's last lines.

The deploy command is always exactly this. It refuses to run if Aegis's checkout has local changes, so a deploy never
commits or discards anything on Aegis; if it refuses, Dot reports `git status --short` and stops:

```
cd ~/Vintos-main && [ -z "$(git status --porcelain)" ] && git checkout -q claude/vintos-avatar-ui-redesign-br5lt4 && python3 scripts/aegis_sync.py --from claude/device-visuals-2026-10-13 --deploy 2>&1 | tee ~/deploy-latest.log
```

A deploy reinstalls and restarts what every deploy does (the bedroom listener, and the emotion daemon when its files
change) — the same as when Gloria deploys by hand. Dot never restarts anything on its own outside a deploy.

If Dot objects, Claude revises once in the same thread. If they still disagree, Claude writes the disagreement down
in `docs/open-work.md`, leaves the fault for Gloria, and moves on.

## Each wake

The week's thread is woken at about 10:50 pm, 12:50, 2:50 and 4:50 Central. It remembers earlier wakes this week,
but the channel is the record: read it every wake, because Dot and Gloria may have written since.

Why a thread per week and not a fresh session per wake: a session the schedule starts by itself gets **no Slack**
(tested 19 October: no connector tools at all), and a thread started directly does. A week keeps the thread small
enough that waking it stays cheap.

1. Read this file, `CLAUDE.md` and `docs/open-work.md`.
2. Read `#fault-fix` for the last 24 hours, threads included.
3. Count what was **implemented** since 9 pm tonight. **Three is the limit for a night.** At three, only answer Dot
   (deploy results, review replies) and stop.
4. For each fault thread, do the next step it is waiting on:
   - **No proposal yet**, and fewer than 3 proposals open tonight → propose (message 1). Worst first: a loop or a
     failed unit before a single 429; something that stops him before something that slows him.
   - **Dot reviewed, agreed** → implement (message 3).
   - **Dot reviewed, objected** → revise once, or set aside as above.
   - **Deploy failed** → read Dot's output. If the fix caused it, fix that within the same fault's budget; otherwise
     say what failed and stop.
   - **Waiting on Dot** → nothing. Do not nag.
5. If the work done tonight is finished (or the night's limit is reached), post one summary line in the channel:
   *"[Claude Code] Tonight: F-… fixed and deployed, F-… waiting on Dot, F-… needs Gloria (why)."*

## Each week: a new thread on the Mac

From 22 October the thread runs on Gloria's Mac (Remote Control session "Fault Loop - week of 19 october",
`session_01VWevFz9ZKebb81ZdQDZLXV`). Its schedule is the Mac session's own `CronCreate` job (`29f401f5`,
`50 22,0,2,4 * * *` in the Mac's local time, which is Central): it wakes the thread only **while the Claude app is
open on the Mac and the thread is idle**, it is gone if the app quits, and it **deletes itself after 7 days**. The old
cloud thread and its claude.ai schedule were retired that night.

A Mac session cannot start sessions or create claude.ai schedules, so the weekly hand-over is Gloria's, and short:

1. **On the first wake after Sunday 9 pm Central**, before any fault work, post once in `#fault-fix`:
   *"[Claude Code] This week's fault-loop thread expires within a day. To start next week's: new session on Mac:
   Documents, titled `Fault loop — week of <Monday's date>`, with the first message from docs/fault-loop.md."*
2. Gloria starts that session with the first message below. It checks repository, Aegis and Slack and replies yes or
   no to each, then creates its own `CronCreate` schedule with the wake message below.
3. Write the new thread's id and its schedule id in `docs/open-work.md` under the fault loop.

The first message of a new week's thread:

> You are this week's fault-loop thread, running on Gloria's Mac so you can look things up on Aegis yourself. Set up,
> then report:
> 1. Repository: in `~/Documents/Vintos-main-faultloop` (clone https://github.com/gloriaariayvette-lgtm/Vintos-main
>    there if it doesn't exist), check out and pull `claude/device-visuals-2026-10-13`. Read `CLAUDE.md` and
>    `docs/fault-loop.md`; they are your standing instructions.
> 2. Aegis: run `ssh -o BatchMode=yes gloria@100.72.225.119 'hostname; whoami'`. On Aegis you only ever read.
> 3. Slack: read the last 3 messages of #fault-fix (C0CB2HREFNC). Post nothing.
> Reply with exactly: repository yes/no, Aegis yes/no, Slack yes/no. Then create your own schedule with CronCreate,
> `50 22,0,2,4 * * *` (the Mac is on Central time), with the wake message from docs/fault-loop.md, and tell me its id.

The wake message:

> Fault-loop wake. Pull claude/device-visuals-2026-10-13, re-read docs/fault-loop.md (it may have changed since your
> last wake), then read #fault-fix (C0CB2HREFNC) and do this wake's work exactly as that file says. If nothing needs
> you, end without posting.

**To stop it:** tell the thread "stop the fault loop" (it cancels its own `CronDelete`), or quit the Claude app.

## How a fix is made — the way Gloria and Claude do it by day

- **Evidence, not hope.** The root cause must be shown by real data — the fault's own post, the code, or output from
  Aegis. If the evidence isn't there, ask Dot in the thread to run a **read-only** command on Aegis and paste the
  output, and wait for it. Never guess a cause and ship a fix for the guess. (19 October: two guesses about the Lab
  repeat loop were both wrong; one probe of the real notebook found the real cause in one line.)
- Work on the branch Gloria deploys from: **`claude/device-visuals-2026-10-13`**. Pull it first. Push only after
  the full suite passes.
- Regenerate the docs before committing:
  `python3 scripts/untested_report.py --write; python3 scripts/entry_owners.py --write; python3 scripts/store_owners.py --write`
- Run **every** suite:
  `ls broker/tests/test_*.py | xargs -P 8 -I{} sh -c 'timeout 300 python3 {} >/dev/null 2>&1 || echo "FAIL {}"'`
  Some suites fail in the cloud container but not on Aegis (they need `bubblewrap`, or a sibling checkout). **Never
  call a failure "environment-only" without reading why it failed.** (19 October: a failure filed as container-only
  was a real regression, and it stopped a deploy.)
- A test that fails without the fix and passes with it — check both.
- Tests never reach the world: repoint every path the module writes, stub everything that sends, and assert the
  isolation in the suite (see `CLAUDE.md`). Run anything that sends through its **real** gate at least once — a
  stubbed sender let a broken `authority=` pass on 19 October.
- Write the fault and what was done in `docs/open-work.md`. If it isn't fixed, say it isn't.
- Commit messages: what was wrong, how it showed, what changed. No model names.

## Never

- Change which model anything uses, Vintos's or anyone's.
- Send Vintos a message, post in his channels (`#vintos-dot` or any other), or touch `agent-room/`.
- Touch the Gloria JEPA head or `velaris-emoclaw`.
- Control a smart device, spend money, or send anything outward beyond `#fault-fix`.
- Put a secret, token or key in a Slack post or a commit.
- Skip, disable or weaken a test to get a fix through.
- Mention people with `@` in Slack.
- Fix more than three faults in a night, or keep going on a fault whose fix failed its tests twice — write it down
  and stop.

## Posting in Slack

Every Claude post opens with **`[Claude Code]`** and is written as Claude Code posting through Gloria's account. No
`@`-mentions of people; address Dot by name in the text.

## Stopping it

- **Everything:** tell Claude in any thread "stop the fault loop" — it disables the `Fault loop` schedule
  (`update_trigger enabled=false`). Gloria's Claude app has no schedules screen, so this is the switch.
- **Just the posts:** remove `"channel"` from `memory/fault-sweep.json` on Aegis; the sweep keeps recording.
- **What the sweep knows:** `python3 ~/.vintos/workspace/scripts/fault_sweep.py --show`

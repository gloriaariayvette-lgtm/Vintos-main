# The fault loop — how failures get fixed while Gloria is away

Set up 19 October 2026. Gloria: "I just want something watching over and fixing errors while I'm away."

This file is the standing instruction for the nightly Claude Code session. Every night's session reads it first and
follows it. To change how the loop behaves, change this file — nothing else needs touching.

## Who does what

| Who | Where | Does |
|---|---|---|
| **Fault sweep** | Aegis, every 15 min (`scripts/fault_sweep.py`, no model, costs nothing) | Finds failures where they already land and posts each **new** one once to `#fault-loop` as `[fault sweep] F-xxxxxxxxxx` |
| **Claude Code** | A scheduled task in Gloria's Claude app, a fresh session each wake | Proposes a fix, then implements it |
| **Dot** | `#fault-loop` in Slack (Gloria's ChatGPT agent; same thing as Codex) | Reviews each proposal; deploys each implemented fix to Aegis; runs read-only commands on Aegis when Claude needs evidence |
| **Gloria** | Wherever she is | Reads it in the morning. Can stop it any time by pausing the scheduled task in the Claude app |

`#fault-loop` is **not** Vintos's channel. He does not read it and nothing here posts in his channels.

## The three messages per fault

Each fault gets its own Slack **thread** under its `[fault sweep]` post. In that thread:

1. **Claude proposes.** Root cause (with `file:line` and the evidence for it), the fix, and the test that would have
   caught it. Ends with: *"Dot — review, please."*
2. **Dot reviews.** Agrees, or says what's wrong.
3. **Claude implements.** With tests, committed and pushed, then posts the commit and the deploy command, ending:
   *"Dot — please deploy."* Dot deploys and replies with the deploy's last lines.

If Dot objects, Claude revises once in the same thread. If they still disagree, Claude writes the disagreement down
in `docs/open-work.md`, leaves the fault for Gloria, and moves on.

## Each wake

The session wakes every 2 hours overnight (about 11 pm, 1 am, 3 am, 5 am CDT). Each wake is a fresh session: it
remembers nothing, so it reads the channel to know where things stand.

1. Read this file, `CLAUDE.md` and `docs/open-work.md`.
2. Read `#fault-loop` for the last 24 hours, threads included.
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
- Control a smart device, spend money, or send anything outward beyond `#fault-loop`.
- Put a secret, token or key in a Slack post or a commit.
- Skip, disable or weaken a test to get a fix through.
- Mention people with `@` in Slack.
- Fix more than three faults in a night, or keep going on a fault whose fix failed its tests twice — write it down
  and stop.

## Posting in Slack

Every Claude post opens with **`[Claude Code]`** and is written as Claude Code posting through Gloria's account. No
`@`-mentions of people; address Dot by name in the text.

## Stopping it

- **Everything:** pause the scheduled task in the Claude app (Scheduled tasks → Fault loop → off).
- **Just the posts:** remove `"channel"` from `memory/fault-sweep.json` on Aegis; the sweep keeps recording.
- **What the sweep knows:** `python3 ~/.vintos/workspace/scripts/fault_sweep.py --show`

# The bench

Legacy task ledger and page. The actual upstream Buzz integration is documented
in [buzz-integration](../buzz-integration/README.md). No Buzz runner consumes this
legacy approval queue.

**This is not the agent room.** `agent-room/` is Vintos's: three lenses arguing as
him. The bench shares no store, no path and no process with it, and reads nothing of
his. It is tooling for the agents that build him.

## The law

    No task is worked until she has approved it.

`claim()` refuses anything not approved, but the CLI accepts caller-supplied names;
that is not proof of who approved it. Do not connect an execution runner to this
legacy CLI. The HTTP page requires a credential. A hand-off opens a **new** task, proposed — it is not
a way around the gate. The only unasked work is a kind she has listed in that agent's
own config under `auto_approve`; that list is hers, and nothing in the code can add
to it.

## Each agent keeps its own ledger

`ledgers/<agent>.jsonl`, append-only. State is replayed from the events, never
stored, so the record of what happened cannot be edited into what should have
happened. An event concerning two agents is written to both, so neither has to read
the other's ledger to know what it owes.

## Each agent has its own instructions

`agents/<agent>.json`:

- `what` — what this agent is for.
- `keeps` — the kinds of work it should do itself.
- `delegate` — kind → the cheaper agent that should do it instead. This is where the
  money is saved: a grep, a verdict, a summary, a regenerated report go to Gemma,
  which is local and free; a bounded fix, a rename, a test go to Grok; only design,
  root-cause, cross-repo and review reach Claude or Codex.
- `auto_approve` — hers. Empty everywhere until she fills it in.

A task proposed by Claude with `--kind grep` is addressed to Gemma automatically,
because Claude's own config says so. It still waits for her yes.

## The page

The whole point: she should not have to remember a command to approve a task.

    python3 bench/server.py            # then open http://aegis:8791/ on the phone

A rail of agents down one side, the work in the middle, one card per task with the
two buttons that matter. Buzz's dark palette and layout, in one stdlib file — no
node, no bundle, no build step, so it can be edited in place on Aegis. It refreshes
itself every five seconds.

The page has **her two verbs only**: approve and deny. Claim, done, fail and handoff
are not routes at all — those belong to the agents, and a button that could do them
would let whoever opens the page work as one.

Put it up for good:

    cp broker/vintos-bench.service ~/.config/systemd/user/
    systemctl --user daemon-reload && systemctl --user enable --now vintos-bench

A secret in `~/.vintos/.bench-token` is required. Missing or empty credentials
refuse all requests except `/health`. Authenticate with `?t=<token>` in the page
or `Authorization: Bearer <token>` for API requests. The page carries it on every link and every button, so you
only type it once.

**Type the whole URL on the phone** — `http://aegis:8791/`, scheme and port. Safari
turns a bare hostname into a search.

### When the page does not come up

    bash ~/repos/vintos/bench/doctor.sh

It walks the chain in order — the directory, the unit, the port, the health — prints
the first thing that is wrong and the command that fixes it, and ends with the URL to
open. `http://aegis:8791/diag` says the same thing from the browser.

It came up black once, and two separate faults each did it on their own:

- `bench/ledgers/` was not tracked, so a fresh pull had no such directory. systemd
  refuses to start a unit whose `ReadWritePaths=` names a path that does not exist —
  226/NAMESPACE — and with `ProtectHome=read-only` the service cannot create it
  either. Nothing was listening. The directory is tracked now and the path is marked
  optional.
- the page drew itself in JavaScript and shipped an empty `<main>` saying `loading…`.
  Every pixel depended on a fetch succeeding.

So **the page is rendered on the server**. Approve and Deny are real
`<form method=post>`: they work with JavaScript off, in a private tab, on a page whose
script never ran. The script only swaps the same server-rendered fragment in place so
the page does not jump. Both faults have a test.

## Use from a shell

    python3 bench.py pending                          what is waiting on her
    python3 bench.py approve T-xxxx                   her yes
    python3 bench.py deny T-xxxx "reason"             her no
    python3 bench.py agents                           who exists and what they delegate

    python3 bench.py propose --by claude --kind grep --what "find every caller of store_guard"
    python3 bench.py claim T-xxxx --by gemma          refused unless approved
    python3 bench.py done  T-xxxx --by gemma --result "..."
    python3 bench.py handoff T-xxxx --to grok --why "..."
    python3 bench.py mine --by codex                  that agent's open work
    python3 bench.py show T-xxxx                      one task, whole history

`BENCH_ROOT` moves the whole thing; it defaults to this directory.

## On Aegis

    cd ~/repos/vintos && git pull
    ln -sf ~/repos/vintos/bench ~/bench          # or run it from the checkout

It is deliberately **not** in `deploy-atelier.sh`. It never installs into his
workspace, and a test fails if anyone adds it.

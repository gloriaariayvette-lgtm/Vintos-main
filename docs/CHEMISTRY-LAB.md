# Vintos Chemistry Lab

The Chemistry Lab is a visible, auditable creative space for computational
protein and molecular play. It is deliberately separate from the Atelier:

- it never reads or writes `memory/atelier/`;
- it has no seal, private audience, visit capability, or stratagem route;
- its records live under `memory/chemistry-lab/` and survive switching it off;
- the Tune switch controls desired activity, not the existence of its history.

## Runtime shape

`vintos-chemistry-lab.service` supervises a small worker. “Continuous” means the
worker is continuously eligible to take another short, checkpointed turn. It
does not own the GPU continuously. Each turn asks `compute_admission` for the
background slot; a foreground turn or another background organ makes it yield.
Switching the Lab off prevents the next turn and preserves all records.

Every Gemma turn receives a bounded, attributed Vintos context made from an
excerpt of `SOUL.md`, `SELF-MODEL.md`, Living Trajectory, and recent Lab notes.
`context-receipts.jsonl` records source paths, sizes, and hashes so “he received
his context” is verifiable without duplicating those documents into the Lab.

## Active loop

The installed loop is `orient -> browse -> embed -> reflect`:

1. Aegis Gemma chooses a small protein-space question in Vintos's voice.
2. The Lab makes a bounded, read-only UniProtKB query and records the exact
   accessions and metadata it saw.
3. The separately installed ESMC-600M adapter writes a content-addressed,
   model-derived representation beneath the Lab artifact store. A deterministic
   adapter also writes the source-backed UniProt descriptor as text; self-review
   embeds that text in the house's Nomic space. The ESM vector remains lineage
   and is never compared directly with Nomic.
4. Gemma writes a notebook observation, with factual observation and imaginative
   reading in different fields.

Installation alone never makes a tool available. The authority for that is
`tool-probes.jsonl`, an append-only ledger written by `chemistry_probe.py`: one row per
measurement, carrying the tool, host, probe version, when it was measured, when the
receipt expires, a typed outcome, a digest of the evidence, and a typed failure. It never
carries command output, and so cannot carry a secret out of an environment into a visible
ledger. `tool-inventory.json` is now only a materialized view of that ledger — regenerated,
safe to delete, and read by nothing. `tools_status()` reads the ledger and decides in code,
so a hand-written inventory file has no power at all.

Aegis instruments are smoke-tested directly. The Mac's cannot be: this side's doorway
carries four named actions and will not widen to run probes, so a Mac instrument is proved
only by a completed run that explicitly names *and* hashes it. What `mac.status()` says
about its own instruments is filed as `reported_by_host_not_smoke_tested` and grants
nothing — a host's word about itself is a claim, not a measurement. Nothing filters the
experiment list: the frontier lens is shown the instrument states beside it and may still
choose. Silencing the Lab is not the remedy for having overstated it.

## Taste, and what it may not be made of

Correctness has its own ledger. Taste is the other one: the folds he returns to, the
molecules he finds elegant, the parameters he keeps moving, the surprises he writes about.
`chemistry_taste.py` reads no grade and cannot — a wrong answer he keeps returning to is
still taste, and a right answer he never revisits is not.

A Lab like this can manufacture its own preferences, so three loops are closed. A generated
`what_surprised_me` makes a *candidate*, never score, and becomes taste only when an
independent choice arrives for the same thing. A key named in the taste block that preceded
a choice cannot be reinforced by that choice — it is recorded as `echo_of_injected_taste`;
since scores decay, a favourite falls out of the block, becomes eligible again, and can be
re-earned, so the cycle limits itself rather than freezing. A repeat must name the eligible
observation it repeats, and following a prior `next_question` counts only when the later
session actually names its predecessor.

Nothing is discarded: every observation lands in `taste-observations.jsonl` with its
eligibility, the refused ones included. A ledger that silently drops what it refused cannot
be audited for what it refused.

## Evidence and collision law

An ESM protein vector and a nomic text vector do not inhabit a shared coordinate
system merely because both are called embeddings. Raw cross-model cosine is
therefore forbidden. `collision-adapter.jsonl` translates only source-backed
protein descriptors into attributed text and names that transformation. The
self-review organ may then encounter those records like any other textual source.
A resemblance may open a speculative reading; it is never biological evidence
or lived experience. Gemma reflections do not enter the adapter.

## Computational-only perimeter

This room produces in-silico artifacts and taste, not wet-lab action. It does
not provide synthesis instructions, order material, contact laboratories,
optimize pathogens/toxins, design against a human target, or claim that a
generated sequence is functional or safe. Those are different capabilities
and cannot emerge by widening a query or installing another adapter.

## Instrument boundary

- ESMC representation runs on Aegis per admitted job rather than resident.
- Structure prediction, ProteinMPNN, RFdiffusion-family tools, and OpenMM are
  separately installed instruments whose outputs remain unvalidated
  computational artifacts until a Lab session interprets them.
- The Mac bench has a Lab-only SSH doorway, separate configuration, visible
  ledger, and a named-experiment allowlist. The bench attests that an experiment
  runs under macOS isolation with no network, home directory, or durable child
  writes, and returns that attestation per run; each grade row records it as
  `host_attested`. This repository holds no independent evidence for that
  boundary — the 2026-09-12 five-seed receipts cover the Atelier seeds through
  `qremote.py`, not this bench — so nothing here calls it verified.
- This side of the doorway carries four actions: `status`, `ledger`, `run`,
  `reading`, and refuses anything else at the point of send. The bench's own door
  is wider: it accepts `action: "code"`, which writes a new executable experiment.
  The scheduled Lab cannot reach it, but that is a near-side guard, not a property
  of the door. Free creation needs its own authority; see `docs/open-work.md`.
- QPanda and the molecular circuit bench are connected through that doorway.
  VQNet, Mac ESMC, pyChemiQ, and Foundry remain available for deliberate bench
  expansion; installation is not represented as automatic use.

## Scheduled Lab sessions

`vintos-chemistry-session.timer` offers one session each day at 03:17, with a
small randomized delay. If the Tune switch is off, the oneshot exits without a
model call or Mac contact. When on, it:

1. asks the Mac which named experiments are actually available;
2. gives one rotating frontier lens (Claude, Sol, then Grok) Vintos's attributed
   Lab context and lets it choose one named experiment and a question;
3. runs that experiment under the Mac isolation boundary and preserves the full
   result on both sides;
4. lets local Aegis Gemma leave Vintos's reading and next question;
5. appends the session to the visible Lab notebook and session ledger.

When conversation arrives mid-session the reading is preempted, and the experiment has
already finished. That result is not lost and not re-run: the session records the debt in
`reading-owed.json`, and the next admitted occasion — the next scheduled session, or the
daemon's reflect phase — interprets the result that was preserved. It costs no bench time.
The lens index does not move; the lens already had its turn, and the notebook records the
later reading as a later reading. A debt that ages out is marked `expired_unread` and stays
in the open list: retiring it would file "he never got to this" under "handled".

There is no automatic fallback from one frontier lens to another inside a
session: refusal or failure is kept as a held occasion, not silently rewritten.
The next offered session advances to the next lens. The scheduled path cannot
submit arbitrary code: its doorway carries four named actions and refuses the
rest, and a lens may choose only an experiment the Mac already offers. The bench
itself can still be handed code by something else, which is a different door.

## Ran, and good

These are two facts and the Lab keeps them apart. A Mac experiment that completes,
returns numbers and writes its ledger row is *operational*; whether its variational
energy beat the Hartree-Fock reference is a separate verdict. The first graded H2
optimisation completed cleanly and returned -0.478030 Ha against a Hartree-Fock
reference of -1.116999 Ha and an exact energy of -1.137306 Ha: the instrument
worked, and that particular shallow ansatz was not scientifically good.
`experiment-grades.jsonl` now says exactly that.

`chemistry_grade.py` computes the verdict on Aegis from the numbers the bench
returned. The bench reports its own error and recovered correlation; those are kept
as `host_reported` and decide nothing, because a host does not grade itself. Every
curve point is graded and the row carries a named aggregate. `execution_state` is
recorded separately from `aggregate_accuracy`. A variational energy below the exact
ground state is checked before any success outcome and recorded as
`INVALID_BELOW_EXACT`, since that is a bug rather than a triumph. A negative
recovered correlation is a correct reading, not a malformed one — it is how "worse
than Hartree-Fock" looks on that scale. Rows are keyed `(run_id, grader_version)`,
so a better grader may revisit an old run without erasing what the old one said.

The verdict reaches his reading before he writes it, so a poor answer arrives as a
poor answer, and recent grades enter his Lab context. The bench's own source stays
on the Mac; `docs/chemistry-bench-reconciliation.md` says how it is brought under
version control, and why nothing here reimplements it.

The tools never own the conversational path. Background use remains subordinate
to compute admission, and installing an instrument does not authorize a new
external effect.

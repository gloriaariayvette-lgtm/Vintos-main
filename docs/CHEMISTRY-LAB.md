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

The installed protein loop is `orient -> browse -> embed -> reflect`. When the separately
commissioned genomics lane is due, that reflection continues once through
`genome -> genome_reflect` before returning to `orient`:

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

### Optional genome-mining campaign

Genome mining is a third lane beside protein browsing and environmental
microbiology. It is offered without a seeded enzyme, organism, or expected
answer. One return performs one bounded source step, so a campaign can continue
through the existing journal and frontier review without becoming the Lab's
default direction.

The discipline follows the public Anthropic ART report at a scale this house can
actually support: reproduce an established result first; map an exact protein to
its source nucleotide record; inspect a bounded annotated neighborhood and its
primary DNA; classify known domains; allow an anomalous neighbor, arrangement,
or non-coding pattern to open a follow-up; then try to eliminate the candidate
with ordinary annotations, related loci, counterexamples, and literature.
Most candidates should be set aside. A first anomaly is explicitly held out of
the automatic Forge-report path. Only a later multi-source survivor review may
form a sourced report for human review, and that report is not a discovery claim.

`ncbi_protein_context` retrieves one exact GenPept record and its provider
`coded_by` mapping. `ncbi_neighborhood` accepts only that sourced nucleotide
accession and one-based coordinates, retrieves at most 5 kb on either side,
retains bounded provider feature annotations, and runs a local repeat screen.
The screen expands frequent 10-18 nt seeds with at most one or two mismatches,
requires three or more roughly regularly spaced copies, and folds overlapping
seed views of the same array together. It establishes neither repeat boundaries
nor significance, novelty, expression, or function. `interpro` returns at most
eight known-family/domain annotations for an exact sourced UniProt accession.

This is method resemblance, not a reproduction of Anthropic's infrastructure.
Their campaign searched roughly 1.9 billion preclustered metagenomic protein
families with HMMER, MMseqs2, a 58-session harness, worker/supervisor/curator/
editor roles, and a private programmatic database assembled from Logan, ENA,
JGI, and NCBI. Vintos has the staged reasoning pattern and public bounded source
doors; he does not have that database, scale, or wet-lab validation. IMG/VR is a
public browsable and bulk-download source rather than an anonymous bounded API.
Aegis is the selected local store for the 40.16-GiB compressed high-confidence
v4.1 bundle. Its primary installation route is the official public DOE NERSC
unrestricted-only mirror: metadata, nucleotide sequences and proteins, totaling
42,362,218,187 bytes compressed. It requires no account. `imgvr_store.py` pins
the mirror filenames and byte sizes, downloads with resume support over TLS,
records local SHA-256 receipts, requires 250 GiB free, builds a local
metadata/full-text and nucleotide-offset SQLite index, and builds a protein-family
MMseqs2 index. NERSC does not publish independent digests on this directory, so
the receipt distinguishes the pinned provider metadata from the locally computed
hashes. The JGI session-token/provider-MD5 route remains optional. The planner
sees no IMG/VR query forms until all three local indexes report ready.
The Aegis installation completed on 2026-09-24. The deployed production wrapper
commissioned metadata, exact multi-contig segment selection, a 120-base slice,
and a sourced GenBank-to-IMG/VR protein search. The latter returned three bounded
hits in 209.9 seconds and retained the non-novelty/non-function truth label.

Once ready, the bounded doors are: metadata terms across the provider's ecology,
taxonomy, host and origin fields; exact sourced UViG nucleotide slices of at most
12 kb (with an exact returned segment header for multi-contig records); and a
sourced 20–2,000-residue protein similarity query returning at most
eight hits. Results retain the release and coverage in their receipt. A match,
annotation or missing match establishes neither novelty nor function.

Installation alone never makes a tool available. The authority for that is
`tool-probes.jsonl`, an append-only ledger written by `chemistry_probe.py`: one row per
measurement, carrying the tool, host, probe version, when it was measured, when the
receipt expires, a typed outcome, a digest of the evidence, and a typed failure. It never
carries command output, and so cannot carry a secret out of an environment into a visible
ledger. `tool-inventory.json` is now only a materialized view of that ledger — regenerated,
safe to delete, and read by nothing. `tools_status()` reads the ledger and decides in code,
so a hand-written inventory file has no power at all.

An Aegis probe must run the named entry point on the smallest real input and prove it with
a parsed result. Importing `torch` is not a ProteinMPNN smoke test. The fixed commissioning
worker therefore requires: an ESMC vector; an OpenMM integration step and energy; a
ProteinMPNN FASTA containing a designed sequence; RFD3 metadata plus a structure artifact;
and an MCP server tool listing plus one dispatched status call. ESMFold loads the cached
checkpoint through Transformers on CUDA and must return a PDB. Exiting zero is never passing.

A passing receipt holds a month; a failure or an unconfigured probe holds a day and is
re-asked. The scheduled session refreshes only expired receipts, inside the background slot,
so this is a real monthly measurement that yields like everything else — an unrefreshed
instrument simply reads stale. The Mac's cannot be refreshed by the scheduled doorway:
it carries four named actions and will not widen to run probes. A separate fixed
`chemistry_mac_probe.py` commissioning surface accepts only five instrument names and emits
a hash-bound run record for ingestion by `chemistry_probe.py --record-run -`; failures are
receipts too and never grant availability. What `mac.status()` says
about its own instruments is filed as `reported_by_host_not_smoke_tested` and grants
nothing — a host's word about itself is a claim, not a measurement. Nothing filters the
experiment list: the frontier lens is shown the instrument states beside it and may still
choose. Silencing the Lab is not the remedy for having overstated it.

## The visible body

The Lab is not a switch with a JSON history behind it. The `LAB` pane reads bounded,
secret-guarded endpoints — notebook, sessions, grades, taste, one run's curve, and the
structure inventory/view doors — and shows
each session with **two marks, never one**: how the instrument behaved, and whether the
answer was any good. A run that completed and answered badly must not read as a run that
worked, and this is where that distinction becomes visible rather than merely recorded.

Energy curves are hand-rolled inline SVG; the client carries no charting library and this
did not add one. Every value drawn passes a finite check first, curves are capped, and the
huge Mac payload stays on the server — the page gets state, not the artifact. The endpoints
recompute nothing: a curve is read from the grade that was already written.

PDB and gzipped/plain mmCIF artifacts already produced beneath the Lab artifact root may be
opened in a small three.js structure gallery. The server resolves opaque inventory ids, enforces
path and byte/atom bounds, and returns parsed coordinates rather than filesystem access. The
phone uses its existing three.js bundle to draw atoms and a backbone trace. Every view remains
labelled as a computational structure artifact, not biological fact.

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

Taste is kept in the terms the choice was actually made in. A molecule, an ansatz, an
optimizer or a fold accrues under its *value* — choosing `uccsd` twice is a preference for
that ansatz, while recording a preference for the word "ansatz" would say nothing. An
ordinary parameter accrues by name, and only counts as moved when its value actually
changed: recurrence of the name is not movement. Accessions accrue from the browse loop, and
only the ones a reflection actually writes about — a record he was handed is not a
preference. The ledger is read-modify-written by the session, the daemon and the decay pass,
so it holds its own organ lock; without it the last writer silently drops the others' bumps.

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

## From a Lab occasion to an instrument

The Lab can invent a game; the Forge can make it durable; neither installs the other's ideas.
The road between them is staged and gated at every step, and it starts before the Lab:

`chemistry_spark.py` writes `spark-feed.jsonl`, one row per occasion that may legitimately
raise a spark. Eligible only if the text is a `next_question` from a completed session or
from an owed reading that was actually paid, with a run behind it — never a speculative
reflection, never a `what_surprised_me`, never a question that hands back something his own
taste block had just named. Each row carries the session, the run, the grade and the context
receipt, because a want that cannot name the occasion it came from is not Lab provenance.
Refusals are written with their reason: a feed that silently drops what it refused cannot be
audited, and this one decides what may reach the Forge.

`from_lab()` reads structured rows now as well as prose, and `gather()` carries their
provenance onto the spark row; `adopt()` hands it to the want door. The reader is still
pointed only where she points it — `chemistry_spark.py configure` is the explicit act.
The feed itself refreshes at the write site after a completed session or a paid owed
reading. It does not depend on somebody remembering a second command after the occasion.

Then `chemistry_proposal.py`: `idea -> bounded_interface -> canary_passed -> offered_to_forge`,
one predecessor each, because a staged approval that can be entered halfway is not staged. An
idea must cite an eligible occasion. An interface must name one function and a typed, bounded
parameter schema — there is no parameter type that accepts code. A canary must actually run
under `isolated_exec`, and its test must contain a real assertion and actually call the
proposed function. Only then may it be offered to `skill_forge.propose()`, against a live want
**she already has** whose source is the `lab` spark.

The Lab does not create that want, does not approve, and does not install. If there is no such
want, the Forge refuses and the refusal is the record rather than something to route around.

## Three lenses, one artifact

Off by default. Switched on, every seventh offered session spends itself not on the bench but
on one artifact he already has: all three lenses receive the byte-identical prompt — the same
preserved result and the same base Vintos context — independently, blind only to one another's
answers. The prompt's hash is on the row so that identity is checkable rather than claimed.

All three paid calls are reserved before the first is made. A third reservation refused after
two calls would leave a two-lens "divergence" that reads like a finding and is not one; if any
reservation is refused, the reservations taken are released and no lens is spent.
Reservations use the actual provider/model buckets and are claimed by the router rather
than charged again. Each lens separately enters background compute admission. A lens that
yields before provider contact returns its unused reservation; any partial result is
`completed_with_held_lenses`, never the unqualified `completed`.

Three readings that agreed would be a fact about how these models are trained. Three that
diverge are three questions, and the questions are the output: `agreement` is recorded as
`not_computed` and nothing votes, scores or synthesises. A lens that refuses is held and never
replaced by another provider. The recorded identity hash binds both system and user parts of
the common prompt.

## Computational-only perimeter

This room produces in-silico artifacts and taste, not wet-lab action. It does
not provide synthesis instructions, order material, contact laboratories,
optimize pathogens/toxins, design against a human target, or claim that a
generated sequence is functional or safe. Those are different capabilities
and cannot emerge by widening a query or installing another adapter.

## Instrument boundary

- ESMC representation runs on Aegis per admitted job rather than resident.
- ProteinMPNN, RFdiffusion-family tools, and OpenMM are separately measured
  instruments whose outputs remain unvalidated
  computational artifacts until a Lab session interprets them.
- ESMFold structure prediction is measured separately through its cached Transformers
  checkpoint; it does not depend on the MCP package's broken fair-esm/OpenFold wrapper.
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
- QPanda and the molecular circuit bench are connected through that doorway. QPanda,
  VQNet, Mac ESMC, pyChemiQ, and Foundry also have fixed functional commissioning probes.
  A receipt proves the named instrument ran; it does not add a named experiment to the
  bench allowlist. Those are separate integration acts.
- Evo 2 is a separate Aegis instrument and does not accept arbitrary sequence input. Its
  public action fetches one bounded window from a fixed non-human reference allowlist,
  verifies accession, taxon, alphabet and digest, and compares the reference likelihood to
  one deterministic single-base substitution. It has no generation action. A likelihood
  delta is a model preference, never a functional-effect claim.
- Evo 2 7B BF16 and resident Gemma do not fit together on Aegis's 16 GB GPU. Evo therefore
  runs only in an admitted background turn while holding the Gemma watchdog lock; it unloads
  Gemma, runs one bounded comparison, and restores Gemma in `finally`. Both that restoration
  and the ordinary crash watchdog use `aegis-gemma-load.sh`: the exact `Q4_0` artifact is
  loaded under the stable `google/gemma-4-12b-qat` identifier. Thinking is not a load-time
  property in LM Studio, so every Aegis text caller goes through the shim's native Chat API
  adapter, which sends `reasoning: "off"` and refuses a reply reporting reasoning output.
  Genomic turns are occasional rather than continuous.
  The isolated environment is `~/.vintos/tools/chemistry-lab/evo2`; the checkpoint cache is
  `~/.vintos/tools/chemistry-lab/checkpoints/huggingface`. Availability still comes only
  from a completed reference/variant score recorded by `chemistry_probe.record_evo2_run()`,
  never from those paths existing. `chemistry_lab.py evo-on|evo-off` commissions or pauses
  this lane; the main Tune switch remains authority for the whole Lab.

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

When a dated protein-design MCP probe is available, the lens may choose one
additional orchestrated instrument call before the named Mac experiment. Native
MCP routes are `score_stability` for a sourced 20–160-residue sequence and
`suggest_hotspots` for an exact PDB ID already present in a source receipt.
`predict_structure_boltz` and `predict_complex` map the MCP intent to the already
commissioned NVIDIA Boltz-2 gateway and share its six-attempt daily cap. Every
route keeps the full result as a mode-0600 artifact, appends Lab provenance, and
gives the reading a bounded excerpt. These are predictions or structural
suggestions, not measured stability or experimental validation.

The orchestrator also records the status of all nineteen advertised MCP names.
Broken package wrappers do not enter the planner menu merely because the server
lists them. Existing commissioned ESMFold, ProteinMPNN, RFD3 and OpenMM paths
remain the house route for their corresponding work; composite and path-based
tools await bounded artifact handoffs, and PyRosetta operations remain unavailable.

### Local-to-frontier bridge

The frontier lens already received a bounded Lab excerpt through `lab_context()`; it was
the last three notebook rows inside the same attributed context budget as SOUL, self-model,
trajectory, taste and grades. What was missing was proof that a particular local finding
survived that excerpt and affected a later plan.

`chemistry_frontier_bridge.py` closes that gap without letting Gemma grade itself.
Completed reflections receive an event-sourced routing assessment based on independent,
inspectable signals: whether the source query really succeeded, whether source accessions
are new to this ledger, lexical contact with the Living Trajectory, and an already-written
cross-organ collision. Repeating a question subtracts priority. `interest_score` means
only "carry this forward sooner"; it is neither biological truth nor importance.

Up to four unsatisfied flagged entries (at most 1,800 characters) are appended only to a
frontier session's context. Their IDs and block hash enter the context receipt. The returned
plan may name only IDs it was offered and is instructed to name one only if it affected the
choice. `frontier-surfaces.jsonl` then records prompt delivery separately from frontier
acknowledgment. The acknowledgment is a model attestation, not proof of comprehension.
Three deliveries without acknowledgment raise `backlog_bug`; nothing is silently retired.

An owed reading is paid before another experiment is started, and if it cannot be paid the
session ends there: the house was busy or the reader faulted, and neither is a reason to
spend the bench again on top of an unread result. The lens does not advance — it never had
its turn.

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

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

## Phase 1: a complete light loop

The installed loop is `orient -> browse -> reflect`:

1. Aegis Gemma chooses a small protein-space question in Vintos's voice.
2. The Lab makes a bounded, read-only UniProtKB query and records the exact
   accessions and metadata it saw.
3. Gemma writes a notebook observation, with factual observation and imaginative
   reading in different fields.

No heavy model is claimed present. The status endpoint reports ESMC, structure
prediction, ProteinMPNN, QPanda and quantum chemistry as unavailable until a
real adapter is installed and measured.

## Evidence and collision law

An ESM protein vector and a nomic text vector do not inhabit a shared coordinate
system merely because both are called embeddings. Raw cross-model cosine is
therefore forbidden. A later collision adapter may translate source-backed
protein descriptors into text and embed that text with the house's nomic model,
or use a separately trained and evaluated bridge. Either route must identify
the transformation. A resemblance may open a speculative reading; it is never
biological evidence or lived experience.

## Computational-only perimeter

This room produces in-silico artifacts and taste, not wet-lab action. It does
not provide synthesis instructions, order material, contact laboratories,
optimize pathogens/toxins, design against a human target, or claim that a
generated sequence is functional or safe. Those are different capabilities
and cannot emerge by widening a query or installing another adapter.

## Later measured adapters

- ESMC representation on Aegis, loaded per admitted job rather than resident.
- Structure prediction after an actual compatibility and peak-memory probe.
- ProteinMPNN / RFdiffusion-family tools in isolated environments, with their
  output remaining unvalidated computational artifacts.
- QPanda and quantum chemistry through a Lab-specific Mac bridge. The existing
  Atelier quantum capability is not reused.

Heavy package/model installation is a separate deployment because it downloads
large weights and changes host resource behavior. The control plane, notebook,
context provenance, source browsing, and off switch do not depend on it.

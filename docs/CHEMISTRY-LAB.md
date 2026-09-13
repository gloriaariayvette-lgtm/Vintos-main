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
   model-derived representation beneath the Lab artifact store. The full vector
   is not treated as a fact about function, nor compared directly with nomic.
4. Gemma writes a notebook observation, with factual observation and imaginative
   reading in different fields.

The status endpoint reads dated smoke-test receipts from
`tool-inventory.json`. Installation alone never makes a tool available.

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

## Instrument boundary

- ESMC representation runs on Aegis per admitted job rather than resident.
- Structure prediction, ProteinMPNN, RFdiffusion-family tools, and OpenMM are
  separately installed instruments whose outputs remain unvalidated
  computational artifacts until a Lab session interprets them.
- QPanda, VQNet, quantum chemistry, Mac ESMC and Mac RFdiffusion live in
  independent arm64 environments. A future Lab-specific remote session may use
  them; the existing Atelier quantum doorway is never reused.

The tools never own the conversational path. Background use remains subordinate
to compute admission, and installing an instrument does not authorize a new
external effect.

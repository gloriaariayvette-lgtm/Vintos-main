# The Mac Chemistry bench — reconciliation, not replacement

The Chemistry bench lives on the Mac at `/Users/kevin/qlab/`, and its source is **not** in
this repository. It is real and further along than this repository knows: as of the Mac's
local commit `db99249` the `molecule` experiment already returns a Hartree–Fock reference,
an exact FCI energy, a variational energy, bond-length curves, source hashes, and an
OS-isolation receipt.

Nothing on the Aegis side should re-implement it. An earlier plan proposed shipping a
replacement molecular engine from here; that would have been a second, blind copy of
working code, and it was dropped. What Aegis was actually missing was a grader, and that
is what `scripts/chemistry_grade.py` now is.

## What Aegis relies on

The doorway (`scripts/chemistry_mac.py`) sends JSON over SSH and reads JSON back. The
scheduled Lab uses four actions only: `status`, `ledger`, `run`, `reading`.

A `run` reply is parsed by the grader at `run.result.results[]` — a list of per-geometry
points. The grader resolves each point's energies by alias and records which key it used
in `field_map`, so a bench rename shows up in the ledger as a changed field name rather
than as a silently ungraded run. Aliases currently accepted:

| quantity | keys tried, in order |
|---|---|
| variational energy | `vqe_energy`, `vqe`, `energy_vqe`, `vqe_energy_hartree`, `optimized_energy`, `lowest_energy`, `energy` |
| Hartree–Fock | `hartree_fock_energy`, `hartree_fock`, `hf_energy`, `hf`, `hartree_fock_energy_hartree`, `reference_energy` |
| exact / FCI | `exact_energy`, `fci_energy`, `exact`, `fci`, `exact_ground_state_energy`, `ground_state_energy` |
| geometry | `bond_length`, `bond_length_angstrom`, `r`, `distance`, `geometry_r`, `separation` |

`error`, `recovered_correlation`, `converged`, `iterations`, `ansatz`, `optimizer`,
`basis`, `molecule` and `seed` are kept per point under `host_reported`. **They never
decide anything.** The verdict is recomputed on Aegis from the energies; a host does not
grade itself.

The bench keeps its isolation claim at **`run.execution`** at `db99249`. That block is
copied verbatim and labelled `host_attested`; `run.execution.isolation`, `run.isolation`,
`isolation` and `run.result.isolation` are also accepted, and a block is only read as an
isolation receipt if it actually names one of isolation, network, writes, sandbox, home or
receipt_owner — an `execution` block that only records a host and a duration is not one.
Searching only the paths this side found natural is how a real receipt gets reported absent,
which is exactly what happened to the first H2 run. This repository holds no independent evidence for the chemistry
bench's sandbox — the 2026-09-12 five-seed evidence covers the *Atelier* seeds through
`qremote.py`, not this bench — so the grade row says attested, never verified.

## Parameters

The bench owns its parameter vocabulary and Aegis does not invent one. The scheduled
session bounds only the *shape* of what a frontier lens may send — finite scalars, short
strings, small lists, twelve keys — and records everything it dropped in
`plan.parameters_dropped`. It deliberately does not name an ansatz, an optimizer, or an
iteration cap: the current experiment has no such knobs, and a plan naming them would read
in the ledger as a choice he made when the Mac had in fact ignored it.

When the bench source is reconciled (below), pin the real per-experiment parameter schema
here and tighten the session's bound to it.

## Bringing the source under version control

This is a manual step and stays manual until it is done deliberately:

1. On the Mac, confirm the commit: `git -C /Users/kevin/qlab log --oneline -1` → `db99249`.
2. Copy `bench_remote.py`, `molecule.py`, and their helpers into `mac/qlab/` in this
   repository, preserving paths.
3. Record the copied files' `sha256` alongside the Mac commit, so a later drift between
   the two copies is visible rather than assumed away.
4. Only then tighten the alias table and the parameter schema above to what the source
   actually says.

Until step 4, the alias table is the contract, and it is deliberately generous.

## The wider door

`bench_remote.py` also accepts `action: "code"`, which writes a new executable experiment
into the bench. The scheduled Lab route cannot reach it — `chemistry_mac.py` now refuses
any action outside its four-item allowlist at the point of send — but that is a guard on
the near side only. The far door remains open to anything that can speak to it.

That capacity belongs to the playground and should not be casually deleted. It needs its
own authenticated, deliberately-invoked authority, separate from the scheduled
named-experiment route: scheduled Chemistry receives `run`; free creation receives `code`
through a door of its own. `docs/open-work.md` carries this as open work.

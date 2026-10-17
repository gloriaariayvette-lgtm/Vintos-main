# TAS1R3: verified 9UTC coordinates and bounded Lab data handoff

This packet was prepared from `claude/device-visuals-2026-10-13` at `56a9b724`, after checking the current
Lab records. No production module was changed or deployed. No folding job, model call, or correspondence
was initiated. The PDB coordinate query and mmCIF retrieval already existed.

## What the deposited model supports

[9UTC](https://www.rcsb.org/structure/9UTC), released 2025-07-16, is a 3.33 Å electron-microscopy structure
of the TAS1R2/TAS1R3 Venus flytrap domains in a sucralose-bound complex. In this entry **both author chain B
and mmCIF label chain B** identify entity 2, human TAS1R3 mapped to **UniProt Q7RTX0**. Entity/label sequence
numbering differs from native/author numbering by eight over the native aligned stretch.

| Scope | One-based, inclusive residue intervals |
| --- | --- |
| Native Q7RTX0 residues with occupied atoms and C-alpha coordinates in model 1 | **22–356; 366–556 (526 residues)** |
| Native sequence mapped into the construct | 21–852, corresponding to entity positions 29–860 |
| Mapped native sequence with no occupied coordinates | 21; 357–365; 557–852 |
| Canonical positions outside that native construct mapping | 1–20 |
| Full engineered entity sequence | 1–1130 in entity numbering; this is not 1130 observed native residues |
| mNeonGreen reference component | Entity 876–1110 / author 868–1102; mapped to A0A1S4NYF2 positions 26–260; **zero observed residues** |
| Other unmapped engineered terminal/linker sequence | Entity 1–28, 861–875, 1111–1130; no occupied coordinates |

Chain A is TAS1R2/Q8TE23 with an engineered mScarlet3 component. Its observed native ranges are
26–44, 58–342 and 357–552. “Mutation count zero” in an archive display does not make these constructs
unmodified full native proteins.

Coverage was derived from the occupied first-model `_atom_site` rows in the
[deposited mmCIF](https://files.rcsb.org/download/9UTC.cif). It agrees with the mmCIF missing-residue
annotations, RCSB's `UNOBSERVED_RESIDUE_XYZ`, the existing `chemistry_reference_compare._residues()` chain
reader, and `lab_sources.Sources(...).query(structure_evidence)` C-alpha counts. Counts mean modeled,
occupied residues; they do not establish every side-chain atom, local density quality, native conditions,
or a complete full-length receptor structure.

The instance's `auth_to_entity_poly_seq_mapping` is populated across all 1130 entity positions, including
unobserved sequence. Its populated positions must **not** be treated as observed-coordinate coverage.
The accession-search operation remains useful for discovery; this packet uses atomic coordinates and
explicit unobserved-residue annotations for coverage.

## Binding claims and the original question

The [published abstract, PMID 40555359](https://pubmed.ncbi.nlm.nih.gov/40555359/) assigns demonstrated
sucralose binding to **TAS1R2's Venus flytrap domain**. These coordinates do not establish TAS1R3 direct
sucralose binding, nor prove that TAS1R3 cannot bind it under any possible condition. They do not establish
TAS1R3 high-affinity L-glutamate binding or the hydrogen-bond/pocket mechanism presupposed in the original
Lab question. `publication-evidence.json` records the abstract-only evidence boundary.

The preserved question is:

> What are the specific structural features of the human T1R3 (umami taste receptor) extracellular Venus Flytrap Domain (VFD), and how do the specific hydrogen-bonding networks and hydrophobic pockets within this domain facilitate its high-affinity binding to L-glutamate?

Its SHA-256 is `9a181cc7dd8f414ecda210365d6d29d748f13351783d195cfeb07ef5fd76887e`. The relevant October 16
entry is `CLF-c189c2309c1fc6c4`; the matching October 17 entry is `CLF-0a9db862d4e5e5da`. The attachment
corrects coordinate availability and coverage. It does not rewrite that question, mark it answered, or
change earlier reflections or unrelated conclusions.

Grok Bot's October 17 message `1a14a06659adfe16` was the discovery lead. The scientific observations were
checked independently against deposited data and the primary publication abstract. They are not attributed
to Gloria. The [9NOT](https://www.rcsb.org/structure/9NOT) metadata was checked separately: its TAS1R3 is
**label chain A, author chain B**, entity 1, at 3.8 Å. Do not transfer 9UTC label-chain assignments to it.
No 9NOT coordinate-coverage analysis is claimed here.

## Existing supported source queries

`source-query.json` is the exact executable deposited-coordinate query:

```json
{"source":"pdb","entry_id":"9UTC","operation":"structure_evidence"}
```

It does not accept a `chain` parameter. Chain identification/coverage is checked against the deposited
mmCIF using the existing reference reader and its BioPython dependency. `accession-search-query.json`
contains the separately supported bounded discovery query:

```json
{"source":"pdb","operation":"search_accession","accession":"Q7RTX0","limit":4}
```

A four-result first page is not an exhaustive absence search. No fold or new general-purpose reader is needed.

## Verification and data ingestion commands

From this checkout, use a Python with the existing Lab/BioPython dependencies:

```sh
python3 docs/research-evidence/2026-10-17-tas1r3-9utc/verify_packet.py
python3 docs/research-evidence/2026-10-17-tas1r3-9utc/attach_to_lab.py --scripts scripts
```

Both commands above are offline and write no Lab records. `packet-sha256.json` authenticates the fixed
retrieved inputs within this packet; compressed coordinate files retain hashes of their original bytes
in `download-manifest.json`. The task-specific scripts verify/replay this fixed observation through existing
readers; they are not installed runtime modules.

**No software installation or service restart is required.** To repeat the data-only attachment on Aegis:

```sh
scp -r docs/research-evidence/2026-10-17-tas1r3-9utc gloria@aegis:/tmp/
ssh gloria@aegis 'PYTHONDONTWRITEBYTECODE=1 ~/.vintos/tools/chemistry-lab/esmc/bin/python /tmp/2026-10-17-tas1r3-9utc/attach_to_lab.py --apply'
```

The importer validates the complete source receipt and observation offline, checks ownership by the exact
original question, imports the already completed public PDB retrieval, and appends a derived receipt plus
one `additional_source` notebook row through installed Lab APIs. It makes no provider request, changes no
cooldown, invokes no model or state-machine turn, edits no reflection, and does not mark the original question
answered. Its stable evidence key makes a repeated import a no-op. The initial attempt to perform an extra live
PDB query was stopped by `source_cooldown_active`; that limit was left intact. The successful handoff imports the
already retrieved evidence instead of making that redundant request.

`live-ingestion.json` records what actually happened on Aegis, separately from the source and offline checks.


## Confirmed live result and remaining visibility boundary

On Aegis, the data attachment completed at `2026-10-17T16:25:07.260968+00:00` (11:25:07 CDT):

- Notebook pointer: `SRC-TAS1R3-683d2013cfc641dd`.
- Original PDB source receipt: `048a0f54b5f5f5be50fc589aa4a3c62efbbc775fdfa7671ed0ffd650ee8f4eb7`.
- Derived coverage receipt: `66c0caede31b70c9de1f4a5501fd99d8270ed33253cb76ffd4de913de7979e50`.
- Data artifacts: `~/.vintos/workspace/memory/chemistry-lab/artifacts/reference/9UTC-TAS1R3-683d2013cfc6/`.

The installed `_structure_cached('9UTC')` returns the imported source receipt. The exact original question's
existing `_planning_evidence()` reader changes when the two attached receipts are included, verified against
an in-memory view omitting only those receipts. No live files were modified for that comparison. This
establishes availability to the existing structural retrieval and planning-evidence workflow.

**The current general Lab context did not expose the coverage excerpt.** Its configured budget is 3800
characters and the recent-event window moved on. The correction is not marked as a model-reviewed finding;
no claim is made that a model has read or understood it. The subject-spent check itself returned false for
the attached summary. Budgets, filters, holds, active state and earlier conclusions were not altered to force
visibility. A later assessment remains separate from the verified evidence attachment.

`live-visibility.jsonl` contains the read-only visibility checks and unchanged hashes of `lab_sources.py`,
`chemistry_lab.py` and `chemistry_reference_compare.py`. `offline-import-verification.json` records the
scratch-only check: two source receipts and one notebook row, repeated import with no further writes,
original reflection unchanged, and network/model/send operations refused by stubs.

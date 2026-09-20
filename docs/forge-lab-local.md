# Forge–Atelier and Lab preparation, 20 September 2026

This change is local. No Aegis deployment, live model call, ntfy message, wallet
operation, marketplace work, or pain-validation change was performed.

## Non-financial loop

`forge_loop_runtime.py` provides a continuous local report-production worker,
authenticated owner controls, explicit private audit, scoped POST cancellation,
restart reconciliation, and an ntfy outbox. It uses the existing shared background
compute admission before each local inference call. Active projects have no scheduled
pause; other house work can take compute priority between calls. Model evaluation
means a report meets its intention, never that a scientific discovery is validated.

The worker's accepted SQLite artifact and event are one transaction. Each accepted
revision projects idempotently into a new `forge-<id>` Atelier project with the broker's
lineage format and hash-chained events. Projection failures retain accepted work and
retry; they do not replay generation. Broker and projection share an event file lock.
Existing projects cannot be adopted or overwritten. Broker write routes refuse these
managed projects. The broker's seal and export preparation/confirmation remain in
force; ending a private interval in the loop UI does not forge an export receipt.

The owner control page lets Eve create, stop, inspect revealed work, or explicitly
end privacy by auditing. A worker may reveal its report, and expiry also opens it.
Private content is not in ordinary status or ntfy payloads. A cancellation during
inference retains the result and prevents the next cycle. A stopped or crashed worker
leaves uncertain work held; offline reconciliation requires recorded evidence and
the exclusive worker lock. It cannot overlap a still-running worker.

Ntfy is explicit server/topic/token configuration. Unconfirmed sends remain pending;
crash-after-delivery can duplicate a notification. View opens the control page;
HTTP Cancel uses only a project-specific capability, never the owner token.

The current production builder creates **reports**, using explicitly configured local
inference. The separate existing Forge capability builder still requires its approved
Astra/Fable review and sandbox/install gates. Its zero-cost injected adapter is tested
in `experiments/forge-loop`; no local reviewer is passed off as Fable. Paid generation,
wallet funding, Taskmarket and capability installation are outside this release.

## Lab sources and scientific standing

- UniProt fields are validated locally before HTTP. Invalid generated fields fall back
  to the existing bounded query with the reason recorded. Receipts bind requested and
  executed queries, content hashes and source observations; PDB/ChEMBL cross-references
  remain available to the reader.
- Atlas uses **`alphagenome==0.9.0`**, `atlas.create`, `scorer_metadata`, and
  `query_interval`. No guessed REST endpoint. A child process enforces a 90-second
  whole-query deadline because SDK creation timeout only covers connection readiness.
  Requests are limited to 32 bases and three actual scorer names; optional ontology/gene
  filters accept up to four sourced IDs. Metadata includes bounded track examples. Raw scores, calibrated
  quantiles, variants, genes/tracks, assembly and SDK version are preserved. An unavailable
  release identifier stays explicitly unknown. Metadata can be queried with
  `{"source":"atlas","operation":"metadata"}`.
- PDB entry reads require experimental-method metadata. Entry identity alone does not
  establish a comparable construct, sequence, resolution or experimental condition.
- ChEMBL target activity reads preserve units, relations, assay IDs/types and validity
  comments. Activity is not automatically evidence of direct binding.
- COSMIC is explicitly unavailable until a registered, appropriately licensed dataset
  is configured. There is no invented anonymous API or interpretation of “no hit” as
  absence in cancer or literature.

Background and frontier planners can request the same typed source queries. Successful
reads enter the same interest ledger and produce a typed followup queue. Interest is
routing priority, not scientific confidence. Source descriptors enter the existing
house text-embedding path; raw protein/genomic vectors are not mixed with text vectors.
A semantic collision is an associative prompt, never supporting biological evidence.

The optional Atlas-directed Evo 2 phase selects an observed variant by calibrated
quantile within the returned bounded set, fetches its GRCh38 reference window, checks
assembly/strand/coordinates/reference allele, and scores that exact substitution.
It reuses the existing Gemma unload/restore lifecycle. It is independently disabled
until `atlas_evo2_enabled` is enabled during commissioning. Its likelihood delta is
not the same quantity as an Atlas functional score; disagreement is a question, not
an experimental result. The older non-human reference lane remains unchanged.

ESMC/ESMFold require a sourced gene-to-protein mapping and sequence. A regulatory
prediction does not imply a mutated protein. ChemiQ requires a defined molecule and
an applicable named experiment. Missing mappings remain explicit followup prerequisites;
there is no automatic fabricated protein or chemistry analysis.

An optional dedicated Lab intake token permits only bounded source-dossier creation,
not control or reading of sealed work. The receiver verifies receipt integrity,
deduplicates source observations transactionally, and limits unfinished projects to
four. Lab handoffs are retained in an outbox for retry. Automatically created reports
start private with a seven-day expiry (an explicit implementation default, not
an inferred wish). Source data remains non-commercial and novelty unestablished.

## Key setup on this Mac

Eve already has approved API access. Do not paste the key into chat, a tracked file,
a command argument, or an environment dump. From this worktree run:

```sh
../review-evidence/venv/bin/python scripts/configure-alphagenome.py
```

The hidden prompt stores it in `~/.config/vintos/alphagenome.key`, mode 0600.
No API query is made by setup. In the Lab's local config, set
`alphagenome_key_file` to that path and `alphagenome_python` to the absolute path of
`../review-evidence/alphagenome-venv/bin/python` (already installed locally).
Aegis needs its own secure provisioning at deployment; this Mac path is not portable.
Supply sourced genomic anchors under `atlas_anchors`, or begin with a metadata query.
Do not invent scorer names, coordinates, protein mappings or API success receipts.

## Before deployment

The deploy manifest names the new Lab modules. The separate Atelier service bundle
is named in `scripts/forge-loop-files.txt`; configuration is illustrated by
`scripts/forge-loop-config.example.json`. Do not deploy placeholder values. Copy the
bundle and `atelier-forge-loop.service` through the existing Aegis deployment process,
provision distinct owner/worker/intake secrets, configure authenticated TLS forwarding
to port 8612, and provision ntfy explicitly. No service is enabled by these local edits.

The service's Atelier user needs read access through the shared compute directory and
write access to **only** `.compute.lock` and `compute-ledger.jsonl`; its systemd unit
names those paths. Confirm existing permissions/ACLs rather than granting broad write
access to house memory. Run the config check as the actual service user:

```sh
python3 forge_loop_runtime.py --config /home/atelier/forge-loop-config.json --check
```

Then verify the deployed model identity, shared admission/foreground yield, actual
Atlas key access, named sources, Linux isolation for capability builds, ntfy delivery
and phone cancellation, private expiry/audit, and restart recovery. These are live
acceptance checks, not established by local fixtures.

## Local validation — 20 September 2026

- All 161 broker suites ran through the isolation runner: **159 passed, 2 failed**.
- All 161 also ran by direct script invocation, without the runner's import-path
  bootstrap, inside a scratch HOME/network sandbox: **159 passed, 2 failed**.
- Both modes failed the same existing cross-repository checks:
  `test_completion_evidence.py` (adjacent vintos-app client mirror) and
  `test_reelroom_frame_and_cost.py` (adjacent plithra-app pending-frame implementation).
  Those checkouts predate the server baseline. Their files were not altered here;
  these remain release blockers, not waived tests.
- 61 focused tests passed, including the separately installed official Atlas SDK
  contract test with a fake client; three sandboxed fixture build cycles passed.
- Browser fixture: owner authentication, public retained-report rendering, and the
  covered private-project card were checked locally. This is not visual acceptance
  of a deployed Atelier integration.
- Public read-only PDB, ChEMBL and Ensembl smoke queries returned bounded valid data.
  No authenticated Atlas query, local model/GPU run, phone notification, Aegis change,
  wallet action, or deployment occurred. API-key provisioning remains outstanding.

Per-suite results and logs are retained locally under
`../review-evidence/forge-lab-regressions/` and
`../review-evidence/forge-lab-direct/` relative to this worktree.

## Official references

[Atlas SDK](https://www.alphagenomedocs.com/api/generated/alphagenome.atlas.atlas.AtlasClient.html),
[API access and non-commercial use](https://www.alphagenomedocs.com/),
[UniProt fields](https://www.uniprot.org/help/query-fields),
[RCSB data API](https://data.rcsb.org/),
[ChEMBL API](https://www.ebi.ac.uk/chembl/api/data/docs),
[COSMIC registration/licensing](https://cancer.sanger.ac.uk/cosmic/download/cosmic),
[Ensembl reference sequence](https://rest.ensembl.org/documentation/info/sequence_region).

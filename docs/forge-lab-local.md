# Forge–Atelier and Lab deployment — 20 September 2026

Release **20260920-180036-dc30734** is deployed on Aegis. All 162 suites passed
through both the isolation runner and direct script invocation on Mac and Linux.
The deploy reported `deploy OK`, with no release failures. Independent hash checks
matched 374 main release files and all nine dedicated Forge bundle files to source.
See [the deployment receipt](review-evidence/2026-09-20/forge-atelier-deploy.json)
and [remaining work](open-work.md).

## Three actual steps per day

Eve's explicit limit is **three attempted Forge report cycles per Chicago calendar
day, across all projects**. A step is one local draft-and-critique cycle. SQLite
reserves a slot atomically before execution. Failures, crashes and reconciled
retries count; restarting cannot replenish the allowance. The worker waits when
exhausted and resumes after midnight America/Chicago. Calendar rollover handles DST.

The original uncapped implementation was a mistake: eight attempts had run before
this limit was installed, producing separate completion/reveal notifications.
Migration conservatively charged those existing attempts to the current day. Live
verification showed **limit 3, used 8, remaining 0** and the count stayed unchanged.
This is a work-execution limit, not a daily notification limit.

## Controls and runtime

- Owner controls: https://aegis.tailaa3de5.ts.net:9443/ — Tailscale required.
- The approved owner key is stored privately on this Mac at
  `~/.config/vintos/forge-owner`; it is not in Git or this report.
- Service: `atelier-forge-loop.service`, running as `atelier`.
- Named bundle: `scripts/forge-loop-files.txt`, installed under
  `/home/atelier/forge-loop`; state under `/home/atelier/atelier`.
- Config: `/home/atelier/forge-loop-config.json`, with distinct owner, worker and
  Lab-intake credentials. Lab intake can create bounded source dossiers, not read
  or control private work. Four unfinished projects is a separate queue bound.
- Model: local `google/gemma-4-12b-qat`, through
  `/gemma-aegis-local/v1/chat/completions`. This route has no remote/paid fallback.
  The shim service's `manifest-path.conf` drop-in selects its manifest-managed file.
- Shared compute admission gives foreground work priority. Atelier received directory
  traversal and write ACLs only for `.compute.lock` and `compute-ledger.jsonl`.
- ntfy uses the existing explicitly configured anonymous topic. Token-backed topics
  remain supported. A publisher acknowledgement is retained before marking delivery.

The owner page shows the remaining execution budget and supports creation, scoped
cancellation, reading revealed work and explicit private audit. Private intervals end
on reveal, expiry, audit, cancellation or abandonment as recorded by the controller.
Private content is suppressed from ordinary reads and notification payloads. A
cancelled in-flight cycle may finish, but cannot authorize the next cycle.

Each accepted artifact and event commits transactionally, then projects idempotently
into a new `forge-<id>` Atelier project with lineage and hash-chained events. Broker
and projection share an event lock; existing projects cannot be adopted. Broker seal
and export gates remain intact. Ending privacy does not fabricate an export receipt.
Interrupted cycles remain held until offline reconciliation records evidence under
an exclusive worker lock. One live JSON-format failure exercised that recovery;
a single Markdown JSON wrapper is now accepted, while surrounding prose still fails.

## Lab sources and live evidence

The installed Lab config retains `alphagenome_key_file`, `alphagenome_python`,
`atlas_anchors` and `forge_report_intake`. SDK **alphagenome==0.9.0** lives in the
host's dedicated `~/.vintos/tools/alphagenome` environment. The approved key is in
`~/.config/vintos/alphagenome.key`, mode 0600. Do not print or commit either key.

Authenticated metadata returned 22 Atlas scorers on Aegis. A bounded one-base GRCh38
query returned three AVI-scored variants. A real receipt then passed through Lab
intake, local report generation/review and retained Atelier projection. Completed
reports and notification acknowledgements were observed. Eve confirmed pushes
arrived. Scoped HTTPS cancellation returned 200, while using that credential for
project reads returned 403. A physical phone-button tap was not observed.

UniProt validates fields before sending; PDB retains experimental-method metadata;
ChEMBL retains assay types, relations and units. Source receipts retain query, hashes,
retrieval time and explicit release uncertainty. Atlas raw scores and calibrated
quantiles are kept distinct. Its optional Evo 2 phase validates GRCh38 coordinates
and reference allele before local scoring. No raw-score ranking across scorers.

Cross-organ associations compare source-backed text in the house semantic space.
They are prompts for investigation, never biological evidence. Report completion
means adequate documentation, not a novel or validated scientific discovery.

Still uncommissioned: interest-specific sourced genomic anchors, COSMIC registered/
licensed access, protein mappings and applicable molecular inputs for ESMC/ESMFold/
ChemiQ followups, and the full scientific instrument chain. Wallet, Taskmarket,
payments and income remain parked. The approved Astra/Fable capability-build path
retains its separate creation, review, verification and installation permissions.

## Recovery

Main release backup:
`/home/gloria/.vintos/backups/atelier-20260920-175653/restore.sh`.
Dedicated worker pre-cap files:
`/home/atelier/forge-loop-backup-pre-dc30734`.
Do not roll back the execution cap while leaving the worker running. Preserve its
SQLite database: replacing it would erase both history and the daily allowance.

## Official references

[Atlas SDK](https://www.alphagenomedocs.com/api/generated/alphagenome.atlas.atlas.AtlasClient.html),
[non-commercial API access](https://www.alphagenomedocs.com/),
[UniProt fields](https://www.uniprot.org/help/query-fields),
[RCSB data API](https://data.rcsb.org/),
[ChEMBL API](https://www.ebi.ac.uk/chembl/api/data/docs),
[COSMIC access](https://cancer.sanger.ac.uk/cosmic/download/cosmic),
[Ensembl reference sequence](https://rest.ensembl.org/documentation/info/sequence_region).

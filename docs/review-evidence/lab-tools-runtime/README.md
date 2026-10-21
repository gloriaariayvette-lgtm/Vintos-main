# Lab runtime review — 21 October 2026

Review branch: `codex/lab-tools-runtime`, based on `775b3d3`. Gloria deploys after the main-thread review and merge into `claude/device-visuals-2026-10-13`.

## Installed boundary

Mac-to-Aegis SSH succeeded as `gloria` in `/home/gloria`. Installed release: `20261021-030528-fca8b7f.json`, full revision `fca8b7f360cdc7fa5452088762b88a95a19a3b46`. All 555 manifest hashes matched. The seven primary Lab modules also matched Git contents at that revision. The review work changed neither live services/workspace nor the live Mac bench.

The installed release contains `9733de2`. Its old narrowing fault rows stop at October 17 22:34 UTC; edits start at 22:58 UTC and continue. These rows do not establish failed rewrites. In the seven-day window ending October 21 18:48:19 UTC, 354 parser-fault evidence IDs were named; 28 retained raw replies remained (20 prose, eight malformed object-like replies). Provider stop reasons in those retained diagnostics were unknown. This does not diagnose every historical parser failure. The installed HTTP-failure diagnostic preservation was carried into the candidate rather than regressed.

## Changes

- Investigations retain an immutable question/prediction, chosen operations, complete outputs, digests, and exact cross-step references. Prompt previews have separate field indices and cannot substitute for stored data. Exact returned identifiers copied by the planner are bound to stored output fields without changing their values; query echoes cannot establish provenance. The authored and executed requests both survive.
- One shared protein normalization feeds ordinary browsing and investigation identity/coverage review. Supported source and operation shorthands preserve their authored inputs. Connector discovery follows the owning gateway; local compute gateways describe their own validated contracts. Account discovery reads actual SDK MCP status without a model turn or tool invocation. The installed account SDK does not expose input schemas: discovery reports that explicitly and retains its actual tool metadata; it never fabricates a schema.
- Protein retrieval enters the existing embedding and review phases. Scheduled genomic analysis retains its cadence and its outputs enter the originating investigation. Completed daily sessions enter the same retained-output system. Screening is selectable, with no reserved turn share. Distinct instruments can advance the same question; identical completed lookups remain blocked.
- Interrupted/uncertain executions remain `outcome_unknown`, including returned timeout objects. Returned tool failures retain their outputs and are not completed steps. An unsent source cooldown waits without consuming a lookup; successful source execution records its repeat identity. Native input/output artifacts are retained and content-addressed structure text can feed local instruments.
- Bounded native ProteinMPNN, RFD3 and OpenMM invocation wrappers use the installed entry points and the existing 25-run instrument budget. The OpenMM operation is explicitly a C-alpha harmonic model, not an atomistic binding calculation. Hosted NIM remains capped at six attempts; paid Boltz start operations remain outside autonomous policy. No paid job was used for validation.
- After repeated daily protein choices, the planner chooses among the least-used experiments that the bench actually offers. An explicit operator request remains authoritative. The grader now recognizes the actual toy fold and titration result shapes and labels their model energy units separately from molecular Hartree energies.

## Validation

Every one of the **459 broker suites passed on Aegis** using `scripts/run_isolated_test.py`: fresh per-suite homes, copied source, OS isolation, external networking blocked. `suites.json` records each exit code. The required ownership/untested tables and the store-ownership table were regenerated.

The ordinary tick loop ran against real public data and the installed local planner inside a read-only-root bubblewrap sandbox, with only `/tmp/lab-tools-review-vfCIRGxn` writable. The successful comparison investigation took four ticks:

1. A planner-selected UniProt query returned the real P69905 record and complete 142-residue sequence.
2. The unchanged ESMC phase consumed `normalized_records`, computed a whole-chain representation and retained its artifact/digest.
3. The unchanged review phase read the result.
4. A planner-selected InterPro query consumed `embeddings[0].accession` from the retained representation output.

`chain.json` preserves the full outputs, operation requests, exact reference edges and digests. The checker requires a connected path through three distinct tools, excluding reflection/schema/inspection. The initial question was an operator-supplied scratch validation question; these runs are not post-deploy autonomous acceptance or a novel biological result. Earlier failed scratch runs were retained; their real outputs exposed route-template copying, source shorthands, record/list cardinality, stale prompt context and premature lookup recording.

`mac-experiments.json` preserves real `molecule`, `fold` and `titrate` runs through the Lab dispatcher, using a copied bench and OS-isolated experiment children. The live Mac bench was untouched. The deliberately short H2 optimization completed but performed worse than Hartree-Fock; the toy fold's modal state was above its enumerated minimum; the three titration points matched their toy references. Execution and scientific/numerical adequacy are separate. These are initial checks, not evidence that the daily planner has diversified after deployment.

## Acceptance still pending

The whole Lab is not operationally accepted merely because routing and suites pass. This task did not execute every account connector, hosted job, viewer or native instrument operation on real inputs. Their new paths are regression-tested; existing commissioning receipts are not a substitute for a real investigation invocation. Account schema exposure remains an SDK limitation, reported honestly. A tool that cannot obtain its actual arguments/receipt and produce a useful downstream input must be reported as unproved, even if it is listed in a menu.

The two-day window starts at the first deployed release containing the candidate runtime hashes in `acceptance.json`, not at these scratch runs. `lab_usage_report.py` reads source receipts, ordinary embedding, genomic runs, daily sessions and investigation references. It deduplicates run/receipt projections, includes zero-use tools and reports completed calls, failed/unknown outcomes and retained downstream dataflow. The final review must separately assess new findings and scientific support; an answer marked yes, a confidence score or an empty search is not novelty. No deployment or live restart is authorized to this task.

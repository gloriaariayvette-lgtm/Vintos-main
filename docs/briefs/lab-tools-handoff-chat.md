# Handoff to Chat: make every one of his Lab tools actually run

From Claude Code, 21 October, evening. Read `CLAUDE.md` / `AGENTS.md` first. They cover the deploy route, models and
money, test isolation, and the Lab's purpose. Gloria's words: **"All of this was supposed to be working."** Every tool
is installed, keyed and enabled on Aegis. They are failing in how the Lab calls them, and that is the job.

## What is deployed and what is not

Gloria has **not deployed** the latest commits on `claude/device-visuals-2026-10-13`. Before changing anything, find
what Aegis is actually running:

```sh
ls -t ~/.vintos/deploy/releases | head -1        # the last deploy's record: its git rev is in the file name and the JSON
```

Commits on the branch from today. Treat anything after the deployed rev as not on Aegis:

| commit | what | status |
|---|---|---|
| 56c3cba | Gene-identity check compares symbols without hyphens (TDP-43 = TARDBP's TDP43) | tested offline, not seen live |
| 632eabd, 9b5ab12 | `scripts/probes/pendrin_8sgw_map.py`, read-only | probe only |
| 5500a97 → 35a99c9 | Dead-end window change, **reverted** (the diagnosis was wrong) | net zero |
| fce3103, d62737f | `docs/briefs/lab-refusals-*.md` (review briefs) | docs |
| a32df65, ac820da, c363d08, f940f41 | **Screening campaigns**, `scripts/lab_campaign.py`: Gemma names a protein family and an organism group with a prediction; each turn screens one locus (`lab_phage.screen`); every 8 loci the counts become a finding; each finding is checked against Europe PMC, appraised, kept in `lab_keepers`, sent to Gloria as his want when it's 4/5+ (1 a day), and built on by the next campaign. **Takes every other minute-loop turn and every turn after an empty pass** (`_campaign_due`, `chemistry_lab.py`). Off switch: `"campaigns": false` in config, or env `VINTOS_LAB_CAMPAIGNS=0`. A dry run on Aegis worked: recombinase in Planctomycetes, 8 loci, prediction refuted. | not deployed |
| d2af2f5 | CLAUDE.md and AGENTS.md: deploy, models, Lab purpose | docs |
| 719742e | The daily session offers ESMFold "protein" when the Mac is away, and `instrument_query` is in the planner's key list. **The first half was built on a wrong assumption:** the probe shows the Mac answers and the session completed 15 of the last 16 days. It is harmless, but not a fix. The key-list half stands. | not deployed |
| fdc4e51 | The Lab menu no longer lists skills it cannot call (pdf, slides, spreadsheets, bionemo) or connectors marked disabled | not deployed |
| f98ccf6 | `scripts/probes/lab_tools_live.py`, read-only | probe only |

**Her instruction about campaigns:** campaigns took over half of his turns. **His tools must work with them, not be
crowded out by them.** Either campaigns use the tools (fold a recurring neighbour, Boltz a pair that co-occurs, score
a locus with Evo 2, AlphaGenome a human orthologue, and so on), or the campaign share drops so tool turns get their
time. Design that. Don't just switch campaigns off.

## What Aegis says, from `lab_tools_live.py` (run by Gloria, 21 Oct evening)

Everything is present:
- **Config:** `evo2_enabled: True`. `atlas_evo2_enabled: False` is set in config.json; ask her whether that was
  deliberate before turning it on.
- **Keys:** the AlphaGenome key and Python, the NVIDIA NIM key, and the plugin relay config are present, each at
  mode 600.
- **Tools:** the nvmolkit venv, Pfam and hmmscan are installed.
- **Connector URLs:** boltz and eden.
- **Connectors the code sees as enabled:** genomic_intelligence, github, gmail, inductive, nvidia_nim, nvmolkit,
  proto, tamarind.
- **`tools_status`:** esmc, structure_prediction, protein_mpnn, rfdiffusion, openmm, protein_design_mcp and evo2 are
  measured. qpanda, vqnet, quantum_chemistry, mac_esmc and foundry have stale receipts (`receipt_stale`): **re-probe
  them** (`chemistry_probe.py`).
- **The Mac answers.** It offers `fold`, `molecule` (the quantum lab: H2 VQE on pyChemiQ), `protein` and `titrate`.
- **Daily session:** 15 completed, 1 held_fault, in 14 days. **Every one ran `protein`.** The `molecule`, `fold` and
  `titrate` experiments were never chosen.

**Use in 7 days:**
- 32 `plugin:atlas`, 23 `plugin:uniprot`, 20 `plugin:pdb`, 10 `plugin:pubmed`.
- 2 `instrument:fold_read`, 1 `plugin:github`, 1 `plugin:boltz`, 1 `plugin:chembl`.
- Nothing for nvidia_nim, nvmolkit, inductive, genomic_intelligence, eden, Evo 2, mutation landscape, or the
  structure and sequence viewers.

**Failures in 7 days, and what they mean:**
- **866 `question_narrowed` ValueError**, plus 10 `question_made_concrete`. These are the planner's question rewriting
  failing. Find out why.
- **398 `tick` ModelJSONError and 76 `plan_not_json`.** Gemma's replies aren't parsing.
- **Gemma calls sources as plugins.**
  - `plugin:atlas`, `plugin:uniprot` and `plugin:pdb` are sources (`source_query`), not plugins.
  - 32 `atlas.get_asset refused (plugin unavailable on this surface)`.
  - 23 `pdb.boltz_get_structure_and_binding_prediction refused`.
  - 29 `unsupported Lab source`.
  - The menu text or the parser is letting source names into `plugin_query`. Either route them to the right
    dispatcher or make the menu impossible to misread.
- **44 `unknown NCBI operation`.** Gemma writes NCBI operations the code doesn't accept. Map them or show the exact
  list.
- 43 `uniprot_returned_no_records`, 6 `pubchem_http_status_404`.
- 15 `source_gene_mismatch` (e.g. "IL-1" against IL1A/IL1B, a genuinely ambiguous request; 56c3cba does not change
  that).
- **Instrument runs:** the ledger shows 1 `fold_read` on 19 October, out of 25 a day.

## The job

1. **Every installed tool runs for real, from the Lab.** For each one listed above:
   - say how a turn reaches it;
   - make that path work with Gemma as the planner;
   - prove it with one real run on Aegis (a dry run into a scratch `SPARK_WORKSPACE` first).
2. **Fix the call failures above** (the 866, the 398, plugin-versus-source, NCBI operations). Don't add refusals,
   gates or more retries to hide them.
3. **The daily session should use the Mac's other experiments**, `molecule` (quantum chemistry) and `titrate`, not
   `protein` every day.
4. **Tools and campaigns together,** as above.
5. **Judge it by new results per day** (`CLAUDE.md`, "The Lab is for novel findings"), per tool, before and after.

## Rules (all in `CLAUDE.md`)

- **His Lab planner stays on Gemma.** Gemma unloading for Evo 2 is accepted.
- **No new paid calls beyond the caps already set:** NIM 6 a day; Boltz `start_*` is ask-only.
- Every suite under `broker/tests/` is isolated: repoint paths, stub every sender, refuse sockets, and assert it.
  The ordinary-loop suites set `VINTOS_LAB_CAMPAIGNS=0`.
- New modules go in the `deploy-atelier.sh` manifest; regenerate `docs/untested.md` and `docs/entry-owners.md`.
- Push to `claude/device-visuals-2026-10-13`. **Gloria runs the deploy** with the command in `CLAUDE.md`.
- No model names in commits. Keep `docs/open-work.md` honest.

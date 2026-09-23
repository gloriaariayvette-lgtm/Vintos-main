# Chemistry Lab access, verified 23 September 2026

This is a map of what Vintos's **Lab surface** can reach, not a list of every
service connected to Gloria's accounts. `plugin_query` is offered to the Lab
planner alongside bounded public `source_query` calls; a returned plugin result
is stored in the shared 0600 receipt ledger and imported as a Lab source receipt
and collision descriptor. The background pass permits at most one source or
plugin query per choice. A scheduled frontier session can request follow-up
queries. A provider prediction is an observation, not experimental validation.

The checks below ran through Aegis on 23 September unless a probe date is
given. A successful catalog read proves that connector and tool, not every
operation in the catalog. Final release `20260923-034059-b55ac15` passed all
171 isolated suites on both preflight and install. Installed module hashes match
Git; the Lab, session timer and plugin gateway units are active. The installed
menu shows the six-attempt allowance and excludes unauthenticated Claude tools.

## Public and keyed Lab sources

| Source and endpoint | Lab use | Verification |
| --- | --- | --- |
| UniProtKB, `https://rest.uniprot.org/uniprotkb/search` | Validated bounded protein and organism queries | Live query returned one reviewed *Bacillus subtilis* record. |
| NCBI E-utilities, `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` | Taxonomy, Assembly, Gene, Protein, PubMed; bounded protein/nuccore FASTA slices | Live taxonomy, Assembly, Gene, Protein, PubMed and exact protein and nuccore FASTA-slice calls all returned records. An initial burst received HTTP 429; four-second spacing made the remaining probes succeed. The normal Lab path enforces a per-source cooldown. |
| BV-BRC, `https://www.bv-brc.org/api/` | Public genome and pathway rows, including genus-descendant lookup | Live genome query for taxon 1423 returned eight rows; a sourced genome ID then returned eight pathway rows. |
| RCSB PDB, `https://data.rcsb.org/rest/v1/core/entry/` | Experimental structure metadata, with method check | Live 1CRN entry returned. |
| EMBL-EBI ChEMBL, `https://www.ebi.ac.uk/chembl/api/data/activity.json` | Bounded bioactivity rows for an exact CHEMBL target ID | Live CHEMBL203 query returned eight rows. This is separate from Claude's ChEMBL MCP. |
| AlphaGenome Atlas, official Python SDK in the Aegis `alphagenome` venv | GRCh38 precomputed variant predictions, sourced scorer names and short intervals | Key and SDK worked: metadata named `AVI_SCORE`; a one-base `chr1` AVI query returned three variant scores. No raw REST URL is invented. |

The source layer writes query, response hash, timestamp, coverage and
truth-status receipts for normal Lab calls. These direct verification probes
used the same source client but did not add sample queries to Vintos's notebook.
COSMIC is closed without a registered/licensed data route. KEGG is closed while
API eligibility remains unresolved; noncommercial use alone was not treated as
academic eligibility.

## ChatGPT-account relay, reached from Aegis through the restricted Mac doorway

The Chat relay has no public endpoint for Vintos to call directly. Aegis uses
`plugin_gateway.py`; the Mac forced command calls one named Chat connector
tool. Live **Lab-surface** calls returned non-error provider results and 0600
receipts for all rows marked verified here.

| Connector | Allowed Lab operations and live result |
| --- | --- |
| Gmail | Search/read mail, labels, attachments, drafts, direct send. `gmail.get_profile` returned a valid account profile. Sending was **not** exercised. Direct outbound send is capped at two attempts per Chicago day with secret and link gates; provider-held draft-send/forward are held. |
| GitHub | Read-only `get_`, `list_`, `search_`, `fetch_`, `compare_` operations; `github.get_profile` succeeded. No repository edits. |
| Tamarind Bio | `get`/`list`/`search`/`validate`/`estimate` discovery and existing-job results. `listModalities` and `getAvailableTools` succeeded. Uploads and job submissions remain closed. |
| Proto | Workspace, tool catalog/schema/example, asset and job/deploy status reads. `workspace_info` and `list_tools` succeeded. Its response reports Modal and Hugging Face linked, but **zero deployed tools**; `run_tool` and deploy are outside Vintos's policy. No local Modal install is needed for catalog reads. |
| Inductive Bio | `list_available_models` and `predict_properties`. A real LogD prediction on ethanol (`CCO`) returned model `mcp_public_logd` v1.7.0 with success status. |
| Genomic Intelligence | Model listing, reference fetch and bounded prediction/job reads. `list_models` and `fetch_region` worked; `predict_promoter` ran on a sourced 2,000-bp reference sequence and returned a valid result with zero predicted regions (receipt `eb2555858900e6d8`). Other prediction types were not individually submitted. |

DoorDash is offered to Wants and Atelier for grocery list discovery, **not** to
the Lab. The Chat-account BioNeMo skill relay remains disabled; hosted NVIDIA
inference is a separate Aegis route below. The Lab's contextless PDF,
Presentations and Spreadsheets skills each completed a live disposable Mac run
and returned a checked PDF, PPTX or XLSX artifact through Aegis. Their receipt
prefixes are `61cfb278e1a89663`, `d08ff1c7cb18ef8d`, and `45fe59babae27d06`.

## Claude-account connectors

The Lab policy names these MCP servers. The Claude Agent SDK relay was found
accepting model prose as a successful tool result even after permission denial.
The relay fix requires an SDK `ToolResultBlock` tied to the requested tool and
fails closed on its error bit. Old receipts produced by the prose fallback are
not proof of connector execution.

| Connector and MCP URL | Live access finding |
| --- | --- |
| PubMed, `https://pubmed.mcp.claude.com/mcp` | A read-only `search_articles` SDK trace contained an actual non-error tool result. The catalog also allows metadata, full text where available, related articles, citation lookup, ID conversion and copyright status. |
| ChEMBL, `https://chembl.caseyjhand.com/mcp` | Post-fix `chembl_search_targets` returned a verified SDK tool result. The catalog allows molecule, target, bioactivity, drug, assay and dataframe reads; those other operations were not each probed. |
| Hugging Face, `https://huggingface.co/mcp` | `hf_whoami` returned **anonymous** status, and a live `hub_repo_search` returned public repository data (receipt `89cb4cca0ad43b29`). Authenticated private access is not confirmed. |
| Spotify, `https://mcp-gateway-external-pilot.spotify.net/mcp` | A direct SDK `get_currently_playing` call returned an authentication error: re-sign-in via `/mcp` is required. **Unavailable through Vintos now.** |
| Google Calendar, `https://calendarmcp.googleapis.com/mcp/v1` | `list_calendars` could not obtain connector permission/auth in noninteractive mode. **Unavailable through Vintos now.** |

Uber Eats has no configured MCP URL and is not on the Lab surface. Claude
account action permissions do not make denied or unauthenticated tools usable.
Spotify and Calendar are removed from the planner's offered menu and rejected
by policy until their account authorization is repaired and retested.

## Local and hosted instruments

| Instrument | Verification and boundary |
| --- | --- |
| Aegis ESMC 600M, ESMFold, ProteinMPNN, RFdiffusion/Foundry RFD3, OpenMM | Fresh Aegis `chemistry_probe.py --refresh --all` completed actual smoke runs on 23 September: embedding, short fold, one fixed-backbone design, two-step diffusion, and an OpenMM step. |
| Aegis protein-design MCP | The 23 September probe listed 19 tools and dispatched a status request. The bounded Lab route offers only `score_stability`, an ESM2 likelihood proxy; a real worker call succeeded after handling the installed server's NumPy serialization fault. MCP `predict_structure` failed for lack of `fair-esm`, so it is not offered; the separate Lab ESMFold path works. The other 18 MCP tools are not offered. The original probe alone did not prove a house call. |
| Aegis Evo 2 7B base | Lab status carries a same-day read-only comparative-likelihood probe. Its background lane is enabled on a fixed nonhuman/nonpathogen reference allowlist, at a configured interval. |
| Mac QPanda, VQNet, pyChemiQ, Mac ESMC and Foundry | Existing completed Mac-run receipts dated 13 September remain within their 30-day validity window. They were not rerun in this audit. |
| Aegis nvMolKit | All four Lab operations ran live on the GPU: `fingerprints`, `similarity`, `cluster`, `conformers`, each with a 0600 result receipt. |
| NVIDIA hosted Boltz-2 | `https://health.api.nvidia.com/v1/biology/mit/boltz2/predict` returned structure/confidence fields through the Lab gateway. |
| NVIDIA hosted ProteinMPNN | `https://health.api.nvidia.com/v1/biology/ipd/proteinmpnn/predict` returned designed FASTA and scores. |
| NVIDIA hosted DiffDock | `https://health.api.nvidia.com/v1/biology/mit/diffdock` returned ligand positions/confidence after setting `time_divisions: 3`. The first 422 was caused by `time_divisions: 1`; the provider requires a value greater than 2. A documentation-listed alternative URL returned 404, so the functioning route was retained. |
| NVIDIA hosted RFdiffusion | `https://health.api.nvidia.com/v1/biology/ipd/rfdiffusion/generate` returned a backbone PDB from a bounded de novo request. Receipt prefix `795861d1165927e0`. Local RFD3 also passed a fresh smoke run. |

NVIDIA's cross-surface allowance is **six** attempted hosted jobs per
America/Chicago day, raised from three by Gloria on 23 September. She had
already authorized one explicit reset after the failed DiffDock probe; its
append-only `operator_reset` event preserves the original three attempts and
records the allowance at the time. An `operator_limit_changed` ledger event
records Gloria's subsequent increase to six. The reset window then used four of the
newly authorized six attempts: the 404 route probe, the 422 diagnostic replay,
the successful corrected DiffDock call and the hosted RFdiffusion probe.
At 03:41 Chicago time on 23 September, two attempts remained in that window.
Parabricks has no verified active
hosted NIM path and is not offered. KERMT has no commissioned finetuned
checkpoint and is not offered.

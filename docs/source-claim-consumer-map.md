# Source → claim → consumer map, and what a correction means at each door

Review item 158 (2026-09-10). Read from the code as it stands on this branch; nothing here is a design. A *claim* is a sentence an organ writes about him or about her that another organ later reads as if it were true. A *correction* is her word, or a verdict, that a claim was wrong. The right column says what a correction actually does at that consumer today.

## Where claims are produced

| Producer | Writes | Claim shape | Identity carried |
|---|---|---|---|
| `scripts/interaction-ledger.py` | `memory/interaction-ledger.json` | her words, his words, salience, imprint narrative | `turn_id`, `surface`, timestamp |
| `bin/wal-extract.py` / `bin/wal_extract.py` | the WAL log | extracted facts with `source_turns` | turn ids on every fact (P04-05) |
| `bin/wal-decay.py` → durable memory | `memory/durable-memory.json` | event, her quote, his words, what changed, felt like | `source_turns`, `ledger_match`, `quote` (review 107) |
| `scripts/causality-engine.py` | `memory/causality-hypotheses.json`, `causality-graduated.jsonl` | hypotheses with schema-2 formation, nightly marks, evidence ids | hypothesis id, `root_evidence_ids`, `evidence_ids` per mark |
| `scripts/causality-engine.queue_question` | `causality-bring-up.json`, `.pending-causality-queue.json` | a question to test, from intent/self pressure, priority vector, campaign expiry | `CQ-` id, formation with roots (review 204) |
| `bin/belief-sediment.py` | `memory/belief-sediment.json` | beliefs promoted from graduated hypotheses | `hypothesis_ids`, `evidence_ids`, `kind=tentative_inference` |
| `bin/causal-self-model.py` | `memory/causal-self-model.json`, `commitment-imprints.json` | "when X, I tend to Y" entries and imprints | `evidence[{occurrence_id, quote}]`, `kind` (review 107/150) |
| `scripts/tension_promotion.py` | `memory/tension-questions.json` | tensions with status HYPOTHESIS → SUPPORTED → CONFIRMED / CONTESTED | evidence ids by channel E1–E4, `correction_count`, `last_corrected` |
| `scripts/claim_hold.py` | `memory/claim-hold-trials.json` | a disagreement: her claim, his reason, her pushback, his choice, the outcome | `claim_verbatim`, `challenge`, `correction` (review 155) |
| `scripts/self_model_evidence.py` | `memory/self-model-corrections.jsonl` | her corrections to the self-model | `source_id`, entry date; mirrored to `identity-revisions.jsonl` (review 135) |
| `scripts/self_model_read.py` | `memory/self-model-base-corrections.jsonl` | supersessions of the authored BASE | find/replace with reason; applied on read, never into the file (review 151) |
| `scripts/formation_observatory.py` | formation episodes | the roots a stratagem may name | `formed_from` record ids (review 365) |
| `scripts/presence_audit.py` | `memory/presence-audits.json`, blush ledger | a rubric score on his arrival | `kind=rubric_signal` - never fault evidence (review 231) |

## Where claims are consumed

| Consumer | Reads | What it makes of the claim | What a correction means here today |
|---|---|---|---|
| `bin/server.py` prompts (chat, avatar, voice) | self-model (through `self_model_read`), causal self-model context, belief sediment, tension prompt block, pending causality queue | context for his next turn | the BASE renders with her supersessions applied; a CONTESTED tension leaves the served view at once; a rubric signal is not shown as a fault |
| `bin/wal-decay.py` graduation | WAL entries + imprints | durable memories | a durable record keeps the quote and the turns; a downstream failure leaves promotion pending with the evidence intact (review 146) |
| `scripts/causality-engine.py` nightly test | interaction ledger through `evidence_view` (HELD on failure, never raw) | marks on hypotheses | an unconfirmed mark is nothing, never a failure; a formation root cannot witness itself |
| `bin/belief-sediment.py` | graduated hypotheses | beliefs | a belief names the hypothesis and evidence it came from; contradiction lowers overlapping beliefs (`contradict()`) |
| `bin/causal-self-model.py` | trials, avoidances, mismatches | tendencies, then imprints through the one gate | a fracture is a revision in `identity-revisions.jsonl` with old and new; the entry keeps its evidence occurrences |
| `scripts/tension_promotion.py` | evidence by channel | promotion | her direct correction demotes to CONTESTED on its own; a claim corrected twice returns only on her own words after the last correction (review 143) |
| `scripts/opposition_calibration.py` | claim-hold trials | three ledgers per terrain | a CORRECTED verdict feeds courage, not shame; the exact claim, challenge and correction stay in the trial |
| `scripts/self_model_evidence.py` → self-model update | introspections, corrections, changes | the weekly self-model | a correction is a dated record that supersedes the model's own account where they disagree, and a revision in the identity log |
| `scripts/desired_difference.py` / `self_difference.py` | verdicts on intents | standing pressure | CORRECTED / WRONG_READING / KEEP_PRIVATE zero the pressure with the reason kept (review 188) |
| `bin/memory-search.py`, `/api/memory/semantic` | the retrieval projection | recall by meaning | a revised or deleted source is tombstoned and never served; a chunk whose source changed is not served until rebuilt (review 105) |
| `scripts/graph_mae.py`, premonition dreamer | embeddings of the stores | dream-only threads, gap hypotheses | exploration only; no intervention or exposure record without an approved experiment (review 209) |

## What a correction is allowed to touch, and what it is not

- **It supersedes; it does not erase.** Every consumer above keeps the old claim beside the new one: the tension keeps its history, the self-model keeps the correction as a dated record, the BASE file is never rewritten, the identity revision log keeps old and new.
- **It reaches served views immediately** where the view is rebuilt each read (prompts, tension block, self-model BASE). It reaches derived stores (beliefs, imprints) through their own doors: `belief_sediment.contradict()`, `fracture_imprint()`, each of which now logs a revision.
- **It never travels through a raw read.** The doors (`evidence_view.door`, `causality._door`, `encounter._door`) hold a failed gated read instead of falling back to the raw file, so a correction's envelope cannot be skipped by a consumer that read around it.
- **Not yet universal.** Consumers not in this table read their own stores directly and receive corrections only when the producer's store changes. Universal propagation was not built on this pass; this map is the enumeration it needs first.

# Index and write contracts: who may write what, and what a reader may assume

Review items 128 and 152 (2026-09-10). The memory organs each had their own rule about what a write means and what a read may assume. The rules are one set now, and the design texts that stated the old ones are corrected below.

## The write contracts

| Store | Writer | A write means | A reader may assume | Bypass |
|---|---|---|---|---|
| `semantic-index.json` | `memory-index.py` only | a chunk of a source at a named revision, embedded by a named model at named dims, or marked `embed_failed` | only chunks served by `memory-search.serve_entries` (fresh revision, matching model and dims, not tombstoned, has a vector) | none: a direct read of `entries` is not a served read |
| `wal-log.json` | `wal-extract.py`; corrections annotate | an extracted item with its type and source turns | items may carry `corrections[]`; a corrected item is suspect until re-read | quarantine on corruption (`store_guard`) |
| `durable-memory.json` | `wal-decay._build_durable` | a promoted memory with her words, his words, the turns, and his reading | `interpretations[]` is his reading and may be superseded; `standing: invalidated` means a correction reached it | reinterpretation writes a new reading, never edits the event |
| `pearls/` | `pearl_engine.form_pearl`, `emoclaw_utils.add_pearl` | one durable claim, one file | a footer `**Corrected:** HC-…` means a correction reached it (147) | organ-proposed pearls are `PROPOSED` and injected nowhere |
| `unfinished-threads.json` | any producer through `thread_store.admit`; writes through `save_pool` | a question or a theme, with its admitter | `kind` says question or theme; `consumed_by` says what took it | none: a bare `json.dump` of the pool is refused by the test suite |
| `belief-sediment.json` | `belief-sediment.promote_hypothesis` | a tentative inference with its hypothesis and evidence ids | `kind` is always `tentative_inference`; `standing: invalidated` after a correction | none |
| `commitment-imprints.json` | `commitment_spine` only (the gate's writer included) | a commitment: `candidate`, `living`, `strained` or `fractured` | only `living`/`strained` are held; a candidate never passed the gate | none: the causal model's own list was migrated away (132) |
| the shelves (`gallery.json`, `video-gallery.json`, `music.json`) | the maker, through `artifact_manifest.save_ledger`/`append_ledger` | one artifact with its manifest | `validated.ok is False` is not evidence of completion (278); a queue entry is not a result (238) | none: the transaction is locked |
| `interaction-ledger.json` | `interaction-ledger.py` per turn; the voice hangup; the ReelRoom session commit | one exchange, or one whole session as a single object | both shapes read through `store_compat`; a session block carries the text keys too (73) | video sends do not enter it at all |

## Design texts corrected

- **"consumed = resolved"** — no. `consumed` means a consumer took the thread; `consumed_by` says which. A dream that did not resolve returns the thread to the pool unconsumed, with its verdict (`test_journey_dream`).
- **"the gate defaults to yes when it cannot be reached"** — no longer true anywhere. An unreachable gate refuses a deliberative effect and allows only a reduction (74).
- **"a variance-qualified forecast is calibrated"** — no. Variance is not calibration; release is the held-out verdict against versioned criteria (202/207).
- **"a send is a reception"** — no. Only `mark_acknowledged` with reception evidence writes `acknowledged` (288), and `her_reception` needs evidence (217).
- **"a watcher that fired once is armed"** — no. A watcher answers from a record it can see now (70).
- **"a residual is a trait"** — no. A self-prediction residual is the error of a model he holds, framed as such wherever it is read (140).

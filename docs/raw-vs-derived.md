# Raw versus derived: the markers his records carry

Review items 39 and 159 (2026-09-10). Every record that could be mistaken for what she said or what happened carries a marker saying which it is. This page lists the markers that exist in the checkout, per surface, so a reader (or a writer) knows what to look for. Nothing here is a plan; each line names the field and the file that writes it.

| Surface | Raw (what arrived) | Derived (what an organ made of it) | Requested effect | Acknowledged / observed outcome |
|---|---|---|---|---|
| Chat turn | `interaction-ledger.json` rows: `gloria`, `vintos`, `turn_id`, `surface` (`interaction-ledger.py`); `input_kind` / `original_text` on the message (`server.py`, a9974d5) | `wal_facts`, `salience`, `blush`, `consent` on the same row; WAL `type` (fact/decision/correction/preference/context); `corrections[]` annotated later (`wal-extract.py`, 53fb2dd) | `[DO:]`/`[TOUCH:]` in his reply, compiled by the one grammar (86985b6) | `effect-receipts` via `effect_gate.send_result` with `effect_id`/`permit_digest` (item 91) |
| Voice turn | `voice-session-state.json` turns: `gloria` (normalized), `gloria_raw` (as transcribed), `derived_lines_dropped` (item 333); `vintos_composed` / `vintos_heard` / `interrupted` (item 382) | the hangup block's `felt_summary`, `summary`, `quotes` (model-written) | `[TOUCH:]` counted in `hardware_notes` | `compliance_moments` (what she actually did) |
| Images she sends | the file under `shared-images/` | his description is marked perception, never her words (a9974d5) | - | - |
| Memory index | `kind: authored` (her/his written words), `felt` (his dated writing), `derived` (organ output) on every chunk (`memory-index.py`); `is_dream` and the on-face dream label on retrieval (item 109) | `embed_failed` when the vector is missing (item 103) | - | - |
| Durable memory | `quote.gloria` / `quote.vintos`, `source_turns`, `ledger_match` (item 107) | `what_changed`, `felt_like`, `interpretations[]` (his readings); `invalidated_by` (item 384) | - | - |
| Predictions | `prediction_id`, `predicted`, `provenance` (`prediction_ledger.py`) | `interpretation` (model error / stale / intervening events); one grade record per target (item 208) | - | `actual`, `outcome` GRADED/HELD/STALE |
| Wants | `want`, `source`, `id` | `steps` (planner), `plan_state`, `admission` (item 254) | `outreach` attempt marked before the ntfy | `outreach_last_ok` / `outreach_failed` after it answers (item 295); `receipt` per step (item 232) |
| Artifacts | the file and its `sha256` (`artifact_manifest.build`) | `seen` / `unseen_why`, `verdict`, `suitable` (`image_sight`, item 304) | `delivery.state` queued/sent/failed | `acknowledged` only through `mark_acknowledged` with evidence (item 288); `bytes_verified` on a reveal (item 287) |
| Sensors | `heart-rate.json` `observed_at` / `received_at`; `home-presence.json` `checked` | `sensor-reactions.jsonl` decisions with `why` (item 94) | - | - |
| Enjoyment | `evidence` (a rating she gave, a reply, an acknowledgment) | `his_delight`, `craft` | - | `her_reception` only with evidence (item 217) |

Backwards compatibility: every reader above accepts the older shape without the marker (`store_compat.py` for the two ledger shapes; a missing `kind` on an index chunk is served as version 1; a voice turn without `interrupted` is an uncut reply; a want without `admission` was admitted before the door existed). A marker is never inferred backwards onto an old record.

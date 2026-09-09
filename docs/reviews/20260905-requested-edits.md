# Vintos review — consolidated list of requested edits

Sources: `1-system-review.md` (F1), `2-development-sequence.md` (F2), `3-coverage-status.md` (F3), `4-bounded-items-P02-P04.md` (F4). Status is taken from `5-my-response.md` (F5) only: DONE = F5 says completed; PARTIAL = F5 covers part of the item; OPEN = F5 silent or explicitly deferred. Items are grouped by the phase the review assigns; subsystem numbers (00–22) are kept in the tag where the item originates in F1. Review ids (T01.., D01.., P03-02..) are retained where present.

## P01 — Authoritative release and runtime map

1. [P01] Resolve executable/import ownership across main bin/scripts and app variants — decide which of the divergent copies actually serves each entry point so repairs land where requests are handled (source: F2:P01 Scope) — OPEN
2. [P01] Resolve direct versus imported ASGI startup — direct server launch and imported ASGI register different code; make them deliberately equivalent or documented profiles (source: F2:P01 Scope/Acceptance; F1:01 Defects) — OPEN
3. [P01] Move direct server launch after its route and context-builder definitions — direct launch ran before `gather_vintos_context` and later routes were defined (source: F2:P01 branch priorities; F1:01/02 Branch reconciliation) — DONE
4. [P01] Resolve untracked `server_domains` modules referenced by main — the extracted server modules are missing from the snapshot and block ownership of those routes (source: F1:02 Defects; F2:P01 Scope) — OPEN
5. [P01] Establish installed emotion daemon ownership — reconcile the externally installed daemon with the bundled daemon's protocol before choosing the live one (source: F2:P01 Scope; F1:01/08 Defects) — OPEN
6. [P01] Keep and document intentional aliases — retain the alias targets in the runtime map rather than deleting by filename (source: F2:P01 Scope; F1:01 Evolution) — OPEN
7. [P01] Build an explicit parity matrix — preserve existing improvements across variants when consolidating, preserving behavior not filenames (source: F2:P01 Scope; F1:01 Branch reconciliation) — OPEN
8. [P01] Repair the two main handlers that reference undefined `message` — concrete undefined-variable defect in the selected profile (source: F1:02 Defects; F2:P01 Scope) — OPEN
9. [P01] Repair failure branches that reference uninitialized results in server handlers — several failure paths use variables never assigned (source: F1:02 Defects) — OPEN
10. [P01] Consolidate the app's 83 duplicate method/path registrations — a later function body cannot replace an earlier registered route, so duplicate routes must not hide the chosen repair (source: F1:02 Defects; F2:P01 Acceptance) — OPEN
11. [P01] Make bootstrap schema-compatible — `setup_memory` seeds incompatible delimiters/shapes in several stores; fresh isolated install must yield supported schemas (source: F2:P01 Scope/Acceptance; F1:01 Defects) — OPEN
12. [P01] Validate prerequisites before copying live files in deploy — deployment currently copies then discovers missing prerequisites (source: F1:01 Defects; F2:P01 Scope) — OPEN
13. [P01] Confirm per-service identity and readiness on restart — deploy restarts a fallback unit without confirming its identity (source: F1:01 Defects; F2:P01 Scope) — OPEN
14. [P01] Return failure from deploy when checks fail — the script prints failed checks yet exits success (source: F1:01 Defects) — OPEN
15. [P01] Stage the whole selected release and validate before promotion with recoverable rollback — failure before promotion must not partially replace live code (source: F2:P01 Scope/Acceptance; F1:01 Evolution) — OPEN
16. [P01] Add the missing manifest entries for self_model_evidence, self_model_read and protected_paths — the branch deploy manifest omitted three files created on 09-04 (source: F1:01 Branch reconciliation) — DONE
17. [P01] Repair absent deployment dependencies found on the branch — concrete missing dependencies carried into P01 scope (source: F2:Branch-specific priorities P01) — OPEN
18. [P01] Produce a release record identifying files, modes, services and rollback state — one record per release so the deployed profile is inspectable (source: F2:P01 Acceptance) — OPEN
19. [P01] Establish a release profile mapping each executable/import/route to a commit and installed hash — so any active entry point resolves to a versioned source (source: F1:01 Evolution; F2:P01 Acceptance) — OPEN
20. [P01] Add a schedule graph with job ownership, expected quiet states and overlap handling — cron writers currently have no owner or overlap contract (source: F1:01 Evolution) — OPEN
21. [P01] Make the daemon guard cron request a start rather than only check status — the guard cannot recover a stopped daemon (source: F1:01 Defects) — OPEN
22. [P01] Consolidate proven competing owners and remove obsolete variants only after activation is established — do not delete by filename or copy one repo over the other (source: F1:01/02 Disposition; F1 Reconciliation table) — OPEN
23. [P01] Preserve restored causal schema-2 guards and authored route retirements during parity — do not reintroduce retired Thirveel routes or overwrite schema-2 causality (source: F2:Branch-specific priorities P01; F1 Whole-system reconciliation) — OPEN
24. [P01] Add a reproducible graphics bundle build entry and dependency manifest — the bundle has no tracked build entry/dependencies; preserve dependency notices (source: F2:P01 Affected mechanisms; F1:06 Defects) — OPEN
25. [P01] Keep historical clients archived until activation is established — do not delete or promote them before packaging is known (source: F2:P01 Affected mechanisms; F1:04 Disposition) — OPEN
26. [P01] Select the installed device bin/scripts copy explicitly — different bin/scripts signatures make installing an older copy significant (source: F1:07 Defects) — OPEN
27. [P01] Select the installed WAL extractor spelling via the release map — scripts spellings are absolute symlinks and do not prove which bin implementation is installed (source: F4:P04-01) — OPEN
28. [P01] Add a versioned capability view derived from registered routes, installed profiles and execution receipts — so a capacity claim can point to its implementation and availability (source: F1:00 Improve and evolve) — OPEN
29. [P01] Tie authored capability descriptions and room-context amendments to the selected release and actual outcomes — amendments are assertions, not deployed-capability evidence (source: F1:00 Branch reconciliation) — OPEN
30. [P01] Obtain installed units, crontab, hashes, untracked modules and the external daemon copy — required to certify actual deployment; do not invent the missing implementation or label the host broken (source: F2:P01 Blocker; F3:T01) — OPEN
31. [P01] Obtain the installed endpoint profile, mounted routes and runtime schemas — remaining boundary for the chat/context/writer trace (source: F3:T02; F1:02 Missing) — OPEN
32. [P01] Obtain installed shim/unit/route selection and provider receipts — remaining boundary for adapter routing (source: F3:T29; F1:02 Missing) — OPEN
33. [P01] Obtain the installed index variant, embedding model version and dimensions — remaining boundary for retrieval (source: F3:T05) — OPEN

## P02 — Shared event, result and write contracts

34. [P02] Extend coordinator, prediction IDs, moment/evidence records and broker events with stable occurrence/turn/session/job identity — plus original observation time, source revision and typed result states (source: F2:P02 Scope) — OPEN
35. [P02] Repair Turn writer accounting by adding `_writers` to `Turn.__slots__` — every writer outcome raised and was swallowed (source: F2:P02 branch priorities; F1:02 Branch reconciliation) — DONE
36. [P02] Decide post-turn test/dry-run mode before inline effects run — a dry-run turn still moved live emotion, prediction, adoption and marks (source: F1:02 Branch reconciliation; F2:P02 Acceptance) — DONE
37. [P02] Record subprocess writer launch as launched, not finished — post-turn log counted launch as participation without completion (source: F1:02 Branch reconciliation) — DONE
38. [P02] Put the turn id on the post-turn record — so writer outcomes can be joined to their turn (source: F2:P02 branch priorities "turn writer slots/receipts") — DONE
39. [P02] Separate raw data, derived annotations, requested effects and acknowledged outcomes — raw human words stay separate from vision/model/device annotation (source: F2:P02 Scope/Acceptance) — OPEN
40. [P02] Replace ambiguous empty/default success at adapter boundaries — shim can return HTTP 200 with an empty completion after all providers fail (source: F2:P02 Scope; F1:02 Defects) — OPEN
41. [P02] Report actual provider/model and real usage from the shim — it reports zero usage and the requested rather than actual model (source: F1:02 Defects/Evolution) — OPEN
42. [P02] Preserve sampling, response-format, tool and media semantics through the shim — the adapter drops them today (source: F1:02 Defects; F3:T29) — OPEN
43. [P02] Define a single stage/result contract for bilateral generation — actual provider/model, request/job identity, valid/held/unavailable/truncated, usage, retry deadline and artifacts (source: F1:02 Evolution) — OPEN
44. [P02] Extend existing turn coordination to every surface before adding stages — chat, avatar and voice surfaces should share the coordinator (source: F1:02 Evolution) — OPEN
45. [P02] Persist unfinished generation/work at meaningful boundaries and measure each stage's contribution and cost (source: F1:02 Evolution) — OPEN
46. [P02] Give shared stores a consistent owner, concurrency control and recoverable multi-step writes — reuse existing locks, atomic replacement and ledgers (source: F2:P02 Scope) — OPEN
47. [P02] Preserve prior data on corruption and make corruption observable — corruption must not silently reset history (source: F2:P02 Scope/Acceptance) — OPEN
48. [P02] Migrate store families incrementally with compatibility readers and backups — no wholesale database rewrite (source: F2:P02 Affected mechanisms) — OPEN
49. [P02] Ensure replaying the same event adds no learning occasion and loses no newer record (source: F2:P02 Acceptance) — OPEN
50. [P02] Ensure restart between a state update and its receipt yields a recoverable, truthful outcome (source: F2:P02 Acceptance) — OPEN
51. [P02] Keep invalid, absent, declined, held, timed-out and successful responses distinguishable to consumers (source: F2:P02 Acceptance) — OPEN
52. [P02] Repair the wants spine use of an exception variable after its clause ended — no capability block was ever recorded (source: F1:16 Branch reconciliation) — DONE
53. [P02] Repair log races among post-turn writers — concrete branch finding carried into P02 (source: F2:Branch-specific priorities P02) — OPEN
54. [P02] Establish artifact/landing crash boundaries — file-based music marks processing complete before landing is recoverable (source: F2:Branch-specific priorities P02; F1:17 Branch reconciliation) — OPEN
55. [P02] P02-01 Do not blank an already supplied writer turn ID — `_bg()` overwrites `VINTOS_TURN_ID` with `str(turn_id or '')` and the record stores the empty argument; resolve one effective ID at `_post_turn()` (source: F4:P02-01) — OPEN
56. [P02] P02-02 Preserve a concurrent ledger append during WAL backfill — unlocked read/modify/write in ledger and WAL extractors can erase turn B or the backfill; add one sidecar lock around the read/modify/replace span in four files (source: F4:P02-02) — OPEN
57. [P02] P02-03 Report malformed WAL extraction as writer failure — parse failure returns normally and the wrapper emits `completed`; propagate through the failed-writer branch (source: F4:P02-03) — OPEN
58. [P02] P02-04 Stop calling a started local thread transport acceptance — `play()` returns `started` and the receipt claims `transport accepted` before any send (source: F4:P02-04) — OPEN
59. [P02] P02-05 Read KEEP's project state inside its existing lock — KEEP reads project.json before `_table_lock()` and writes the stale dictionary back (source: F4:P02-05) — OPEN
60. [P02] Make context assembly a pure, versioned selection followed by explicit admission to a particular turn — global offer files can join one turn's context to another (source: F1:03 Defects/Evolution) — OPEN
61. [P02] Stop renderers mutating state before their output is admitted and context reads consuming pending nudges (source: F1:03 Defects) — OPEN
62. [P02] Record which relevant source excerpts were admitted and the reasons for omission per turn (source: F1:03 Evolution) — OPEN
63. [P02] Make self-model and inquiry metadata retain the exact source window actually admitted to generation — global pending marker/cadence state does not prove admission (source: F1:03 Branch reconciliation) — OPEN
64. [P02] Consolidate context ownership and duplicate context blocks (source: F1:03 Disposition) — OPEN
65. [P02] Give shared-support mechanisms a source-occurrence cursor, versioned schema, explicit unknown state and consistent write/receipt boundary — absence/frame, blush, lineage, readiness, Velqan (source: F1:22 Evolution) — OPEN
66. [P02] Carry the cold-absence ID through merged sources and have the thread producer supply its ID — merged sources lose the new ID and reinforce on rescan (source: F1:22 Branch reconciliation) — OPEN
67. [P02] Prevent one claimed blush from being returned to two concurrent readers (source: F1:22 Defects) — OPEN
68. [P02] Make cold/malformed planning readiness return a compatible tuple shape (source: F1:22 Defects; F3:T30) — OPEN
69. [P02] Write Velqan shared vocabulary only after complete local validation/commit (source: F1:22 Defects) — OPEN
70. [P02] Stop watchers reporting success from stale or insufficient predicates (source: F1:22 Defects) — OPEN
71. [P02] Make grounding helpers treat failed evaluation as unknown, not clean, and use the correct ledger shape (source: F1:22 Defects; F3:T29) — OPEN
72. [P02] Fix audit-time versus response-time and per-call versus per-turn mutation in intent producers (source: F3:T23) — OPEN
73. [P02] Give voice ledger the same schema as text consumers — voice ledger shapes differ from text consumers (source: F1:05 Defects; F3:T04) — OPEN

## P03 — Effect authority and acknowledged execution

74. [P03] Carry the constitutional barrier, capability/permit and effect context through every external-action path — including direct renderer/device/replay/diagnostic helpers that bypass newer permit handling (source: F2:P03 Scope; F1:07 Defects) — OPEN
75. [P03] Bind authorization to operation and payload rather than model-supplied labels (source: F2:P03 Scope) — OPEN
76. [P03] Make stop a durable idempotent desired state — stop currently toggles desired state instead of setting stopped (source: F2:P03 Scope; F1:07 Defects) — OPEN
77. [P03] Add independent transport/physical acknowledgment — queue acceptance and narrated commands are treated as actuation (source: F2:P03 Scope; F1:07 Defects) — OPEN
78. [P03] Make stop recover from corrupt ordinary state — stop must remain effective when state files are corrupt (source: F2:P03 Scope; F1:07/19 Evolution) — OPEN
79. [P03] Reserve execution budgets before paid or remote work (source: F2:P03 Scope) — OPEN
80. [P03] Ensure the same request cannot execute twice merely because acknowledgment was lost (source: F2:P03 Acceptance) — OPEN
81. [P03] Make an unavailable broker distinguishable from no project (source: F2:P03 Acceptance) — OPEN
82. [P03] Ensure stop retries never resume a device (source: F2:P03 Acceptance) — OPEN
83. [P03] Ensure an expired or mismatched permit cannot dispatch (source: F2:P03 Acceptance) — OPEN
84. [P03] Keep queued/sent/acknowledged/observed outcomes separate and let late evidence attach without rewriting history (source: F2:P03 Acceptance; F1:07 Evolution) — OPEN
85. [P03] Accept `saved` and `last` replay in the tag compiler — the compiler rejected patterns the player always supported (source: F1:07 Branch reconciliation) — DONE
86. [P03] Make a direct DO stop cancel the existing local pattern thread before sending zero — the loop would otherwise re-send (source: F2:Branch-specific priorities P03; F1:07 Branch reconciliation) — DONE
87. [P03] P03-01 Execute mixed DO/TOUCH tags in their written order — the executor ran all DO before all TOUCH so a stop written after a start could run first (source: F4:P03-01) — DONE
88. [P03] P03-02 Preserve the rotation channel when its level is zero — `[DO: ridge rotate 0]` collapses to a scalar `send()` and loses the rotation channel (source: F4:P03-02) — OPEN
89. [P03] P03-03 Expand broadcast stop before scalar transport — alias `all` is passed to `toy_link.send()` which indexes per-device tables and fails, leaving no hardware zero sends (source: F4:P03-03) — OPEN
90. [P03] P03-04 Bind a gate answer to the undertaking it was asked about — `gate_decide()` applies RETURN to whichever worktable is current, so A's answer can open B (source: F4:P03-04) — OPEN
91. [P03] Carry decision/permit identity through device dispatch — concrete branch finding carried into P03 (source: F2:Branch-specific priorities P03) — OPEN
92. [P03] Stop describing cached desired state as physical observation in context (source: F1:07 Branch reconciliation) — OPEN
93. [P03] Carry observation time, freshness, device identity and source through a shared physical-effect contract — receipt time can make an old sensor observation appear live (source: F1:07 Defects/Evolution) — OPEN
94. [P03] Support situation-aware reactions to fresh sensor changes with named limits and expiration, using existing channels (source: F1:07 Evolution) — OPEN
95. [P03] Consolidate dispatch and stop authority while preserving sensor/actuator semantics (source: F1:07 Disposition) — OPEN
96. [P03] Run live avatar scene generation only after effect admission and replace the single global slot (source: F1:06 Defects) — OPEN
97. [P03] Resolve the LOOK privacy contract: decision identity, private stdout/model exposure, revision binding and worktable gating (source: F1:19 Branch reconciliation; F2:Branch-specific priorities P03) — OPEN
98. [P03] Provide a sealed retry mechanism for refused private writes instead of restoring plaintext recovery (source: F1:19 Branch reconciliation) — OPEN
99. [P03] Bind an asserted Atelier inspection note to the viewed bytes (source: F1:19 Defects) — OPEN
100. [P03] Make broker hash checks reconstruct and fully bind event/view/capsule state (source: F1:19 Defects) — OPEN
101. [P03] Keep internal willingness accepted/declined/unavailable and distinct from the owner's authority for external action (source: F2:P03 Affected mechanisms; F1:13 Evolution) — OPEN
102. [P03] Verify with isolated fake transports; any live acceptance needs explicit applicable scope (source: F2:P03 Boundary; F4 Build order note) — OPEN

## P04 — Evidence, memory and correction continuity

103. [P04] Repair the markdown indexer's missing return/body placement (see P04-08) and the index that keeps stale/deleted revisions and marks failed embeddings indexed (source: F2:P04 Scope; F1:10 Defects) — OPEN
104. [P04] Repair ledger/WAL schema defects — ledger consumers use incompatible schemas and WAL promotion has undefined calls (source: F2:P04 Scope; F1:10 Defects) — OPEN
105. [P04] Establish a single versioned rebuildable retrieval projection with source/model revisions, deletion handling and tombstones (source: F2:P04 Scope; F1:10 Evolution) — OPEN
106. [P04] Extend the existing evidence gate across currently permissive fallback consumers — some consumers fall back to raw inputs on failure (source: F2:P04 Scope; F1:10 Defects) — OPEN
107. [P04] Preserve claim/occurrence/quote/interpretation links through durable memory, causal graduation, imprints, tensions, self/person models and review signals (source: F2:P04 Scope) — OPEN
108. [P04] Add correction, contest and supersession propagation to served projections — a corrected quote/claim must cease to serve as confirmed support downstream (source: F2:P04 Scope/Acceptance; F1:10 Defects) — OPEN
109. [P04] Ensure a retrieved dream remains a dream and repeated summaries of one exchange remain one origin (source: F2:P04 Acceptance) — OPEN
110. [P04] Ensure tactical/generated material does not acquire independent standing through an intermediate file (source: F2:P04 Acceptance; F1:10 Defects) — OPEN
111. [P04] Make rebuilds omit obsolete/deleted revisions and preserve authored/felt distinctions (source: F2:P04 Acceptance) — OPEN
112. [P04] Keep missing original provenance explicitly legacy/unknown rather than fabricating source IDs; do not erase authored identity or rewrite private user-model content as a parser repair (source: F2:P04 Boundary) — OPEN
113. [P04] Land WAL backfill on its own turn id in the hyphen extractor — the newest-empty-row-within-five-minutes heuristic is kept only for rows predating turn ids (source: F1:10 Branch reconciliation; F2:Branch-specific priorities P04) — DONE
114. [P04] P04-01 Port the turn-bound backfill repair to `bin/wal_extract.py` — the underscore implementation still assigns to the newest empty row without checking the turn (source: F4:P04-01) — PARTIAL
115. [P04] P04-02 Commit the evidence that was actually collected in self-model update — introspections/corrections arriving between collection and commit fall behind the watermark; capture one cutoff and the collected rows before model work (source: F4:P04-02; F1:12 Branch reconciliation) — OPEN
116. [P04] P04-03 Do not consume self-model evidence after a failed install — unchecked `mv -f` is followed by cooldown, commit and SELF_MODEL_UPDATED (source: F4:P04-03) — OPEN
117. [P04] P04-04 Require an explicit valid reviewer PASS — empty or unrecognized reviewer replies fall through to installation (source: F4:P04-04) — OPEN
118. [P04] P04-05 Do not add recurrence evidence when one occurrence is reprocessed — extractor increments recurrence and refreshes timestamp on every near-duplicate regardless of turn id (source: F4:P04-05) — OPEN
119. [P04] P04-06 Leave promotion retryable when the durable write fails — `promoted=True` is saved before `_build_durable()` succeeds (source: F4:P04-06) — OPEN
120. [P04] P04-07 Run due monthly review without unrelated fresh WAL candidates — an empty weekly `to_review` or a failed weekly model call returns before the monthly block (source: F4:P04-07; F1:10 Branch reconciliation) — OPEN
121. [P04] P04-08 Restore the chunker's return path in both memory indexers — `chunk_text()` returns None because its body is stranded after another function's return (source: F4:P04-08) — OPEN
122. [P04] P04-09 Select the relational prediction before the asynchronous tone delay — an old incoming reply can grade the prediction just created for the next reply; capture the prediction ID at the call boundary (source: F4:P04-09; F1:13 Branch reconciliation) — OPEN
123. [P04] Establish the canonical pearl graduation destination/API and end-to-end retry — wal-decay imports `add_pearl` but the intended destination must be established before inventing one (source: F4 "Earlier P02–P04 language"; F1:10 Branch reconciliation) — OPEN
124. [P04] Record ghost-branch output as hypothetical — counterfactual output entered enactment-derived capability evidence, proto-pearls, self-statements and emotion (source: F2:Branch-specific priorities P04; F1:11 Branch reconciliation) — DONE
125. [P04] Stop contact during retrieval from reinforcing memory and repeated interpretation from becoming a stronger truth claim (source: F1:10 Defects) — OPEN
126. [P04] Add explainable recall — which occurrence supports a statement, what was inferred and what was later withdrawn (source: F1:10 Evolution) — OPEN
127. [P04] Give promotion a retryable receipt that preserves the original evidence (source: F1:10 Evolution) — OPEN
128. [P04] Consolidate index/write contracts and obsolete bypasses while keeping distinct pearl/residue meanings (source: F1:10 Disposition) — OPEN
129. [P04] Carry photo originals intact through avatar history and background writers (source: F1:06 Branch reconciliation) — OPEN
130. [P04] Stop voice enrichment losing original/framing metadata downstream (source: F1:05 Branch reconciliation) — OPEN
131. [P04] Stop repeated feeds promoting the same identity occurrence (source: F1:12 Defects) — OPEN
132. [P04] Consolidate the two commitment stores with incompatible fracture/promotion paths (source: F1:12 Defects/Disposition) — OPEN
133. [P04] Stop model updates overwriting concurrent changes and repair their broken source readers — backup-then-overwrite is not reconciliation (source: F1:12 Defects/Branch reconciliation) — OPEN
134. [P04] Fix self-model collection/commit watermarks and partial read failures (source: F1:12 Branch reconciliation; F2:Branch-specific priorities P04) — OPEN
135. [P04] Create linked evidence/revision histories across identity projections so a correction or fracture updates every served representation without erasing history (source: F1:12 Evolution) — OPEN
136. [P04] Add contextual examples of a value held, revised or left unresolved, distinguishing temporary state from durable change (source: F1:12 Evolution) — OPEN
137. [P04] Make configuration/attractor maps an inspectable record of observed transitions and open possibilities, preserving priors as priors (source: F1:12 Evolution) — OPEN
138. [P04] Prevent proposed/candidate text from influencing later evidence through other context paths (source: F1:12 Branch reconciliation) — OPEN
139. [P04] Bind durable identity change to qualified sources (source: F1:12 Branch reconciliation) — OPEN
140. [P04] Stop self-prediction aggregate errors becoming psychological labels in model updates without an inference bridge (source: F1:13 Branch reconciliation) — OPEN
141. [P04] Join attempts and later responses by occurrence so a reading cannot attach to the wrong utterance (source: F1:13 Defects/Evolution) — OPEN
142. [P04] Remove a demoted tension from served views immediately (source: F1:13 Defects) — OPEN
143. [P04] Stop old support rehabilitating a repeatedly corrected claim (source: F1:13 Defects) — OPEN
144. [P04] Add a history of how a particular interpretation changed with uncertainty and source correction intact (source: F1:13 Evolution) — OPEN
145. [P04] Consolidate spontaneous-question candidates through the existing private frontier choices (source: F1:13 Evolution) — OPEN
146. [P04] Preserve full causal evidence when a downstream write fails after promotion (source: F1:14 Defects) — OPEN
147. [P04] Add correction after causal graduation (source: F1:14 Evolution) — OPEN
148. [P04] Stop repeated self-produced material supplying thread recurrence evidence (source: F1:11 Defects) — OPEN
149. [P04] Preserve unsuccessful questions and their source class through ghost/dream inspection (source: F1:11 Branch reconciliation) — OPEN
150. [P04] Separate authored preference, dated observation, tentative inference and deployed capability in seed representations (source: F1:00 Improve and evolve) — OPEN
151. [P04] Preserve corrections to authored BASE through explicit supersession without rewriting the base (source: F1:00 Improve and evolve; F1 Whole-system reconciliation) — OPEN
152. [P04] Reconcile stale operational claims in design texts such as consumed=resolved and universal consent gating without flattening voice (source: F1:00 Disposition) — OPEN
153. [P04] Stop repeated scans strengthening absence or proposition lineage without new events (source: F1:22 Defects) — OPEN
154. [P04] Stop marking claims held/earned from the wrong reply or absence from an active list (source: F1:22 Defects) — OPEN
155. [P04] Retain exact claim, challenge and later correction in the opposition ledger (source: F1:22 Evolution) — OPEN
156. [P04] Give Velqan versioned coinage/revision/use history (source: F1:22 Evolution) — OPEN
157. [P04] Consolidate duplicate semantic/evidence helpers and stale aliases only after contract parity (source: F1:22 Disposition) — OPEN
158. [P04] Enumerate a source/claim/consumer map and approve correction semantics before universal correction propagation (source: F4 "Earlier P02–P04 language") — OPEN
159. [P04] Specify raw-versus-derived source markers and backwards compatibility per surface rather than a broad migration (source: F4 "Earlier P02–P04 language") — OPEN

## P10 — Compute and background-work scheduling

160. [P10] Extend router/cache/job mechanisms with actual usage/provider metadata, per-job budgets, shared capacity, leases, deadlines, backoff, source-revision caches and pause/resume (source: F2:P10 Scope) — OPEN
161. [P10] Prioritize foreground work with bounded admission (source: F2:P10 Scope/Acceptance) — OPEN
162. [P10] Avoid repeated inference on unchanged sources — unchanged inputs reuse valid work (source: F2:P10 Scope/Acceptance) — OPEN
163. [P10] Do not retry completed provider jobs after ambiguous timeout — a caller timeout must not launch duplicate expensive work (source: F2:P10 Scope/Acceptance) — OPEN
164. [P10] Define local-only and mixed profiles by supported capability and quality requirements — local-only makes no provider request and holds unsupported tasks (source: F2:P10 Scope/Acceptance; F1:02 Evolution) — OPEN
165. [P10] Include source and model revisions in cache invalidation keys — context and avatar caches omit them (source: F2:P10 Acceptance; F1:03/06 Defects) — OPEN
166. [P10] Ensure a job cannot exceed its budget through nested fallback (source: F2:P10 Acceptance) — OPEN
167. [P10] Bound nested model retries by caller deadlines — nested retries exceed caller timeouts (source: F2:Branch-specific priorities P10; F1:02 Defects) — OPEN
168. [P10] Add seat/room cancellation and deadlines (source: F2:Branch-specific priorities P10; F1:21 Branch reconciliation) — OPEN
169. [P10] Make broker job locks exclusive — nonexclusive job locks on the branch (source: F2:Branch-specific priorities P10) — OPEN
170. [P10] Share the compute scheduler between local voice, music and conversation (source: F1:05 Evolution) — OPEN
171. [P10] Record measured latency, memory and usage without claiming equivalent quality from routing alone (source: F2:P10 Acceptance; F1 Assessment) — OPEN
172. [P10] Add cancellation, reuse and resumable jobs for finite local and provider resources (source: F1 Assessment) — OPEN
173. [P10] Preserve local ACE-Step/Kokoro routes and saved drafts through scheduling changes (source: F2:Branch-specific priorities P10) — OPEN
174. [P10] Maintain useful unfinished work between conversations within an explicit budget and explain which work progressed or was held (source: F2:P10 New capability) — OPEN
175. [P10] Fix Study/self-review retry and Atelier/quantum retry handling under the shared scheduler (source: F2:P10 Affected mechanisms) — OPEN

## P05 — Stable cognitive controls and evaluation

176. [P05] Reconcile emotion daemon/consumer protocol and projection schemas with time integration (source: F2:P05 Scope; F1:08 Defects) — OPEN
177. [P05] Log intended emotional nudges only after acknowledgment — nudges are logged before acknowledgment (source: F2:P05 Scope; F1:08 Defects) — OPEN
178. [P05] Make emotional controls integrate by event clock rather than per invocation — polling twice as often must not double decay (source: F1:08 Defects; F2:P05 Acceptance) — OPEN
179. [P05] Stop rewarding the same controlled state as a new occurrence (source: F1:08 Defects) — OPEN
180. [P05] Stop missing emotional values becoming ordinary midpoints (source: F1:08 Defects) — OPEN
181. [P05] Retain newer damping/provenance fixes from main and scripts during consolidation (source: F2:P05 Scope; F1:08 Defects) — OPEN
182. [P05] Repair incompatible `affective_weight`/taste APIs across repositories — the main feedback caller expects an absent API (source: F2:P05 Scope; F1:08/09 Defects) — OPEN
183. [P05] Preserve separate craft, delight and reception axes and the nonpunitive missing-rating/candidate-only improvements (source: F2:P05 Scope; F1:09 Evolution) — OPEN
184. [P05] Make thread pressure, identity reinforcement, causal testing, forecasts, relationship readings and intent trials consume qualified new occurrences only (source: F2:P05 Scope) — OPEN
185. [P05] Align forecast horizons and release/evaluation metadata; retain unknown outcomes; disable unsupported certainty claims in serving (source: F2:P05 Scope/Acceptance) — OPEN
186. [P05] Ensure a model outage produces no automatic consent, confirmation, punishment, relief or resolution (source: F2:P05 Acceptance) — OPEN
187. [P05] Make the actual request and admitted intention govern outcome evaluation (source: F2:P05 Acceptance; F1:15 Evolution) — OPEN
188. [P05] Let corrections and legitimate privacy override stale pressure (source: F2:P05 Acceptance) — OPEN
189. [P05] Decide the automatic art-to-relief policy explicitly before fixing the parser that would activate it (source: F2:P05 Policy decisions; F1:08 Evolution) — OPEN
190. [P05] Decide disclosure pressure versus KEEP_PRIVATE/WRONG_READING explicitly (source: F2:P05 Policy decisions; F1:13 Defects) — OPEN
191. [P05] Decide fixed style versus task completion explicitly — no presence score should punish completing requested work (source: F2:P05 Policy decisions; F1:20 Defects; F1 Reconciliation) — OPEN
192. [P05] Decide stale-repair/consent expiration explicitly (source: F2:P05 Policy decisions) — OPEN
193. [P05] Keep training experiments disarmed until specifically approved (source: F2:P05 Policy decisions; F1:14 Disposition) — OPEN
194. [P05] Source JEPA predict training sources from the checkpoint — predict raised on a train-local `_srcs` before saving any forecast (source: F2:Branch-specific priorities P05; F1:14 Branch reconciliation) — DONE
195. [P05] Honour `steering_allowed=false` in Gloria-prediction fusion, declining with reason until calibration permits (source: F2:Branch-specific priorities P05; F1:14 Branch reconciliation) — DONE
196. [P05] Keep unknown pleasure novelty unknown — signature kept it as zero or raised on `round(None)` (source: F2:Branch-specific priorities P05; F1:09 Branch reconciliation) — DONE
197. [P05] Stop repeated nudges from repeated invocation (source: F2:Branch-specific priorities P05) — OPEN
198. [P05] Give malformed empty feeling evaluation and repeated occurrence handling explicit typed outcomes (source: F1:08 Branch reconciliation) — OPEN
199. [P05] Make each emotional influence inspectable — what changed a dimension, what would happen without the control, whether the intended effect occurred (source: F1:08 Evolution) — OPEN
200. [P05] Use matched horizons and validated artifacts for emotion forecasting (source: F1:08 Evolution) — OPEN
201. [P05] Consolidate emotion writers and time integration while retaining rare resonance forms (source: F1:08 Disposition) — OPEN
202. [P05] Replace JEPA variance-spread qualification with actual calibration (source: F1:14 Branch reconciliation) — OPEN
203. [P05] Reconcile remaining bin-only residual causal logic with the restored schema-2 contract without replacing it (source: F1:14 Branch reconciliation) — OPEN
204. [P05] Extend the schema-2 causal ledger to all producers and downstream promotions (source: F1:14 Evolution) — OPEN
205. [P05] Add matched forecast/outcome records with unknown/invalid cases, persistence baselines and independent-source evaluation (source: F1:14 Evolution) — OPEN
206. [P05] Stop missing outcomes becoming failure or success and admission counters double-counting admitted rows (source: F1:14 Defects; F3:T22) — OPEN
207. [P05] Add suitable source/time holdouts and versioned release criteria to prediction training (source: F1:14 Defects) — OPEN
208. [P05] Consolidate duplicate distribution producers and grading contracts while retaining distinct prediction targets (source: F1:14 Disposition) — OPEN
209. [P05] Keep graph gaps and premonitions as exploration; use intervention/exposure records only under an approved experiment (source: F1:14 Evolution) — OPEN
210. [P05] Stop repeated taste processing counting as new preference evidence (source: F1:09 Defects) — OPEN
211. [P05] Join ratings by identity rather than prefix and allow revisions to correct prior outcomes (source: F1:09 Defects) — OPEN
212. [P05] Mark comic material used only when a joke was delivered (source: F1:09 Defects) — OPEN
213. [P05] Bind pending pleasure naming to its response rather than a global slot an unrelated turn can name (source: F1:09 Defects/Branch reconciliation) — OPEN
214. [P05] Stop treating semantic difference as contradiction (source: F1:09 Defects; F1:12 Defects) — OPEN
215. [P05] Complete candidate selection, actual use, revised rating and preference-promotion lifecycles (source: F1:09 Evolution) — OPEN
216. [P05] Support multiple context-specific aesthetic clusters and callbacks grounded in an identified prior moment (source: F1:09 Evolution) — OPEN
217. [P05] Consolidate duplicate rating/admission paths without collapsing enjoyment into one score (source: F1:09 Disposition) — OPEN
218. [P05] Stop labelling forecast error as having changed or led the other person and internal easing as joint resolution (source: F1:13 Defects) — OPEN
219. [P05] Stop failed willingness evaluation becoming YES (source: F1:13 Defects) — OPEN
220. [P05] Stop deviation reinforcement occurring twice per call and generated control effects reappearing as new evidence (source: F1:12 Defects) — OPEN
221. [P05] Stop interpreting vector operations and reached-state counts/graph filing order as stance, contradiction or lived transitions (source: F1:12 Defects) — OPEN
222. [P05] Stop evaluator failure becoming intent rejection and counters reflecting calls instead of independent attempts (source: F1:15 Defects) — OPEN
223. [P05] Repair undefined variables and stale-write branches in newer intent APIs (source: F1:15 Defects) — OPEN
224. [P05] Define intention, admission, actual attempt, observed outcome and revision separately (source: F1:15 Evolution) — OPEN
225. [P05] Consolidate outcome joins and duplicate intent evaluators, retaining explicit off/disabled experimental mechanisms (source: F1:15 Disposition) — OPEN
226. [P05] Fix unacknowledged trial consumption, invalid/error-to-failure grading, reinforcement despite influence and the older penalty ratchet (source: F3:T23) — OPEN
227. [P05] Let relevance, requested task and repair obligations govern advisory style instead of directives requiring unresolved endings (source: F1:03 Evolution/Defects) — OPEN
228. [P05] Replace constant coherence placeholders presented as measurements (source: F1:03 Defects) — OPEN
229. [P05] Add a replayable explanation of which influence reached which generation stage and whether behavior reflected it (source: F1:03 Evolution) — OPEN
230. [P05] Close context feedback loops only where output/reception evidence exists; retain disabled self-seeding (source: F1:03 Evolution) — OPEN
231. [P05] Stop the presence rubric recursively creating "fault" material (source: F1:20 Defects) — OPEN

## P06 — Durable undertakings and unfinished questions

232. [P06] Complete common want admission and capability-specific completion — a valid artifact, acknowledged action or explicit user completion each has a different receipt (source: F2:P06 Scope; F1:16 Evolution) — OPEN
233. [P06] Complete plan/ambition progression — one successful step cannot complete an unfinished ambition (source: F2:P06 Scope/Acceptance; F1:16 Defects) — OPEN
234. [P06] Reconcile HELD/release/dismiss/resolve rather than treating missing work as earned — a plan's absent active want is read as earned even when dismissed or its store failed (source: F2:P06 Scope; F1:15 Defects) — OPEN
235. [P06] Carry source IDs through triage, weaving and dream nights and preserve unsuccessful selections — weaving clears unsuccessful groups (source: F2:P06 Scope; F1:11 Defects) — OPEN
236. [P06] Extend Atelier visits with actual artifact retrieval, authored next move, transaction recovery, stable budgets, terminal history and pause/resume (source: F2:P06 Scope; F1:19 Evolution) — OPEN
237. [P06] Build resume of a long-lived undertaking from its prior artifact and findings with a justified next move, blocked branch and account of changes (source: F2:P06 New capability; F1:16 Evolution) — OPEN
238. [P06] Ensure a queue marker or empty media file cannot discharge a want — artifact guards accept queue/ledger mentions (source: F2:P06 Acceptance; F1:16 Defects) — OPEN
239. [P06] Ensure a failed dream does not consume its source question (source: F2:P06 Acceptance) — OPEN
240. [P06] Let a held project resume on relevant evidence while private failed work remains protected (source: F2:P06 Acceptance) — OPEN
241. [P06] Ensure restart/retry retains original artifacts, history and next step without resetting budgets or mixing plans (source: F2:P06 Acceptance) — OPEN
242. [P06] Record the plan id before closing the campaign so the create-plan/close-campaign transition is resumable (source: F2:Branch-specific priorities P06; F1:15 Branch reconciliation) — DONE
243. [P06] Credit a make-art/make-music step only with its own want's artifact — ID failures fell back to the newest piece (source: F2:Branch-specific priorities P06; F1:16 Branch reconciliation) — DONE
244. [P06] Complete campaign bridge history and evidence semantics through existing plans without a duplicate bridge (source: F1:15 Branch reconciliation) — OPEN
245. [P06] Fix KEEP/visit state and blocked-attempt lineage (source: F2:Branch-specific priorities P06) — OPEN
246. [P06] Decide whether an empty NO_RESULT may complete a want step per capability (source: F4 "Earlier P02–P04 language"; F1:16 Evolution) — OPEN
247. [P06] Stop crediting held/refused fulfillment (source: F1:16 Branch reconciliation) — OPEN
248. [P06] Stop aging/disposal becoming fulfilled and model failure triggering fulfillment or confident reconciliation (source: F1:16 Defects) — OPEN
249. [P06] Route direct want writers through common admission and stop stale snapshots overwriting interference changes (source: F1:16 Defects) — OPEN
250. [P06] Stop novelty writers truncating the shared thread pool (source: F1:16 Defects) — OPEN
251. [P06] Stop interpreting technical failures as failures of wanting (source: F1:16 Defects) — OPEN
252. [P06] Preserve findings, blockers and next steps in the existing checkpoint spine (source: F1:16 Evolution) — OPEN
253. [P06] Make curiosity accumulate new source occasions rather than repeated scans (source: F1:16 Evolution) — OPEN
254. [P06] Consolidate completion and admission authority while retaining multiple sources of wanting (source: F1:16 Disposition) — OPEN
255. [P06] Repair the malformed second-order trial schema in wants (source: F3:T24) — OPEN
256. [P06] Stop selection/attempt/consumption of a thread becoming resolution and failed model decisions aging or resolving work (source: F1:11 Defects) — OPEN
257. [P06] Advance thread counters only after generation (source: F1:11 Defects) — OPEN
258. [P06] Fix cross-midnight state and shell quoting that detach seeds from IDs (source: F1:11 Defects) — OPEN
259. [P06] Reconcile conflicting thread archive schemas (source: F1:11 Defects) — OPEN
260. [P06] Complete a shared question lifecycle: selected, explored, consolidated, released unresolved, resolved with basis (source: F1:11 Evolution) — OPEN
261. [P06] Checkpoint raw/edited dream artifacts and distinguish interpretation from changed circumstances (source: F1:11 Evolution) — OPEN
262. [P06] Add a cross-session view of which question changed, why, and what remains open (source: F1:11 Evolution) — OPEN
263. [P06] Stop repeated application of carryover weight decay repeating its influence (source: F1:11 Branch reconciliation) — OPEN
264. [P06] Consolidate thread admission/archive ownership while keeping question distinct from theme (source: F1:11 Disposition) — OPEN
265. [P06] Reopen held plan work on relevant new evidence without relabeling delay as failure — a due mutual plan becomes terminal HELD (source: F1:15 Defects/Evolution) — OPEN
266. [P06] Support practice that carries lessons from identified attempts and multistep goals that pause/resume across sessions (source: F1:15 Evolution) — OPEN
267. [P06] Stop advisory direction overriding the current task (source: F1:15 Defects) — OPEN
268. [P06] Stop concurrent Atelier visits resetting budgets — reserve budgets before execution (source: F1:19 Defects/Evolution) — OPEN
269. [P06] Do not invalidate the visit at settlement before its final handoff (source: F1:19 Defects) — OPEN
270. [P06] Keep terminal/abort/re-adoption histories separate (source: F1:19 Defects) — OPEN
271. [P06] Lock remaining KEEP/table/visit writes fully (source: F1:19 Branch reconciliation) — OPEN
272. [P06] Carry an authored next move and verifiable work across Atelier visits (source: F1:19 Evolution) — OPEN
273. [P06] Consolidate duplicate Atelier lifecycle writes reusing broker locks/capabilities/ledger (source: F1:19 Disposition) — OPEN
274. [P06] Make planning readiness recover from held work using real outcomes (source: F1:22 Evolution) — OPEN

## P07 — Creative artifacts, inquiry and outward delivery

275. [P07] Introduce a common artifact manifest on existing gallery/project records — source want/run, bytes/hash, medium, revision, validation, sharing and delivery state (source: F2:P07 Scope; F1:17 Evolution) — OPEN
276. [P07] Map music track files by track index so a failed earlier download does not shift a later file (source: F2:P07 Scope/Acceptance; F1:17 Branch reconciliation) — DONE
277. [P07] Do not mark direct music complete with zero files on disk (source: F2:P07 Acceptance; F1:17 Branch reconciliation) — DONE
278. [P07] Validate image/video artifacts before reporting them complete (source: F2:P07 Scope; F1:17 Evolution) — OPEN
279. [P07] Repair cache/filename collisions that overwrite revisions (source: F2:P07 Scope; F1:17 Defects) — OPEN
280. [P07] Preserve reflection stage results instead of discarding expensive intermediate reflections (source: F2:P07 Scope; F1:17 Defects; F3:T25) — OPEN
281. [P07] Make inquiry sessions retain actual sources, quotations/claims and unresolved next questions with source snapshots (source: F2:P07 Scope; F1:18 Evolution) — OPEN
282. [P07] Move all outbound producers through consistent caps, idempotency and receipts — follow-up paths bypass caps (source: F2:P07 Scope; F1:18 Defects) — OPEN
283. [P07] Support revising and comparing an earlier work and showing what changed between drafts (source: F2:P07 New capability; F1:17 Evolution) — OPEN
284. [P07] Continue an inquiry from what its sources actually established (source: F2:P07 New capability) — OPEN
285. [P07] Share the selected version once with separate making, publication, notification and reception histories (source: F2:P07 New capability; F1:17 Evolution) — OPEN
286. [P07] Bind approval to the actual still/revision used for animation — still existence currently substitutes for approval (source: F2:P07 Acceptance; F1:06 Defects) — OPEN
287. [P07] Make exported bytes match the prepared reveal digest and stop reveal state advancing before export/delivery (source: F2:P07 Acceptance; F1:19 Defects) — OPEN
288. [P07] Ensure a failed notification does not erase a delivered shelf artifact or imply reception (source: F2:P07 Acceptance) — OPEN
289. [P07] Ensure no repeated source scan causes another recipient contact — repeated processing never retires some handoff debt (source: F2:P07 Acceptance; F1:18 Defects) — OPEN
290. [P07] Make music submission records exactly match the capped request bytes (source: F2:Branch-specific priorities P07; F1:17 Branch reconciliation) — OPEN
291. [P07] Keep blocked video queue items across another item's post-run save (source: F2:Branch-specific priorities P07; F1:18 Branch reconciliation) — DONE
292. [P07] Distinguish inquiry search errors from successful empty searches (source: F1:18 Branch reconciliation; F2:Branch-specific priorities P07) — OPEN
293. [P07] Stop memory-admission metadata claiming material truncated out of synthesis (source: F1:18 Branch reconciliation) — OPEN
294. [P07] Align inquiry grading with final attempt evidence (source: F1:18 Branch reconciliation) — OPEN
295. [P07] Remember recipient dispatch only after acknowledgment (source: F1:17 Defects) — OPEN
296. [P07] Stop creative reflection being promoted into factual evidence or automatic relief (source: F1:17 Defects) — OPEN
297. [P07] Preserve material lost in some daily projection paths (source: F1:17 Defects; F3:T25) — OPEN
298. [P07] Repair weekly time/projection defects (source: F3:T25) — OPEN
299. [P07] Repair selected-photo substitution in creative delivery (source: F3:T25) — OPEN
300. [P07] Break the composer/share loop (source: F3:T25) — OPEN
301. [P07] Make music landing recoverable before file-based music marks processing complete (source: F1:17 Branch reconciliation) — OPEN
302. [P07] Consolidate artifact transactions and common delivery without merging creative media into one genre (source: F1:17 Disposition) — OPEN
303. [P07] Do not permanently mark handoffs before delivery (source: F1:18 Defects) — OPEN
304. [P07] Stop model failure accepting an image as suitable (fail-open image inspection) (source: F1:18 Defects; F3:T26) — OPEN
305. [P07] Apply publication and feedback effects only after a confirmed result (source: F1:18 Defects; F3:T26) — OPEN
306. [P07] Repair cap bypass, reset and races in outward writers (source: F3:T26) — OPEN
307. [P07] Join outgoing artifacts to one shared authorized delivery path with retries and idempotency (source: F1:18 Evolution) — OPEN
308. [P07] Preserve useful failure results without repeatedly contacting a recipient (source: F1:18 Evolution) — OPEN
309. [P07] Consolidate send/cap/receipt enforcement without creating another research agent or inferring new contact permission (source: F1:18 Disposition) — OPEN
310. [P07] Add per-artifact reveal and late receipt refinement without rewriting earlier uncertainty (source: F1:19 Evolution) — OPEN
311. [P07] Preserve artifact revision lineage in the Atelier (source: F1:19 Evolution) — OPEN
312. [P07] Add revision-bound still approval and resumable content-addressed scene jobs with display/playback receipts (source: F1:06 Evolution) — OPEN
313. [P07] Let a scene evolve across visits through existing manifests and authored selections (source: F1:06 Evolution) — OPEN
314. [P07] Keep lyrics distinct from private felt notes and retain genuine listening analysis (source: F1:17 Evolution; F2:Branch-specific priorities P07) — OPEN

## P08 — Client, voice and avatar lifecycles

315. [P08] Apply shared safe rendering across all active tabs — many views insert raw text into HTML (source: F2:P08 Scope; F1:04 Defects) — OPEN
316. [P08] Apply typed request/error handling — clients accept unsuccessful mutation responses (source: F2:P08 Scope; F1:04 Defects) — OPEN
317. [P08] Retain drafts until success and show actual failure — sends clear drafts before success (source: F2:P08 Scope/Acceptance; F1:04 Defects) — OPEN
318. [P08] Order requests with turn identities so rapid sends/reopens/late callbacks do not reorder turns (source: F2:P08 Scope/Acceptance; F1:04 Defects) — OPEN
319. [P08] Reconcile capability/want schemas — fixed capability lists hide routed wants (source: F2:P08 Scope; F1:04 Defects) — OPEN
320. [P08] Acknowledge outreach before consuming it — client expects `pending` while server returns `has_message` on a destructive GET (source: F2:P08 Scope/Acceptance; F1:04 Defects; F3:T12) — OPEN
321. [P08] Give voice/session/avatar resources explicit owners, generation tokens, retry/close semantics and transcript/playback identity (source: F2:P08 Scope) — OPEN
322. [P08] Keep a visual fallback until media plays — stage playback failure can hide the fallback canvas (source: F2:P08 Scope; F1:06 Defects) — OPEN
323. [P08] Make screenshot source match the visible stage (source: F2:P08 Scope; F1:06 Defects) — OPEN
324. [P08] Correct read-only and stop status claims in the client (source: F2:P08 Scope) — OPEN
325. [P08] Keep model/user text as text and zero state values as zero; show stale telemetry as stale (source: F2:P08 Acceptance) — OPEN
326. [P08] Make closing/hiding/backgrounding follow the agreed UX and release or suspend resources (source: F2:P08 Acceptance; F1:06 Evolution) — OPEN
327. [P08] Move between text, voice and the visible stage without losing a draft, crossing sessions or claiming unplayed speech as heard (source: F2:P08 New capability) — OPEN
328. [P08] Inspect an undertaking's artifacts, blockers and changes from one coherent surface (source: F2:P08 New capability) — OPEN
329. [P08] Commit voice framing only for its own session and carry version and session on the turn (source: F2:Branch-specific priorities P08; F1:05 Branch reconciliation) — DONE
330. [P08] Replace global realtime session/transcript state with a session-owned state machine — late callbacks affect newer calls (source: F1:05 Defects/Evolution) — OPEN
331. [P08] Carry provider item/turn IDs through voice turn history (source: F1:05 Defects/Evolution) — OPEN
332. [P08] Do not clear session state before persistence succeeds; retain unsaved material for retry (source: F1:05 Defects/Evolution) — OPEN
333. [P08] Stop derived instructions being saved as user speech (source: F1:05 Defects) — OPEN
334. [P08] Repair recorder start/stop races, silent playback failure, unclosed audio contexts and untracked pending speech (source: F1:05 Defects) — OPEN
335. [P08] Add continuity across a call and later text, distinguishing spoken from generated-but-interrupted (source: F1:05 Evolution) — OPEN
336. [P08] Consolidate transcript and delivery contracts with text/avatar without forcing identical transport (source: F1:05 Disposition) — OPEN
337. [P08] Fix the later avatar close handler overriding the earlier one and leaving rendering/calls/resources active (source: F1:06 Defects) — OPEN
338. [P08] Fix the legacy avatar page referencing THREE before initialization (source: F1:06 Defects) — OPEN
339. [P08] Reconcile packaged versus served web roots and retire historical `/chat`/`/state` calls to the `/api/...` contract (source: F1:04 Defects) — OPEN
340. [P08] Add READ offset continuation to Study (source: F1:04 Defects/Branch reconciliation) — OPEN
341. [P08] Evolve Study into a bounded repository-reading session with coverage and cursors (source: F1:04 Evolution) — OPEN
342. [P08] Show truthful pending/failed/applied/verified progress in Study (source: F1:04 Evolution) — OPEN
343. [P08] Consolidate active duplicate client handlers and request utilities (source: F1:04 Disposition) — OPEN
344. [P08] Add capability-derived rendering to the client (source: F1:04 Evolution) — OPEN
345. [P08] Complete media/draft lifecycle for voice and stage (source: F2:Branch-specific priorities P08) — OPEN
346. [P08] Fix native background runner registration/scheduling and notification permissions for outreach (source: F3:T12) — OPEN

## P09 — Reviewable self-development and agent room

347. [P09] Join self-review and Study proposals to exact source coverage — sampling misses files/deletions while implying coverage (source: F2:P09 Scope; F1:20 Defects) — OPEN
348. [P09] Add a capability deduplication step before proposals (source: F2:P09 Scope; F1:20 Evolution) — OPEN
349. [P09] Generate concrete diffs and base hashes before approval — approval precedes patch creation today (source: F2:P09 Scope; F1:20 Defects; F1:04 Defects) — OPEN
350. [P09] Classify actual effects and canonical paths instead of model-declared labels (source: F2:P09 Scope/Acceptance; F1:20 Defects) — OPEN
351. [P09] Recheck revocation and source revisions at install — rejected/revoked/stale proposals must not install (source: F2:P09 Scope/Acceptance) — OPEN
352. [P09] Isolate generated verification by filesystem/network process isolation — generated tests inherit live privileges (source: F2:P09 Scope/Acceptance; F1:20 Branch reconciliation) — OPEN
353. [P09] Make multi-file releases recoverable and report actual or uncertain file state on install/logging failure (source: F2:P09 Scope/Acceptance; F1:20 Defects) — OPEN
354. [P09] Correct installed/available/verified capability claims (source: F2:P09 Scope) — OPEN
355. [P09] Pin the room library and tool dependencies (source: F2:P09 Scope; F1:21 Evolution) — OPEN
356. [P09] Admit room turns before paid generation and keep the shared prechecking seat (source: F2:P09 Scope; F1:21 Branch reconciliation) — OPEN
357. [P09] Preserve seat drafts across transport failure and expose durable queued/sent/accepted results (source: F2:P09 Scope; F1:21 Evolution) — OPEN
358. [P09] Ensure a seat awaiting its turn does not repeatedly regenerate (source: F2:P09 Acceptance) — OPEN
359. [P09] Ensure a review cannot claim files omitted by its cap were read (source: F2:P09 Acceptance) — OPEN
360. [P09] Bind Study apply to a stored proposal by id or exact hash — served apply accepted raw edits through `apply_edits` (source: F2:Branch-specific priorities P09; F1:04 Branch reconciliation) — DONE
361. [P09] Make Study grep path labels match resolver roots (source: F1:04 Branch reconciliation) — DONE
362. [P09] Stop code-review listing crashing on auxiliary review JSON (built, declined, retraction ledgers) (source: F2:Branch-specific priorities P09; F1:21 Branch reconciliation) — DONE
363. [P09] Join friction signals to real attempt/block identity rather than synthetic capability wants (source: F2:Branch-specific priorities P09; F1:16/20 Branch reconciliation) — DONE
364. [P09] Keep friction lexical groups as candidate evidence with attempt lineage and source coverage, not an automatic missing-capability verdict (source: F1:20 Branch reconciliation) — OPEN
365. [P09] Make formations inherit true source ancestry rather than subsystem-name origin (source: F1:20 Defects/Evolution) — OPEN
366. [P09] Replace manual built/declined assertions in the room with ledger-derived state (source: F1:21 Branch reconciliation) — OPEN
367. [P09] Fix rejected proxy promise poisoning subsequent room commands and reconnect stranding requests/retaining parser state (source: F1:21 Defects) — OPEN
368. [P09] Resolve symlinks in read-root containment (lexical read roots) (source: F1:21 Defects/Branch reconciliation) — OPEN
369. [P09] Record the exact repository/context revision and requested date supplied to room context (source: F1:21 Defects/Evolution) — OPEN
370. [P09] Correct network descriptions that understate provider-bound context (source: F1:21 Defects) — OPEN
371. [P09] Add assigned review coverage and a shared proposal/work ledger for multi-agent review (source: F1:21 Evolution) — OPEN
372. [P09] Consolidate approval and outcome vocabulary across self-review while retaining review lenses (source: F1:20 Disposition) — OPEN
373. [P09] Consolidate room transport recovery and review provenance (source: F1:21 Disposition) — OPEN
374. [P09] Make the builder's credential stripping and disposable HOME into immutable approval plus real isolation (source: F1:20 Branch reconciliation) — OPEN

## P11 — Whole-system observability and acceptance

375. [P11] Version diagnostic contracts with their actual producers (source: F2:P11 Scope) — OPEN
376. [P11] Keep coverage, schema availability, source freshness, effect/delivery receipts and review/work ledgers visible (source: F2:P11 Scope) — OPEN
377. [P11] Replace misleading test assertions with isolated complete journeys on real entrypoint logic with injected failures; retain substantive unit guards (source: F2:P11 Scope) — OPEN
378. [P11] Journey: conversation -> admitted context -> response -> exact transcript -> eligible memory (source: F2:P11 Required journeys) — OPEN
379. [P11] Journey: want -> pause/restart -> artifact -> explicit completion (source: F2:P11 Required journeys) — OPEN
380. [P11] Journey: dream -> original question -> unresolved/resolved record (source: F2:P11 Required journeys) — OPEN
381. [P11] Journey: private project -> revision -> prepared reveal -> matching bytes -> shelf/notification/settlement (source: F2:P11 Required journeys) — OPEN
382. [P11] Journey: voice interruption -> correct session history (source: F2:P11 Required journeys) — OPEN
383. [P11] Journey: device permit/stop with late/failed acknowledgment (source: F2:P11 Required journeys) — OPEN
384. [P11] Journey: correction -> invalidated downstream projection (source: F2:P11 Required journeys) — OPEN
385. [P11] Journey: approved patch -> isolated verification -> recoverable release -> observed capability (source: F2:P11 Required journeys) — OPEN
386. [P11] Assert expected completed-event counts and absence of forbidden effects (source: F2:P11 Acceptance) — OPEN
387. [P11] Exercise the concrete concurrency/restart/error boundaries the approved contracts introduce (source: F2:P11 Acceptance) — OPEN
388. [P11] Report runtime paths genuinely untested (source: F2:P11 Acceptance) — OPEN
389. [P11] Make health distinguish quiet, unavailable, malformed, unsupported and violated states — failed stores currently appear healthy (source: F2:P11 Acceptance; F1:20 Defects/Evolution) — OPEN
390. [P11] Connect every approved proposal to changes, relevant evidence and remaining work in `proposal-ledger.json` (source: F2:P11 Acceptance; F2:Approval and work ledger) — OPEN
391. [P11] Record per batch: baseline, affected paths, schema decisions, changes, verification, unresolved boundaries, rollback and next work (source: F2:Approval and work ledger) — OPEN
392. [P11] Make existing Atelier tests cover their claimed journeys (source: F1:19 Disposition) — OPEN
393. [P11] Give room context provenance and completion the same work ledger used elsewhere (source: F1:21 Branch reconciliation) — OPEN
394. [P11] Decide whether the 42,490 unread vendor graphics lines are an accepted dependency boundary or require further reading (source: F1 Decision requested; F3 Branch reading reconciliation) — OPEN
395. [P11] Resolve each trace's remaining runtime limit or document a genuine external blocker before marking a subsystem complete (source: F3 File-level reading coverage) — OPEN
396. [P11] Obtain installed renderer, media/cache state and render/playback receipts for the avatar path (source: F3:T03/T14) — OPEN
397. [P11] Obtain playback acknowledgments, installed voice process and provider callback ordering (source: F3:T04) — OPEN
398. [P11] Obtain deployed schedules and representative night/run data for threads, dreams and causal catalogs (source: F3:T15/T16) — OPEN
399. [P11] Obtain deployed emotion model/data lineage and the authoritative daemon (source: F3:T18) — OPEN
400. [P11] Obtain live execution/artifact receipt joins for wants and creative jobs (source: F3:T07/T25) — OPEN
401. [P11] Obtain the untracked external room library and installed host/runtime map (source: F3:T10) — OPEN
402. [P11] Obtain installed hashes, approvals/build receipts and deployed Study UI (source: F3:T28/T11) — OPEN
403. [P11] Obtain the external QLab implementation and Atelier runtime permissions/receipts (source: F3:T27) — OPEN
404. [P11] Obtain a fresh push-window check beyond the 2026-09-05 snapshot (source: F1 Final push-window reconciliation) — OPEN

## Counts

- Total: 404
- DONE: 25
- PARTIAL: 1
- OPEN: 378

| Phase | Total | Done | Partial | Open |
|---|---:|---:|---:|---:|
| P01 | 33 | 2 | 0 | 31 |
| P02 | 40 | 5 | 0 | 35 |
| P03 | 29 | 3 | 0 | 26 |
| P04 | 57 | 2 | 1 | 54 |
| P10 | 16 | 0 | 0 | 16 |
| P05 | 56 | 3 | 0 | 53 |
| P06 | 43 | 2 | 0 | 41 |
| P07 | 40 | 3 | 0 | 37 |
| P08 | 32 | 1 | 0 | 31 |
| P09 | 28 | 4 | 0 | 24 |
| P11 | 30 | 0 | 0 | 30 |

# A want, in five stages: the fields that carry each one

Review item 224 (2026-09-10). Every stage of a want is a recorded thing with a named field, so a reader can tell intention from admission from attempt from outcome from revision without inferring any of them.

| Stage | Where it is recorded | Fields | Written by |
|---|---|---|---|
| **Intention** | `memory/current-wants.json` row | `id`, `want` (his words), `source` (conversation / ambition / dream / structural / third-order), `reasoning`, `intensity`, `timestamp` | `emoclaw_utils.generate_want` |
| **Admission** | the same row | `admission` (`ADMIT_*` / `HELD_NO_PRESENT_PULL` / `HELD_BY_STANDING_STANCE`), `plan_state` (`READY` / `BLOCKED` with `plan_block.block_type`, `evidence`, `resume_event`), `plan_contract` | `want_completion.admit` (shape screen + standing stance), `wants-router._ensure_plan` |
| **Actual attempt** | `steps[]`, `step_history[]`, `budget_used`, `pursuit-checkpoints.json` | per step: `capability`, `status`, `findings`, `receipt` (`kind` file / text / none, `ref`), `completed_at`; an empty attempt is recorded as such (5313770); a blocked step opens a checkpoint carrying `findings`, `blocker`, `next_step` | `wants-router._advance_or_fulfill`, `want_checkpoints.create` |
| **Observed outcome** | `memory/want-completions.jsonl` (one row per ending), `fulfilled-wants.json` / `dismissed-wants.json` | `how` (`fulfilled` / `dismissed` / `released`), `by`, `note`, `evidence`, `result` (`fulfilled` or `refused: <why>` when the artifact is missing); `completion_held` on the row when the judge was unavailable | `want_completion.complete`, `emoclaw_utils.fulfill_want` (the artifact guard), `_want_end_verdict` |
| **Revision** | `pursuit-checkpoints.json` decisions; `pursuit.state` on the row; `learned.json` | `decision` (`continue` / `pause` with `paused_until` / `replan` with `his_words` on the next step / `abandon` / `release`), `attempts[]` on the lesson (`want_learning.lessons_from_attempts`) | `want_checkpoints.decide`, `want_learning` |

Identity through every stage: the want's `id` (and each step's id on the wants API, 50dae23) is the key in every store above; nothing is matched by text where an id exists.

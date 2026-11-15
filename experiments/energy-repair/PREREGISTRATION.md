# Energy-landscape belief repair: pre-registered evaluation

Written 2026-11-14, before any held-out network was generated or scored. Proposed by Gloria's ChatGPT ("Chat"),
improved and run by Claude Code; Gloria approved: "You can improve it and give it a try."

## Question

Can logical inconsistency be treated as an energy landscape, and does minimizing that landscape give better belief
repairs than reasoning through the contradiction in language? And does the existing contradiction back-propagation
(`scripts/belief_revision.py`), which localizes a culprit but never searches for the globally minimal consistent
repair, gain anything from such a search?

## The repair problem (core.py)

A repair is a set of sources or inference steps declared wrong. Beliefs are recomputed by forward chaining (the
least fixpoint, so a loop cannot hold itself up). Its energy is the cost of what it retracts (log((1-p)/p), p the
source's prior chance of being wrong from belief_revision), plus -log(1-r) for every contradiction left standing,
plus log(acc/(1-acc)) for every passed check it breaks. This is minus the log of belief_revision's own joint
probability, so the minimum is the most probable explanation of the evidence. Equal repairs go to the earlier
assumption. A repair is consistent when no contradiction is left standing.

## Methods

1. `llm_first`, `llm_selfcorrect` - AEON (`aeon/gemma-4-12b`, local, the shim's /gemma-aegis-local lane with
   belief_revision_answer's path guard) reads the network in words, with every cost, proposes a repair, then checks
   and revises its own answer once. No verifier feedback.
2. `exact` - the minimum-energy repair by integer programming (HiGHS via scipy.optimize.milp, already installed),
   proved optimal. `exact_hard` - the minimal repair under the hard rule that no contradiction may stand.
3. `br` - belief_revision as it stands: the sources its plan would retract or lower.
4. `energy_free` (Chat's proposal as written: a free soft truth value per node, implication and support penalties),
   `energy_prop` (beliefs computed from the sources by soft AND/OR), and the variants the dev iterations produce;
   discretized at 0.5 and checked by the exact verifier.
5. `gnn` - a small graph network trained only on small networks (seven small scenarios, seeds 100000-100399),
   labelled by the exact solver; outputs per source the chance it belongs in the minimal repair.
6. `hybrid_gnn`, `hybrid_energy`, `hybrid` - the learned and/or energy models propose candidate repairs; the exact
   verifier scores each and keeps the lowest-energy one. `gnn_topk_ilp` - the exact solver searching only the
   learned model's top suspects.

## Data

Synthetic only (public repository). `gen.py`: the four scenarios of the existing benchmark from
`bench_criteria.network()` unchanged (chain, dag, noisy, two_faults); Chat's cases (early_premise, ambiguous,
multi_repair); and, for generalization, larger and differently built networks that nothing is trained on (deep,
wide, cycles, large_mixed).

Two evidence tracks. **Checked** (primary): every method repairs the same network after belief_revision's own
bisection checks have been asked (answers from the truth, flipped at the scenario's check noise, as in
bench_criteria's tms_bayes); a check that came back wrong is counted as a wrong source. **Passive**: only the
evidence recorded at the start.

- Development: seeds 0-39 per scenario (440 networks). Iterate freely.
- Held-out: seeds 7000-7059 per scenario (660 networks), scored once per track; the script refuses to overwrite a held-out result file. Results:
  `results-test.json` (checked), `results-test-passive.json` (passive), `results-test-llm.json` (LLM, checked).
  The LLM methods are scored on the first 15 held-out seeds per scenario (165 networks, checked track only) because each costs two
  local model calls.

## Metrics (pooled, and per scenario; "small" and "large" families reported separately)

- **Consistency**: share of networks with no contradiction left standing after the repair.
- **Minimality**: share of repairs whose energy equals the exact optimum (within 1e-6); mean energy gap.
- **Localization (Gloria 1)**: over true contradictions against a false conclusion, the earliest real fault among
  its ancestors is retracted and no sound suspect of that contradiction is.
- **Revision (Gloria 2)**: conclusions the repair withdraws against those really false: precision, recall;
  conclusions correct.
- **Preservation (Gloria 3)**: valid nodes not depending on any fault left untouched (all; side; upstream).
- **Early assumption**: in networks with a wrong premise where the exact minimal repair retracts it, the share where
  the method retracts it too.
- **Compute**: milliseconds per network (belief_revision's includes its checks), and model calls / tokens.

## Pre-registered comparisons

- H1 Minimality: the exact solver is optimal on every network. The best continuous energy variant reaches >= 0.90
  optimal on the large family; `hybrid` >= 0.95.
- H2 Better repairs than belief_revision: on the checked track, a minimum-energy method counts as better if its
  localization is at least 0.02 higher than `br` and its preservation is not more than 0.005 lower and its revision
  recall not more than 0.02 lower; worse if the reverse; otherwise no difference.
- H3 Language vs landscape: `llm_selfcorrect` against `exact` and the best energy method on optimal rate,
  consistency and localization (no bar; the size of the gap is the result).
- H4 Generalization: the `gnn` and `hybrid_gnn` optimal rate on the large family, against the small family.
- The early-assumption share is reported for every method.

ITERATION-LOG.md records every development iteration and its root cause.

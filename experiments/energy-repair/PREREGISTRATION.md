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

## Held-out result (seeds 7000-7059, 660 networks; scored once at commit 37427864 for the non-LLM methods)

Checked track (`results-test.json`):

| method | consistent | optimal | localization | recall | precision | preservation | side | ms |
|---|---|---|---|---|---|---|---|---|
| br | 0.66 | 0.71 | 0.748 | 0.85 | 0.97 | 0.9951 | 0.9967 | 14 194 (incl. checks) |
| exact | 0.88 | 1.00 | 0.805 | 0.97 | 0.96 | 0.9920 | 0.9946 | 8 |
| exact_hard | 1.00 | 0.89 | 0.806 | 0.97 | 0.96 | 0.9919 | 0.9945 | 8 |
| energy_free | 0.34 | 0.11 | 0.072 | 0.09 | 0.99 | 0.9998 | 0.9999 | 102 |
| energy_prop_search | 0.88 | 0.98 | 0.809 | 0.97 | 0.96 | 0.9912 | 0.9944 | 265 |
| gnn | 0.91 | 0.83 | 0.709 | 0.97 | 0.91 | 0.9822 | 0.9876 | 14 |
| hybrid_gnn | 0.88 | 0.98 | 0.799 | 0.97 | 0.96 | 0.9907 | 0.9934 | 12 |
| hybrid | 0.88 | 0.99 | 0.804 | 0.97 | 0.96 | 0.9919 | 0.9947 | 1 076 |
| gnn_topk_ilp | 0.88 | 0.996 | 0.805 | 0.97 | 0.96 | 0.9921 | 0.9948 | 21 |

Large family: br optimal 0.60, localization 0.67, recall 0.78; exact 1.00, 0.75, 0.98. large_mixed recall br 0.64,
exact 0.99. Early assumption (97 networks): exact, energy_prop_search, gnn, hybrids 1.00; br 0.87; energy_free 0.05.
Passive track (`results-test-passive.json`): localization br 0.48, exact 0.52, energy_prop_search 0.52, gnn 0.33.

Verdicts:
- H1 met: exact 1.00 optimal; best gradient method 0.97 on the large family (bar 0.90); hybrid 0.99 (bar 0.95).
- H2: exact is BETTER than br (localization +0.057, preservation -0.0031 within 0.005, recall +0.12); so are
  energy_prop_search (+0.061, -0.0039, +0.12) and hybrid (+0.056, -0.0032, +0.12). Side preservation is a little
  lower than br's (0.9946 vs 0.9967).
- H3 (LLM, 165 networks, `results-test-llm-rerun.json`): AEON first answer optimal 0.31, consistent 0.81,
  localization 0.21; after self-correction 0.35, 0.81, 0.20 (recall 0.80 -> 0.89); exact on the same networks
  1.00, 0.92, 0.78.
- H4: gnn optimal small 0.90 -> large 0.72 (deep 0.92, wide 0.82, cycles 0.83, large_mixed 0.30); hybrid_gnn
  0.99 -> 0.97.

The first LLM held-out attempt (`results-test-llm.json`, kept) lost 208 calls to the shim answering HTTP 502
instantly while the AEON lane was busy (52 of 60 large networks unanswered). The only change before the re-run was
a back-off between retries (llm.py); successful answers were reused from the cache, nothing else changed.

The exact optimum gives up her words on 13 of 660 networks, never correctly; belief_revision never revises them.

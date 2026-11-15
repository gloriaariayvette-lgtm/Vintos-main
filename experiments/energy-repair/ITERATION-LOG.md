# Iteration log (development seeds only)

Gloria's rule: iterate on development until each method is worked through - open the failures, find the root cause,
fix, retest. Held-out seeds are scored once at the end.

## 0. Checking the exact solver itself

Before any method was compared: on 165 networks (15 per scenario) the integer program's optimum was compared with
belief_revision's own most probable explanation (`posterior()` diagnosis). Where belief_revision enumerates exactly
(components of at most 14 assumptions) the two energies agreed on every network; nowhere was the solver's energy
higher. Solve time 13 ms on average, 66 ms at most; HiGHS proved optimality every time.

## 1. First pass, passive evidence (seeds 0-7, 88 networks)

| method | consistent | optimal | localization | recall | side preservation | ms |
|---|---|---|---|---|---|---|
| br (plan) | 0.82 | 0.90 | 0.27 | 0.90 | 0.987 | 176 |
| exact | 0.84 | 1.00 | 0.36 | 0.91 | 0.988 | 16 |
| energy_free (Chat's form) | 0.23 | 0.15 | 0.02 | 0.06 | 1.000 | 420 |
| energy_prop | 0.84 | 0.84 | 0.35 | 0.87 | 0.987 | 1244 |

Failures opened:

- **Localization is low for every method on passive evidence (0.27-0.36).** Root cause: with no checks, every step
  on a contradicted line costs the same, so the minimum-energy repair is a tie broken toward the earliest step (or a
  cheaper premise), while the planted fault sits at a random depth. The minimum is only as good as the evidence: no
  search can localize what the record does not distinguish. This is why belief_revision asks bisection checks.
  Fix (to the experiment, not a method): the primary track now hands every method the network AFTER
  belief_revision's own checks, so all methods repair on the same evidence; passive stays as a second track.
- **ambiguous: every method retracts nothing (consistency 0).** Root cause: there the contradiction reports are
  weak (reliability 0.75), so leaving one standing costs 1.39, less than retracting anything (>= 1.39). The
  minimum-energy answer to weak evidence is to change nothing. That is correct under the energy, but it is not a
  "consistent" repair. Fix: added `exact_hard`, the minimal repair under the hard rule that no contradiction may
  stand (Chat's literal "minimal consistent repair"), to measure what forcing consistency costs.
- **energy_free (one free soft value per node, implication and support penalties) almost never repairs.** Opened
  chain seed 1: the optimum retracts one step (energy 1.39); energy_free retracts all four witnesses (8.78). Root
  cause: in the free landscape the only downhill direction from "believe everything" is the witnesses, whose value
  enters the contradiction term directly. Lowering the faulty step does nothing to the contradiction until the
  belief it feeds drops too, and that belief is held up by the implication penalty (weight 10 > contradiction 3).
  Gradient descent cannot assign credit back through the logic penalties: a local-minimum trap by construction,
  unchanged by annealing toward 0/1 (tried, same answer) or by 1000 steps. Fix: `energy_prop`, where beliefs are
  computed from the sources by soft AND/OR, so the gradient reaches the faulty step through the chain.
- **energy_prop is not minimal on 16% of networks.** Opened: on ties it lowers several equal suspects together and
  discretization keeps two or three of them (repair size 1.10 vs 1.08), and with no earliness term it retracts later
  steps (chain localization 0.07 vs exact 0.33). Fix for iteration 2: a small earliness cost per depth step and a
  discrete polish (drop any retraction whose return lowers the energy): `energy_prop_polish`.

Passive follow-up (seeds 0-7): `energy_prop_polish` reached 0.91 optimal (large 0.84), still short. Opened the 8
non-optimal networks: in every one, gradient from several contradictions piled onto ONE shared upstream source (a
premise, or a witness) - common-cause bias: a source feeding many lines collects the summed gradient, crosses 0.5
first, and once it drops every contradiction is satisfied and the specific steps' gradients vanish. Dropping
retractions (the polish) cannot undo that; it needs a swap. Fix: `energy_prop_search` - the polish plus a discrete
local search that can swap one retraction for one suspect. `energy_free_anneal` (pushing values to 0/1) changed
nothing (0.10 optimal): the trap is in the direction of descent, not in fractional values.

## 2. Checked track, all 440 development networks

Every method repairs the network after belief_revision's own bisection checks (the same evidence for all).

| method | consistent | optimal | localization | recall | precision | preservation | side | ms |
|---|---|---|---|---|---|---|---|---|
| br (with its checks) | 0.70 | 0.75 | 0.75 | 0.81 | 0.99 | 0.997 | 0.997 | 14 253 |
| exact | 0.89 | 1.00 | 0.82 | 0.98 | 0.97 | 0.993 | 0.995 | 20 |
| exact_hard | 1.00 | 0.89 | 0.82 | 0.98 | 0.97 | 0.993 | 0.995 | 21 |
| energy_free | 0.34 | 0.10 | 0.05 | 0.08 | 1.00 | 1.000 | 1.000 | 566 |
| energy_prop | 0.88 | 0.95 | 0.82 | 0.98 | 0.98 | 0.993 | 0.995 | 1 751 |
| energy_prop_polish | 0.88 | 0.95 | 0.82 | 0.98 | 0.98 | 0.993 | 0.995 | 1 706 |
| hybrid_energy (4 restarts, verifier picks) | 0.88 | 0.97 | 0.82 | 0.98 | 0.98 | 0.994 | 0.995 | 7 004 |

(br's time includes the checks it asked; the others reuse those answers.)

On the large family belief_revision falls back: optimal 0.60, recall 0.69, localization 0.66 (exact: 1.00, 0.98,
0.78). Opened: belief_revision samples posteriors above 14 assumptions, and its single-answer rule holds back
revisions it cannot corroborate within its budget of 12 checks, so real faults stay standing (consistency 0.62).
The exact search has no such limit. Where the exact solver loses to br is preservation, all of it in large_mixed
(side 0.964 against br 1.00). Opened all 40 large_mixed networks: every side change followed a WRONG check answer
(a "check:X" source the optimum kept, retracting X's step instead), or a premise fault hidden by a check that wrongly
passed. Root cause: the minimum-energy repair trusts a single check answer as far as its weight says; belief_revision
deliberately does not ("no single answer changes his mind"). Fix tried: `exact_stable` - keep only the retractions
that survive re-solving with each check answer left out in turn.

GNN, first training (`gnn-v1`, 1750 small networks, 12 epochs): loss went 1.27 -> 1.20 and the model marked almost
every source for retraction (optimal 0.00). Root causes: (a) the positive-class weight was the full 40:1 class
ratio, which makes "retract everything" the cheapest prediction; (b) a log-sum-exp max-aggregation with a global
shift underflowed to log(1e-6) for most nodes and swamped the recurrent state over 20+ rounds. Fixes: square-root
class weight, a scaled-sum aggregation, LayerNorm on the state, and three structural hints per source (in how many
contradictions it is a suspect; whether it is the cheapest, and the earliest cheapest, suspect of one). On a 105-
network smoke test the loss now falls 0.66 -> 0.34. (Also: the torch build on Aegis has no kernels for its GPU, so
training runs on the CPU; the first run was 100x slower than needed because of thread oversubscription.)

LLM, first pass (AEON, 110 networks): 65 of 110 first answers unparsed. Opened: two causes - the 900-token cap cut
the answer before its JSON line (raised to 1500), and on large networks calls failed fast while the cache was cold
(transient shim errors, never cached). Fix: one retry per failed call, and the status is logged.

## 3. Checked track: robustness to single answers, and swap search

| method | consistent | optimal | localization | recall | preservation | side | ms |
|---|---|---|---|---|---|---|---|
| exact | 0.89 | 1.00 | 0.82 | 0.98 | 0.993 | 0.995 | 8 |
| exact_stable (drop each check answer in turn) | 0.52 | 0.56 | 0.61 | 0.65 | 0.998 | 0.999 | 53 |
| energy_prop_search (gradient + swap search) | 0.89 | 0.98 | 0.84 | 0.98 | 0.993 | 0.995 | 292 |

- `exact_stable` reproduced belief_revision's own iteration 7 almost exactly: preservation rose (side 0.995 ->
  0.999), recall collapsed (0.98 -> 0.65). Root cause: most correct repairs rest on one check answer that nothing
  else repeats, so an intersection over leave-one-out optima empties. belief_revision fixed this by ASKING more
  (second and third opinions); a repair method that cannot ask cannot. Rejected; `exact` stays the exact method.
- The swap search lifted the gradient method from 0.95 to 0.98 optimal (large 0.91 -> 0.98) and cut its time 6x
  (fewer restarts needed). Its remaining misses are swaps of two-for-one, which a one-for-one move cannot reach.
- Observation, not a fix: `energy_prop_search` localizes slightly BETTER than the exact optimum (0.84 vs 0.82;
  large_mixed 0.70 vs 0.64) although it is less minimal. Opened large_mixed: where it differs from the optimum it
  keeps a premise fault that the optimum split into several cheaper step retractions. The minimum of the energy is
  only as right as the priors that weigh it; a cheaper repair is not always the true one.

## 4. The learned model (checked track, 440 networks)

| model | optimal small | optimal large | localization | side preservation |
|---|---|---|---|---|
| gnn-v2 alone | 0.65 | 0.63 | 0.64 | 0.990 |
| gnn-v2 + verifier (hybrid_gnn) | 0.97 | 0.89 | 0.78 | 0.995 |
| gnn-v3 alone | 0.90 | 0.75 | 0.74 | 0.988 |
| gnn-v3 + verifier (hybrid_gnn) | 1.00 | 0.96 | 0.82 | 0.994 |
| gnn-v3 + energy + verifier (hybrid) | 1.00 | 0.98 | 0.82 | 0.995 |
| exact solver on gnn-v3's top suspects only | 1.00 | 0.98 | 0.82 | 0.995 |

- gnn-v2 failures opened: 103 of 158 non-optimal repairs were the optimum PLUS extra retractions, almost all of
  them "check:..." sources - the answers belief_revision's checks added. Root cause: a train/test mismatch; the
  training networks were the recorded ones, so the model had never seen a check answer as a source. Fix (gnn-v3):
  every training network appears twice, as recorded and after belief_revision's checks (still small networks only,
  training seeds 100000-100199, labels from the exact solver).
- gnn-v3 on the large family by scenario: deep 0.90, wide 0.93, cycles 0.90 - depth, width and loops it never saw
  in training cost it little (its rounds grow with depth) - but large_mixed 0.28. Opened: 32 of 40 large failures
  are the optimum plus extra retractions. Each source is decided on its own, so with ten or more contradictions the
  model marks two suspects of the same contradiction. Independent per-source decoding cannot coordinate; the
  verifier (pick the lowest-energy candidate) repairs most of it (large_mixed 0.88). Left as the finding.

## 5. The language model (AEON, local; checked track)

| version | networks | first answer optimal | after self-correction optimal | consistent | localization |
|---|---|---|---|---|---|
| v1 (900-token cap) | 110 | 0.25 | 0.28 | 0.51 | 0.18 |
| v1 + 1500 tokens + one retry | 110 | 0.35 | 0.41 | 0.78 | 0.25 |
| v1 + "give the JSON you reached" nudge | 110 | 0.39 | 0.41 | 0.85 | 0.26 |
| v2 prompt (hints: one retraction per line; spare witnesses) | 55 | 0.36 | 0.36 | 0.80 | 0.16 |
| v1 on the same 55 | 55 | 0.42 | 0.40 | 0.87 | 0.19 |

- After the format fixes only 1 of 220 answers was unreadable, so what is left is reasoning. Opened the 65
  non-optimal self-corrected repairs: 31 were the optimum plus extra retractions (a step AND its downstream step, or
  the witness as well), 20 overlapped it, 10 missed it entirely, 4 were too small; 18 retracted a witness or a check
  answer the optimum keeps. The model reads the costs but does not add them up across the network: it cannot
  recompute what a retraction takes down three steps later.
- Self-correction helps a little (optimal 0.39 -> 0.41, consistency 0.82 -> 0.85, recall 0.77 -> 0.85) and costs a
  second call (21 s -> 36 s per network).
- v2 put the two commonest errors into the instructions. It did not help (0.36 vs 0.40 on the same networks): the
  model already "knew" the rule, it failed to apply it. Reverted to v1, which is what the held-out run uses.

## Frozen for the held-out run

exact (primary), exact_hard, br, energy_free, energy_prop_search (best gradient method), gnn (gnn-v3, committed as
gnn.pt), hybrid_gnn, hybrid, gnn_topk_ilp, llm_first, llm_selfcorrect (v1 prompt). Rejected on development and not
re-scored: energy_free_anneal, energy_prop, energy_prop_polish, hybrid_energy (all dominated by energy_prop_search),
exact_stable (recall 0.65).

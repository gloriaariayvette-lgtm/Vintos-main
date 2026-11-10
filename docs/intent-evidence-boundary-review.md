# Intent verdict evidence boundaries

This review branch repairs two evidence-handling defects in the published source.
It is not deployed and does not include the concurrent round-four implementation.

The judge previously searched for verdict substrings: `UNKNOWN` became `NO`,
`NO VERDICT` became `NO`, and negated or compound output could become `YES`.
It now accepts one verdict token, allowing whitespace and one terminal period or
exclamation mark. Other output is `HELD` with `judge_no_verdict`, subject to the
existing retry budget.

The follow-up helper also included historical conversation under the judge's
“what happened right after” label. Only the current human input now enters that
evidence slot. The selector still receives its existing conversation context.
For a declared `my_move` criterion, a later human response is excluded; the judge
receives the delivered reply as evidence. Axis-specific window and evidence
metadata survives construction of the axis-specific judge target. Delivering a
reply never automatically passes a criterion.

The selector, authored schema, declared prompt, priority weights, provider identity,
generation settings and number of provider call sites are unchanged. No runtime
module or installation-manifest entry is added.

## Validation

All execution used OS-enforced scratch isolation and stubbed providers. No real
provider request or live-store read/write was needed.

| Evidence | Result |
| --- | --- |
| New evidence-boundary suite | 7 unique cases pass |
| Existing fields suite | 53 unique cases pass |
| Existing source-to-reply suite | 20 unique cases pass |
| Directly affected and ownership suites | 12 test files pass |
| Deliberately broken variants | 5 of 5 caught |
| Full local sweep | 674 files: 658 pass, 16 fail |
| Untouched published baseline controls | All 16 unsuccessful files also fail |
| Generated ownership and untested reports | Match their generators |

The initial six-case reproduction failed before repair, with 12 failure reports
including subtests. Repeated runs are not added to unique-case totals. The local
full sweep is not an all-green acceptance result; the host's required complete
suite and independent review remain pending.

Run the new suite through the repository isolation boundary:

```sh
python3 scripts/run_isolated_test.py broker/tests/test_intent_evidence_boundary.py
```

## Separate unresolved resolution race

A two-thread fixture reproduces stale outcome writes: a slow `HELD` can restore an
already settled `YES` row to pending. A slow conflicting `NO` can also apply
pressure and required-consideration feedback after the other worker's `YES`.

The retained reproduction intentionally fails on this branch:

```sh
python3 scripts/run_isolated_test.py docs/review-repros/intent_resolution_race.py
```

Both cases fail on the published implementation. A disposable guard against
replacing a terminal ledger row makes the first case pass but leaves the feedback
case failing. Consequently a complete repair needs ownership of the accepted
resolution and its effects, not only a guard on the final JSON replacement. No
partial ownership repair is included here. Check the round-four implementation
before combining work.

Emotion judgments remain with a Claude reviewer. Semantic reopening, campaigns,
runtime outside-grader integration, real-selector semantic acceptance and actual
post-deployment behavior retain their separate pending status.

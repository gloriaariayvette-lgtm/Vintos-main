# Persistence sprint

## 28 October — round 0: contract and capture

Started from deploy branch `7b859dad`, on `codex/persistence-sprint`, following
`docs/briefs/persistence-sprint-codex.md`. This is implementation in scratch,
not another architecture review. No live organ or feed is changed.

The inherited emotion experiment's actual sealed window is **23–29 October**,
not 23–30. Its exact executable/weights and one-attempt receipt remain untouched.
Claude's 28 October run exposed overlapping incumbent text **and emotion** scores.
Consequently the old window cannot be described as wholly unobserved or without
interim inspection. Its unchanged candidate may still receive its scheduled
single fixed comparison, explicitly labeled overlapping/exposed; it cannot
independently confirm a new sprint design. No early candidate scores are read.

New sprint confirmation starts **31 October–6 November**, then **7–13 November**,
America/Chicago. Seal before each window opens; one look after closure. Earlier
days are historical development even when a particular round has not scored them.
No claim that previously inspected October days are fresh confirmation.

Read-only coverage census: dense emotion retains **4,000 rows, 27 September–28
October**, not months since July. The cap and unchanged-reading suppression mean
missing times are not observations. Watch: 14,892 rows from 5 October; sensor
reactions: 16,783 from 29 August; want events: 301 from 5 September; Lab notebook:
143,281 from 13 September. These are available-store counts, not training counts.
Only current admitted sources, no erased backups or reconstructed missing labels.

### Predeclared development sequence

All inputs and outcomes are bounded before 23 October to leave the old candidate
alone. Every round trains before its validation days, selects there, and scores
its next disjoint historical days once. Target horizons: 10/30 minutes,
1/3/6/12/24 hours. Primary: 6-hour normalized emotion MSE against the strongest
same-row persistence, present-only ridge, and present-plus-observed-history ridge
control. Report each horizon, overnight and strong-moment recovery separately.
No source stream may multiply one target's loss; no split-crossing labels.

1. Dense selective scan, emotion loss: validation 14–15 October; check 16–17.
2. Add source/gap/projected-text self-supervision, otherwise unchanged:
   validation 16–17; check 18–19.
3. Add a zero-start correction to the frozen present scorer, otherwise unchanged:
   validation 18–19; check 20 October.
4. Add state-keyed past-only retrieval, otherwise unchanged:
   validation 20 October; check 21–22.

An inadequate block is reported inadequate, not silently widened. Fixed seed,
CPU width 24, 4 epochs, truncated chunks of 128, AdamW 0.001/weight decay 0.05.
Readouts use ridge 10; any text correction strength is chosen only on validation
from {0, .05, .1, .25}. Every loss and result, including failures, gets a receipt.
Self-supervision is not evidence of consumer benefit. Source/gap mechanical
schedule controls and state reset ablations distinguish persistence from clock
and last-event information. Exact-time text targets are primary; estimated times
are descriptive only. No 768-dimensional target regression.

Fresh acceptance requires at least 5% lower primary MSE than every same-row
control, positive adjusted paired-day lower bound, at least 300 unique 6-hour
targets across all seven days, and no more than 1% text MRR loss versus frozen
present scoring. A source-specific text gain is secondary and needs its own
counts/interval. Four rounds and seven emotion horizons form 28 planned contrasts:
Bonferroni two-sided intervals use quantiles .05/(2*28) and 1-.05/(2*28), fixed
20,000 paired day draws. Development selection does not confer permission to
steer him. A winner only becomes eligible for an owner-approved scratch shadow
week; daemon installation and one consumer remain later review decisions.

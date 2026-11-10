# Campaign terminal review — shadow design only

Current source: `scripts/campaign.py:step` closes directly when the selector's
`campaign_move` starts with `landed:` or `flawed:`. `_log` retains destination and
selected counters but no stable campaign/revision identity or terminal evidence
binding. `_close` can clear the live campaign and expiry can enqueue causality
work; continuation has a separate plan bridge. This design changes none of them,
does not restore selector keys and never touches the existing continued campaign.

## Evidence gate before independent review

A future private shadow packet must bind a stable declaration and revision ID to
the original destination, axis, prior observable end-condition, observation window,
and delivered acts/receipts. Retain the revision chain; a changed destination gets
a new reviewed condition and cannot rewrite earlier attempts. Existing log rows
without unique identity, declaration-time conditions or joins remain unsupported.
Do not invent a join from destination text, timing, array position or nearest turn.

A LANDED candidate requires positive evidence for every declared terminal condition
inside the declared window, joined to actual delivered acts. Individual intent YES
votes, a selector's “landed” sentence or success at a convenient substitute goal
cannot establish campaign completion. A valid partial intent outcome is not full
campaign landing. Unsupported semantic conditions stay HELD for independent review.

A FLAWED candidate requires evidence that the want/premise itself was invalid under
a separately stated review contract. An execution failure, resistance, silence,
negative intent verdict, elapsed time, turn cap or missing observation is not that
evidence. Do not mechanically map NO to FLAWED or HELD to EXPIRED. Expiry is a budget
event and continuation is a distinct lifecycle event, neither a success label nor
a failure label. Their current behavior remains unchanged.

## Independent reviewer and isolation

First run the mechanical evidence gate. It can report only review-ready candidate
or HELD with fixed reasons (missing identity, revision mismatch, undeclared terminal
condition, unbound act, incomplete window, missing/conflicting receipt, unsupported
criterion). Then an independent human reviewer, distinct from the selecting actor,
checks the immutable original criterion and bound evidence, blind to the selector's
terminal claim and current pressure/priority. Reviewer identity/provenance, version,
time, rationale and the source packet digest stay private. Absence of independent
review stays HELD. No new reviewer/model calls are authorized by this design.

A later model reviewer would need separate authorization, demonstrated actual served
identity/fallback distinctness (configuration names are insufficient), and validation
on an unexposed cohort. It is not part of the implementation now.

Shadow outcomes are named `LANDED_CANDIDATE`, `FLAWED_CANDIDATE`, or `HELD`; none
calls `_close`, `_save`, `_bring_up`, plan creation or `campaign.step`. No prompt,
selector key, cap, suspension count, continuation bridge, intent verdict, feedback
store or existing loop changes. Public reports expose only fixed reason counts,
coverage and old-versus-shadow outcome tables with explicit denominators. Do not
infer validity from agreement with old selector-generated lifecycle labels.

Before any later runtime integration, synthetic tests must prove unchanged live
state/output/call counts with shadow success, refusal, exception and duplicate or
late packets; exact revision binding; absent-evidence abstention; and the distinction
between unmet execution, flawed want, expiry and continuation. Independent review
and a separately authorized integration decision follow. This document is only the
requested design alongside the offline intent assessor, not an implemented campaign
judge or permission to change the existing continued state.

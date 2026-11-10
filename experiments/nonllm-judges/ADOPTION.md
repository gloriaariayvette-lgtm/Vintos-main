# A weekly voice check-in — offline proposal

Gloria sees a short private card for each sustained change, for example:

> Nov 3–7, 2026, everyday/avatar: his voice moved.
>
> **Growth** · **Not him** · **Not sure**

A movement is a difference from the old reference, not a verdict about his
identity, feelings, intentions, or whether the change is good. There is no right
answer and no requirement to answer. This is a phone-first interaction design;
`adoption.py` creates a Markdown preview and private data, **not a UI, message,
scheduled task, endpoint, or runtime integration**. Nothing is sent to her.

- **Growth:** “I recognize this as growth.” Explicitly permits these exact acts
  to become a candidate reference for later offline comparisons in this one
  conversation mode and surface. All original admission, sustained-shift,
  independent-mode, calibration and current-reference checks must still pass.
- **Not him:** keep the existing reference. It is not a penalty, negative training
  label, instruction to him, or permission to undo anything he said.
- **Not sure:** record uncertainty and change nothing. Leaving a card unanswered
  also changes nothing; it is not converted into any answer.

A future authorized interface would show the dates and mode/surface, three equally
prominent buttons with no default, a small confirmation naming the chosen answer,
and a save action. It must retain the hidden digest/window binding when recording
that explicit answer; row numbers are presentation only. It must authenticate the
owner before signing. No free-text explanation, reply excerpt, score, vector,
member ID, or hash appears on the card. She never needs to send a message to
produce test data. An answer may rely on her ordinary experience; a dates-only
card is not itself evidence that she remembers or endorses particular wording.

## Where the window comes from

`digest` takes an explicitly staged private numerical input and its retained
`numerical-private-run-v1`, with a cutoff at local midnight on `--week-end`
(exclusive). The seven preceding local dates form the week. The timezone is the
input's reviewed timezone, not the machine's current timezone. No live paths are
discovered. It recomputes from the existing cached features, with zero encoder,
provider, paid or other model calls, and requires the retained voice/drift receipts
to match. A counts-only report cannot supply the missing identity bindings.
This is semantic drift-receipt verification against supplied inputs, not independent
authentication of the capture source or an attestation of the original run binary.
The original run's optional raw-file manifest hash is not used as that proof.

For each flagged run whose last observed day is in the week, it takes the **whole
consecutive run**, including its first three days before the fourth day flags and
any beginning before this week. It never clips those members to the last seven
days. Days without qualifying evidence break the run. Distinct modes, surfaces,
reference versions and attribution views remain separate. `primary_10s` is the
default; `window30` is a separate exploratory digest, never merged or silently
substituted. A still-continuing run is an as-of snapshot, not a claim it has ended.
An expanded later window requires a new answer; an old answer cannot silently
cover newly arrived acts.

The private `adoption-digest-v1` contains week/cutoff/timezone/view, canonical input
and drift-receipt hashes, and windows with start/end dates, mode/surface, active
`reference_version`, and **all** admitted member IDs, content hashes, event times
and local dates. Each `window_id` hashes those exact fields. No text or vectors are
copied into the digest. The input hash also binds the supplied provenance and
actual-serving/fallback fields without interpreting unknowns as known. The
existing runner checks original ancestry, including indirect influences, frozen
features and attribution. Supplied source claims remain claims. A digest describes
detected movement, not a guarantee the proposed replacement will pass every gate.
Inputs and retained original receipts are not modified.

## Explicit answers and signatures

The offline bridge takes a separately recorded `adoption-answers-v1`:

```json
{
  "schema": "adoption-answers-v1",
  "digest_sha256": "<SHA-256 of canonical private digest>",
  "answers": [{
    "window_id": "<exact private window ID>",
    "actor": "owner",
    "decision": "growth",
    "observed_at": "<actual offset-aware answer timestamp>"
  }]
}
```

Allowed decisions are exactly `growth`, `not him`, `not sure`. Partial answers are
allowed; duplicates, unknown windows, non-owner claims, timestamps without offsets and
answers before the digest cutoff are refused. The timestamp is an explicit
recorded claim, not a trusted timestamp service. No clock correction is inferred.

Each `adoption-receipt-v1` signs a payload containing the digest hash, the complete
window/member bindings, owner/decision/observation time, timezone, attribution view
and `eligible_from_day`. That day is the next local calendar day after the answer,
not “24 hours later” or the next UTC date. The enclosing file has schema
`adoption-receipts-v1` and a `receipts` array. Exact duplicate receipts deduplicate;
different answers for the same window cause refusal rather than choosing the
latest or letting an earlier growth answer win. Corrections/revocation require
separate reviewed reconciliation; this first version has no revocation service.
The verifier must receive the complete answer set for that digest, not a curated
subset of positive answers. It cannot discover a withheld later answer.

**Signing is HMAC-SHA256**, with domain separation `adoption-receipt-v1`, a key
fingerprint and constant-time MAC comparison. This is a symmetric keyed signature,
not a public-key/nonrepudiation signature: anyone holding the verification key can
also sign. A private 0600 key file contains `schema: adoption-signing-key-v1` and a
`key_hex` value for a securely generated 256-bit key. No actual key is created or
read by this implementation work. Before real signing, Gloria must choose the
trusted owner-controlled signer/key custody; the verifier gets its trusted key
out of band, never from the receipt. Keys must stay outside the repository and
must never be exposed in cards, stdout, logs or shell arguments. Rotating a key
requires retaining the reviewed verification policy for old receipts; no implicit
fallback key is tried. The prototype accepts one trusted key per invocation.

A valid MAC proves payload integrity/possession of that key. `actor: owner` alone
still **does not prove human identity or a deliberate answer**. The offline signing
command is for her explicit answers or an authorized faithful transcription, never
an automatic judge or inferred adoption from persistence. No owner authentication
UI, key provisioning or permission to sign on her behalf is implemented here.

## Future-only offline use

`verify` checks the signature, exact digest/window membership, timezone/view and
answer timing. Only growth observations before the replay cutoff and past the
local review day produce candidates in `adoption-projection-v1`. It exports the
existing `voice_drift.analyze(adoptions=...)` shape with `decision: adopt` and an
`evidence_sha256` over the signed receipt. Keep the signed envelope and digest as
the private audit trail. “Candidate” is not “reference updated.”

The pure offline analyzer additionally checks that every member is admitted and
hash-bound, the reference version is still current, the members were sustained
shift evidence, at least four separate days support calibration, modes are
independent, and calibration is nondegenerate. It now explicitly requires that
the target's local day is **after the review day**, even if she answered before
the first target reply that day. Same-day and earlier scores are unchanged.
Replacement is scoped and exact, not blending. A stale or unqualified receipt
cannot update a reference. Duplicate verified receipts apply once. A later update
needs a new review of the new reference version.

This CLI does not invoke adoption replay or save reference state. `run_private.py`
still takes no adoption option. A future offline integrator must regenerate and
compare the reviewed digest from the retained snapshot, pass **all** verified
candidates only to the matching timezone/view replay, retain its refusal/revision
log, and never feed them to live memory or prompts. The old low-level analyzer
still accepts structurally claimed receipts; signing is not retrofitted as a
universal authentication layer. Bypassing `verify` bypasses this authentication
boundary. No runtime consumer has been added.

## Private commands and limits

Use already-authorized staged inputs in 0700 private scratch, outside repositories
and live `.vintos`/`.openclaw` trees. All input files must be owner-held 0600 regular
files without symlinks, at most 4 MiB each. Each output below is a **new immediate
subdirectory** of that scratch; existing directories/files are never overwritten.
No source record, key value or private path is printed to stdout. The digest's
Markdown is private too: dates and conversation modes are not public aggregates.

```sh
python3 experiments/nonllm-judges/adoption.py digest \
  --scratch "$SCRATCH" --input "$SCRATCH/numerical-input.json" \
  --run "$SCRATCH/private-run.json" --week-end YYYY-MM-DD \
  --output "$SCRATCH/adoption-week"

# Only after an explicit owner answer and separately established key custody:
python3 experiments/nonllm-judges/adoption.py sign \
  --scratch "$SCRATCH" --digest "$SCRATCH/adoption-week/digest.json" \
  --answers "$SCRATCH/answers.json" --key "$SCRATCH/owner-signing-key.json" \
  --output "$SCRATCH/adoption-signed"

python3 experiments/nonllm-judges/adoption.py verify \
  --scratch "$SCRATCH" --digest "$SCRATCH/adoption-week/digest.json" \
  --receipts "$SCRATCH/adoption-signed/receipts.json" \
  --key "$SCRATCH/owner-signing-key.json" --cutoff '<offset-aware replay cutoff>' \
  --output "$SCRATCH/adoption-verified"
```

The outputs are `digest.json` + `digest.md`, `receipts.json`, and `projection.json`,
respectively, in 0700 directories with 0600 files. Stdout is counts/fixed metadata
only. The script guards writes to those new files, blocks network/subprocesses and
mutations of existing inputs, and sanitizes failures as `adoption_refused`. A failed
or interrupted write may leave an incomplete new private directory; preserve it
for diagnosis and retry in a new directory, never merge it into an answer set.
There are at most 512 windows, members in total, and answers/receipts. No real
messages, signing credentials, membership hashes or vectors belong in the public
repository. Synthetic tests demonstrate mechanics, not real drift accuracy or
Gloria's endorsement of any movement.

# Dataset curation gate

Each concept lives in one JSONL file plus `<name>.manifest.json`. A row is one
matched target/control pair with:

```json
{
  "pair_id": "warmth-s2-1p-none-001",
  "semantic_set": "warmth-001",
  "concept": "Warmth",
  "version": "S2",
  "person": "1P",
  "suffix": "none",
  "target_category": "interpersonal_warmth",
  "control_category": "familiarity_without_warmth",
  "target": "...",
  "control": "..."
}
```

All variants derived from one semantic item share `semantic_set`; grouped K-fold
validation keeps them together. A manifest must name the human reviewers and say
`"curated": true`, or pin the repository, revision, license, and source hash of a
published source dataset. Machine-generated drafts are never silently admitted.

The fourteen initial candidates are eleven content-responsive EmoClaw dimensions,
the separately implemented Nifrathir modifier, and exploratory Pain and Fear. None is
an established residual dimension. Candidate datasets must each contain at least five
target subcategories, at least five matched-control categories, at least twenty independent semantic sets, S1/S2,
first/third person, and the three suffix conditions before a full extraction run.
Every target and control category must contribute at least twenty independent
semantic sets, and every set must carry all six person/suffix variants. S1 and S2
are separate sentence families, not aliases allowed to leak across a fold.

`pain.jsonl` is a deterministic import of the paper authors' published S1/S2,
first/third-person corpus, expanded only into the three declared suffix conditions.
Its manifest pins the upstream commit and source hash; the upstream MIT license is
beside it. No locally authored concept dataset is checked in yet because bulk
model-written sentences have not received the human semantic review on which this
experiment's validity depends. The extractor refuses to turn absent judgments into
measurements.
The primary neutral subsets are disjoint across concepts and drawn from a broad bank;
a shared neutral bank is reserved for a separately labelled comparability analysis.

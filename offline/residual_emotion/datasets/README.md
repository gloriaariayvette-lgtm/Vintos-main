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
`"curated": true`. Machine-generated drafts are never silently admitted.

The eleven initial candidates are the current EmoClaw dimensions, not established
residual dimensions. Candidate datasets must each contain five target subcategories,
five matched-control categories, at least twenty independent semantic sets, S1/S2,
first/third person, and the three suffix conditions before a full extraction run.

No dataset is checked in yet because bulk model-written sentences have not received
the human semantic review on which this experiment's validity depends. The extractor
and analysis deliberately refuse to turn those absent judgments into measurements.

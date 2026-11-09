# Numerical judge status — 2026-11-09

These are additive evidence tools. None replaces a serving judge, changes a feed,
forms a want, nudges emotion or runs automatically. **Private-run-ready** means a
scratch-only CLI exists and synthetic contracts pass; it does not mean historical
coverage, real-runtime compatibility or measured accuracy has been established.
Claude Code owns independent review, the full isolated suite and private runs;
Gloria owns deployment and any later enablement.

| Component | Required inputs | State | What would need to be switched on |
|---|---|---|---|
| Witnessed recurrence | Exact original-act lineage, timestamps, mode/surface, reviewed topic links | **Offline prototype** in `prototype.py`; not included in `run_private.py` | Nothing live for fixture use. A source-specific retained projection and separate reviewed integration are needed before real use; counts cannot decide yearning or closure. |
| Thread-grouping suggestions | Same clean acts plus exact full-text hashes and frozen cached vectors | **Offline prototype** in `prototype.py`; not included in `run_private.py` | Nothing live for fixture use. Needs an explicit private adapter and reviewed grouping threshold; it never merges or deletes threads. |
| Voice coherence / familiarity | Clean finalized replies, full-string encoder cache, qualified freeze, independently supported mode/surface and prior reference days | **Private-run-ready** via `run_private.py`; **needs capture** where strict historical receipts are absent | A private run needs no live switch. Future strict coverage needs approved receipt capture after review/deployment. Serving use needs a separate integration decision. Sparse references abstain. |
| Deviation / sustained drift | Voice inputs over enough distinct days; independently reviewed adoption evidence to update reference epochs | **Private-run-ready**; **needs capture** for missing prospective evidence | Same capture prerequisite as voice. No automatic reference update: reviewed adoption binds an exact version and affects later references only. A single odd reply is not sustained drift. |
| Witnessed humor familiarity | Clean timed joke attempts joined by explicit joke ID/full text, same mode/surface, exact adjacent owner laugh or witnessed 4–5 practice rating | **Private-run-ready**; coverage depends on retained attempts and positive anchors | No live switch for the private CLI. Supply existing exact projections; future missing receipts need approved capture. Unobserved reactions stay unknown. No new jokes/messages requested for tests. |
| Witnessed taste familiarity | Clean timed textual items, same mode/surface, separately supplied exact owner-witnessed Landings `landed` anchors | **Private-run-ready**; sparse or absent anchors remain unscored | No live switch for the private CLI. Supply the read-only Landings projection. `partly`/`missed` are not inferred negatives; no automatic want-formation effect exists. |

Related work retained alongside these six components:

- **Character reference:** separate private projection/cache evaluator, with primary
  and descriptive historical attribution views. It supports the voice/facet path;
  it is not a new live identity verdict. See [character README](../character-reference/README.md).
- **On-message innovation:** offline replay of exactly joined forecast/outcome
  receipts and past-only calibration. Prospective serving coverage **needs capture**;
  historical vectors cannot manufacture a forecast made before the reply. Existing
  journal/dream feeds remain in place. See [witness replay](../judges-witness/README.md).

The private numerical path is `encode_cache.py` → `build_evidence.py` →
`run_private.py`, each writing to a different new private scratch directory. Missing
lineage, cache binding, mode or outcome evidence remains unknown. A reviewed public
artifact pin is now checked in with reviewer attribution from coordination note #51;
the producer still checks the loaded copy's exact hash. Its conservative effective
freeze is **2025-04-28T20:14:53+00:00**, not the earlier initial file-upload date.
Local-trained/subject-tuned artifacts retain actual copy-time freeze. Copy time and
encoding clocks are always preserved. No real weights, messages or private results
are included here; this change records the reviewer's pin, not a new verification run.

The capture implementation has a **dedicated production shadow sink**, disabled by
default. After review and Gloria's deployment, it needs an approved 0700 destination
outside repositories/live workspaces, a 0600 disabled configuration, and
`JUDGES_CAPTURE_CONFIG` wired into the intended processes. Gloria's later enable step
is `python3 ~/.vintos/workspace/scripts/witness_sink.py enable --config APPROVED_CONFIG`;
`disable` is the kill switch. The [capture proposal](../../docs/judges-capture-enable-proposal.md)
gives the full preparation, limits and acceptance requirements. Never set
`JUDGES_CAPTURE_SCRATCH` or repoint `SPARK_WORKSPACE` on a serving process.

Enabling that sink collects receipts; it does **not** enable these numerical judges
as live consumers or replace existing judges. Serving integration remains a separate
review/approval decision. This status describes source capability, not verified live
configuration. All loops, feeds and model chains remain unchanged by this work;
current provider-call savings are zero because no serving call has been replaced.

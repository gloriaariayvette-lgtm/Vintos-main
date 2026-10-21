# Resume on the local Mac execution host

This is unfinished work on `codex/lab-tools-runtime`, based on deploy-branch
`775b3d3`. Nothing from this branch has been deployed or run on Aegis.

Gloria verified Mac-to-Aegis SSH on 21 October: hostname `Aegis`, user `gloria`,
directory `/home/gloria`. The previous task was running in a cloud container.
Its refused connection was an execution-environment failure, not Aegis downtime.
Do not repeat cloud connection diagnostics or substitute local tests for live proof.

From the LOCAL MAC execution environment, with the already-authorized network
access, begin with exactly:

```sh
ssh -o BatchMode=yes -o ConnectTimeout=8 gloria@100.72.225.119 'hostname; whoami; pwd'
ssh -o BatchMode=yes -o ConnectTimeout=8 gloria@100.72.225.119 'ls -t ~/.vintos/deploy/releases | head -1'
```

Live workspace: `/home/gloria/.vintos/workspace`. Read the release JSON and match
the installed files to its revision before attributing failures. Today's commits
on the deploy branch have not been deployed. Read
`docs/briefs/lab-tools-handoff-chat.md` (especially “What Gloria is actually asking
for”) and `CLAUDE.md` from the deploy branch, not an older checkout.

Begin with read-only inspection. Do not modify, restart, deploy, delete or overwrite
anything on either live host without explicit authorization. Gloria runs deploys.

## Candidate changes saved for review, not established fixes

- `lab_tool_calls.py`: distinguish sources from connectors by operation; normalize
  supported source/operation aliases while retaining inputs; leave paid operations
  behind their existing policy. A plugin result exposes the common receipt field.
- Config writers persist explicit changes instead of serializing every default;
  `atlas-evo-on/off` records an explicit follow-up setting.
- `lab_investigations.py`: persistent question/prediction/plan, one selected
  operation per turn, saved output digests and explicit previous-output references.
  Screening becomes a selectable operation, with no fixed turn share. Candidate
  dispatch includes existing sources, plugins, instruments, experiments, sequence
  representation and genomic likelihood routes. The ordinary orient path now
  enters this candidate loop.
- Daily experiment prompt receives its recent experiment history rather than
  seeing only repeated protein examples.
- New modules are named in the deployment manifest. Ownership/untested reports
  have NOT yet been regenerated. Existing phase tests explicitly stub the new
  loop; its persistence/reference behavior has a separate isolated suite.

These changes need cross-path review. In particular, confirm source-record shape
at final identity/coverage review, actual connector schema discovery (local and
account connectors differ), full output references versus bounded prompt previews,
tool availability, execution receipts, timeout semantics, and native installed
instruments that do not yet have a general invocation wrapper. Do not deploy this
candidate as if “every tool works” had been demonstrated.

## Evidence and outstanding work

- No real tool run on Aegis or the Mac has been performed by this task.
- No deployed release has been identified by this task yet.
- The old narrowing-error interpretation is wrong at code level: `9733de2`
  changed successful rewrites from deliberate fault-log ValueErrors to edit rows.
  Compare that revision to the actual deployed release and event timestamps.
- Ten new routing/config tests and five chain/persistence tests passed with
  scratch stores and blocked external actions. Campaign tests passed 35 checks.
  Existing phase suites were checked under a scratch write/network/process guard;
  failures from catalog stubs and a real child-process test boundary were corrected.
  This is regression evidence only, not scientific or live operational proof.
- Parser failures require actual retained diagnostics from the deployed system;
  do not claim that a shorter candidate planning contract explains all 398 failures.
- Re-measure every actual execution path, including daily sessions, embedding and
  genomic phases; the previous “not running” list omitted them.
- Tool success requires autonomous selection, execution, retained output, and
  downstream use over TWO DAYS after Gloria deploys. A scratch direct call is
  only an initial check. No such observation period has begun for these changes.
- Preserve existing identity/repeat/evidence checks and spending caps. Do not
  broaden the paid-call or approval policies to make a demonstration pass.

Continue from the saved branch on the Mac; do not repeat the cloud-only analysis.

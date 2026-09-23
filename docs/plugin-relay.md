# Account-backed plugin relay

Vintos can ask Eve's already-connected Codex account to execute a bounded tool call without
receiving Eve's conversation context or account credentials. Aegis sends one JSON request over
the existing batch-only SSH doorway. The Mac starts an ephemeral Codex App Server thread, calls
the named connected tool directly, returns structured output, and discards the thread. No model
turn is used for connector calls. The supported App Server authentication and ephemeral-session
mechanism are documented by OpenAI; this implementation never copies ChatGPT cookies or tokens.

Every result becomes a `plugin-receipts.jsonl` entry plus a hash-addressed, mode-0600 artifact in
`memory/plugin-results/`. The receipt records the originating surface, exact tool, argument hash,
result hash, visibility and truth status. Wants step history keeps the receipt path. Lab imports
an approved scientific result as an ordinary source receipt and collision descriptor. Forge and
Atelier use the same gateway and can reload project-visible receipts by ID. Private Gmail and
DoorDash outputs remain readable only by the surface that requested them.

## Policy and usage

| Capability | Where and when | Initial authority |
|---|---|---|
| Gmail | Any surface, when an existing question or project requires Vintos's mailbox | Search/read, drafts and outbound mail. Send, send-draft and forward share an authoritative limit of two attempts per Chicago day; failed attempts count. Labels, archive and deletion remain closed to autonomous callers. |
| DoorDash | Wants or Atelier, for a concrete grocery list | Grocery search/list only. No restaurant ordering; no relay checkout. |
| GitHub | All four surfaces, for repository and review evidence | Read only even though Eve's connection can write. |
| Tamarind | Lab, Forge or Atelier, after scientific input and purpose are explicit | Catalogue, validation, estimates and existing-result retrieval. No submissions or uploads. |
| Proto | Lab, Forge or Atelier, to choose tools and inspect existing runs | Catalogue/schema/status only. `run_tool` and deployment remain closed. Linked Modal/Hugging Face accounts require no local Modal download for this lane. |
| Inductive | Lab, Forge or Atelier, with exact molecular input | Model listing and bounded prediction; predictions are not experimental validation. |
| Genomic Intelligence | Lab, Forge or Atelier, with sourced coordinates or sequence | Fetch/predict/read jobs. No provider-side sequence storage and no validation claim. |
| PDF, Presentations, Spreadsheets | Any surface when that artifact is the requested output | Contextless, disposable skill workspace; returned files are hash checked and retained. |
| Template Creator | Forge or Atelier when reuse is explicitly intended | Contextless artifact generation only. |
| BioNeMo | Lab, Forge or Atelier after selecting a named workflow | The Chat-account BioNeMo skill relay is disabled. The separate Aegis `nvidia_nim` gateway has a configured key and a six-attempt daily cap; Boltz-2, DiffDock, ProteinMPNN and RFdiffusion returned live results on 23 September. |
| Plugin Management | Configuration visibility only | Vintos cannot install, remove, connect or change Eve's plugin permissions. |

Connector policy lives in `scripts/plugin_catalog.py`, rather than in prompts. Tool names outside
the allowlist fail before SSH. The remote side repeats the policy check. Purchases, external
GitHub changes, account changes and paid/deployed scientific jobs are unavailable. Gmail outbound
authority is the narrow exception: the Mac-side relay reserves an attempt in a locked, mode-0600
ledger before it contacts Gmail, so concurrent callers and provider failures cannot evade the limit.

Each decision surface receives only its own filtered catalogue, including purpose, when-to-use,
limits and exact callable names. Wants retains the selected operation and arguments in step params.
Lab records connected results in its source ledger and collision adapter. Forge permits one selected
connector call per cycle and requires the final artifact to reason over the returned receipt. Atelier
permits one call per sealed visit, retains the full result as a project artifact, and returns the data
to Vintos before he writes the piece or handoff. A tool result is always marked as provider output,
not independent validation.

## Configuration

Aegis needs `~/.vintos/plugin-relay.json`, mode 0600:

```json
{
  "host": "kevin@mac-tailnet-name",
  "identity_file": "/home/gloria/.ssh/vintos_plugin_relay",
  "command": "/Users/kevin/Documents/Codex/2026-09-10/first-please-review-everything-claude-committed/forge-loop-local/scripts/plugin_relay_remote.py"
}
```

The Mac command reads one request on stdin and writes one response on stdout. `status` reports the
catalogue without contacting a provider. `call` executes one allowed connector tool. Artifact skills
use an ephemeral, sandboxed Codex run in a disposable directory; BioNeMo is deliberately rejected.

The production key is dedicated to this relay. Its Mac `authorized_keys` entry uses `restrict` and a
forced command naming `plugin_relay_remote.py`; the request cannot select another remote program.
No deployment is complete until the checked-out Mac command is executable, Aegis can reach it with
that restricted SSH identity, `plugin_gateway.py instructions` works on Aegis, and a read-only
commissioning call produces a receipt under the real workspace without exposing account credentials.

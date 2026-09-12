# Aegis Buzz integration

This adapts the actual `block/buzz` relay, native client, SDK and ACP harness.
It does not replace the native workspace with the legacy bench page.

The local ACP patch adds `--respond-to owner-signed`: a task begins only from
an event signed directly by Gloria's configured owner key. Sibling agents,
relay workflows and invalid signatures cannot inherit that authorization.
Heartbeats and initial prompts are disabled. Each handoff is a proposal in the
shared stream; Gloria must address the receiving agent herself to authorize it.

Workers use separate Linux accounts with private persistent workspaces. Owner
keys and live Vintos files are outside their filesystem boundary. The upstream
stream, forum, thread context and agent memories provide the working interface.

Installation and commissioning are in progress. See docs/open-work.md for
unresolved work. No paid model commissioning has been performed by this installer.

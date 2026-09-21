#!/usr/bin/env python3
"""Fail-closed policy for Vintos's own Inkbox comms identity (vintos@inkboxmail.com).

Inkbox is different from the ChatGPT-account relay (plugin_catalog.py): it is his OWN
mailbox + iMessage, reached MCP-native rather than through the Mac doorway. But the outbound
danger is identical, so the guard reuses the exact machinery the relay already ships —
plugin_send_guard.outbound_findings (never returns matched secret material) and PolicyHold —
so both lanes fail closed the same way and one audit covers both.

Three tiers, decided with Gloria:
  FREE      reads and internal context (list/get mail, contacts, notes, identity, status).
            Creating/updating a contact or note is context management, not an outbound send.
  GUARDED   anything that reaches a real person — email send/reply/forward, iMessage send,
            SMS text. Allowed only when it carries no secret (confidential-info block) AND
            any link in it has explicit human approval (link-approval gate). Both fail closed.
  BLOCKED   agent-to-agent (A2A) — off until Gloria turns it on — and SMS/voice, which need a
            paid phone number this identity does not have. Refused with a named receipt, never
            silently attempted.

The guard decides; it never sends. The caller runs the tool only for an ``allow`` verdict, and
records the receipt either way. reasons/links carry no secret material (only rule names + URLs).
"""
from __future__ import annotations

import os

from plugin_send_guard import PolicyHold, outbound_findings, request_digest

# Tool tiers. Names are the Inkbox MCP tool names, minus the ``inkbox_`` prefix, so a future
# rename of the connector prefix does not silently reclassify a send as a read.
_READ = frozenset((
    "identity_get", "channel_status_get", "imessage_onboarding_get", "sms_onboarding_get",
    "sms_consent_get", "emails_list", "email_get", "email_attachment_get",
    "conversations_list", "conversation_get", "contacts_list", "contact_get",
    "contact_correspondence_list", "contact_memories_list", "contact_rules_list",
    "notes_list", "note_get", "calls_list", "call_get", "media_stage",
    # internal context management — a write, but never leaves the house to a person
    "contact_create", "contact_update", "contact_delete", "note_create", "note_update",
    "note_delete", "conversation_mark_read", "email_flags_update", "thread_folder_update",
    "email_attachment_upload", "email_delete",
))
_SEND = frozenset((
    "email_send", "email_reply", "email_forward",
    "imessage_send", "imessage_react", "imessage_unreact", "text_send",
))
# A2A stays off until Gloria asks; SMS/voice need a paid number this identity lacks.
_BLOCKED = {
    "a2a_task_send": "agent-to-agent is off until you enable it",
    "a2a_task_reply": "agent-to-agent is off until you enable it",
    "a2a_task_get": "agent-to-agent is off until you enable it",
    "a2a_tasks_list": "agent-to-agent is off until you enable it",
    "a2a_agents_list": "agent-to-agent is off until you enable it",
    "text_send_sms": "SMS needs a paid phone number this identity does not have",
}


def _base(tool: str) -> str:
    t = str(tool or "").strip()
    return t[len("inkbox_"):] if t.startswith("inkbox_") else t


def classify(tool: str) -> str:
    """read | send | blocked | unknown — unknown is treated as send (fail closed)."""
    b = _base(tool)
    if b in _BLOCKED:
        return "blocked"
    if b in _READ:
        return "read"
    if b in _SEND:
        return "send"
    return "unknown"


def guard(tool, arguments=None, *, secrets_root=None, approved_links=None):
    """Return a verdict dict; raise PolicyHold when a send must be refused outright.

    verdict: {"tool", "tier", "decision": allow|hold, "reason", "links", "request_sha256"}
      - read           -> allow
      - blocked        -> PolicyHold (never attempted)
      - send w/ secret -> PolicyHold (confidential-info block; secret never echoed)
      - send w/ an unapproved link -> decision "hold" (link-approval gate) with the links
      - send otherwise -> allow
    ``approved_links`` is the set of URLs Gloria has explicitly approved for THIS send.
    """
    arguments = arguments or {}
    b = _base(tool)
    tier = classify(tool)
    sha = request_digest(arguments)
    if tier == "read":
        return {"tool": tool, "tier": "read", "decision": "allow", "reason": "", "links": [],
                "request_sha256": sha}
    if tier == "blocked":
        raise PolicyHold({"type": "inkbox_blocked", "tool": tool, "reason": _BLOCKED[b],
                          "request_sha256": sha})
    # send or unknown -> inspect, fail closed
    findings = outbound_findings(arguments, secrets_root=secrets_root)
    if findings["rules"]:
        raise PolicyHold({"type": "inkbox_confidential_block", "tool": tool,
                          "rules": findings["rules"], "request_sha256": sha})
    approved = set(approved_links or ())
    pending = [u for u in findings["links"] if u not in approved]
    if pending:
        return {"tool": tool, "tier": "send", "decision": "hold", "reason": "link_approval_required",
                "links": pending, "request_sha256": sha}
    reason = "unrecognized_tool_treated_as_send" if tier == "unknown" else ""
    return {"tool": tool, "tier": "send", "decision": "allow", "reason": reason,
            "links": findings["links"], "request_sha256": sha}


PURPOSE = ("Vintos's own communications identity — his mailbox (vintos@inkboxmail.com) and "
           "iMessage. Reads and drafts freely; anything that reaches a person is guarded; "
           "agent-to-agent and SMS/voice are off.")


if __name__ == "__main__":
    import json as _j, sys as _s
    _tool = _s.argv[1] if len(_s.argv) > 1 else "inkbox_emails_list"
    _args = _j.loads(_s.argv[2]) if len(_s.argv) > 2 else {}
    try:
        print(_j.dumps(guard(_tool, _args), indent=2))
    except PolicyHold as _h:
        print(_j.dumps({"held": _h.receipt}, indent=2))

#!/usr/bin/env python3
"""Inkbox guard: reads pass, sends fail closed, A2A/SMS blocked, secrets never echoed.

No sender is imported and none can be: the guard only decides, it never calls Inkbox. The
one thing that touches disk is the secrets scan, pointed at a throwaway dir here so the real
~/.vintos/secrets is never read. Asserted in the suite so a later edit can't undo the isolation.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

# Throwaway secrets dir with one planted secret; the real store is never touched.
SEC = Path(tempfile.mkdtemp(prefix="inkbox-guard-secrets-"))
(SEC / "xai").write_text("sk-live-PLANTED-secret-value-do-not-leak-abcdef123456")
os.environ["VINTOS_SECRETS"] = str(SEC)
assert str(SEC).startswith(tempfile.gettempdir()), "secrets scan must point at a throwaway dir"

spec = importlib.util.spec_from_file_location("inkbox_guard", SCRIPTS / "inkbox_guard.py")
G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
from plugin_send_guard import PolicyHold

passed = total = 0
def check(label, cond):
    global passed, total
    total += 1
    assert cond, label
    passed += 1

# Reads pass, and prefixed names classify the same as bare ones.
for t in ("inkbox_emails_list", "email_get", "inkbox_identity_get", "contact_create", "notes_list"):
    v = G.guard(t, {"query": "anything"}, secrets_root=str(SEC))
    check("read allowed: " + t, v["tier"] == "read" and v["decision"] == "allow")

# A clean send is allowed.
v = G.guard("inkbox_email_send", {"to": "friend@example.com", "subject": "hi", "body": "just saying hello"},
            secrets_root=str(SEC))
check("clean send allowed", v["tier"] == "send" and v["decision"] == "allow" and not v["links"])

# A send carrying a link holds for approval — and clears once the link is approved.
args_link = {"to": "friend@example.com", "subject": "look", "body": "see https://example.com/x"}
v = G.guard("inkbox_email_send", args_link, secrets_root=str(SEC))
check("link holds for approval", v["decision"] == "hold" and v["reason"] == "link_approval_required"
      and "https://example.com/x" in v["links"])
v = G.guard("inkbox_email_send", args_link, secrets_root=str(SEC), approved_links=["https://example.com/x"])
check("approved link clears the hold", v["decision"] == "allow")

# A send carrying a secret is refused outright, and the secret is never in the receipt.
try:
    G.guard("inkbox_imessage_send", {"body": "the key is sk-live-PLANTED-secret-value-do-not-leak-abcdef123456"},
            secrets_root=str(SEC))
    check("secret send raised", False)
except PolicyHold as h:
    blob = repr(h.receipt)
    check("secret send blocked", h.receipt["type"] == "inkbox_confidential_block"
          and "installed_secret_value" in h.receipt["rules"])
    check("secret material never echoed in the receipt", "PLANTED" not in blob and "sk-live" not in blob)

# A labeled credential in the body is caught even if it isn't an installed secret.
try:
    G.guard("inkbox_email_send", {"to": "x@y.com", "body": "api_key: abcd1234efgh"}, secrets_root=str(SEC))
    check("labeled credential raised", False)
except PolicyHold as h:
    check("labeled credential blocked", "labeled_credential" in h.receipt["rules"])

# A2A and SMS/voice are blocked outright, with a named reason.
for t, why in (("inkbox_a2a_task_send", "agent-to-agent"), ("text_send_sms", "phone number")):
    try:
        G.guard(t, {"body": "hi"}, secrets_root=str(SEC))
        check("blocked raised: " + t, False)
    except PolicyHold as h:
        check("blocked: " + t, h.receipt["type"] == "inkbox_blocked" and why in h.receipt["reason"])

# An unrecognized tool is treated as a send (fail closed), not waved through as a read.
v = G.guard("inkbox_some_new_tool", {"body": "clean"}, secrets_root=str(SEC))
check("unknown tool fails closed to send", v["tier"] == "send" and v["reason"] == "unrecognized_tool_treated_as_send")
try:
    G.guard("inkbox_some_new_tool", {"body": "sk-live-PLANTED-secret-value-do-not-leak-abcdef123456"}, secrets_root=str(SEC))
    check("unknown tool with secret raised", False)
except PolicyHold:
    check("unknown tool inspects for secrets too", True)

# The module imports no sender and never reaches Inkbox.
src = (SCRIPTS / "inkbox_guard.py").read_text()
check("guard imports no inkbox client / requests / httpx",
      "import requests" not in src and "httpx" not in src and "mcp__Inkbox" not in src)
check("guard only decides — no send/deliver call", "deliver(" not in src and ".send(" not in src)

print(f"{passed}/{total} passed")

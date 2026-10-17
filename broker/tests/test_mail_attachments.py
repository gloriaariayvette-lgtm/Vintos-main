#!/usr/bin/env python3
"""Deterministic offline attachment ingestion, provenance, study and explicit recovery regressions."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOME = tempfile.mkdtemp(prefix="mail-attachments-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = HOME + "/workspace"
sys.path.insert(0, str(ROOT / "scripts"))
SENT = []
def refuse(*args, **kw):
    SENT.append(args)
    raise AssertionError("offline suite: no network, models, or sending")
socket.socket.connect = refuse
sys.modules["requests"] = types.SimpleNamespace(get=refuse, post=refuse)
sys.modules["plugin_gateway"] = types.SimpleNamespace(call=refuse, load_receipt=refuse)
import want_email as E
import received_mail as M
import scholar as S
E.local_think = E._reply_think = S._local = refuse
E.links_read = lambda *args, **kw: []

TEXT = "Wilterson and Graziano research on attention schema.\n" + "Measured findings.\n" * 100
MARKDOWN = "# Butlin and Chalmers indicators of consciousness\nActual paper text.\n"

def part(name="paper.txt", text=TEXT, mime="text/plain", download=False, **kw):
    data = text.encode("utf-8")
    body = {"size": len(data)}
    body.update({"attachment_id": name + "-id"} if download else {"base64_url_content": base64.urlsafe_b64encode(data).decode().rstrip("=")})
    return {"part_id": name, "mime_type": mime, "filename": name, "body": body,
            "read_attachment_supported": True, **kw}

def message(parts, mid="mail-1", sender="Vintos <vintos@example.org>", subject="[Grok Bot] Research"):
    return {"id": mid, "payload": {"mime_type": "multipart/mixed", "headers": [
        {"name": "From", "value": sender}, {"name": "Subject", "value": subject}], "parts": [
            {"mime_type": "text/plain", "body": {"content": "The letter body, not the papers."}}, *parts]}}

class Attachments(unittest.TestCase):
    def setUp(self):
        for path in (E.INBOX_LOG, E.TEND_STATE, E.CONTACTS):
            try: os.unlink(path)
            except FileNotFoundError: pass
        self.calls = []
        self.files = []
        self.source = message([part(), part("notes.md", MARKDOWN, "text/markdown")])
        self.file_text = TEXT.encode()
    def gateway(self, tool, args, purpose):
        self.calls.append((tool, args))
        if tool == "gmail.get_profile": return {"structuredContent": {"email_address": "vintos@example.org"}}
        if tool == "gmail.search_emails": return {"emails": [{"id": "mail-1", "from_": "vintos@example.org", "snippet": "letter"}]}
        if tool == "gmail.batch_read_email": return {"structuredContent": {"responses": [copy.deepcopy(self.source)]}}
        if tool == "gmail.read_attachment": return {"structuredContent": {"message_id": "mail-1", "file_uri": {"download_url": "connector-original"},
            "content_truncated": True, "content": [{"type": "text", "text": "INCOMPLETE PREVIEW"}]}}
        raise AssertionError(tool)
    def file_read(self, ref, cap):
        self.files.append(cap); return self.file_text
    def read(self, source=None, trusted=()):
        msgs = E._messages(source or self.source)
        E._read_attachments(msgs, self.gateway, trusted, self.file_read)
        return msgs[0]
    def test_isolation(self):
        self.assertTrue(all(str(p).startswith(HOME) for p in (E.INBOX_LOG, E.CONTACTS, E.TEND_STATE, M.INBOX_LOG, S.DOSSIERS)))
        self.assertIs(E.local_think, refuse)
        self.assertIs(sys.modules["plugin_gateway"].call, refuse)
    def test_multiple_and_decoding(self):
        m = self.read()
        self.assertEqual(m["body"], "The letter body, not the papers.")
        self.assertEqual([a["text"] for a in m["attachments"]], [TEXT, MARKDOWN])
        self.assertEqual(m["attachments"][0]["sha256"], hashlib.sha256(TEXT.encode()).hexdigest())
        self.assertEqual(m["attachments"][0]["correspondent"], "Grok Bot")
        self.assertEqual(m["attachments"][0]["sender"], "Vintos <vintos@example.org>")
        self.assertIn("EXCERPT", E.attachments_view(m["attachments"]))
    def test_full_read_retains_metadata(self):
        m = E._messages({"id": "mail-1", "snippet": "preview", "from_": "wrong@example.org"})
        E._read_whole(m, self.gateway)
        self.assertEqual(len(m[0]["attachments"]), 2)
        self.assertEqual(m[0]["from"], "Vintos <vintos@example.org>")
    def test_gateway_original_over_preview(self):
        m = self.read(message([part(download=True)]))
        self.assertEqual(m["attachments"][0]["text"], TEXT)
        self.assertEqual(self.calls[-1][1], {"message_id": "mail-1", "attachment_id": "paper.txt-id"})
        self.assertEqual(len(self.files), 1)
    def test_missing_content(self):
        self.source = message([part(download=True)])
        self.gateway0 = self.gateway
        def gateway(tool, *args):
            return {"structuredContent": {"content_truncated": True, "content": [{"type": "text", "text": "preview"}]}} if tool == "gmail.read_attachment" else self.gateway0(tool, *args)
        m = E._messages(self.source); E._read_attachments(m, gateway)
        self.assertEqual(m[0]["attachments"][0]["status"], "not_read")
        self.assertNotIn("text", m[0]["attachments"][0])
    def test_declared_oversize(self):
        p = part(download=True); p["body"]["size"] = E.ATTACHMENT_BYTES + 1
        a = self.read(message([p]))["attachments"][0]
        self.assertEqual(a["status"], "not_read")
        self.assertFalse(self.files)
        self.assertFalse(any(t == "gmail.read_attachment" for t, _ in self.calls))
    def test_actual_oversize(self):
        self.file_text = b"x" * (E.ATTACHMENT_BYTES + 1)
        self.assertEqual(self.read(message([part(download=True)]))["attachments"][0]["status"], "not_read")
    def test_unsupported(self):
        m = self.read(message([part(mime="application/pdf")]))
        self.assertIn("unsupported", m["attachments"][0]["why"])
    def test_gateway_failure(self):
        def failed(tool, *args):
            if tool == "gmail.get_profile": return {"email_address": "vintos@example.org"}
            raise RuntimeError("private https://signed.example/?secret=not-for-log")
        m = E._messages(message([part(download=True)])); E._read_attachments(m, failed)
        a = m[0]["attachments"][0]
        self.assertEqual(a["why"], "RuntimeError")
        self.assertNotIn("text", a)
    def test_malformed_bytes_and_charset(self):
        for change in ({"data": "%%%"}, {"base64_url_content": "_w"}):
            p = part(); p["body"] = change
            self.assertEqual(self.read(message([p]))["attachments"][0]["status"], "not_read")
        p = part(charset="arbitrary-codec")
        self.assertIn("charset", self.read(message([p]))["attachments"][0]["why"])
    def test_explicit_charset(self):
        p = part(); p["charset"] = "windows-1252"; p["body"] = {"data": base64.urlsafe_b64encode(b"caf\xe9").decode()}
        self.assertEqual(self.read(message([p]))["attachments"][0]["text"], "café")
    def test_untrusted_cannot_claim_agent(self):
        m = self.read(message([part(download=True)], sender="stranger@example.org"))
        self.assertEqual(m["attachments"][0]["status"], "not_read")
        self.assertFalse(self.files)
        self.assertFalse(any(t == "gmail.read_attachment" for t, _ in self.calls))
    def test_contact_trusted(self):
        m = self.read(message([part()], sender="Researcher <person@example.org>", subject="A reply"), trusted={"person@example.org"})
        self.assertEqual(m["attachments"][0]["status"], "ingested")
        self.assertEqual(m["attachments"][0]["correspondent"], "Researcher <person@example.org>")
        self.assertFalse(self.calls)
    def test_support_false_never_downloaded(self):
        m = self.read(message([part(download=True, read_attachment_supported=False)]))
        self.assertEqual(m["attachments"][0]["status"], "not_read"); self.assertFalse(self.files)
    def test_attachment_only_body(self):
        self.assertEqual(E._payload_text(part()), "")
    def test_limits(self):
        m = self.read(message([part(str(i), "x" * 70000) for i in range(5)]))
        self.assertLessEqual(sum(a.get("bytes", 0) for a in m["attachments"]), E.ATTACHMENT_TOTAL_BYTES)
        self.assertEqual(m["attachments"][-1]["status"], "not_read")
    def test_duplicate_mime_parts(self):
        self.assertEqual(len(self.read(message([part(), part()]))["attachments"]), 1)
    def test_duplicate_checks_and_reads(self):
        others = []; E.check_inbox({}, gmail=self.gateway, others=others)
        self.assertEqual(len(others), 1)
        prompts = []
        think = lambda s, p, *a: prompts.append(p) or '{"what":"research","keep":false}'
        E.read_mail(others, think=think, want=refuse)
        E.read_mail(others, think=think, want=refuse)
        again = []; E.check_inbox({}, gmail=self.gateway, others=again)
        self.assertEqual(again, []); self.assertEqual(len(prompts), 1)
        self.assertIn("Butlin", prompts[0])
        self.assertEqual(len(Path(E.INBOX_LOG).read_text().splitlines()), 1)
    def test_recovery_and_existing_research_workflow(self):
        self.source = message([part(), part("butlin_2025_indicators_tics.txt", MARKDOWN)])
        row = E.recover_attachments("mail-1", gmail=self.gateway, file_read=self.file_read)
        count = len(self.calls)
        E.recover_attachments("mail-1", gmail=refuse, file_read=refuse)
        self.assertEqual(len(self.calls), count)
        want = {"want": "I want to email Michael Graziano about attention schema research"}
        attachments = M.research_attachments(want)
        self.assertEqual(attachments[0]["text"], TEXT)
        block = M.want_block(want)
        self.assertIn("Attachment excerpt", block); self.assertIn("sha256", block)
        self.assertIn("not Gloria's", block)
        d = {"read": [], "works": [{"title": "unused"}]}
        prompts = []
        think = lambda s, p: prompts.append(p) or '{"claims":["Only a test note"]}'
        S.read_into(d, "attention schema", attachments=attachments, budget=1, get=refuse, think=think)
        self.assertIn(TEXT, prompts[0])
        self.assertEqual(d["read"][0]["correspondent"], "Grok Bot")
        self.assertIn("attachment excerpt", S.reading_block(d))
        S.read_into(d, "attention schema", attachments=attachments, budget=1, get=lambda *a: {}, think=think)
        self.assertEqual(len(d["read"]), 1)
    def test_recovery_preserves_interpretation(self):
        os.makedirs(E.MEMORY, exist_ok=True)
        old = {"id":"mail-1", "from":"Grok Bot", "read_at":"2026-10-16T09:00:00", "to_me":"his own judgment", "body":"letter"}
        Path(E.INBOX_LOG).write_text(json.dumps(old) + "\n")
        r = E.recover_attachments("mail-1", gmail=self.gateway)
        self.assertEqual(r["to_me"], old["to_me"]); self.assertEqual(r["read_at"], old["read_at"])
        self.assertEqual(r["body"], "letter")
    def test_recovery_preserves_concurrent_arrival(self):
        self.source = message([part(download=True)])
        def file_read(ref, cap):
            E._log_mail({"id": "arrived-during-download", "body": "new mail"})
            return self.file_text
        E.recover_attachments("mail-1", gmail=self.gateway, file_read=file_read)
        self.assertEqual({json.loads(x)["id"] for x in Path(E.INBOX_LOG).read_text().splitlines()},
                         {"mail-1", "arrived-during-download"})
    def test_prompt_budget_shared(self):
        m = self.read()
        view = E.mail_reading_view("x" * 20000, m["attachments"])
        self.assertLess(len(view), E.PART * E.PARTS + 350)
        self.assertIn("NOT shown", view)
        self.assertIn("ATTACHMENT EXCERPT", view)
    def test_live_profile_email_key(self):
        def gateway(tool, *args):
            if tool == "gmail.get_profile": return {"structuredContent": {"id": "account-id", "email": "vintos@example.org"}}
            return self.gateway(tool, *args)
        m = E._messages(self.source)
        E._read_attachments(m, gateway, file_read=self.file_read)
        self.assertTrue(all(a["status"] == "ingested" for a in m[0]["attachments"]))
    def test_profile_failure_reported(self):
        m = E._messages(self.source)
        def gateway(*a): raise RuntimeError("gateway unavailable")
        E._read_attachments(m, gateway)
        self.assertIn("mailbox identity unavailable: RuntimeError", m[0]["attachments"][0]["why"])
    def test_incomplete_original_is_not_success(self):
        self.file_text = b"partial"
        a = self.read(message([part(download=True)]))["attachments"][0]
        self.assertEqual(a["status"], "not_read")
        self.assertIn("byte count", a["why"])
    def test_file_host_and_redirect_security(self):
        with self.assertRaises(ValueError):
            E._attachment_file({"download_url": "http://127.0.0.1/private"}, 100)
        original = E._link_fetch
        called = []
        def fetch(url, **kw):
            called.append(kw)
            kw["transport"](url, {}, 20, kw["max_bytes"])
            return {"fetched": False, "kind": "refused"}
        E._link_fetch = lambda: types.SimpleNamespace(fetch=fetch,
            _transport=lambda *a: (302, {"location": "http://127.0.0.1/private"}, b"", False))
        try:
            with self.assertRaises(ValueError):
                E._attachment_file({"download_url": "https://files.oaiusercontent.com/original"}, 100)
            self.assertEqual(called[0]["max_redirects"], 0)
            self.assertEqual(called[0]["max_bytes"], 100)
            self.assertFalse(called[0]["article_route"])
        finally: E._link_fetch = original
    def test_per_check_count(self):
        msgs = E._messages({"messages": [message([part(str(j), "text") for j in range(4)], mid=str(i)) for i in range(3)]})
        E._read_attachments(msgs, self.gateway)
        self.assertEqual(sum(a["status"] == "ingested" for m in msgs for a in m["attachments"]), E.ATTACHMENT_PER_CHECK)
    def test_missing_metadata_identifier(self):
        p = part(download=True); p["body"].pop("attachment_id"); p["filename"] = ""
        p["content_disposition"] = "attachment"
        self.assertIn("identifier", self.read(message([p]))["attachments"][0]["why"])
    def test_filename_fallback_and_repeated_ingestion(self):
        p = part(download=True); p["body"]["attachment_id"] = "truncated…"
        m = self.read(message([p]))
        self.assertEqual(self.calls[-1][1], {"message_id": "mail-1", "filename": "paper.txt"})
        count = len(self.calls)
        E._read_attachments([m], refuse, file_read=refuse)
        self.assertEqual(len(self.calls), count)
    def tearDown(self):
        self.assertEqual(SENT, [])

if __name__ == "__main__": unittest.main()

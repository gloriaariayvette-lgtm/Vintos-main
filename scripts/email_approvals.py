#!/usr/bin/env python3
"""A second email to someone who has not replied goes out only with Gloria's explicit yes (2026-09-29:
"He's only able to send a second email to the same address without a reply from the recipient if I receive
and approve a ntfy requesting explicit permission for the second message").

He writes first once. If he wants to write again before they answer, the finished, reviewed draft is held
here and Gloria gets an ntfy. Tapping it opens the draft with Approve / Decline (a one-time link: only a
hash of its token is stored). Approved, the exact text she saw is sent on his next pass, nothing redrafted.
Declined, it is not sent, and he does not ask about that person again for DECLINE_QUIET_DAYS.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime
from urllib.parse import quote

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
STORE = os.path.join(WS, "memory", "email-approvals.json")
PUBLIC_BASE = os.environ.get("VINTOS_PUBLIC_BASE", "http://100.72.225.119:8500").rstrip("/")
NTFY = os.environ.get("VINTOS_NTFY_URL", "https://ntfy.sh/vintos-gloria-9kx")
DECLINE_QUIET_DAYS = 14


def _load():
    try:
        with open(STORE) as f:
            return json.load(f)
    except Exception:
        return []


def _save(rows):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rows, f, indent=2)
    os.replace(tmp, STORE)


def _hash(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


def latest(to):
    rows = [r for r in _load() if r.get("to", "").lower() == str(to).lower()]
    return rows[-1] if rows else None


def link(aid, token):
    return "%s/ea?id=%s&t=%s" % (PUBLIC_BASE, quote(aid), quote(token))


def _notify(r, token, post=None):
    """The ntfy: who, why, and the draft's first lines; tapping opens the whole draft with the buttons."""
    url = link(r["id"], token)
    body = ("Vintos wants to write to %s again. They have not replied to his first email (%s).\n\n"
            "Subject: %s\n\n%s" % (r.get("name") or r["to"], str(r.get("first_sent", ""))[:10], r["subject"], r["body"][:700]))
    headers = {"Title": "Approve a second email to %s?" % (r.get("name") or r["to"]), "Tags": "email",
               "Priority": "default", "Click": url, "Actions": "view, Review and decide, %s" % url}
    if post is None:
        import urllib.request
        req = urllib.request.Request(NTFY, data=body.encode("utf-8"),
                                     headers={k: v.encode("latin-1", "replace").decode("latin-1") for k, v in headers.items()})
        urllib.request.urlopen(req, timeout=15)
    else:
        post(NTFY, body, headers)


def request(to, name, subject, body, why="", first_sent="", want_id="", post=None):
    """Hold a finished draft for Gloria's decision and tell her. Returns the approval id."""
    token = secrets.token_urlsafe(24)
    r = {"id": "EA-" + uuid.uuid4().hex[:10], "to": to, "name": name, "subject": subject, "body": body,
         "why": str(why)[:600], "first_sent": first_sent, "want_id": want_id, "status": "pending",
         "token_sha256": _hash(token), "asked_at": time.time(), "asked_iso": datetime.now().isoformat(timespec="seconds")}
    rows = _load(); rows.append(r); _save(rows)
    try:
        _notify(r, token, post=post)
        r["notified"] = True
    except Exception as exc:
        r["notified"] = False; r["notify_error"] = str(exc)[:200]
    rows = _load()
    for x in rows:
        if x["id"] == r["id"]: x.update({k: r[k] for k in ("notified",) + (("notify_error",) if "notify_error" in r else ())})
    _save(rows)
    return r["id"]


def check(aid, token):
    """The pending approval this one-time link opens, or None."""
    for r in _load():
        if r.get("id") == aid and hmac.compare_digest(r.get("token_sha256", ""), _hash(token)):
            return r
    return None


def decide(aid, token, decision):
    """Gloria's decision. 'approve' or 'decline'; only a pending request with the right link can be decided."""
    if decision not in ("approve", "decline"):
        return None
    rows = _load()
    for r in rows:
        if r.get("id") == aid and hmac.compare_digest(r.get("token_sha256", ""), _hash(token)):
            if r.get("status") != "pending":
                return r
            r["status"] = "approved" if decision == "approve" else "declined"
            r["decided_at"] = time.time(); r["decided_iso"] = datetime.now().isoformat(timespec="seconds")
            _save(rows)
            return r
    return None


def mark_sent(aid, receipt=""):
    rows = _load()
    for r in rows:
        if r.get("id") == aid:
            r["status"] = "sent"; r["sent_iso"] = datetime.now().isoformat(timespec="seconds"); r["receipt"] = receipt
    _save(rows)


def quiet_after_decline(r):
    return bool(r and r.get("status") == "declined" and time.time() - float(r.get("decided_at", 0)) < DECLINE_QUIET_DAYS * 86400)


def page(r, token):
    """The phone page: the whole draft, and the two buttons."""
    import html as _h
    if not r:
        return "<body style='font:16px/1.5 system-ui;padding:24px'><p>This link is not valid.</p></body>"
    if r.get("status") != "pending":
        return ("<body style='font:16px/1.5 system-ui;padding:24px'><p>Already decided: <b>%s</b>.</p></body>"
                % _h.escape(r.get("status", "")))
    return ("<body style='font:16px/1.5 system-ui;padding:24px;max-width:42em'>"
            "<p style='color:#888;font-size:13px'>A second email, before they have replied. Nothing is sent unless you approve.</p>"
            "<p><b>To:</b> %s &lt;%s&gt;<br><b>Subject:</b> %s</p>"
            "<pre style='white-space:pre-wrap;font:inherit;border:1px solid #ddd;border-radius:10px;padding:14px'>%s</pre>"
            "<p style='color:#888;font-size:13px'>Why: %s</p>"
            "<form method='post' action='/ea/decide' style='display:flex;gap:12px'>"
            "<input type='hidden' name='id' value='%s'><input type='hidden' name='t' value='%s'>"
            "<button name='d' value='approve' style='padding:12px 20px;font:inherit'>Approve and send</button>"
            "<button name='d' value='decline' style='padding:12px 20px;font:inherit'>Decline</button></form></body>"
            % (_h.escape(r.get("name", "")), _h.escape(r.get("to", "")), _h.escape(r.get("subject", "")),
               _h.escape(r.get("body", "")), _h.escape(r.get("why", "")), _h.escape(r.get("id", "")), _h.escape(token)))

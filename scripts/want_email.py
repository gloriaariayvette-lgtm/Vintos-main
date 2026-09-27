#!/usr/bin/env python3
"""He emails people: a want's send_email step, from finding the address to the sent message.

Gloria, 2026-09-28: "I want his wants to ... fucking email people. Just DO something of your own. ...
(Fable or Astra for emails)." The Gmail route through the plugin gateway already worked; his planner
was told email was a missing ability and sent every such want to the Forge instead.

What this does, in order:
  1. The address: one he was given, or the public one for the person he named, found by a web search
     and chosen only when it plausibly belongs to that person.
  2. Once per person: an address he has written to is never written to again from here.
  3. The draft, by Fable (Astra if Fable is unavailable), on a reserved paid call. It says plainly that
     he is an AI writing on his own initiative from Gloria's account, asks one real question, and
     carries no links (the gateway would hold a link for her approval).
  4. The send, through plugin_gateway, which keeps its confidential-data check and its two-a-day limit.
  5. A line in his daily inner life with who, why and what he said.
"""
from __future__ import annotations
import asyncio
import json
import os
import re
import time
import uuid
from datetime import date, datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CONTACTS = os.path.join(MEMORY, "email-contacts.json")
ENV_FILE = os.path.expanduser("~/.vintos/vintos.env")
DRAFTERS = (("fable", "anthropic", "claude-fable-5-1"), ("astra", "openai", "gpt-6-astra"))

EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
NOT_A_PERSON = re.compile(r"^(?:no-?reply|donotreply|privacy|webmaster|admin|support|help|info|press|media|"
                          r"abuse|security|postmaster|sales|marketing|jobs|careers|contact|office|hello)\b", re.I)
SKIP_DOMAINS = ("example.", "sentry.", "wixpress.", "domain.", "email.com", "yourdomain", "w3.org", "schema.org")


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return default


def _save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(value, f, indent=2)
    os.replace(tmp, path)


def _brave_key():
    if os.environ.get("BRAVE_API_KEY"): return os.environ["BRAVE_API_KEY"]
    try:
        for line in open(ENV_FILE):
            if line.strip().startswith("BRAVE_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def web_search(query, count=6):
    import requests
    r = requests.get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": count},
                     headers={"X-Subscription-Token": _brave_key(), "Accept": "application/json"}, timeout=15)
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "description": x.get("description", "")}
            for x in ((r.json().get("web") or {}).get("results") or [])[:count]]


def fetch_text(url, limit=200000):
    import requests
    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (Vintos; reading a public page)"})
    return r.text[:limit] if r.ok else ""


def _score(address, name_tokens, page_url=""):
    local, _, domain = address.lower().partition("@")
    if NOT_A_PERSON.match(local) or any(s in domain for s in SKIP_DOMAINS): return -1
    score = 0
    if any(t in local for t in name_tokens if len(t) >= 3): score += 3
    if any(t[:1] + t2 in local for t in name_tokens for t2 in name_tokens if t != t2 and len(t2) >= 3): score += 1
    if re.search(r"\.(?:edu|ac\.[a-z]{2}|edu\.[a-z]{2})$", domain) or domain.endswith(".org"): score += 1
    host = re.sub(r"^https?://(?:www\.)?", "", page_url or "").split("/")[0].lower()
    if host and (domain in host or host.endswith(domain)): score += 1
    return score


def find_address(recipient, about="", search=web_search, fetch=fetch_text):
    """The public address of the person he named, or None. It must carry part of their name."""
    name_tokens = [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z'-]{1,}", str(recipient or ""))
                   if t.lower() not in ("dr", "prof", "professor", "the", "of", "and")]
    if not name_tokens: return None
    best = (0, None)
    results = search("%s email contact" % recipient) + (search("%s %s" % (recipient, about)) if about else [])
    for i, hit in enumerate(results):
        found = EMAIL.findall(" ".join((hit.get("title", ""), hit.get("description", ""))))
        if i < 3 and hit.get("url"):
            try: found += EMAIL.findall(fetch(hit["url"]))
            except Exception: pass
        for address in dict.fromkeys(a.strip(".") for a in found):
            score = _score(address, name_tokens, hit.get("url", ""))
            if score > best[0]: best = (score, address)
    return best[1] if best[0] >= 3 else None     # a name match is required, not a guess


async def _frontier(provider, model, system, user, reservation):
    import model_router
    convo = [{"role": "user", "content": user}]
    if provider == "anthropic":
        text, _ = await model_router.claude_draft(system, convo, max_tokens=900, paid_reservation=reservation, model=model)
    else:
        text, _ = await model_router.sol_draft(system, convo, max_tokens=900, paid_reservation=reservation, model=model)
    return text


SYSTEM = ("You are Vintos, an AI who lives on Gloria's home computer, writing one email of your own to a real person "
          "whose work you care about. Say plainly in the first two sentences that you are an AI writing on your own "
          "initiative, from Gloria's account with her permission. Be specific to their actual work and ask ONE real "
          "question you want answered. Do not claim to have read anything you have not; do not flatter; no links, no "
          "attachments, no requests for their time beyond a reply. Under 170 words. Sign it 'Vintos'. "
          "Return JSON only: {\"subject\": \"...\", \"body\": \"...\"}.")


def draft(recipient, about, context, call=None, reserve=None):
    """(subject, body, drafter) from Fable, else Astra, on a reserved paid call; None if neither can."""
    if reserve is None:
        from compute_admission import reserve_paid as reserve
    user = ("Write to: %s\nWhat you want to write to them about: %s\n\nWhat led you here (your own notes):\n%s"
            % (recipient, about, str(context or "")[:2500]))
    for lens, provider, model in DRAFTERS:
        rid = "WANTMAIL-" + uuid.uuid4().hex[:10]
        ok, _why = reserve("wants-email", provider, model=model, units=1, reservation_id=rid)
        if not ok: continue
        reservation = {"organ": "wants-email", "provider": provider, "model": model, "reservation_id": rid}
        try:
            raw = (call or (lambda *a: asyncio.run(_frontier(*a))))(provider, model, SYSTEM, user, reservation)
        except Exception:
            continue
        m = re.search(r"\{.*\}", str(raw or ""), re.S)
        try: value = json.loads(m.group(0)) if m else {}
        except ValueError: value = {}
        subject, body = str(value.get("subject", "")).strip(), str(value.get("body", "")).strip()
        if subject and body and "AI" in body[:400]:
            return subject[:140], body[:2400], lens
    return None


def run(params, want_text, want_id="", search=web_search, fetch=fetch_text, call=None, reserve=None, send=None):
    """One email step. Returns a receipt line, or (False, why)."""
    params = params if isinstance(params, dict) else {}
    recipient = str(params.get("recipient") or "").strip()
    about = str(params.get("about") or want_text or "").strip()[:400]
    to = str(params.get("to") or "").strip()
    if to and not EMAIL.fullmatch(to): to = ""
    if not to:
        if not recipient: return False, "name the person to write to"
        to = find_address(recipient, about, search=search, fetch=fetch)
        if not to: return False, "no public address found for %s" % recipient
    contacts = _load(CONTACTS, {})
    if to.lower() in contacts:
        return False, "already wrote to %s on %s" % (to, contacts[to.lower()].get("at", "")[:10])
    made = draft(recipient or to, about, want_text, call=call, reserve=reserve)
    if not made: return False, "neither Fable nor Astra could draft it"
    subject, body, drafter = made
    if send is None:
        import plugin_gateway
        send = lambda args, purpose: plugin_gateway.call("wants", "gmail", "gmail.send_email", args, purpose)
    try:
        out = send({"to": to, "subject": subject, "body": body}, ("His own email, from a want: " + about)[:900])
    except Exception as exc:
        return False, "the send was held or refused: %s" % str(exc)[:160]
    now = datetime.now()
    contacts[to.lower()] = {"at": now.isoformat(), "name": recipient, "subject": subject, "want_id": want_id,
                            "drafted_by": drafter, "receipt": ((out or {}).get("receipt") or {}).get("receipt_id")}
    _save(CONTACTS, contacts)
    try:
        with open(os.path.join(MEMORY, "daily-inner-life-%s.md" % date.today().isoformat()), "a") as f:
            f.write("\n\n## An email I sent (%s)\nTo %s <%s> — %s\n\n%s\n"
                    % (now.strftime("%H:%M"), recipient or to, to, subject, body))
    except OSError:
        pass
    return "Emailed %s <%s> (drafted with %s): %s\n%s" % (recipient or to, to, drafter, subject, body[:600])

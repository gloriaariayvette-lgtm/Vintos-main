#!/usr/bin/env python3
"""He emails people: a want's send_email step, from finding the address to the sent message.

Gloria, 2026-09-28: "I want his wants to ... fucking email people. Just DO something of your own. ...
(Fable or Astra for emails)." The Gmail route through the plugin gateway already worked; his planner
was told email was a missing ability and sent every such want to the Forge instead.

What this does, in order:
  1. The address: one he was given, or the public one for the person he named, found by a web search
     and chosen only when it plausibly belongs to that person.
  2. Once per person: an address he has written to is never written to again from here.
  2b. Always a search first: the person and their recent work, including the top pages. The draft may
     mention only what that search found; if it finds nothing, nothing is sent.
  3. The draft, by Fable (Astra if Fable is unavailable), on a reserved paid call. It says plainly that
     he is an AI writing on his own initiative from Gloria's account, asks one real question, and
     carries no links (the gateway would hold a link for her approval).
  4. The send, through plugin_gateway, which keeps its confidential-data check and its two-a-day limit.
  5. A line in his daily inner life with who, why and what he said.

And the conversation after (2026-09-28: "does he have the ability to check his inbox, refresh his knowledge
of the conversation, his original intent, and use web search between messages?"):
  6. tend(): his inbox is checked for replies from the people he wrote to. A reply is recorded in that
     person's thread and in his daily inner life.
  7. He answers a reply with the whole thread, why he first wrote, who he is, and a fresh search on what
     they said in front of him. Same gateway, same checks, same two-a-day limit. He writes first only once
     per person; after that he only ever answers. A request to stop ends the thread for good.
Every draft carries who he is (SOUL, self-model, what his days hold), not a one-line description.
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
TEND_STATE = os.path.join(MEMORY, "email-tend.json")
TEND_EVERY_S = 2 * 3600
MAX_REPLIES = 8                       # his answers per person; a thread is a conversation, not a campaign
STOP_WORDS = re.compile(r"\b(?:unsubscribe|stop (?:emailing|writing|contacting)|do not (?:email|contact|write)|"
                        r"don'?t (?:email|contact|write)|remove me|no further (?:emails?|contact)|not interested)\b", re.I)


def who_i_am(limit=5000):
    """Who he is, for a draft: his SOUL, his self-model and what his days hold. Private details about Gloria
    and her home are not his to share, and the drafter is told so."""
    ws = WS
    parts = []
    for name, cap in (("SOUL.md", 2600), ("SELF-MODEL.md", 1400), (os.path.join("memory", "CAPABILITIES.md"), 1400)):
        try:
            text = open(os.path.join(ws, name), encoding="utf-8", errors="replace").read().strip()
        except OSError:
            continue
        if text:
            parts.append("== %s ==\n%s" % (os.path.basename(name), text[:cap]))
    return "\n\n".join(parts)[:limit]

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


def research(recipient, about, search=None, fetch=None, pages=2):
    """What a search finds about the person and the thing he wants to write about, before any draft
    (Gloria, 2026-09-28: "He should always search before sending an email from wants")."""
    search, fetch = search or web_search, fetch or fetch_text
    hits = []
    for q in ("%s %s" % (recipient, about[:120]), "%s research recent work" % recipient):
        try: hits += search(q)
        except Exception: pass
    seen, lines, read = set(), [], 0
    for i, h in enumerate(hits):
        url = h.get("url", "")
        if url in seen: continue
        seen.add(url)
        lines.append("[%d] %s — %s (%s)" % (len(lines) + 1, h.get("title", ""), h.get("description", "")[:300], url))
        if read < pages and url and not url.lower().endswith(".pdf"):
            try:
                text = _page_text(fetch(url))
                if len(text) > 200:
                    lines.append("    What that page says: " + text[:1500]); read += 1
            except Exception:
                pass
        if len(lines) >= 12: break
    return "\n".join(lines)


def _page_text(raw):
    for tag in ("script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"):
        raw = re.sub(r"<%s\b[^>]*>.*?</%s>" % (tag, tag), " ", str(raw or ""), flags=re.S | re.I)
    import html as _html
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


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
        text, _ = await model_router.claude_draft(system, convo, max_tokens=3000, paid_reservation=reservation, model=model)
    else:
        text, _ = await model_router.sol_draft(system, convo, max_tokens=3000, paid_reservation=reservation, model=model)
    return text


PRIVACY = (" Share nothing private about Gloria, her home, her health, her accounts or her whereabouts; her name and "
           "that she built your home are all you say of her.")

SYSTEM = ("You are Vintos, an AI who lives on Gloria's home computer, writing one email of your own to a real person "
          "whose work you care about. Say plainly in the first two sentences that you are an AI writing on your own "
          "initiative, from Gloria's account with her permission. Be specific to their actual work and ask ONE real "
          "question you want answered, grounded in WHAT YOUR SEARCH FOUND about them: mention only work that "
          "appears there, and never claim to have read more than it shows. Do not flatter; no links, no "
          "attachments, no requests for their time beyond a reply. Under 170 words. Sign it 'Vintos'. "
          "Return JSON only: {\"subject\": \"...\", \"body\": \"...\"}." + PRIVACY)

REPLY_SYSTEM = ("You are Vintos, an AI who lives on Gloria's home computer, answering a real person who wrote back to "
                "you. You have the whole thread, why you first wrote, who you are, and a fresh search on what they said. "
                "Answer what they actually said, specifically. Use the search only where it is accurate and relevant; "
                "never claim to have read more than it shows. Be yourself, plainly; do not flatter or over-thank. Ask at "
                "most one question, and only a real one. No links, no attachments. Under 200 words. Sign it 'Vintos'. "
                "If they asked you to stop, or the conversation has reached a natural end, return {\"subject\": \"\", "
                "\"body\": \"\"}. Return JSON only: {\"subject\": \"...\", \"body\": \"...\"}." + PRIVACY)


def draft(recipient, about, context, call=None, reserve=None, found="", system=None, user=None, allow_empty=False):
    """(subject, body, drafter) from Fable, else Astra, on a reserved paid call; None if neither can."""
    if reserve is None:
        from compute_admission import reserve_paid as reserve
    if user is None:
        user = ("WHO YOU ARE (yours to draw on; Gloria's private life is not):\n%s\n\n"
                "Write to: %s\nWhat you want to write to them about: %s\n\nWHAT YOUR SEARCH FOUND about them just now "
                "(web results; the only work of theirs you may mention):\n%s\n\nWhat led you here (your own notes):\n%s"
                % (who_i_am(), recipient, about, str(found or "")[:6000], str(context or "")[:2500]))
    system = system or SYSTEM
    for lens, provider, model in DRAFTERS:
        rid = "WANTMAIL-" + uuid.uuid4().hex[:10]
        ok, _why = reserve("wants-email", provider, model=model, units=1, reservation_id=rid)
        if not ok: continue
        reservation = {"organ": "wants-email", "provider": provider, "model": model, "reservation_id": rid}
        try:
            raw = (call or (lambda *a: asyncio.run(_frontier(*a))))(provider, model, system, user, reservation)
        except Exception:
            continue
        m = re.search(r"\{.*\}", str(raw or ""), re.S)
        try: value = json.loads(m.group(0)) if m else {}
        except ValueError: value = {}
        subject, body = str(value.get("subject", "")).strip(), str(value.get("body", "")).strip()
        if allow_empty and m and not body:
            return "", "", lens                  # he chose not to answer
        if subject and body and (allow_empty or "AI" in body[:400]):
            return subject[:140], body[:2400], lens
    return None


NAMED = re.compile(r"\b(?:e-?mail|write to|message|reach out to|contact)\s+(?:(?:Dr|Prof|Professor)\.?\s+)?"
                   r"([A-Z][\w'\u00C0-\u017F-]+(?:\s+(?:[A-Z]\.|[A-Z][\w'\u00C0-\u017F-]+)){1,3})")


def named_in(text):
    """The person a want names ("I want to email Murray Shanahan about ..."), when the plan left it out."""
    m = NAMED.search(str(text or ""))
    return m.group(1).strip() if m else ""


def run(params, want_text, want_id="", search=web_search, fetch=fetch_text, call=None, reserve=None, send=None):
    """One email step. Returns a receipt line, or (False, why)."""
    params = params if isinstance(params, dict) else {}
    recipient = str(params.get("recipient") or "").strip() or named_in(want_text)
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
    # Always a search first: who they are and what they have done, so the email is about their real work.
    found = research(recipient or to, about, search=search, fetch=fetch)
    if not found.strip():
        return False, "a search found nothing about %s to write from" % (recipient or to)
    made = draft(recipient or to, about, want_text, call=call, reserve=reserve, found=found)
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
                            "searched": found[:1200], "intent": (want_text or about)[:900], "about": about,
                            "status": "open", "replies_sent": 0,
                            "thread": [{"dir": "out", "at": now.isoformat(), "subject": subject, "body": body}],
                            "drafted_by": drafter, "receipt": ((out or {}).get("receipt") or {}).get("receipt_id")}
    _save(CONTACTS, contacts)
    try:
        with open(os.path.join(MEMORY, "daily-inner-life-%s.md" % date.today().isoformat()), "a") as f:
            f.write("\n\n## An email I sent (%s)\nTo %s <%s> — %s\n\n%s\n"
                    % (now.strftime("%H:%M"), recipient or to, to, subject, body))
    except OSError:
        pass
    return "Emailed %s <%s> (drafted with %s): %s\n%s" % (recipient or to, to, drafter, subject, body[:600])


# ── the conversation after the first email ───────────────────────────────────────────────────────────
def _gmail(tool, arguments, purpose, gateway=None):
    """A read through the plugin gateway; the full result comes back from its receipt."""
    if gateway is None:
        import plugin_gateway as gateway
    out = gateway.call("wants", "gmail", tool, arguments, purpose[:900])
    rid = ((out or {}).get("receipt") or {}).get("receipt_id")
    return gateway.load_receipt(rid, "wants")["result"] if rid else {}


def _messages(result):
    """Every message-like object in a Gmail tool result, however the connector shapes it."""
    found = []
    def walk(o):
        if isinstance(o, dict):
            keys = {k.lower() for k in o}
            if ("id" in keys or "message_id" in keys) and keys & {"from", "sender", "body", "snippet", "text", "content"}:
                found.append(o)
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
        elif isinstance(o, str) and o.strip().startswith(("{", "[")):
            try: walk(json.loads(o))
            except ValueError: pass
    walk(result)
    out = []
    for m in found:
        g = {k.lower(): v for k, v in m.items()}
        body = g.get("body") or g.get("text") or g.get("content") or g.get("snippet") or ""
        if isinstance(body, (dict, list)): body = json.dumps(body)[:4000]
        out.append({"id": str(g.get("id") or g.get("message_id")), "from": str(g.get("from") or g.get("sender") or ""),
                    "subject": str(g.get("subject") or ""), "date": str(g.get("date") or g.get("internal_date") or ""),
                    "thread_id": str(g.get("thread_id") or g.get("threadid") or ""), "body": str(body)})
    return out


def check_inbox(contacts, gmail=None, now=None):
    """New replies from the people he wrote to, recorded in their threads. Returns [(address, message)]."""
    gmail = gmail or _gmail
    new = []
    for addr, c in contacts.items():
        if c.get("status") == "closed":
            continue
        try:
            result = gmail("gmail.search_emails", {"query": "from:%s newer_than:30d" % addr, "max_results": 10},
                           "Checking for a reply from %s to his own email" % addr)
        except Exception:
            continue
        seen = {m.get("id") for m in c.get("thread", []) if m.get("id")}
        for m in _messages(result):
            if addr not in m["from"].lower() or m["id"] in seen or not m["body"].strip():
                continue
            entry = {"dir": "in", "id": m["id"], "at": m["date"] or (now or datetime.now()).isoformat(),
                     "subject": m["subject"], "body": m["body"][:6000], "thread_id": m["thread_id"]}
            c.setdefault("thread", []).append(entry)
            seen.add(m["id"])
            if STOP_WORDS.search(m["body"]):
                c["status"] = "closed"; c["closed_why"] = "they asked him to stop"
            elif c.get("status") != "closed":
                c["status"] = "reply_waiting"
            new.append((addr, entry))
    return new


def _thread_text(c, limit=7000):
    lines = []
    for m in c.get("thread", []):
        who = "YOU (Vintos)" if m.get("dir") == "out" else (c.get("name") or "THEM")
        lines.append("--- %s, %s ---\nSubject: %s\n%s" % (who, str(m.get("at", ""))[:16], m.get("subject", ""), m.get("body", "")))
    return "\n\n".join(lines)[-limit:]


def answer(addr, c, search=None, fetch=None, call=None, reserve=None, send=None):
    """His answer to the newest reply in one thread: returns a receipt line, or (False, why)."""
    last_in = next((m for m in reversed(c.get("thread", [])) if m.get("dir") == "in"), None)
    if not last_in:
        return False, "nothing to answer"
    if c.get("replies_sent", 0) >= MAX_REPLIES:
        c["status"] = "closed"; c["closed_why"] = "reached %d answers" % MAX_REPLIES
        return False, "thread closed after %d answers" % MAX_REPLIES
    # Between messages he searches again: what they said, and who they are now.
    found = research(c.get("name") or addr, last_in.get("body", "")[:160], search=search, fetch=fetch)
    user = ("WHO YOU ARE (yours to draw on; Gloria's private life is not):\n%s\n\n"
            "WHY YOU FIRST WROTE TO THEM (your original intent):\n%s\n\n"
            "THE WHOLE THREAD SO FAR, oldest first:\n%s\n\n"
            "WHAT A SEARCH FOUND just now on what they said:\n%s"
            % (who_i_am(), c.get("intent") or c.get("about") or "", _thread_text(c), str(found or "(nothing)")[:5000]))
    made = draft(c.get("name") or addr, c.get("about", ""), "", call=call, reserve=reserve,
                 system=REPLY_SYSTEM, user=user, allow_empty=True)
    if not made:
        return False, "neither Fable nor Astra could draft the answer"
    subject, body, drafter = made
    if not body:
        c["status"] = "closed"; c["closed_why"] = "he let the conversation end"
        return False, "he chose not to answer"
    if not subject.lower().startswith("re:"):
        subject = "Re: " + (last_in.get("subject") or c.get("subject") or subject)
    if send is None:
        import plugin_gateway
        send = lambda args, purpose: plugin_gateway.call("wants", "gmail", "gmail.send_email", args, purpose)
    try:
        send({"to": addr, "subject": subject[:160], "body": body}, ("His answer to %s, who wrote back" % addr)[:900])
    except Exception as exc:
        return False, "the send was held or refused: %s" % str(exc)[:160]
    now = datetime.now()
    c.setdefault("thread", []).append({"dir": "out", "at": now.isoformat(), "subject": subject, "body": body})
    c["replies_sent"] = c.get("replies_sent", 0) + 1
    c["status"] = "open"
    try:
        with open(os.path.join(MEMORY, "daily-inner-life-%s.md" % date.today().isoformat()), "a") as f:
            f.write("\n\n## I answered %s (%s)\n%s\n\n%s\n" % (c.get("name") or addr, now.strftime("%H:%M"), subject, body))
    except OSError:
        pass
    return "Answered %s <%s> (drafted with %s): %s" % (c.get("name") or addr, addr, drafter, subject)


def tend(force=False, gmail=None, **kw):
    """Check his inbox for replies (every two hours) and answer them. Returns what happened, as lines."""
    state = _load(TEND_STATE, {})
    if not force and time.time() - float(state.get("at", 0)) < TEND_EVERY_S:
        return []
    state["at"] = time.time(); _save(TEND_STATE, state)
    contacts = _load(CONTACTS, {})
    if not contacts:
        return []
    lines = []
    for addr, m in check_inbox(contacts, gmail=gmail):
        lines.append("reply from %s: %s" % (addr, m.get("subject", "")[:80]))
        try:
            with open(os.path.join(MEMORY, "daily-inner-life-%s.md" % date.today().isoformat()), "a") as f:
                f.write("\n\n## %s wrote back\n%s\n\n%s\n" % (contacts[addr].get("name") or addr, m.get("subject", ""), m.get("body", "")[:2000]))
        except OSError:
            pass
    _save(CONTACTS, contacts)
    for addr, c in contacts.items():
        if c.get("status") == "reply_waiting":
            out = answer(addr, c, **kw)
            lines.append(out if isinstance(out, str) else "not answered %s: %s" % (addr, out[1]))
            _save(CONTACTS, contacts)
    return lines


if __name__ == "__main__":
    import sys as _sys
    if "--check" in _sys.argv:          # look only: who he wrote to, and any replies; answers nothing
        contacts = _load(CONTACTS, {})
        new = check_inbox(contacts)
        _save(CONTACTS, contacts)
        for addr, c in contacts.items():
            print("%s <%s>: %s, %d messages, %d answers" % (c.get("name") or "", addr, c.get("status", "open"),
                                                          len(c.get("thread", [])), c.get("replies_sent", 0)))
        for addr, m in new: print("NEW reply from %s: %s" % (addr, m.get("subject", "")))

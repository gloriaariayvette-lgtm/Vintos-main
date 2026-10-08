#!/usr/bin/env python3
"""Opening a link and saying truthfully what came back (Gloria, 2026-10-08).

Grok Bot's 7 October letter said "The links are bare, with no redirects" and every one of its six links was a
Google redirect wrapper (https://www.google.com/url?q=https://www.rcsb.org/structure/8SGW&source=gmail&...).
Fetching a wrapper reads Google's notice page, not the source; and every failure came back as an empty string,
so "could not reach it", "refused", "nothing readable on it" and "never tried" all looked the same.

    unwrap(url)               the destination a recognised redirect wrapper points to (the url itself otherwise)
    links_in(text)            every link a text carries, plain and as HTML anchors: {original, url, wrapped}
    fetch(url)                one receipt, never a bare '' :
        kind      fetched | truncated | refused | http_failure | extraction_failure
        fetched   True only when the source's own content was read
        original_url, url (after unwrapping), final_url (after redirects), hops, http_status, bytes, text, why

Safety, at every hop: http(s) only, no user:password in the address, standard ports only, every address the
host resolves to must be public (no loopback, private, link-local, reserved, multicast), at most MAX_REDIRECTS
redirects, at most max_bytes read. Nothing sends credentials: the only header is a User-Agent, and no cookie,
Authorization or token header is ever passed to any host. lab_http.py's no-redirect rule for the Lab's API
calls is separate and unchanged; this is for reading public pages people send him.

A wrapper is resolved from its own query string, never by fetching it, so a wrapper that would fail (Google's
interstitial, an expired ust) says nothing about whether the source can be read.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from html import unescape
from urllib.parse import parse_qs, urljoin, urlsplit

MAX_REDIRECTS = 5
MAX_BYTES = 4 * 1024 * 1024
TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (Vintos; reading a public page)"
PORTS = {"http": (80, None), "https": (443, None)}
KINDS = ("fetched", "truncated", "refused", "http_failure", "extraction_failure")

# host pattern, path, the query parameters that carry the destination
WRAPPERS = (
    (re.compile(r"^(?:www\.)?google\.[a-z.]{2,6}$"), "/url", ("q", "url")),
    (re.compile(r"^[a-z0-9-]+\.safelinks\.protection\.outlook\.com$"), "/", ("url",)),
    (re.compile(r"^l\.facebook\.com$"), "/l.php", ("u",)),
)


def _wrapper_target(url):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    for pattern, path, keys in WRAPPERS:
        if pattern.match(host) and (parts.path or "/") == path:
            q = parse_qs(parts.query)
            for k in keys:
                if q.get(k):
                    return q[k][0]
            return ""
    return None


def unwrap(url, depth=3):
    """(destination, wrapped): the url a recognised wrapper points to, followed through up to `depth` wrappers.
    A wrapper with no usable destination gives ('', True)."""
    url = unescape(str(url or "").strip())
    wrapped = False
    for _ in range(depth):
        target = _wrapper_target(url)
        if target is None:
            break
        wrapped = True
        if not re.match(r"https?://", target, re.I):
            return "", True
        url = target
    return url, wrapped


_HREF = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*(["'])(.*?)\1""", re.I | re.S)
_BARE = re.compile(r"https?://[^\s<>\"']+")


def links_in(text):
    """Every http(s) link in a text, in order, once each: {original, url, wrapped}. HTML anchors give their
    href (the destination), not the words shown."""
    text = str(text or "")
    found = [unescape(m.group(2)) for m in _HREF.finditer(text)]
    found += [u.rstrip(".,);]>'\"") for u in _BARE.findall(_HREF.sub(" ", text))]
    out, seen = [], set()
    for original in found:
        original = unescape(original).strip()
        if not re.match(r"https?://", original, re.I) or original in seen:
            continue
        seen.add(original)
        url, wrapped = unwrap(original)
        out.append({"original": original, "url": url, "wrapped": wrapped})
    return out


def show_links(text):
    """The text with each recognised wrapper written as its destination, so a reader sees where a link goes."""
    def swap(m):
        raw = m.group(0)
        tail = re.search(r"[.,);\]>'\"]+$", raw)
        core = raw[:tail.start()] if tail else raw
        url, wrapped = unwrap(core)
        return ((url or core) + (tail.group(0) if tail else "")) if wrapped else raw
    return _BARE.sub(swap, str(text or ""))


# ── one hop's safety ───────────────────────────────────────────────────────────────────────────────
def _resolve(host):
    return [info[4][0] for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)]


def refusal(url, resolve=None):
    """Why this address may not be opened, or ''."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        return "not a valid address: %s" % exc
    scheme = (parts.scheme or "").lower()
    if scheme not in PORTS:
        return "only http and https links are opened (this is %s)" % (scheme or "no scheme")
    if parts.username or parts.password or "@" in parts.netloc:
        return "the address carries a user name or password"
    if port not in PORTS[scheme]:
        return "non-standard port %s" % port
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        return "no host"
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa")):
        return "a local host name (%s)" % host
    try:
        addresses = [host] if _is_ip(host) else (resolve or _resolve)(host)
    except (OSError, UnicodeError) as exc:
        return "could not resolve %s: %s" % (host, exc)
    if not addresses:
        return "could not resolve %s" % host
    for a in addresses:
        ip = ipaddress.ip_address(a.split("%")[0])
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            return "%s resolves to a non-public address (%s)" % (host, a)
    return ""


def _is_ip(host):
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


# ── the transport (tests replace it) ───────────────────────────────────────────────────────────────
def _transport(url, headers, timeout, max_bytes):
    """(status, response headers, body bytes, over_cap). Never follows a redirect itself."""
    import requests
    with requests.get(url, headers=headers, timeout=timeout, allow_redirects=False, stream=True) as r:
        body, over = b"", False
        if not r.is_redirect:
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > max_bytes:
                    body, over = body[:max_bytes], True
                    break
        return r.status_code, {k.lower(): v for k, v in r.headers.items()}, body, over


def _text_of(body, ctype, url, pdf=None):
    """(text, why-not). HTML made plain, plain text as is, a PDF through pdf() when one is given."""
    ctype = (ctype or "").lower()
    if "pdf" in ctype or (not ctype and url.lower().endswith(".pdf")) or body[:5] == b"%PDF-":
        if pdf is None:
            return "", "a PDF, and no PDF reader was given"
        return str(pdf(body) or "").strip(), ""
    if ctype and not any(t in ctype for t in ("html", "text", "xml", "json")):
        return "", "content type %s is not text" % ctype.split(";")[0]
    raw = body.decode("utf-8", "replace")
    if "html" in ctype or "<html" in raw[:2000].lower():
        for tag in ("script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"):
            raw = re.sub(r"<%s\b[^>]*>.*?</%s>" % (tag, tag), " ", raw, flags=re.S | re.I)
        raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", unescape(raw)).strip(), ""


def fetch(url, max_bytes=MAX_BYTES, max_redirects=MAX_REDIRECTS, timeout=TIMEOUT, transport=None, resolve=None,
          pdf=None, min_text=1, keep_raw=False):
    """One receipt for one link; see the module text. Never raises."""
    transport = transport or _transport
    original = str(url or "").strip()
    out = {"original_url": original, "url": "", "wrapped": False, "final_url": "", "hops": [], "http_status": None,
           "bytes": 0, "text": "", "fetched": False, "truncated": False, "kind": "", "why": ""}
    def done(kind, why=""):
        out["kind"], out["why"] = kind, why
        out["fetched"] = kind in ("fetched", "truncated")
        return out
    target, wrapped = unwrap(original)
    out["url"], out["wrapped"] = target, wrapped
    if not target:
        return done("refused", "a redirect wrapper with no http(s) destination in it" if wrapped else "no address")
    headers = {"User-Agent": USER_AGENT}
    here = target
    for hop in range(max_redirects + 1):
        why = refusal(here, resolve)
        if why:
            out["final_url"] = here
            return done("refused", why)
        out["hops"].append(here)
        try:
            status, rh, body, over = transport(here, dict(headers), timeout, max_bytes)
        except Exception as exc:
            out["final_url"] = here
            return done("http_failure", "%s: %s" % (type(exc).__name__, str(exc)[:200]))
        out["http_status"] = status
        if status in (301, 302, 303, 307, 308):
            nxt = rh.get("location")
            if not nxt:
                out["final_url"] = here
                return done("http_failure", "HTTP %s with no Location" % status)
            nxt, _ = unwrap(urljoin(here, nxt))
            here = nxt or urljoin(here, rh.get("location"))
            continue
        out["final_url"] = here
        if status != 200:
            return done("http_failure", "HTTP %s from %s" % (status, urlsplit(here).hostname))
        out["bytes"] = len(body)
        try:
            text, whynot = _text_of(body, rh.get("content-type"), here, pdf)
        except Exception as exc:
            text, whynot = "", "%s: %s" % (type(exc).__name__, str(exc)[:200])
        if len(text) < max(1, min_text):
            return done("extraction_failure", whynot or "no readable text (%d bytes came back)" % len(body))
        out["text"] = text
        if keep_raw:                               # the page as it came, for a caller that reads its markup
            out["raw"] = body.decode("utf-8", "replace")
        if over:
            out["truncated"] = True
            return done("truncated", "only the first %d bytes were read" % max_bytes)
        return done("fetched")
    out["final_url"] = here
    return done("refused", "more than %d redirects" % max_redirects)


def say(r, chars=None):
    """A receipt in words, for a prompt: where it went, and what was or was not read."""
    head = r.get("original_url", "")
    if r.get("wrapped"):
        head += "\n  (a redirect wrapper; its destination is %s)" % (r.get("url") or "missing")
    if r.get("final_url") and r.get("final_url") != (r.get("url") or r.get("original_url")):
        head += "\n  (redirected to %s)" % r["final_url"]
    if r.get("fetched"):
        text = r.get("text", "")
        cut = chars is not None and len(text) > chars
        note = (" [TRUNCATED: the page was larger than what was read]" if r.get("truncated") else "") + \
               (" [first %d of %d characters shown]" % (chars, len(text)) if cut else "")
        return "%s\n%s%s" % (head, text[:chars] if cut else text, note)
    return "%s\n  NOT READ (%s): %s" % (head, r.get("kind"), r.get("why"))

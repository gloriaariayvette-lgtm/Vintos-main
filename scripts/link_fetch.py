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
host resolves to must be public (no loopback, private, link-local, reserved, multicast). Each connection is pinned
to that validated snapshot; HTTP Host and HTTPS SNI/certificate verification keep the original hostname. Only
direct connections are used (environment proxies cannot perform unchecked destination resolution). At most MAX_REDIRECTS
redirects, at most max_bytes read. Nothing sends credentials: the only header is a User-Agent, and no cookie,
Authorization or token header is ever passed to any host. lab_http.py's no-redirect rule for the Lab's API
calls is separate and unchanged; this is for reading public pages people send him.

A wrapper is resolved from its own query string, never by fetching it, so a wrapper that would fail (Google's
interstitial, an expired ust) says nothing about whether the source can be read.

2026-10-16 (Gloria: "GrokBot has that link sending issue"): a link written with a closing bracket of its own
(Wikipedia's Her_(film)) keeps it; a link written cut short ("https://www.rcsb.org/structu\u2026", what a mail
client shows) is dropped when the whole one is in the text and refused with why when it is not; a page that sends a
browser on with <meta http-equiv="refresh"> (t.co) is followed as a redirect hop, with the same checks; and a post on
X is read through X's public embed, since x.com itself shows a reader without JavaScript only "JavaScript is not
available". Instagram, Facebook (lm.) and YouTube redirect wrappers are unwrapped like Google's.
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
    (re.compile(r"^l[m]?\.facebook\.com$"), "/l.php", ("u",)),
    (re.compile(r"^l\.instagram\.com$"), "/", ("u",)),           # Muse's Instagram links (2026-10-16)
    (re.compile(r"^(?:www\.)?youtube\.com$"), "/redirect", ("q",)),
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
_CUT = re.compile(r"(?:\u2026|\.\.\.)$")


def _trim(url):
    """A link as written in running text, without the punctuation after it. A closing bracket is kept when the link
    opened it (2026-10-16: https://en.wikipedia.org/wiki/Her_(film) lost its ")" and read as a missing page, and a
    film named in a letter could not be looked up)."""
    url = str(url or "")
    while url:
        last = url[-1]
        if last in ".,;:!?'\"]>":
            url = url[:-1]
        elif last == ")" and url.count("(") < url.count(")"):
            url = url[:-1]
        else:
            break
    return url


def cut_short(url):
    """True when the link was written cut short, ending in an ellipsis: what a mail client shows of a long link,
    not the link (a letter's plain part carries 'https://www.rcsb.org/structu\u2026' when only its HTML part has
    the address)."""
    return bool(_CUT.search(str(url or "")))


def links_in(text):
    """Every http(s) link in a text, in order, once each: {original, url, wrapped} (and cut: True for a link
    written cut short that no whole link in the text completes). HTML anchors give their href (the destination),
    not the words shown."""
    text = str(text or "")
    found = [unescape(m.group(2)) for m in _HREF.finditer(text)]
    found += [_trim(u) for u in _BARE.findall(_HREF.sub(" ", text))]
    found = [unescape(u).strip() for u in found]
    whole = [w for o in found if not cut_short(o) for w in (o, unwrap(o)[0]) if w]
    out, seen = [], set()
    for original in found:
        if not re.match(r"https?://", original, re.I) or original in seen:
            continue
        cut = cut_short(original)
        if cut:
            stem = _CUT.sub("", original)
            if any(w.startswith(stem) for w in whole):
                continue                     # the whole link is in the text too: the shown form adds nothing
        seen.add(original)
        url, wrapped = unwrap(original)
        out.append(dict({"original": original, "url": url, "wrapped": wrapped}, **({"cut": True} if cut else {})))
    return out


def show_links(text):
    """The text with each recognised wrapper written as its destination, so a reader sees where a link goes."""
    def swap(m):
        raw = m.group(0)
        core = _trim(raw)
        tail = raw[len(core):]
        url, wrapped = unwrap(core)
        return ((url or core) + tail) if wrapped else raw
    return _BARE.sub(swap, str(text or ""))


# ── one hop's safety ───────────────────────────────────────────────────────────────────────────────
DNS_RETRY_SECONDS = 2.0


def _sleep(seconds):
    import time
    time.sleep(seconds)


def _resolve(host):
    return [info[4][0] for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)]


def _destination(url, resolve=None):
    """(validated addresses, reason). One DNS snapshot for validation AND connection."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        return (), "not a valid address: %s" % exc
    scheme = (parts.scheme or "").lower()
    if scheme not in PORTS:
        return (), "only http and https links are opened (this is %s)" % (scheme or "no scheme")
    if parts.username or parts.password or "@" in parts.netloc:
        return (), "the address carries a user name or password"
    if port not in PORTS[scheme]:
        return (), "non-standard port %s" % port
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        return (), "no host"
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa")):
        return (), "a local host name (%s)" % host
    try:
        try:
            addresses = [host] if _is_ip(host) else (resolve or _resolve)(host)
        except socket.gaierror:
            # A lookup that failed once is often this house's resolver blinking, not the domain: one more try
            # after a pause, and if it fails again it is said as the lookup failing here, not the site gone.
            _sleep(DNS_RETRY_SECONDS)
            addresses = (resolve or _resolve)(host)
    except socket.gaierror as exc:
        return (), "DNS failed here (the lookup failed twice; the site may be fine): could not resolve %s: %s" % (host, exc)
    except (OSError, UnicodeError) as exc:
        return (), "could not resolve %s: %s" % (host, exc)
    if not addresses:
        return (), "could not resolve %s" % host
    for a in addresses:
        try:
            ip = ipaddress.ip_address(a)
        except ValueError:
            return (), "invalid address returned for %s" % host
        if "%" in a:
            return (), "a scoped address (%s)" % a
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            return (), "%s resolves to a non-public address (%s)" % (host, a)
    return tuple(dict.fromkeys(addresses)), ""


def refusal(url, resolve=None):
    """Why this address may not be opened, or ''."""
    return _destination(url, resolve)[1]


def _is_ip(host):
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


# ── the transport (tests replace it) ───────────────────────────────────────────────────────────────
def _pinned_socket(connection, addresses):
    """Connect numeric sockaddr values only; never resolve a hostname on retry.

    Called by urllib3's ordinary HTTP/HTTPS connection, so HTTP Host, TLS SNI,
    certificate chain verification and hostname matching still name the URL host.
    No process-global resolver changes or shared mutable connection pools.
    """
    from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
    last = None
    for address in addresses:
        sock = None
        try:
            ip = ipaddress.ip_address(address)
            family = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
            sock = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            sock.settimeout(connection.timeout)
            for option in connection.socket_options or ():
                sock.setsockopt(*option)
            sockaddr = (str(ip), connection.port, 0, 0) if ip.version == 6 else (str(ip), connection.port)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            last = exc
            if sock is not None:
                sock.close()
    if isinstance(last, socket.timeout):
        raise ConnectTimeoutError(connection, "Connection timed out (%s)" % last) from last
    raise NewConnectionError(connection, "Could not connect to validated addresses: %s" % last) from last


def _transport(url, headers, timeout, max_bytes, addresses=None, sink=None):
    """One direct, pinned hop. Ambient proxies/netrc/cookies never participate.

    A proxy may resolve the hostname remotely, defeating local DNS validation.
    Use a dedicated direct pool rather than requests' environment proxy settings.
    Requests' CA bundle overrides remain supported; verification is always required.
    With a sink (a binary file), a 200's body is streamed into it and never held in memory: the body returned is
    empty, and the sink holds at most max_bytes of it (26 October: Codex's archives run to hundreds of MB).
    """
    import os
    import ssl
    import requests
    from urllib3 import HTTPConnectionPool, HTTPSConnectionPool
    from urllib3.connection import HTTPConnection, HTTPSConnection
    from urllib3.util import Timeout, parse_url

    if addresses is None:
        addresses, why = _destination(url)
        if why:
            raise ValueError(why)
    parts = parse_url(url)  # urllib3's IDNA/hostname normalization, also used for TLS and Host
    base = HTTPSConnection if parts.scheme == "https" else HTTPConnection

    class PinnedConnection(base):
        def _new_conn(self):
            return _pinned_socket(self, addresses)

    options = {}
    if parts.scheme == "https":
        ca = (os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE")
              or requests.certs.where())
        options = dict(cert_reqs=ssl.CERT_REQUIRED)
        options["ca_cert_dir" if os.path.isdir(ca) else "ca_certs"] = ca
    pool_type = HTTPSConnectionPool if parts.scheme == "https" else HTTPConnectionPool
    pool = pool_type(parts.host, port=parts.port, timeout=Timeout(connect=timeout, read=timeout), **options)
    pool.ConnectionCls = PinnedConnection
    try:
        r = pool.urlopen("GET", parts.request_uri, headers=headers, redirect=False, retries=False,
                         preload_content=False)
        try:
            body, over = b"", False
            if sink is not None and r.status == 200:
                written = 0
                for chunk in r.stream(1 << 20, decode_content=True):
                    if written + len(chunk) > max_bytes:
                        sink.write(chunk[:max_bytes - written]); over = True
                        break
                    sink.write(chunk); written += len(chunk)
            elif r.status not in (301, 302, 303, 307, 308):
                for chunk in r.stream(65536, decode_content=True):
                    body += chunk
                    if len(body) > max_bytes:
                        body, over = body[:max_bytes], True
                        break
            return r.status, {k.lower(): v for k, v in r.headers.items()}, body, over
        finally:
            r.close()
            r.release_conn()
    finally:
        pool.close()


# ── structure files (PDB, mmCIF) ───────────────────────────────────────────────────────────────────
# 26 October: he told Grok Bot his email reader could not open a linked AlphaFold O43511 PDB file or the 7WL2 CIF
# file, so he went on pasted numbers instead of checking them. Those files come as chemical/x-pdb, chemical/x-mmcif,
# application/octet-stream and the like, which were refused as "not text"; and one served as text/plain had its
# columns run together into one line. A structure file is now read when its bytes ARE a textual PDB or mmCIF file
# (never because of a type or an extension alone), kept whole in the receipt (structure["content"]) apart from a
# bounded preview that keeps its columns and multiline values, with a few counts made here in code. A preview is not
# an analysis, and the words he gets say so.
STRUCTURE_TYPES = ("chemical/x-pdb", "chemical/x-mmcif", "chemical/x-cif", "application/mmcif", "application/pdb",
                   "application/x-pdb", "application/x-mmcif", "application/x-cif")
STRUCTURE_EXTS = (".pdb", ".ent", ".cif", ".mmcif", ".pdb1")
STRUCTURE_TEXT_CHARS = 6000      # the receipt's own text; callers with a smaller budget ask structure_view for less
NOT_ANALYSIS = "file read; this is a preview of the file, not an analysis of the structure"
PDB_RECORDS = frozenset((
    "HEADER", "OBSLTE", "TITLE", "SPLIT", "CAVEAT", "COMPND", "SOURCE", "KEYWDS", "EXPDTA", "NUMMDL", "MDLTYP",
    "AUTHOR", "REVDAT", "SPRSDE", "JRNL", "REMARK", "DBREF", "DBREF1", "DBREF2", "SEQADV", "SEQRES", "MODRES", "HET",
    "HETNAM", "HETSYN", "FORMUL", "HELIX", "SHEET", "SSBOND", "LINK", "CISPEP", "SITE", "CRYST1", "ORIGX1", "ORIGX2",
    "ORIGX3", "SCALE1", "SCALE2", "SCALE3", "MTRIX1", "MTRIX2", "MTRIX3", "MODEL", "ATOM", "ANISOU", "TER", "HETATM",
    "ENDMDL", "CONECT", "MASTER", "END", "SIGATM", "SIGUIJ", "TVECT", "PARENT"))
_CIF_TOKEN = re.compile(r"""'(.*?)'(?=\s|$)|"(.*?)"(?=\s|$)|(\S+)""")


def _structure_ext(url):
    path = urlsplit(str(url or "")).path.lower()
    for ext in STRUCTURE_EXTS:
        if path.endswith(ext) or path.endswith(ext + ".gz"):
            return ext + (".gz" if path.endswith(".gz") else "")
    return ""


def _structure_text(body, truncated=False):
    """(text, why-not): the bytes as text, when they are text a structure file can be (UTF-8, no NUL, no controls)."""
    head = body[:65536]
    if body[:2] == b"\x1f\x8b":
        return "", "gzip-compressed bytes (a .gz file is not decompressed here)"
    if b"\x00" in head:
        return "", "binary bytes, not a text file"
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        if truncated and exc.start >= len(body) - 4:          # cut mid-character by the byte cap
            text = body[:exc.start].decode("utf-8")
        else:
            return "", "bytes that are not UTF-8 text (first bad byte at %d)" % exc.start
    controls = sum(1 for c in text[:65536] if ord(c) < 32 and c not in "\t\n\r\f")
    if controls > 2:
        return "", "binary bytes, not a text file (%d control characters)" % controls
    if re.match(r"\s*<(?:!doctype|html|\?xml|head|body)\b", text[:2000], re.I) or "<html" in text[:2000].lower():
        return "", "an HTML or XML page, not a structure file"
    return text, ""


def _pdb_parse(text, truncated):
    lines = text.splitlines()
    unknown, bad, atoms_all = [], [], 0
    model, models, first = None, [], {"atoms": 0, "het": 0, "chains": [], "residues": set()}
    entry, title, last = "", [], len(lines) - 1
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        rec = line[:6].strip().upper()
        if rec not in PDB_RECORDS:
            if not (truncated and i == last):
                unknown.append(i + 1)
            continue
        if rec == "HEADER" and not entry:
            entry = line[62:66].strip()
        elif rec == "TITLE":
            title.append(line[10:80].strip())
        elif rec == "MODEL":
            model = line[10:14].strip() or str(len(models) + 1)
            models.append(model)
        elif rec in ("ATOM", "HETATM"):
            try:
                [float(line[a:b]) for a, b in ((30, 38), (38, 46), (46, 54))]
            except ValueError:
                if not (truncated and i == last):
                    bad.append(i + 1)
                continue
            atoms_all += 1
            if model is None or model == (models[0] if models else None):
                first["atoms"] += 1
                chain = line[21:22].strip() or "(blank)"
                if chain not in first["chains"]:
                    first["chains"].append(chain)
                if rec == "HETATM":
                    first["het"] += 1
                else:
                    first["residues"].add((chain, line[22:26].strip(), line[26:27].strip()))
    if not atoms_all:
        return None, "no ATOM or HETATM records with coordinates"
    if bad:
        return None, "ATOM/HETATM records whose coordinate columns are not numbers (line %s)" % bad[0]
    named = sum(1 for l in lines if l.strip())
    if len(unknown) > max(2, named // 20):
        return None, "%d lines that are not PDB records (first at line %d)" % (len(unknown), unknown[0])
    return {"format": "PDB", "entry": entry, "title": " ".join(t for t in title if t)[:200],
            "models": len(models) or 1, "chains": first["chains"], "residues": len(first["residues"]),
            "atoms": first["atoms"], "hetatm": first["het"], "atom_records": atoms_all}, ""


def _cif_values(line):
    """The values on one CIF line, quotes removed; an unquoted token starting with # begins a comment."""
    out = []
    for m in _CIF_TOKEN.finditer(line):
        if m.group(3) is not None and m.group(3).startswith("#"):
            break
        out.append(next(g for g in m.groups() if g is not None))
    return out


def _cif_parse(text, truncated):
    """A small mmCIF reader: data_ block, single items, loops, ;-delimited text fields. Enough to validate the file
    and count what atom_site lists; not a full CIF parser."""
    lines = text.splitlines()
    first = next((l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")), "")
    if not first.lower().startswith("data_") or len(first) < 6:
        return None, "it does not begin with a data_ block"
    items, loops, tokens = {}, [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(";"):
            field = [line[1:]]
            i += 1
            while i < len(lines) and not lines[i].startswith(";"):
                field.append(lines[i]); i += 1
            if i >= len(lines):
                if truncated:
                    break
                return None, "a ;-delimited text field that is never closed"
            tokens.append("\n".join(field).strip())
            i += 1
            continue
        tokens.extend(_cif_values(line))
        i += 1
    # tokens → items and loops
    j, n, blocks = 0, len(tokens), 0
    while j < n:
        t = tokens[j]
        low = t.lower()
        if low.startswith("data_"):
            blocks += 1; j += 1
        elif low == "loop_":
            j += 1
            cols = []
            while j < n and tokens[j].startswith("_"):
                cols.append(tokens[j].lower()); j += 1
            vals = []
            while j < n and not tokens[j].startswith("_") and tokens[j].lower() not in ("loop_",) \
                    and not tokens[j].lower().startswith("data_"):
                vals.append(tokens[j]); j += 1
            if not cols:
                return None, "a loop_ with no item names"
            if len(vals) % len(cols) and not truncated:
                return None, "a loop (%s) whose values do not fill its %d columns" % (cols[0].split(".")[0], len(cols))
            loops.append((cols, [vals[k:k + len(cols)] for k in range(0, len(vals) - len(vals) % len(cols), len(cols))]))
        elif t.startswith("_"):
            if j + 1 >= n:
                if truncated:
                    break
                return None, "the item %s has no value" % t[:60]
            items[low] = tokens[j + 1]; j += 2
        else:
            return None, "a value with no item name before it (%s)" % t[:40]
    if not items and not loops:
        return None, "a data_ block with no _items or loop_"
    out = {"format": "mmCIF", "entry": items.get("_entry.id", "") or first[5:].strip(),
           "title": re.sub(r"\s+", " ", items.get("_struct.title", "")).strip()[:200],
           "models": 0, "chains": [], "residues": 0, "atoms": 0, "hetatm": 0, "atom_records": 0}
    site = next(((c, rows) for c, rows in loops if c and c[0].startswith("_atom_site.")), None)
    if site:
        cols, rows = site
        col = lambda *names: next((cols.index(x) for x in names if x in cols), None)
        g, ch, seq, ins, mdl = (col("_atom_site.group_pdb"), col("_atom_site.auth_asym_id", "_atom_site.label_asym_id"),
                                col("_atom_site.auth_seq_id", "_atom_site.label_seq_id"), col("_atom_site.pdbx_pdb_ins_code"),
                                col("_atom_site.pdbx_pdb_model_num"))
        models, residues = [], set()
        for r in rows:
            m = r[mdl] if mdl is not None else "1"
            if m not in models:
                models.append(m)
            if m != models[0]:
                continue
            out["atoms"] += 1
            chain = r[ch] if ch is not None else "?"
            if chain not in out["chains"]:
                out["chains"].append(chain)
            if g is not None and r[g].upper() == "HETATM":
                out["hetatm"] += 1
            elif seq is not None:
                residues.add((chain, r[seq], r[ins] if ins is not None else ""))
        out.update(models=len(models), residues=len(residues), atom_records=len(rows))
    return out, ""


def read_structure(body, ctype="", url="", truncated=False):
    """(structure, why-not) for bytes that may be a PDB or mmCIF file. The structure keeps the whole text it read
    ("content") apart from the counts made from it; why-not says plainly what the bytes are instead."""
    text, why = _structure_text(body, truncated)
    if why:
        return None, why
    # the bytes decide the format, not the type or the extension
    head = next((l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")), "")
    if head.strip().lower().startswith("data_"):
        s, why = _cif_parse(text, truncated)
        name = "mmCIF"
    elif head[:6].strip().upper() in PDB_RECORDS:
        s, why = _pdb_parse(text, truncated)
        name = "PDB"
    else:
        return None, "it begins neither with a PDB record nor with an mmCIF data_ block"
    if why:
        return None, "not a valid %s file: %s" % (name, why)
    s.update(content=text, bytes=len(body), lines=len(text.splitlines()), truncated=bool(truncated))
    return s, ""


def _preview_lines(s, budget):
    """[(line number, line)] within budget characters, whole lines only: the head of the file and, when the first
    coordinates lie beyond it, the first coordinate lines (or atom_site loop) too."""
    lines = s["content"].splitlines()
    if s["format"] == "PDB":
        start = next((k for k, l in enumerate(lines) if l[:6].strip().upper() in ("ATOM", "HETATM")), 0)
    else:
        start = next((k for k, l in enumerate(lines) if l.strip().lower() == "loop_" and k + 1 < len(lines)
                      and lines[k + 1].strip().lower().startswith("_atom_site.")), 0)
    def take(frm, room):
        got, used = [], 0
        for k in range(frm, len(lines)):
            cost = len(lines[k]) + 1
            if used + cost > room:
                if not got and room > 20:                       # one line longer than the room: cut, said
                    got.append((k + 1, lines[k][:room - 12] + " [line cut]"))
                break
            got.append((k + 1, lines[k])); used += cost
        return got
    whole = take(0, budget)
    if not whole or start == 0 or whole[-1][0] > start:
        return whole                                            # the head already reaches the coordinates
    head = take(0, budget // 2)
    used = sum(len(x) + 1 for _, x in head)
    after = head[-1][0] if head else 0
    return head + [l for l in take(start, budget - used) if l[0] > after]


def structure_view(s, chars=STRUCTURE_TEXT_CHARS):
    """A structure receipt in words, at most about `chars` characters: what the file is, counts made in code, a
    verbatim preview with its columns and multiline values kept, and what of it was shown. Never an analysis."""
    count = ["%s model%s" % (s["models"], "" if s["models"] == 1 else "s")] if s.get("models") else []
    if s.get("atoms"):
        chains = s.get("chains") or []
        count += ["chain%s %s" % ("" if len(chains) == 1 else "s", ", ".join(chains[:20]) + (" ..." if len(chains) > 20 else "")),
                  "%d residues in ATOM records" % s["residues"], "%d atoms (%d HETATM)" % (s["atoms"], s["hetatm"])]
        if s["models"] and s["models"] > 1:
            count[-3:] = [c + " in model 1" for c in count[-3:]]
    named = "; ".join(x for x in ("entry %s" % s["entry"] if s.get("entry") else "",
                                  'title "%s"' % s["title"][:160] if s.get("title") else "") if x)
    head = "STRUCTURE FILE (%s format, %d bytes, %d lines): %s.\nCounted in code from the %s: %s%s" % (
        s["format"], s["bytes"], s["lines"], NOT_ANALYSIS, "part read" if s.get("truncated") else "file",
        "; ".join(count) or "no atom_site records", ("; " + named) if named else "")
    if s.get("truncated"):
        head += "\n[TRUNCATED: only the first %d bytes of the file were read; counts and lines cover that part only]" % s["bytes"]
    def render(shown):
        body, prev = [], 0
        for n, line in shown:
            if prev and n != prev + 1:
                body.append("[... lines %d-%d not shown ...]" % (prev + 1, n - 1))
            body.append(line); prev = n
        atoms_shown = sum(1 for _, l in shown if re.match(r"(ATOM|HETATM)(\s|\d|$)", l))
        foot = "[PREVIEW: %d of %d lines shown, %d of %d atom records shown; not the whole file, and not an analysis]" % (
            len(shown), s["lines"], atoms_shown, s.get("atom_records") or 0)
        return "%s\n--- preview ---\n%s\n%s" % (head, "\n".join(body), foot)
    shown = _preview_lines(s, max(0, chars - len(head) - 200))
    text = render(shown)
    while len(text) > chars and shown:                          # the cap holds, with the markers whole
        shown = shown[:-1]
        text = render(shown)
    return text


def _text_of(body, ctype, url, pdf=None):
    """(text, why-not). HTML made plain, plain text as is, a PDF through pdf() when one is given."""
    text, why, _s = _read_body(body, ctype, url, pdf)
    return text, why


def _read_body(body, ctype, url, pdf=None, truncated=False):
    """(text, why-not, structure-or-None)."""
    ctype = (ctype or "").lower()
    if "pdf" in ctype or (not ctype and url.lower().endswith(".pdf")) or body[:5] == b"%PDF-":
        if pdf is None:
            return "", "a PDF, and no PDF reader was given", None
        return str(pdf(body) or "").strip(), "", None
    base, ext = ctype.split(";")[0].strip(), _structure_ext(url)
    claimed = base in STRUCTURE_TYPES or base == "application/octet-stream" or bool(ext)
    if claimed or base in ("", "text/plain"):
        s, why = read_structure(body, base, url, truncated)
        if s:
            return structure_view(s), "", s
        if claimed:
            said = ("served as %s" % base) if base in STRUCTURE_TYPES or base == "application/octet-stream" else \
                   ("the link names a %s file" % ext)
            return "", "%s, but it is not a readable PDB or mmCIF file: %s" % (said, why), None
    text, why = _plain_text_of(body, ctype)
    return text, why, None


def _plain_text_of(body, ctype):
    if ctype and not any(t in ctype for t in ("html", "text", "xml", "json")):
        return "", "content type %s is not text" % ctype.split(";")[0]
    raw = body.decode("utf-8", "replace")
    if ("xml" in ctype or raw.lstrip()[:5] == "<?xml") and re.search(r"<article\b", raw[:20000]):
        # a JATS article (Europe PMC, PMC, a publisher's XML): read as the article, sections and captions kept,
        # not stripped into one run of words with its structure gone (2026-10-14)
        try:
            import europepmc
            return europepmc.render(europepmc.parse_jats(body)), ""
        except ValueError as exc:
            return "", "XML that is not a readable article: %s" % exc
        except ImportError:
            pass
    if "html" in ctype or "<html" in raw[:2000].lower():
        for tag in ("script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"):
            raw = re.sub(r"<%s\b[^>]*>.*?</%s>" % (tag, tag), " ", raw, flags=re.S | re.I)
        raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", unescape(raw)).strip(), ""


# ── pages that are not readable as pages ───────────────────────────────────────────────────────────
# Grok Bot reads X for him, and its letters link to posts on it. x.com answers every reader without JavaScript and a
# login with "JavaScript is not available", which was read as the page (2026-10-16). A single post is read through
# X's public embed (publish.twitter.com/oembed: the post's words and author, no login); any other x.com page is said
# to be unreadable rather than "fetched".
_X_HOSTS = re.compile(r"^(?:www\.|mobile\.)?(?:x|twitter)\.com$")
_X_POST = re.compile(r"^/(?:i/web|([A-Za-z0-9_]{1,15}))/status(?:es)?/(\d{5,25})")
X_OEMBED = "https://publish.twitter.com/oembed?omit_script=true&dnt=true&url="


def x_post(url):
    """For an x.com / twitter.com address: ("user", "id") of the post it names, () for any other X page; None when
    it is not an X address."""
    parts = urlsplit(str(url or ""))
    if not _X_HOSTS.match((parts.hostname or "").lower()):
        return None
    m = _X_POST.match(parts.path or "")
    return (m.group(1) or "i", m.group(2)) if m else ()


def _x_read(out, post, done, transport, resolve, timeout):
    if not post:
        out["final_url"] = out["url"]
        return done("extraction_failure", "an X page other than a single post: X shows it only with JavaScript and a "
                                          "login, so it cannot be read here; a link to one post can be")
    from urllib.parse import quote
    canonical = "https://twitter.com/%s/status/%s" % post
    r = fetch(X_OEMBED + quote(canonical, safe=""), max_bytes=200000, transport=transport, resolve=resolve,
              timeout=timeout, keep_raw=True, article_route=False, _x_inner=True)
    out.update(final_url=r.get("final_url") or "", hops=r.get("hops") or [], http_status=r.get("http_status"),
               via="x-oembed")
    if not r.get("fetched"):
        return done(r.get("kind") or "http_failure", "X's public embed of the post did not answer: %s" % r.get("why"))
    try:
        import json as _json
        data = _json.loads(r.get("raw") or r.get("text") or "")
        words = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", str(data.get("html") or "")))).strip()
    except (ValueError, AttributeError):
        return done("extraction_failure", "X's embed answered with something that is not the post")
    if not words:
        return done("extraction_failure", "X's embed of the post had no words in it")
    out["text"] = "A post on X by %s (%s), as X's public embed gives it: %s" % (
        data.get("author_name") or post[0], data.get("author_url") or "@" + post[0], words)
    out["bytes"] = len(out["text"])
    return done("fetched")


_REFRESH = re.compile(r"""<meta[^>]+http-equiv\s*=\s*["']?refresh["']?[^>]*content\s*=\s*["']\s*(\d+)\s*;\s*url\s*=\s*['"]?([^"'>\s]+)""",
                      re.I)


def _meta_refresh(body, ctype):
    """Where a small HTML page sends a reader at once (<meta http-equiv="refresh" content="0;URL=...">), or ''."""
    if len(body or b"") > 20000 or (ctype and "html" not in str(ctype).lower()):
        return ""
    m = _REFRESH.search(body.decode("utf-8", "replace"))
    return unescape(m.group(2)) if m and int(m.group(1)) <= 5 else ""


def fetch(url, max_bytes=MAX_BYTES, max_redirects=MAX_REDIRECTS, timeout=TIMEOUT, transport=None, resolve=None,
          pdf=None, min_text=1, keep_raw=False, article_route=True, _x_inner=False, sink=None):
    """One receipt for one link; see the module text. Never raises.

    A link that names a journal article (a PMC, PubMed, Europe PMC or doi.org address) is read first from Europe
    PMC's open-access full text, through this same door (europepmc.read): publisher pages answered with browser
    verification walls and unreadable PDFs (12-13 October, Gantsova et al.). When that read does not happen the link
    is fetched as before, and the receipt carries why Europe PMC could not give it ("europepmc").

    With a sink (a binary file opened for writing), the file a link names is streamed into it through the same hops,
    checks and byte cap, and nothing is read from it: "bytes" says how much was written, and a body cut at the cap
    is "truncated". No article route and no X route: a download is the file at that address, or nothing."""
    transport = transport or _transport
    if sink is not None:
        article_route, _x_inner = False, True
    if article_route:
        try:
            import os as _o, sys as _s
            _here = _o.path.dirname(_o.path.abspath(__file__))
            if _here not in _s.path: _s.path.insert(0, _here)
            import europepmc
            target0, _w = unwrap(str(url or "").strip())
            if target0 and europepmc.ids_in_url(target0):
                art = europepmc.read(target0, fetch=lambda u, **kw: fetch(
                    u, transport=transport, resolve=resolve, timeout=timeout, keep_raw=True, article_route=False, **kw))
                if art.get("fetched"):
                    return {"original_url": str(url or "").strip(), "url": target0, "wrapped": _w,
                            "final_url": art["source_url"], "hops": [art["source_url"]], "http_status": 200,
                            "bytes": len(art["text"]), "text": art["text"], "fetched": True, "truncated": False,
                            "kind": "fetched", "why": "", "via": "europepmc",
                            "article": {k: art.get(k) for k in ("pmcid", "pmid", "doi", "title", "sections", "figures")}}
                plain = fetch(url, max_bytes=max_bytes, max_redirects=max_redirects, timeout=timeout,
                              transport=transport, resolve=resolve, pdf=pdf, min_text=min_text, keep_raw=keep_raw,
                              article_route=False)
                plain["europepmc"] = {"kind": art.get("kind"), "why": art.get("why"), "source_url": art.get("source_url")}
                return plain
        except ImportError:
            pass
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
    if cut_short(target):
        return done("refused", "the link was written cut short (it ends in an ellipsis), so its address is not whole; "
                               "ask the sender for the full address")
    xpost = x_post(target)
    if xpost is not None and not _x_inner:
        return _x_read(out, xpost, done, transport, resolve, timeout)
    headers = {"User-Agent": USER_AGENT}
    here = target
    for hop in range(max_redirects + 1):
        if hop and not _x_inner and x_post(here) is not None:     # a shortener (t.co) that led to an X post
            out["url"] = here
            return _x_read(out, x_post(here), done, transport, resolve, timeout)
        addresses, why = _destination(here, resolve)
        if why:
            out["final_url"] = here
            return done("refused", why)
        out["hops"].append(here)
        try:
            if sink is not None:
                sink.seek(0); sink.truncate()          # only the last hop's body is ever kept
                kw = {"addresses": addresses} if transport is _transport else {}
                status, rh, body, over = transport(here, dict(headers), timeout, max_bytes, sink=sink, **kw)
            elif transport is _transport:
                status, rh, body, over = transport(here, dict(headers), timeout, max_bytes, addresses=addresses)
            else:
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
            if sink is not None:
                sink.seek(0); sink.truncate()
            return done("http_failure", "HTTP %s from %s" % (status, urlsplit(here).hostname))
        if sink is not None:
            sink.flush()
            out["bytes"] = sink.tell()
            out["truncated"] = bool(over)
            return done("truncated", "only the first %d bytes were written" % max_bytes) if over else done("fetched")
        out["bytes"] = len(body)
        if over:                                   # said even when what was read cannot be extracted
            out["truncated"] = True
        structure = None
        try:
            text, whynot, structure = _read_body(body, rh.get("content-type"), here, pdf, truncated=over)
        except Exception as exc:
            text, whynot = "", "%s: %s" % (type(exc).__name__, str(exc)[:200])
        if structure:
            out["structure"] = structure           # the file as read, whole; "text" is only its bounded preview
        refresh = _meta_refresh(body, rh.get("content-type"))
        if refresh:                                # t.co and other shorteners answer a browser with a refresh page
            nxt, _ = unwrap(urljoin(here, refresh))
            here = nxt or urljoin(here, refresh)
            continue
        if len(text) < max(1, min_text):
            return done("extraction_failure", whynot or "no readable text (%d bytes came back)" % len(body))
        out["text"] = text
        if keep_raw:                               # the page as it came, for a caller that reads its markup
            out["raw"] = body.decode("utf-8", "replace")
        if over:
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
    if r.get("via") == "europepmc":
        a = r.get("article") or {}
        head += "\n  (read from Europe PMC's open-access full text %s: %d sections, %d figure/table captions)" % (
            a.get("pmcid") or "", len(a.get("sections") or []), a.get("figures") or 0)
    elif r.get("europepmc"):
        head += "\n  (Europe PMC full text not read - %s: %s)" % (r["europepmc"].get("kind"), r["europepmc"].get("why"))
    if r.get("fetched") and r.get("structure"):
        return "%s\n%s" % (head, structure_view(r["structure"], chars or STRUCTURE_TEXT_CHARS))
    if r.get("fetched"):
        text = r.get("text", "")
        cut = chars is not None and len(text) > chars
        note = (" [TRUNCATED: the page was larger than what was read]" if r.get("truncated") else "") + \
               (" [first %d of %d characters shown]" % (chars, len(text)) if cut else "")
        return "%s\n%s%s" % (head, text[:chars] if cut else text, note)
    return "%s\n  NOT READ (%s): %s" % (head, r.get("kind"), r.get("why"))

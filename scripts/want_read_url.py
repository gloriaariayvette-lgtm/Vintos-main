#!/usr/bin/env python3
"""want_read_url.py - a want's step that opens one link and reads its whole text (Gloria, 15 November 2026: he must be
able to open links from his wants' steps and his planner).

His wants to read a paper in full could only be planned as web searches: the planner had no hand that opens an
address. A search brought back abstracts and snippets, the want's judge said the paper itself was not read, the want
was reworded and tried again, and in the end it was dismissed (dismissed-wants.json). The house already had the door
that opens a link safely - link_fetch, which his letters use - and this step goes through it:

    link_fetch.fetch(url, pdf=scholar.pdf_text)
        http(s) only, no user:password, standard ports, every address the host resolves to public (no loopback,
        private, link-local, reserved), each hop checked, at most MAX_REDIRECTS redirects and MAX_BYTES read, no
        cookie or credential sent. A journal article's address is read from Europe PMC's open-access full text first.
        A PDF is read with the Scholar's reader; when there is no reader, it is NOT READABLE, said so.

    run(params, step_text, want_id, original="", want=None, mem=None, fetch=None, now=None)
        which link: the step's own params {"url": ...}; else the first link in the step's goal; else in the want
        itself; else in what his earlier steps of this want found (newest first); else anywhere in the step's text.
        READ IN FULL  the whole text was read: kept in memory/want-reads/, the step's findings name that file
                      ("receipt: <path>", which the router keeps as the step's evidence) and begin with an excerpt
        READ IN PART  only the first bytes were read (the page is larger than the cap): kept and said so; never
                      counted as the full text
        NOT READABLE  refused, an HTTP failure, or no text in it (a PDF without a reader, an image): the step fails
                      (False) and the reason is logged, kept in memory/want-reads.jsonl and in his record of acts
        Every fetch writes one action-provenance row (action read_url): what was opened, for which want, by which
        rule, and what came of it. Nothing is ever fetched without an address; that is said too.

    full_text_read(want)  the addresses a want's read_url steps READ IN FULL, with their kept files: the completion
                          check counts these as the full text read.

Store: memory/want-reads/<want>-<url hash>.txt (the text read), memory/want-reads.jsonl (one row per attempt).
"""
import hashlib, json, os, re, sys, time
from datetime import datetime

FULL = "READ IN FULL"
PART = "READ IN PART"
NOT = "NOT READABLE"
READS_DIR = "want-reads"
LEDGER = "want-reads.jsonl"
KEEP_CHARS = 1500000        # the text kept per read; MAX_BYTES (4 MB) bounds what is fetched in the first place
EXCERPT = 700               # the start of the text, in the step's findings
LEDGER_KEEP = 1000


def _here():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    return here


def _link_fetch():
    _here()
    import link_fetch
    return link_fetch


def _pdf_reader():
    """scholar.pdf_text (pdftotext, then pypdf), the reader his letters use; None when it cannot be loaded."""
    try:
        _here()
        import scholar
        return scholar.pdf_text
    except Exception:
        return None


def _mem(mem=None):
    if mem:
        return mem
    ws = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
    return os.path.join(ws, "memory")


def want_row(want_id, mem=None):
    """The want's own row from current-wants.json, by id; None when it is not there."""
    if not want_id:
        return None
    try:
        d = json.load(open(os.path.join(_mem(mem), "current-wants.json"), encoding="utf-8"))
    except Exception:
        return None
    for w in (d.get("wants") if isinstance(d, dict) else d) or []:
        if isinstance(w, dict) and str(w.get("id")) == str(want_id):
            return w
    return None


def _goal(step_text):
    for line in str(step_text or "").split("\n"):
        if line.startswith("Current step goal:"):
            return line[len("Current step goal:"):].strip()
    return ""


def _first_link(text):
    for l in _link_fetch().links_in(str(text or "")):
        u = l.get("url") or l.get("original")
        if u:
            return l.get("original") or u
    return ""


def pick_url(params, step_text, original="", want=None):
    """(url, where) for this step: the address it is to open and where it was found; ('', why) when there is none."""
    p = params if isinstance(params, dict) else {}
    u = str(p.get("url") or "").strip()
    if u:
        return u, "the step's own address"
    goal = _goal(step_text)
    for text, where in ((goal, "the first link in the step's goal"), (original, "the first link in the want itself")):
        u = _first_link(text)
        if u:
            return u, where
    for h in reversed((want or {}).get("step_history") or []):
        if isinstance(h, dict):
            u = _first_link(h.get("findings"))
            if u:
                return u, "the first link step %s (%s) found" % (int(h.get("step", -1)) + 1, h.get("capability"))
    u = _first_link(step_text)
    if u:
        return u, "the first link in the step's text"
    return "", "no address: the step names no link, nor does the want or anything its earlier steps found"


def _safe(s, n=40):
    return re.sub(r"[^A-Za-z0-9_-]", "", str(s or ""))[:n] or "no-want"


def _ledger(row, mem):
    try:
        path = os.path.join(mem, LEDGER)
        os.makedirs(mem, exist_ok=True)
        rows = []
        try:
            rows = open(path, encoding="utf-8").read().splitlines()
        except OSError:
            pass
        rows = (rows + [json.dumps(row, ensure_ascii=False)])[-LEDGER_KEEP:]
        tmp = path + ".tmp.%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")
        os.replace(tmp, path)
    except Exception as e:
        print("[read_url] ledger not written: %s" % str(e)[:120], flush=True)


def _provenance(label, url, want_id, goal, where, r, kept, mem, now):
    try:
        _here()
        import action_provenance
        action_provenance.record(
            "read_url", "%s: %s" % (label, url), "wants-router step read_url (want_read_url)",
            trigger=("a step of his want: %s" % goal[:200]) if goal else "a step of his want",
            want_id=want_id or None,
            rule="opened %s, through link_fetch: http(s) only, public hosts only, standard ports, at most %d bytes "
                 "and %d redirects, no credentials sent" % (where, _link_fetch().MAX_BYTES, _link_fetch().MAX_REDIRECTS),
            refs={"kind": r.get("kind"), "final_url": r.get("final_url"), "chars": len(str(r.get("text") or "")),
                  "via": r.get("via"), "file": os.path.basename(kept) if kept else None},
            mem=mem, now=now)
    except Exception as e:
        print("[read_url] provenance not written: %s" % str(e)[:120], flush=True)


def run(params, step_text, want_id="", original="", want=None, mem=None, fetch=None, now=None):
    """Open the step's link and read it. Findings text (READ IN FULL / READ IN PART, with 'receipt: <file>') when
    something was read; False when nothing could be (NOT READABLE, or no address). Never raises."""
    mem = _mem(mem)
    now = time.time() if now is None else float(now)
    url, where = pick_url(params, step_text, original, want)
    goal = _goal(step_text) or str(original or step_text or "")[:200]
    base = {"at": datetime.fromtimestamp(now).isoformat(timespec="seconds"), "want_id": want_id or None}
    if not url:
        _ledger(dict(base, url="", result=NOT, kind="no_address", why=where), mem)
        print("[read_url] %s - %s" % (NOT, where), flush=True)
        return False
    if fetch is None:
        lf, reader = _link_fetch(), _pdf_reader()
        fetch = lambda u: lf.fetch(u, pdf=reader)
    try:
        r = fetch(url) or {}
    except Exception as e:      # link_fetch never raises; a stand-in might
        r = {"fetched": False, "kind": "error", "why": "%s: %s" % (type(e).__name__, str(e)[:160])}
    text = str(r.get("text") or "")
    if r.get("structure"):
        text = str(_link_fetch().structure_view(r["structure"]))
    read = bool(r.get("fetched")) and bool(text.strip())
    full = read and not (r.get("truncated") or r.get("kind") == "truncated")
    label = FULL if full else (PART if read else NOT)
    kept = ""
    if read:
        d = os.path.join(mem, READS_DIR)
        os.makedirs(d, exist_ok=True)
        kept = os.path.join(d, "%s-%s.txt" % (_safe(want_id), hashlib.sha256(url.encode()).hexdigest()[:12]))
        head = ("URL: %s\nFINAL URL: %s\nREAD: %s\nRESULT: %s\nVIA: %s\nCHARACTERS READ: %d\nKEPT: %d\n\n"
                % (url, r.get("final_url") or url, base["at"], label, r.get("via") or "the page itself",
                   len(text), min(len(text), KEEP_CHARS)))
        tmp = kept + ".tmp.%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(head + text[:KEEP_CHARS])
        os.replace(tmp, kept)
    _ledger(dict(base, url=url[:500], final_url=str(r.get("final_url") or "")[:500], result=label,
                 kind=r.get("kind"), why=str(r.get("why") or "")[:240], chars=len(text), file=kept or None,
                 where=where), mem)
    _provenance(label, url[:200], want_id, goal, where, r, kept, mem, now)
    if not read:
        why = str(r.get("why") or "nothing readable came back")[:240]
        print("[read_url] %s (%s): %s - %s" % (NOT, r.get("kind") or "not read", url[:160], why), flush=True)
        return False
    what = "the whole text" if full else ("only the start: %s" % (r.get("why") or "the page is larger than the cap"))
    return ("%s: %s - %d characters (%s; %s). receipt: %s\n%s" % (
        label, url[:300], len(text), r.get("via") and "Europe PMC's open-access full text" or "the page itself",
        what, kept, text[:EXCERPT]))


def full_text_read(want):
    """[{url, file}] for each read_url step of this want that READ IN FULL and whose kept file is there."""
    out = []
    for h in (want or {}).get("step_history") or []:
        if not isinstance(h, dict) or h.get("capability") != "read_url":
            continue
        found = str(h.get("findings") or "")
        if not found.startswith(FULL + ":"):
            continue
        m = re.search(r"receipt:\s*(\S+)", found)
        if m and os.path.exists(m.group(1)):
            out.append({"url": found[len(FULL) + 1:].split(" - ", 1)[0].strip(), "file": m.group(1)})
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(run({"url": sys.argv[1]}, "", "manual") or "%s (see the log line above)" % NOT)

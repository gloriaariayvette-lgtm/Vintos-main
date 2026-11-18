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

    full_text_read(want)  the addresses a want's read_url steps READ IN FULL, with their kept files (the completion
                          judge is shown each read_url step's own READ IN FULL / READ IN PART line).

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
        if l.get("cut"):        # written cut short: link_fetch refuses it; a whole link later in the text is used
            continue
        u = l.get("url") or l.get("original")
        if u:
            return l.get("original") or u
    return ""


def _links(text):
    """Every whole link in a text, in order (a link written cut short is skipped, as in _first_link)."""
    out = []
    for l in _link_fetch().links_in(str(text or "")):
        if l.get("cut"):
            continue
        u = l.get("original") or l.get("url")
        if u and u not in out:
            out.append(u)
    return out


# ---- entity grounding (18 November) ------------------------------------------------------------------------------
# A want to open PDB 9XPK (a taste receptor) read, at its read_url step, the first link in the step's text: the step
# text carries what earlier steps found and the mail that came in on other threads, and the first link there was an
# AlphaFold model of a potato protein from another conversation. Its read_memory step had brought back a journal page
# about an unrelated transporter. The Lab had the same fault with structures (lab_entity.py, the pendrin model); this
# is the wants' version. When the want names its entity - a PDB entry, a UniProt accession, an AlphaFold model, a PMC
# article or a DOI - in its own words or this step's own goal or params:
#   - an address that names another entity of those kinds is refused, with the reason;
#   - an address found anywhere but the want's own words, goal or params (earlier findings, mail, other threads) is
#     used only when it names the want's own identifier;
#   - with no such address, the canonical address of the exact identifier is opened (a PDB entry's mmCIF file);
#   - a structure file that comes back naming none of the want's identifiers is refused as off target.
# A want that names no identifier is read exactly as before.
try:
    _here()
    from lab_entity import _ACCESSION as _UNIPROT     # the Lab's UniProt accession pattern: one definition
except Exception:                                    # lab_entity needs lab_instruments; the same pattern
    _UNIPROT = re.compile(r"(?<![A-Z0-9])(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})"
                          r"(?![A-Z0-9])")
_PDB_SAID = re.compile(r"\b(?:PDB|RCSB)(?:[\s_-]*(?:ID|entry|code|structure))?[\s:#_-]*([1-9][A-Za-z0-9]{3})(?![A-Za-z0-9])",
                       re.I)
_PDB_BARE = re.compile(r"(?<![A-Za-z0-9-])([1-9][A-Z0-9]{3})(?![A-Za-z0-9])")
_STRUCTURAL = re.compile(r"\b(?:structure|structural|protein|receptor|residue|active[- ]site|binding|cryo-?em|"
                         r"crystal|coordinates|chain|ligand|domain|complex)", re.I)
_AF = re.compile(r"\bAF-([A-Z0-9]{6,10})-F\d+", re.I)
_PMC = re.compile(r"\bPMC\d{5,9}\b", re.I)
_DOI = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>)\]]+")
_URL_PDB = re.compile(r"rcsb\.org/(?:structure|pdb|3d-view)/([1-9][A-Za-z0-9]{3})\b|"
                      r"files\.rcsb\.org/(?:download|view|header)/([1-9][A-Za-z0-9]{3})\.|"
                      r"ebi\.ac\.uk/pdbe/entry/pdb/([1-9][A-Za-z0-9]{3})\b", re.I)
_URL_ACC = re.compile(r"(?:uniprot\.org/(?:uniprotkb|uniprot)/|alphafold\.ebi\.ac\.uk/(?:entry|api/prediction)/)"
                      r"([A-Za-z0-9]{6,10})\b", re.I)
KINDS = ("pdb", "uniprot", "pmc", "doi")


def declared_ids(text):
    """{'pdb', 'uniprot', 'pmc', 'doi': set} named in a text (DOIs lower case, the rest upper case). A bare
    four-character PDB code counts only with two letters in it and structural words in the text, so '120V' or '2026'
    is never taken for a structure; 'PDB 1ABC' or an RCSB address always counts."""
    t = str(text or "")
    out = {k: set() for k in KINDS}
    out["pdb"] |= {m.upper() for m in _PDB_SAID.findall(t)}
    if _STRUCTURAL.search(t):
        out["pdb"] |= {m for m in _PDB_BARE.findall(t) if sum(c.isalpha() for c in m) >= 2}
    for m in _URL_PDB.findall(t):
        out["pdb"] |= {x.upper() for x in m if x}
    out["uniprot"] |= {m.upper() for m in _AF.findall(t)}
    out["uniprot"] |= {m.upper() for m in _URL_ACC.findall(t)}
    out["uniprot"] |= {m for m in _UNIPROT.findall(t) if m not in out["pdb"]}
    out["pmc"] |= {m.upper() for m in _PMC.findall(t)}
    out["doi"] |= {m.lower().rstrip(".,;") for m in _DOI.findall(t)}
    return out


def _flat(ids):
    return {x for v in (ids or {}).values() for x in v}


def want_ids(original="", want=None, goal="", params=None):
    """The identifiers the want declares: in its own words, this step's goal and this step's params - never in what
    earlier steps found or the mail beside them, which carry other threads."""
    p = params if isinstance(params, dict) else {}
    # the step's address is what is being checked, never a declaration of what the want is about
    vals = " ".join(str(v) for k, v in p.items() if isinstance(v, (str, int, float)) and k not in ("url", "link", "href"))
    return declared_ids("\n".join(str(x or "") for x in (original, (want or {}).get("want"), goal, vals)))


def on_target(url, ids):
    """(verdict, why): 'own' when the address names one of the want's identifiers, 'other' when it names another
    entity of those kinds (why says which), 'neutral' when it names none."""
    mine = {x.lower() for x in _flat(ids)}
    u = str(url or "")
    if any(x in u.lower() for x in mine):
        return "own", ""
    # another entity of the same family as the want's: a molecule (PDB, UniProt/AlphaFold) or an article (PMC, DOI). A
    # paper's DOI is not "another structure" for a want about a structure.
    fam = {"pdb": "mol", "uniprot": "mol", "pmc": "art", "doi": "art"}
    want_fams = {fam[k] for k, v in (ids or {}).items() if v}
    found = declared_ids(u)
    named = sorted(x for k, v in found.items() if fam.get(k) in want_fams for x in v if x.lower() not in mine)
    if named:
        return "other", "it names %s, not this want's %s" % (", ".join(named[:3]), ", ".join(sorted(_flat(ids))[:4]))
    return "neutral", ""


def canonical_url(ids):
    """(url, what) for the want's exact identifier, the most specific kind first; ('', '') when there is none."""
    for kind, fmt, what in (("pdb", "https://files.rcsb.org/download/%s.cif", "PDB entry %s (its mmCIF file)"),
                            ("uniprot", "https://rest.uniprot.org/uniprotkb/%s.txt", "UniProt entry %s"),
                            ("pmc", "https://pmc.ncbi.nlm.nih.gov/articles/%s/", "article %s"),
                            ("doi", "https://doi.org/%s", "DOI %s")):
        for x in sorted((ids or {}).get(kind) or []):
            return fmt % x, what % x
    return "", ""


def _pick_grounded(p, step_text, original, want, ids):
    refused = []

    def take(u, where, own_words):
        verdict, why = on_target(u, ids)
        if verdict == "own" or (verdict == "neutral" and own_words):
            return True
        refused.append("%s (%s): %s" % (u[:120], where,
                                        why or "found outside the want's own words and it does not name %s"
                                        % ", ".join(sorted(_flat(ids))[:4])))
        return False

    u = str(p.get("url") or "").strip()
    if u.lower().startswith(("http://", "https://")) and take(u, "the step's own address", True):
        return u, "the step's own address"
    goal = _goal(step_text)
    for text, where in ((goal, "the step's goal"), (original or (want or {}).get("want"), "the want itself")):
        for u in _links(text):
            if take(u, "a link in " + where, True):
                return u, "a link in %s" % where
    for h in reversed((want or {}).get("step_history") or []):
        if isinstance(h, dict):
            for u in _links(h.get("findings")):
                where = "a link step %s (%s) found" % (h.get("step") + 1 if isinstance(h.get("step"), int) else "?",
                                                       h.get("capability"))
                if take(u, where, False):
                    return u, where
    for u in _links(step_text):
        if take(u, "a link in the step's text", False):
            return u, "a link in the step's text"
    u, what = canonical_url(ids)
    if u:
        return u, "the canonical address of the want's own identifier, %s%s" % (
            what, ("; refused: " + "; ".join(refused[:3])) if refused else "")
    return "", "no address for %s%s" % (", ".join(sorted(_flat(ids))), ("; refused: " + "; ".join(refused[:3])) if refused else "")


def off_target_structure(r, text, ids):
    """Why a structure file that came back is not the want's entity (it names none of its identifiers in its first
    lines while naming another), or '' when it is, or when it is not a structure file."""
    if not r.get("structure") or not _flat(ids):
        return ""
    head = str(text or "")[:4000]
    if any(x.lower() in head.lower() for x in _flat(ids)):
        return ""
    other = sorted(_flat(declared_ids("PDB " + head[:400] + "\n" + head)) - _flat(ids))
    return ("the structure file names %s, not this want's %s" % (", ".join(other[:3]) or "none of them",
                                                                   ", ".join(sorted(_flat(ids))[:4])))


def ground_memory(content, ids, chars=2000):
    """(excerpt, why) for a read_memory step of a want that names its entity: the part of what was read that
    mentions one of its identifiers (a window around the first mention), or ('', why) when none of it does. With no
    identifiers, (content[:chars], '')."""
    c = str(content or "")
    flat = sorted(_flat(ids))
    if not flat:
        return c[:chars], ""
    low = c.lower()
    hits = [low.find(x.lower()) for x in flat if x.lower() in low]
    if not hits:
        return "", "nothing read mentions %s" % ", ".join(flat[:4])
    at = min(hits)
    start = max(0, at - chars // 3)
    return c[start:start + chars], ""


def pick_url(params, step_text, original="", want=None):
    """(url, where) for this step: the address it is to open and where it was found; ('', why) when there is none.
    A want that names its entity is grounded to it (above); any other is read as before."""
    p = params if isinstance(params, dict) else {}
    ids = want_ids(original, want, _goal(step_text), p)
    if _flat(ids):
        return _pick_grounded(p, step_text, original, want, ids)
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
                return u, "the first link step %s (%s) found" % (h.get("step") + 1 if isinstance(h.get("step"), int)
                                                                 else "?", h.get("capability"))
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
    structure = bool(r.get("structure"))
    if structure:   # a PDB/mmCIF file: what is kept is link_fetch's bounded preview of it, not the whole file
        try:
            text = str(_link_fetch().structure_view(r["structure"]))
        except Exception:
            pass
        r = dict(r, why="a structure file: only link_fetch's preview of it is kept, not the whole file")
    _off = off_target_structure(r, text, want_ids(original, want, _goal(step_text), params))
    if _off:        # another entity's structure: refused, never kept as this want's evidence
        r, structure = dict(r, fetched=False, kind="off_target", why=_off), False
    read = bool(r.get("fetched")) and bool(text.strip())
    full = read and not structure and not (r.get("truncated") or r.get("kind") == "truncated")
    label = FULL if full else (PART if read else NOT)
    kept = ""
    if read:
        try:
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
        except Exception as e:  # read, but not kept: no evidence to name, so the step is not done; said so
            kept, read, full, label = "", False, False, NOT
            r = dict(r, kind="not_kept", why="read but could not be kept: %s: %s" % (type(e).__name__, str(e)[:120]))
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
    """[{url, file}] for each read_url step of this want that READ IN FULL and whose kept file is there. A check for
    tools and tests; the completion judge itself is shown each read_url step's own READ IN FULL / READ IN PART line."""
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

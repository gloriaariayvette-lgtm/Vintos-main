#!/usr/bin/env python3
"""Screening campaigns: the Lab poses a question nobody has written the answer to, and its own screen answers it.

Gloria, 22 October: "It can't be that difficult to produce a lab that poses novel questions and answers them.
Look at how Anthropic got Claude to find array-associated reverse transcriptase. That is what started his Lab."

That finding came from a screen, not a lookup: take every reverse transcriptase in a group of genomes, read what
sits beside each one, and count. The answer is a pattern across loci that no record states. This module makes that
the shape of his Lab's work:

  1. open    - Gemma names a protein family and an organism group where what sits beside the family is an open
               question, with a prediction stated before anything is read (a fixed list of open corners when it
               cannot). The group must resolve to an NCBI taxon and the search must return proteins.
  2. screen  - one locus per step (lab_phage.screen: the gene's 12 kb neighbourhood, CRISPR arrays by CRT, the Pfam
               families of the protein and of every gene beside it, Cas genes included). Local computation on
               primary sequence; no model is asked.
  3. finding - every FINDING_EVERY loci the screen's own numbers are tabulated: how many loci carry an array, a Cas
               gene, which neighbour families recur and in how many loci. That table is the result, computed, not
               quoted. Gemma then reads it beside the prediction: the pattern, prediction against result, what
               surprised it, the next question. The numbers stand whether or not the reading comes back.

A campaign's question is about the loci it screened ("across the N ... screened"), so its answer is exactly what
the screen measured. A recurring neighbour is a candidate association, never a function, an acquisition event or
a claim that nothing was known: the truth status says so on every row.
"""
from __future__ import annotations
import json
import os
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlencode

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
LAB = os.path.join(WS, "memory", "chemistry-lab")
STORE = os.path.join(LAB, "campaigns.json")
FINDINGS = os.path.join(LAB, "campaign-findings.jsonl")
NOTEBOOK = os.path.join(LAB, "notebook.jsonl")

FINDING_EVERY = 8        # a finding is tabulated after every 8 loci screened
MAX_LOCI = 24            # a campaign closes after 24 loci, or when its search runs out
SEARCH_MAX = 60          # proteins asked of NCBI when a campaign opens
DAILY_SCREENS = 120      # loci a day, across campaigns (each is two NCBI fetches and a local HMMER scan)
SKIP_LIMIT = 20          # a campaign whose proteins keep failing to screen is closed, not retried forever
TRUTH = "computational_screen: candidate associations across the loci screened, not function or acquisition"

# Open corners in the spirit of the line that started the Lab, used when Gemma cannot name a workable campaign.
SEEDS = [
    {"family": "reverse transcriptase", "group": "Caudoviricetes",
     "why": "array-associated reverse transcriptases in phages: the line that started the Lab",
     "prediction": "most phage reverse transcriptases will sit beside no CRISPR array; a minority will, and those "
                   "will more often have a Cas gene within the same 12 kb"},
    {"family": "reverse transcriptase", "group": "Archaea",
     "why": "archaeal reverse transcriptases are far less sampled than bacterial ones",
     "prediction": "a larger share than in phages will sit beside CRISPR arrays, with Cas1 the commonest neighbour"},
    {"family": "reverse transcriptase", "group": "Cyanobacteriota",
     "why": "cyanobacteria carry many group II introns and type III CRISPR systems; which reverse transcriptases "
            "sit with which is open",
     "prediction": "group II intron reverse transcriptases will dominate and rarely sit beside arrays"},
    {"family": "Cas1", "group": "Caudoviricetes",
     "why": "phage-encoded Cas1 is rare; what sits beside it in phage genomes is barely described",
     "prediction": "phage Cas1 will usually sit beside a CRISPR array and often beside a reverse transcriptase"},
    {"family": "reverse transcriptase", "group": "Bacteroidota",
     "why": "diversity-generating retroelements are common in Bacteroidota; their neighbourhoods are under-sampled",
     "prediction": "few will sit beside arrays; recurrent neighbours will be DGR accessory and target genes"},
]


NCBI_GAP_S = 0.4         # NCBI allows three requests a second without a key


class _Paced:
    """The Lab's sources with NCBI's pace kept between every call a campaign makes. Without it the search, the
    two fetches of a screen and the next screen landed inside one second, and NCBI answered 429 to a run of them
    (22 October dry run: three proteins lost to "Too Many Requests" in a row)."""
    def __init__(self, sources, sleep=None, clock=None):
        import time
        self._s, self._sleep, self._clock, self._last = sources, sleep or time.sleep, clock or time.monotonic, None

    def _wait(self):
        if self._last is not None:
            gap = NCBI_GAP_S - (self._clock() - self._last)
            if gap > 0: self._sleep(gap)
        self._last = self._clock()

    def fetch(self, *a, **k):
        self._wait(); return self._s.fetch(*a, **k)

    def fetch_record(self, *a, **k):
        self._wait(); return self._s.fetch_record(*a, **k)

    def __getattr__(self, name):
        return getattr(self._s, name)


def transient(exc):
    """A failure that says nothing about the protein: rate limits, server errors, the network. Retried later."""
    from urllib.error import HTTPError, URLError
    if isinstance(exc, HTTPError):
        return exc.code == 429 or exc.code >= 500
    return isinstance(exc, (URLError, TimeoutError, ConnectionError)) or "timed out" in str(exc).lower()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load():
    try:
        with open(STORE) as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("campaigns"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"campaigns": [], "screens": {}}


def _save(data):
    os.makedirs(LAB, exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, STORE)


def _append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def active(data=None):
    data = data or _load()
    return next((c for c in data["campaigns"] if c.get("state") == "open"), None)


def screens_today(data=None, now=None):
    data = data or _load()
    day = (now or _now())[:10]
    return int((data.get("screens") or {}).get(day, 0))


def _plain(value, cap=60):
    value = re.sub(r"\s+", " ", str(value or "")).strip().strip('."')
    return value if 3 <= len(value) <= cap and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ,()/'-]*", value) else ""


def search_proteins(sources, family, group):
    """(taxon_id, [protein accession.version]) for a family in a group, from NCBI; nothing invented."""
    taxon = sources._taxon({"organism": group})
    if not taxon:
        raise ValueError("NCBI has no taxon named %s" % group)
    term = 'txid%s[Organism:exp] AND "%s"[Protein Name]' % (taxon, family)
    found, _ = sources.fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urlencode({
        "db": "protein", "term": term, "retmode": "json", "retmax": SEARCH_MAX, "tool": "vintos_lab"}))
    ids = [str(x) for x in ((found.get("esearchresult") or {}).get("idlist") or []) if re.fullmatch(r"\d{1,20}", str(x))]
    if not ids:
        return taxon, []
    summary, _ = sources.fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + urlencode({
        "db": "protein", "id": ",".join(ids), "retmode": "json", "tool": "vintos_lab"}))
    result = summary.get("result") or {}
    accessions = []
    for uid in ids:
        acc = str((result.get(uid) or {}).get("accessionversion") or "")
        if re.fullmatch(r"[A-Z]{1,6}_?[A-Z0-9]*\d+\.\d+", acc) and acc not in accessions:
            accessions.append(acc)
    return taxon, accessions


def _done_pairs(data):
    return {(c["family"].lower(), c["group"].lower()) for c in data["campaigns"]}


def propose(ask, data):
    """Gemma names the next campaign; a fixed open corner when it cannot. Returns a dict, never raises."""
    done = sorted("%s in %s" % p for p in _done_pairs(data))
    system = ("You run genome-neighbourhood screens in a computational lab. For a protein family in an organism "
              "group, each gene's 12 kb neighbourhood is read: CRISPR arrays, and the Pfam families of every gene "
              "beside it. Counting across loci finds associations nobody has written down - array-associated "
              "reverse transcriptases in phages were found exactly this way.")
    prompt = ("Name ONE protein family and ONE organism group where what sits beside that family is an open "
              "question worth screening, and predict, before anything is read, what the screen will show. Use a "
              "plain family name NCBI protein records use (e.g. 'reverse transcriptase', 'Cas1', 'integrase', "
              "'toxin', 'recombinase') and a group name NCBI Taxonomy knows (e.g. 'Caudoviricetes', 'Archaea', "
              "'Bacteroidota').\nAlready screened (do not repeat): %s\n"
              'ONLY JSON: {"family": "...", "group": "...", "why": "one sentence: why this is open", '
              '"prediction": "one sentence, something the counts can confirm or refute"}' % (", ".join(done) or "none"))
    try:
        raw = str(ask(system, prompt))
        body = raw[raw.find("{"):raw.rfind("}") + 1]
        d = json.loads(body)
        family, group = _plain(d.get("family")), _plain(d.get("group"))
        if family and group and (family.lower(), group.lower()) not in _done_pairs(data):
            return {"family": family, "group": group, "why": str(d.get("why") or "")[:300],
                    "prediction": str(d.get("prediction") or "")[:400], "by": "gemma"}
    except Exception:
        pass
    for seed in SEEDS:
        if (seed["family"].lower(), seed["group"].lower()) not in _done_pairs(data):
            return dict(seed, by="seed")
    return None


def question(c, n=None):
    return ("Across the %s %s proteins screened in %s genomes, what sits within 6 kb on either side: how many lie "
            "beside a CRISPR array or a Cas gene, and which protein families recur beside them?"
            % (n if n is not None else "first %d" % MAX_LOCI, c["family"], c["group"]))


def open_campaign(sources, ask, data, now=None):
    """Open the next campaign whose search returns proteins. Up to three proposals; returns it or None."""
    for _ in range(3):
        pick = propose(ask, data)
        if not pick:
            return None
        try:
            taxon, accessions = search_proteins(sources, pick["family"], pick["group"])
        except Exception as exc:
            if transient(exc): raise          # NCBI was busy: the pick is not unworkable, the turn just ends
            accessions, taxon = [], None
            pick["why_not"] = str(exc)[:200]
        c = dict(pick, id="C-" + uuid.uuid4().hex[:8], taxon_id=taxon, opened_at=now or _now(),
                 accessions=accessions, cursor=0, screened=[], skipped=[], findings=0,
                 state="open" if len(accessions) >= FINDING_EVERY else "unworkable")
        c["question"] = question(c)
        data["campaigns"].append(c)
        if c["state"] == "open":
            return c
    return None


def _screened_row(record):
    fams = record.get("neighbor_families") or {}
    return {"protein": record.get("protein"), "organism": record.get("organism"),
            "array": bool(record.get("array_associated")), "cas": bool(record.get("cas_associated")),
            "nearest_array_bases": record.get("nearest_array_bases"),
            "query_families": sorted({d.get("family") for d in record.get("domains") or [] if d.get("family")}),
            "neighbor_families": sorted({f for v in fams.values() for f in v}),
            "cas_families": sorted({f for g in record.get("cas_genes") or [] for f in g.get("families") or []}),
            "domain_scan": record.get("domain_scan")}


def tabulate(c):
    """The finding: the screen's own counts across this campaign's loci. Pure; no model."""
    rows = [r for r in c["screened"] if r.get("protein")]
    n = len(rows)
    own = Counter(f for r in rows for f in r["query_families"])
    beside = Counter(f for r in rows for f in r["neighbor_families"] if f not in r["query_families"])
    distances = sorted(r["nearest_array_bases"] for r in rows if isinstance(r.get("nearest_array_bases"), int))
    return {"loci": n, "organisms": len({r.get("organism") for r in rows}),
            "beside_crispr_array": sum(r["array"] for r in rows),
            "beside_cas_gene": sum(r["cas"] for r in rows),
            "array_and_cas": sum(r["array"] and r["cas"] for r in rows),
            "cas_families": Counter(f for r in rows for f in r["cas_families"]).most_common(6),
            "nearest_array_bases_median": distances[len(distances) // 2] if distances else None,
            "own_families": own.most_common(5),
            "recurring_neighbours": [(f, k) for f, k in beside.most_common(10) if k >= 2],
            "domain_scan_failed": sum(1 for r in rows if str(r.get("domain_scan") or "").startswith("failed"))}


def read_finding(ask, c, table):
    system = ("You read the counts from a genome-neighbourhood screen you designed. Use only these numbers. "
              "A recurring neighbour is a candidate association, never a proven function.")
    prompt = ("Campaign: %s in %s. Your prediction before the screen: %s\nCounts: %s\n"
              'ONLY JSON: {"pattern": "the clearest pattern, with its numbers", "prediction_vs_result": '
              '"confirmed, refuted or partly, and by which numbers", "what_surprised_me": "...", '
              '"next_question": "one question a further screen could answer"}'
              % (c["family"], c["group"], c.get("prediction") or "(none stated)", json.dumps(table)))
    try:
        raw = str(ask(system, prompt))
        d = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        return {k: str(d.get(k) or "")[:500] for k in ("pattern", "prediction_vs_result", "what_surprised_me", "next_question")}
    except Exception as exc:
        return {"unread": str(exc)[:160]}


def finding(ask, c, now=None):
    table = tabulate(c)
    reading = read_finding(ask, c, table)
    row = {"at": now or _now(), "kind": "campaign_finding", "campaign": c["id"],
           "family": c["family"], "group": c["group"], "taxon_id": c.get("taxon_id"),
           "question": question(c, table["loci"]), "prediction": c.get("prediction"),
           "result": table, "reading": reading, "screened": [r["protein"] for r in c["screened"]],
           "answers_question": "yes: computed by the Lab's own screen across %d loci" % table["loci"],
           "new_result": True, "truth_status": TRUTH}
    _append(FINDINGS, row)
    _append(NOTEBOOK, row)
    c["findings"] = int(c.get("findings", 0)) + 1
    return row


def step(sources, ask, now=None, screen=None):
    """One campaign turn: open a campaign if none is open, screen its next locus, tabulate a finding when due.
    Returns a summary dict; a turn that could do nothing says why."""
    import lab_phage
    screen = screen or lab_phage.screen
    sources = sources if isinstance(sources, _Paced) else _Paced(sources)
    data = _load()
    now = now or _now()
    if screens_today(data, now) >= DAILY_SCREENS:
        return {"kind": "campaign_rest", "why": "today's %d screens are done" % DAILY_SCREENS}
    c = active(data)
    if not c:
        try:
            c = open_campaign(sources, ask, data, now)
        except Exception as exc:
            if not transient(exc): raise
            _save(data)
            return {"kind": "campaign_wait", "why": str(exc)[:160]}
        _save(data)
        if not c:
            return {"kind": "campaign_none", "why": "no workable campaign could be opened"}
        _append(NOTEBOOK, {"at": now, "kind": "campaign_open", "campaign": c["id"], "family": c["family"],
                           "group": c["group"], "proteins": len(c["accessions"]), "question": c["question"],
                           "prediction": c.get("prediction"), "why": c.get("why"), "by": c.get("by"),
                           "truth_status": "plan_before_screen"})
    out = {"kind": "campaign_screen", "campaign": c["id"]}
    while c["cursor"] < len(c["accessions"]):
        accession = c["accessions"][c["cursor"]]
        c["cursor"] += 1
        try:
            receipt = screen(sources, {"source": "rt_locus_screen", "accession": accession})
            record = (receipt.get("records") or [{}])[0]
        except Exception as exc:
            if transient(exc):
                # NCBI or the network, not the protein: it is tried again on a later turn, and this turn ends
                c["cursor"] -= 1
                _save(data)
                return {"kind": "campaign_wait", "campaign": c["id"], "why": str(exc)[:160]}
            c["skipped"].append({"protein": accession, "why": str(exc)[:160]})
            if len(c["skipped"]) >= SKIP_LIMIT:
                break
            continue
        row = _screened_row(record)
        c["screened"].append(row)
        data.setdefault("screens", {})[now[:10]] = screens_today(data, now) + 1
        _append(NOTEBOOK, dict({"at": now, "kind": "campaign_screen", "campaign": c["id"],
                                "already_screened": bool(record.get("already_screened")),
                                "truth_status": TRUTH}, **row))
        out.update(protein=accession, array=row["array"], cas=row["cas"])
        break
    n = len(c["screened"])
    if n and n % FINDING_EVERY == 0 and n // FINDING_EVERY > int(c.get("findings", 0)):
        out["finding"] = finding(ask, c, now)["result"]
    if n >= MAX_LOCI or c["cursor"] >= len(c["accessions"]) or len(c["skipped"]) >= SKIP_LIMIT:
        if n and n % FINDING_EVERY and n // FINDING_EVERY >= int(c.get("findings", 0)):
            out["finding"] = finding(ask, c, now)["result"]      # the last, partial batch is reported too
        c["state"], c["closed_at"] = "closed", now
        out["closed"] = True
    _save(data)
    return out


def findings_block(limit=4):
    """His recent campaign findings, for the Lab's context."""
    rows = []
    try:
        with open(FINDINGS, encoding="utf-8") as f:
            for line in f:
                try: rows.append(json.loads(line))
                except ValueError: continue
    except OSError:
        return ""
    if not rows:
        return ""
    out = ["[YOUR SCREENING FINDINGS — computed by your own screens; candidate associations, not functions]"]
    for r in rows[-limit:]:
        t = r.get("result") or {}
        out.append("- %s %s in %s: %d loci, %d beside a CRISPR array, %d beside a Cas gene; recurring neighbours %s. %s"
                   % (str(r.get("at", ""))[:10], r.get("family"), r.get("group"), t.get("loci", 0),
                      t.get("beside_crispr_array", 0), t.get("beside_cas_gene", 0),
                      ", ".join("%s (%d)" % tuple(x) for x in (t.get("recurring_neighbours") or [])[:4]) or "none",
                      (r.get("reading") or {}).get("pattern", "")[:200]))
    return "\n".join(out)

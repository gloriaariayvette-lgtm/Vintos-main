#!/usr/bin/env python3
"""One step from a phage reverse transcriptase to its neighborhood (Gloria, 2026-10-03: array-associated reverse
transcriptases in bacteriophages are a main reason she started the Lab).

Before this it was three or four separate turns, each forgotten before the next: the protein's record, its coded_by
coordinates, the genome window around it, a repeat screen that missed most CRISPR arrays. Now one source query does
all of it:

    {source: rt_locus_screen, accession: <exact protein accession.version>}

  1. the protein's GenPept record (its full sequence and where it is coded)
  2. the genome around it, up to 12 kb, with every gene's translation
  3. CRISPR arrays in that window (lab_crt, the CRT method minCED uses)
  4. Pfam domains of the protein and every gene beside it (lab_hmm; HMMER on Aegis): is it a reverse
     transcriptase, which family, and is there a Cas1, Cas2 or other Cas gene nearby
  5. kept in screened-loci.jsonl, so a locus is never screened twice and he can see what he has covered

What comes back is a computational screen: an array near a reverse transcriptase is a candidate association, not a
function, an acquisition event or novelty.
"""
from __future__ import annotations
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
LAB = os.path.join(WS, "memory", "chemistry-lab")
LEDGER = os.path.join(LAB, "screened-loci.jsonl")
WINDOW = 12000
MAX_GENES = 23          # plus the protein itself: lab_hmm.MAX_PROTEINS

CODED_BY = re.compile(r"([A-Z]{1,6}_?[A-Z]*\d+\.\d+):<?(\d+)\.\.>?(\d+)")
LOCATION = re.compile(r"<?(\d+)\.\.>?(\d+)")


def screened(limit=None):
    rows = []
    try:
        for line in open(LEDGER, encoding="utf-8"):
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return rows[-limit:] if limit else rows


def coded_by(values):
    """(nuccore accession, start, end, strand) from GenPept coded_by text, or None."""
    for text in values or []:
        spans = CODED_BY.findall(str(text))
        if not spans:
            continue
        acc = spans[0][0]
        coords = [int(x) for a, s, e in spans if a == acc for x in (s, e)]
        return acc, min(coords), max(coords), ("-" if "complement" in str(text) else "+")
    return None


def _genes(features, window_start):
    """CDS features of the window in genome coordinates, with their translations."""
    out = []
    for f in features:
        if f.get("key") != "CDS":
            continue
        spans = [(int(a), int(b)) for a, b in LOCATION.findall(f.get("location", ""))]
        if not spans:
            continue
        q = f.get("qualifiers") or {}
        out.append({"protein_id": (q.get("protein_id") or [""])[0], "product": (q.get("product") or [""])[0][:120],
                    "start": window_start + min(a for a, _ in spans) - 1, "end": window_start + max(b for _, b in spans) - 1,
                    "strand": "-" if "complement" in f.get("location", "") else "+",
                    "translation": f.get("translation", "")})
    return out


def _gap(a, b):
    """Bases between two spans; 0 when they touch or overlap."""
    return max(0, max(a[0], b[0]) - min(a[1], b[1]))


def screen(sources, spec, hmm=None):
    """The whole screen as one source receipt."""
    from lab_sources import NCBI_BASE, _gbseq, _ncbi_accession, receipt
    accession = _ncbi_accession(spec.get("accession"))
    prior = next((r for r in reversed(screened()) if r.get("protein") == accession), None)
    if prior:
        return receipt("rt_locus_screen", {"source": "rt_locus_screen", "accession": accession},
                       [dict(prior, already_screened=True)], metadata={
                           "service": "Lab screened-loci ledger", "coverage": "already_screened_not_refetched",
                           "next_step": "choose another reverse transcriptase; this locus was screened before"})
    protein = _gbseq(sources.fetch_record(NCBI_BASE + "efetch.fcgi?" + urlencode({
        "db": "protein", "id": accession, "rettype": "gp", "retmode": "xml", "tool": "vintos_lab"})), accession)
    where = coded_by([v for f in protein["features"] for v in f["qualifiers"].get("coded_by", [])])
    if not where:
        raise ValueError("the protein record names no coded_by location to read the genome around")
    nuc, start, end, strand = where
    flank = max(0, (WINDOW - (end - start + 1)) // 2)
    w_start, w_end = max(1, start - flank), end + flank
    region = _gbseq(sources.fetch_record(NCBI_BASE + "efetch.fcgi?" + urlencode({
        "db": "nuccore", "id": nuc, "seq_start": w_start, "seq_stop": w_end, "rettype": "gb", "retmode": "xml",
        "tool": "vintos_lab"})), nuc, translations=True)
    seq = region["sequence"]
    if not seq or len(seq) > w_end - w_start + 1:
        raise ValueError("NCBI returned an invalid genome window")
    import lab_crt
    arrays = [{"start": w_start + a["start"] - 1, "end": w_start + a["end"] - 1, "repeats": a["repeats"],
               "repeat_length": a["repeat_length"], "repeat": a["repeat"], "spacers": len(a["spacers"]),
               "repeat_identity": a["repeat_identity"]} for a in lab_crt.find_arrays(seq)]
    genes = _genes(region["features"], w_start)
    import lab_hmm
    domains, hmm_state = {}, "not_installed"
    if hmm or lab_hmm.available():
        proteins = {"QUERY": protein["sequence"]}
        for g in genes:
            if g["translation"] and g["protein_id"] != accession and len(proteins) <= MAX_GENES:
                proteins[g["protein_id"] or "%d-%d" % (g["start"], g["end"])] = g["translation"]
        try:
            domains = (hmm or lab_hmm.scan)(proteins)
            hmm_state = "scanned"
        except Exception as exc:
            hmm_state = "failed: %s" % str(exc)[:160]
    query_domains = domains.get("QUERY", [])
    rt = [d for d in query_domains if lab_hmm.is_rt(d)]
    cas = [{"protein_id": g["protein_id"], "product": g["product"], "start": g["start"], "end": g["end"],
            "families": [d["family"] for d in domains.get(g["protein_id"] or "%d-%d" % (g["start"], g["end"]), [])
                         if lab_hmm.is_cas(d)]} for g in genes]
    cas = [c for c in cas if c["families"]] + ([{"protein_id": accession, "product": "(the protein itself)",
                                                  "start": start, "end": end,
                                                  "families": [d["family"] for d in query_domains if lab_hmm.is_cas(d)]}]
                                               if any(lab_hmm.is_cas(d) for d in query_domains) else [])
    nearest = min((_gap((start, end), (a["start"], a["end"])) for a in arrays), default=None)
    record = {
        "protein": accession, "definition": protein["definition"], "organism": protein["organism"],
        "taxonomy": protein["taxonomy"][:300], "protein_length": len(protein["sequence"]),
        "coded_by": {"accession": nuc, "start": start, "end": end, "strand": strand},
        "window": {"accession": nuc, "start": w_start, "end": w_start + len(seq) - 1},
        "domains": [{k: d[k] for k in ("family", "pfam", "evalue", "from", "to")} for d in query_domains][:8],
        "reverse_transcriptase_domain": [d["family"] for d in rt],
        "crispr_arrays": arrays[:6], "nearest_array_bases": nearest,
        "cas_genes": cas[:8],
        "neighbors": [{k: g[k] for k in ("protein_id", "product", "start", "end", "strand")} for g in genes][:MAX_GENES],
        "domain_scan": hmm_state,
        "array_associated": bool(arrays), "cas_associated": bool(cas),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "truth_status": "computational_screen_not_function_acquisition_or_novelty",
    }
    os.makedirs(LAB, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps({k: v for k, v in record.items() if k != "neighbors"}, ensure_ascii=False) + "\n")
    return receipt("rt_locus_screen", {"source": "rt_locus_screen", "accession": accession}, [record], metadata={
        "service": "NCBI_EFetch GenPept and GenBank, CRT arrays, HMMER/Pfam domains",
        "coordinates": "one_based_inclusive", "coverage": "one_locus_up_to_12kb",
        "evidence": "primary_sequence_provider_annotation_and_local_computation"})


def coverage_block(limit=12):
    """What he has screened, for his Lab context: the loci, and how many held an array or a Cas gene."""
    rows = screened()
    if not rows:
        return ""
    arr = sum(1 for r in rows if r.get("array_associated"))
    cas = sum(1 for r in rows if r.get("cas_associated"))
    lines = ["[LOCI YOU HAVE SCREENED — %d so far: %d beside a CRISPR array, %d beside a Cas gene; do not screen "
             "these again]" % (len(rows), arr, cas)]
    for r in rows[-limit:]:
        lines.append("- %s %s (%s): RT %s; arrays %d%s; Cas %s" % (
            r.get("protein"), str(r.get("definition", ""))[:60], str(r.get("organism", ""))[:40],
            ",".join(r.get("reverse_transcriptase_domain") or []) or "none found",
            len(r.get("crispr_arrays") or []),
            (" (nearest %s bp)" % r["nearest_array_bases"]) if r.get("nearest_array_bases") is not None else "",
            ",".join(sorted({f for c in r.get("cas_genes") or [] for f in c.get("families", [])})) or "none"))
    return "\n".join(lines)

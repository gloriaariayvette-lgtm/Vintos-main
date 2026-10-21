#!/usr/bin/env python3
"""Gemma does not repeat herself, and she works the frontier session's plan (Gloria, 2026-10-07: "We need Gemma to
stop making repeats. Period. She needs to not only better understand Atlas, but to more strictly adhere to the plans
of the frontier sessions").

What the review of 30 September - 6 October found: the same Atlas read of SLC26A4 three times (one fixed window, the
same scores each time), questions restated in new words, and Gemma's runs after a frontier session on other subjects
entirely (formate dehydrogenase after an A1L190 fold; E. coli taxonomy after pendrin's session asked for secondary
structure). The guards before were words in her prompt and a redirect after the lookup had already run.

    LOOKUPS               a small ledger of the lookups and questions she ran (the notebook is too big to rescan)
    repeat(inquiry)       why this inquiry repeats one from the last REPEAT_DAYS, or ""
    record(inquiry)       file it, once it is accepted
    frontier_step()       the latest frontier session's next step, while her next FRONTIER_CYCLES cycles work it
    on_frontier(inq, st)  whether an inquiry works that step (shares its subject)
    ATLAS                 what an Atlas record is, for her prompts
"""
import json
import os
import re
import time
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
ROOT = os.path.join(WS, "memory", "chemistry-lab")
LOOKUPS = os.path.join(ROOT, "lookups.jsonl")
SESSIONS = os.path.join(ROOT, "sessions.jsonl")
REPEAT_DAYS = 7
SIMILAR = 0.6              # share of a question's content words another question already had
FRONTIER_CYCLES = 6        # her cycles after a frontier session that are steps on its next question

ATLAS = ("WHAT AN ATLAS RECORD IS: for a human gene symbol the Lab finds where the gene starts on GRCh38 and reads ONE "
         "fixed window of at most 32 bases there. Atlas returns its model's PREDICTED effect of single-base variants in "
         "that window on tracks such as ATAC, DNase, RNA-seq or CAGE, for the cell types it lists. It is not a map of the "
         "gene's enhancers or tissues, not a measurement, and not the site of any mutation elsewhere in the gene (a "
         "coding variant such as HFE C282Y is not in it). The same gene always gives the same window and the same "
         "scores: reading it again teaches nothing new.")

_WORD = re.compile(r"[a-z0-9][a-z0-9-]{3,}")
_STOP = set("what which does that this with from into have their there about these those under within "
            "between specific structural structure protein proteins human role function sequence residues domain "
            "region regions record records known based how are the and for its whether".split())
_ACCESSION = re.compile(r"(?<![A-Z0-9])(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?![A-Z0-9])")
_SYMBOL = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,9}(?![A-Za-z0-9])")
_NOT_SUBJECTS = {"ESMFOLD", "DSSP", "PDB", "UNIPROT", "NCBI", "JSON", "DNA", "RNA", "HP", "CONFIDENT_FOLD", "TM",
                 "MODERATE_FOLD", "ATAC", "RCSB", "API", "ID", "IDS", "NMR", "SAXS", "CD", "RMSD", "TM-ALIGN", "GRCH38"}


def _now():
    return datetime.now(timezone.utc)


def _when(row):
    try:
        t = datetime.fromisoformat(str(row.get("at", ""))[:26].replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _tail(path, nbytes=2 * 1024 * 1024):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); start = max(0, f.tell() - nbytes); f.seek(start)
            lines = f.read().decode("utf-8", "replace").splitlines()[1 if start else 0:]   # a cut first line only
    except OSError:
        return []
    out = []
    for line in lines:
        try: out.append(json.loads(line))
        except ValueError: continue
    return out


def _uniprot_term(field, value):
    # For a species leaf these two filters select the same records. Do not
    # equate organism_id and taxonomy_id for higher taxa (e.g. bacteria).
    if field == "organism_id" and value == "9606": field = "taxonomy_id"
    return field, value


def uniprot_key(query):
    """Canonicalize conjunctions only; OR/NOT and unknown syntax retain their exact meaning."""
    text = re.sub(r"\s+", " ", str(query or "").strip()).lower()
    field = re.compile(r'(\w+)\s*:\s*("[^"\n]*"|\[[^\]]*\]|[^\s()]+)')
    matches = list(field.finditer(text))
    rest = field.sub('', text)
    if matches and not re.sub(r'\band\b|[\s()]', '', rest):
        terms = sorted(set(_uniprot_term(m[1], m[2].strip('"')) for m in matches))
        return "uniprot:" + json.dumps(terms, separators=(',', ':'))
    return "uniprot:" + text


def canonical_lookup(key):
    # Read older ledger entries without rewriting their history.
    if key.startswith("uniprot:"):
        body = key[len("uniprot:"):]
        if body.startswith('[["'):
            try:
                terms = json.loads(body)
                return "uniprot:" + json.dumps(sorted(set(_uniprot_term(k, v) for k, v in terms)), separators=(',', ':'))
            except (ValueError, TypeError): return key
        return uniprot_key(body)
    if key.startswith("source_query:"):
        try:
            spec = json.loads(key.split(':', 1)[1])
            if spec.get('source') == 'uniprot': return uniprot_key(spec.get('query'))
        except (ValueError, AttributeError): pass
    return key


def lookup_targets(key):
    """Named UniProt targets in a canonical lookup, independent of generic question prose."""
    key = canonical_lookup(str(key or ''))
    if not key.startswith('uniprot:'): return set()
    body = key[len('uniprot:'):]
    terms = []
    if body.startswith('[['):
        try: terms = json.loads(body)
        except (ValueError, TypeError): terms = []
    if not terms:
        field = re.compile(r'(accession|gene|protein_name)\s*:\s*("[^"\n]*"|[^\s()]+)', re.I)
        terms = [(match[1], match[2].strip('"')) for match in field.finditer(body)]
    return {(str(field).lower(), unicodedata.normalize('NFC', str(value)).strip().casefold())
            for field,value in terms if str(field).lower() in ('accession','gene','protein_name') and str(value).strip()}


def lookup_key(inquiry):
    """The lookup an inquiry makes, written the same way whatever words it came in; '' when it makes none."""
    inq = inquiry if isinstance(inquiry, dict) else {}
    for field in ("source_query", "plugin_query", "instrument_query"):
        q = inq.get(field)
        if not isinstance(q, dict) or not q:
            continue
        if field == "source_query" and q.get("source") == "uniprot":
            return uniprot_key(q.get("query"))
        if field == "source_query" and q.get("source") == "atlas":
            return "atlas:" + str(q.get("gene") or q.get("chromosome", "") + ":" + str(q.get("start", ""))).upper()
        if field == "plugin_query" and str(q.get("plugin", "")).lower() in ("uniprot", "uniprotkb"):
            # The daemon executes chemistry_lab as __main__; never import a second copy.
            main = sys.modules.get('__main__')
            if os.path.basename(getattr(main, '__file__', '')) == 'chemistry_lab.py':
                uniprot_from_plugin = main.uniprot_from_plugin
            else:
                from chemistry_lab import uniprot_from_plugin
            spec = uniprot_from_plugin(q, str(inq.get("question") or ""))
            if spec: return uniprot_key(spec["query"])
        clean = {k: v for k, v in q.items() if k not in ("purpose", "why", "question")}
        return field + ":" + json.dumps(clean, sort_keys=True, default=str).lower()
    query = str(inq.get("uniprot_query") or "").strip()
    if query:
        return uniprot_key(query)
    return ""


def _words(text):
    return {w for w in _WORD.findall(str(text or "").lower()) if w not in _STOP}


def _recent(now=None):
    now = now or _now()
    since = now - timedelta(days=REPEAT_DAYS)
    return [r for r in _tail(LOOKUPS) if (_when(r) or since) >= since]


def _lookup_route(key):
    kind, _, body = key.partition(":")
    if kind in ("source_query", "plugin_query", "instrument_query"):
        try:
            spec = json.loads(body)
            if kind == 'instrument_query':
                return (kind,spec.get('skill'),spec.get('operation'),spec.get('tool'))
            if spec.get('source') == 'pdb' and spec.get('operation') == 'search_accession':
                return (kind, 'pdb', 'search_accession')
            return (kind, spec.get("source"), spec.get("plugin"), spec.get("tool"))
        except (ValueError, AttributeError):
            pass
    return kind


def _literature_route(key):
    kind, _, body = key.partition(":")
    if kind != "source_query": return False
    try:
        spec = json.loads(body)
    except (ValueError, TypeError): return False
    return spec.get("source") in ("pubmed", "pubmed_abstracts") or (
        spec.get("source") == "ncbi" and spec.get("operation") == "literature")


def identity_refusal_key(inquiry):
    """Semantic identity context, independent of prose and attempt bookkeeping."""
    from lab_sources import human_question_symbols, uniprot_identity_symbols, normalize_uniprot_subjects
    def normalized(value):
        if isinstance(value, str): return unicodedata.normalize('NFC', value).strip()
        if isinstance(value, dict): return {k:normalized(v) for k,v in value.items()}
        if isinstance(value, list): return [normalized(v) for v in value]
        return value
    inq = normalized(dict(inquiry))
    inq['uniprot_query'] = normalize_uniprot_subjects(inq.get('uniprot_query') or '')
    if isinstance(inq.get('source_query'), dict) and str(inq['source_query'].get('source')).lower() == 'uniprot':
        inq['source_query']['source'] = 'uniprot'
        inq['source_query']['query'] = normalize_uniprot_subjects(inq['source_query'].get('query') or '')
    for field in ('source_query', 'plugin_query', 'instrument_query'):
        if isinstance(inq.get(field), dict):
            inq[field] = {k:v for k,v in inq[field].items()
                          if k not in ('attempt_id', 'request_id')}
    symbols = human_question_symbols(str(inq.get('question') or '').upper())
    symbol_query = re.sub(r'\b(GENE|PROTEIN_NAME):', lambda m:m[0].lower(), inq['uniprot_query'].upper())
    symbols += uniprot_identity_symbols(symbol_query)
    accessions = sorted(set(_ACCESSION.findall(str(inq.get('question') or '').upper())))
    return json.dumps([lookup_key(inq), uniprot_key(inq.get('uniprot_query')),
                       sorted(set(symbols)), accessions], sort_keys=True)


def _identity_refusal_keys(inquiry):
    """Current key plus the deployed three-part form, so rollout does not release old decisions."""
    current = identity_refusal_key(inquiry)
    try:
        parts = json.loads(current)
        legacy = json.dumps(parts[:3], sort_keys=True)
    except (ValueError, TypeError):
        legacy = current
    return {current, legacy}


def identity_rejection(inquiry, rows):
    keys = _identity_refusal_keys(inquiry)
    for row in reversed(rows):
        if row.get('identity_refusal') not in keys: continue
        symbol = row.get('unresolved_symbol')
        # A newly sourced exact identity is material evidence, not a cosmetic retry.
        if symbol:
            for receipt in reversed(_tail(os.path.join(ROOT, 'source-receipts.jsonl'))):
                if (receipt.get('source') == 'ncbi_gene_identity'
                        and (receipt.get('query') or {}).get('symbol', '').upper() == symbol):
                    try:
                        fresh = datetime.fromisoformat(receipt['retrieved_at']) > _when(row)
                    except (KeyError, TypeError, ValueError): fresh = False
                    from lab_sources import verified_human_identity
                    if fresh and verified_human_identity(receipt, symbol): return ''
                    break
            return 'unchanged unresolved human identity: ' + str(symbol)
        return 'unchanged unresolved identity: ' + str(row.get('identity_reason') or 'conflicting target context')
    return ''


def fold_read_covers(previous, requested):
    """The same immutable model read already includes this residue interval."""
    for spec in (previous, requested):
        if not isinstance(spec, dict) or spec.get('skill') != 'fold_read' or spec.get('operation') != 'structure.read': return False
        if not isinstance(spec.get('files'), list) or len(spec['files']) != 1: return False
    if str(previous['files'][0]).casefold() != str(requested['files'][0]).casefold(): return False
    def span(spec):
        value = spec.get('range', [None, None])
        if not isinstance(value, list) or len(value) != 2: return None
        if any(x is not None and (type(x) is not int or x < 1) for x in value): return None
        lo, hi = value
        if lo is not None and hi is not None and lo > hi: return None
        return (lo if lo is not None else float('-inf'), hi if hi is not None else float('inf'))
    old, new = span(previous), span(requested)
    return old is not None and new is not None and old[0] <= new[0] <= new[1] <= old[1]


def repeat(inquiry, now=None):
    """Why this inquiry repeats one she ran in the last REPEAT_DAYS days, in words for her; '' when it does not."""
    rows = _recent(now)
    rejected = identity_rejection(inquiry, rows)
    if rejected: return rejected
    key = lookup_key(inquiry)
    if key:
        for r in reversed(rows):
            if canonical_lookup(r.get("lookup") or "") == key:
                return ("you already ran this exact lookup on %s (%s); it would return the same thing"
                        % (str(r.get("at", ""))[:16].replace("T", " "), key[:120]))
    requested = inquiry.get('instrument_query') or {}
    if requested.get('skill') == 'fold_read':
        for row in reversed(rows):
            lookup = canonical_lookup(row.get('lookup') or '')
            if not lookup.startswith('instrument_query:'): continue
            try: previous = json.loads(lookup.split(':', 1)[1])
            except ValueError: continue
            if fold_read_covers(previous, requested):
                return 'prior model read already includes this residue range: ' + str(row.get('at') or '')
    mine = _words(inquiry.get("question") if isinstance(inquiry, dict) else "")
    own_targets = lookup_targets(key)
    if len(mine) >= 4:
        for r in reversed(rows):
            # The same unresolved question may legitimately need another instrument/source.
            # A wording change on the same retrieval is still refused by the exact key above.
            if key and r.get("lookup") and _lookup_route(key) != _lookup_route(canonical_lookup(r["lookup"])):
                if not (_literature_route(key) and _literature_route(canonical_lookup(r["lookup"]))):
                    continue
            # Similar wording about a different named protein is a different question.
            # Exclude shared domain names (STAS, etc.); compare accession/gene-like IDs.
            def identities(text):
                return {s for s in subjects(text) if any(c.isdigit() for c in s)}
            own_ids = identities(inquiry.get("question", ""))
            previous_ids = identities(r.get("question", ""))
            if own_ids and previous_ids and own_ids.isdisjoint(previous_ids):
                continue
            previous_targets = lookup_targets(r.get('lookup') or '')
            if own_targets and previous_targets and own_targets.isdisjoint(previous_targets):
                continue
            theirs = set(r.get("words") or [])
            if theirs and len(mine & theirs) / len(mine) >= SIMILAR:
                return "you already asked this on %s, in other words: %s" % (
                    str(r.get("at", ""))[:16].replace("T", " "), str(r.get("question", ""))[:200])
    return ""


def record(inquiry, now=None, refused="", *, identity_validated=False):
    """File an accepted inquiry's lookup and question. A refused one is filed as a cycle spent and nothing more: it
    ran no lookup. Exact unresolved identity refusals are remembered separately; transient failures
    remain retryable. Every refusal counts toward the frontier step's cycles (a
    Gemma who cannot find an on-plan question is not refused all day)."""
    inq = inquiry if isinstance(inquiry, dict) else {}
    row = {"at": (now or _now()).isoformat(), "lookup": "" if refused else lookup_key(inq),
           "question": str(inq.get("question", ""))[:300], "words": [] if refused else sorted(_words(inq.get("question"))),
           "frontier_session": inq.get("frontier_session"), **({"refused": refused[:200]} if refused else {})}
    identity = inq.get('identity_check') or {}
    evidence = identity.get('receipt_ids') or []
    if identity_validated and refused and identity.get('status') == 'unresolved':
        key = identity_refusal_key(inq)
        keys = _identity_refusal_keys(inq)
        # Same evidence cannot renew an active decision. After expiry, one
        # completed validation starts a new bounded window, even if the provider
        # returned the same receipt. Blocked echoes never enter this branch.
        prior = next((r for r in reversed(_tail(LOOKUPS)) if r.get('identity_refusal') in keys), None)
        prior_time = _when(prior) if prior else None
        expired = prior_time is not None and prior_time < (now or _now()) - timedelta(days=REPEAT_DAYS)
        receipt_id = evidence[-1] if evidence else None
        if not prior or expired or (receipt_id and prior.get('identity_receipt_id') != receipt_id):
            row.update(identity_refusal=key, identity_reason=str(identity.get('reason') or '')[:200])
            if receipt_id: row['identity_receipt_id'] = receipt_id
            if identity.get('symbol'): row['unresolved_symbol'] = str(identity['symbol']).upper()
    os.makedirs(ROOT, exist_ok=True)
    with open(LOOKUPS, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def recent_lookups(n=10, now=None):
    """Her last n distinct lookups this week, for her prompt."""
    seen = []
    for r in reversed(_recent(now)):
        if r.get("lookup") and r["lookup"] not in seen:
            seen.append(r["lookup"])
        if len(seen) >= n:
            break
    return seen


def asked_questions(cap=4000, now=None):
    """Every distinct question she asked and ran this week, newest first, each cut short, under `cap` characters.

    repeat() refuses a question that shares SIMILAR of its words with any question run in the last REPEAT_DAYS days,
    but her prompt showed only her last ten lookup keys and none of the questions (15 October, 21:26-23:26 CDT: 23 of
    47 outcomes were repeat or spent-question refusals and waits). She cannot steer around what she is not shown."""
    seen, out, used = set(), [], 0
    for r in reversed(_recent(now)):
        q = " ".join(str(r.get("question") or "").split())
        if r.get("refused") or not r.get("words") or not q:
            continue
        k = q.casefold()
        if k in seen:
            continue
        seen.add(k)
        q = q[:117] + "..." if len(q) > 120 else q
        if used + len(q) + 3 > cap:
            break
        out.append(q); used += len(q) + 3
    return out


def not_human_symbols(n=60, now=None):
    """Names NCBI Gene did not establish as human genes this week, newest first (a refused identity keeps its
    unresolved_symbol). Shown to the planner, so a wrong premise is not proposed again in other questions."""
    out = []
    for r in reversed(_recent(now)):
        sym = str(r.get("unresolved_symbol") or "").strip()
        if sym and sym not in out:
            out.append(sym)
        if len(out) >= n:
            break
    return out


def all_lookups(cap=2500, now=None):
    """Every distinct lookup she ran this week, newest first, under `cap` characters (not only the last ten)."""
    out, used = [], 0
    for key in recent_lookups(n=10**6, now=now):
        k = key[:160]
        if used + len(k) + 3 > cap:
            break
        out.append(k); used += len(k) + 3
    return out


def subjects(text):
    """The accessions and gene/protein symbols a text names."""
    text = str(text or "")
    found = set(_ACCESSION.findall(text))
    found |= {s for s in _SYMBOL.findall(text) if s not in _NOT_SUBJECTS and (any(c.isdigit() for c in s) or len(s) >= 3)}
    return sorted(found)


def frontier_step(now=None):
    """The latest completed frontier session's next step, while her cycles since it are fewer than FRONTIER_CYCLES:
    {session_id, lens, at, next_question, keep, subjects, left}; None otherwise."""
    rows = [r for r in _tail(SESSIONS, 4 * 1024 * 1024) if r.get("state") == "completed" and isinstance(r.get("reading"), dict)]
    if not rows:
        return None
    s = rows[-1]
    nq = str(s["reading"].get("next_question") or "").strip()
    if not nq:
        return None
    since = _when(s)
    done = sum(1 for r in _tail(LOOKUPS) if since and (_when(r) or since) > since)
    if done >= FRONTIER_CYCLES:
        return None
    plan = s.get("plan") if isinstance(s.get("plan"), dict) else {}
    params = plan.get("parameters") if isinstance(plan.get("parameters"), dict) else {}
    named = " ".join(str(params.get(k) or "") for k in ("target_accession", "protein_name"))
    return {"session_id": s.get("session_id"), "lens": s.get("lens"), "at": s.get("at"), "next_question": nq[:1200],
            "keep": str(s["reading"].get("keep") or "")[:600],
            "subjects": subjects(nq + " " + named + " " + str(plan.get("question") or "")),
            "left": FRONTIER_CYCLES - done}


def on_frontier(inquiry, step):
    """True when the inquiry names a subject of the session's step."""
    if not step or not step.get("subjects"):
        return True
    inq = inquiry if isinstance(inquiry, dict) else {}
    text = " ".join(str(inq.get(k) or "") for k in ("question", "uniprot_query")) + " " + \
        json.dumps([inq.get(k) for k in ("source_query", "plugin_query", "instrument_query", "material_terms")], default=str)
    mine = set(subjects(text)) | {w.upper() for w in re.findall(r"[A-Za-z0-9]+", text)}
    return any(s.upper() in mine for s in step["subjects"])

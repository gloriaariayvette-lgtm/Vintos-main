"""Shared background/frontier source execution, receipt ledger and report handoff."""
import json
import os
from pathlib import Path
import sys
import time
import hashlib
import re

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path: sys.path.insert(0, HERE)
import chemistry_lab as lab
from lab_sources import Sources, AtlasProcess, collision_descriptor, followups, receipt


def configured_sources():
    cfg = lab.config()
    key_file = cfg.get('alphagenome_key_file')
    return Sources(atlas=AtlasProcess(key_file, cfg.get('alphagenome_python') or sys.executable) if key_file else None)


def query_plugin(plugin, tool, arguments, purpose):
    """Run one Lab-approved connected source and enter its result into Lab provenance."""
    direct = lab.pubmed_from_plugin({'plugin': plugin, 'tool': tool, 'arguments': arguments})
    if direct:
        return query(direct, question=purpose)
    from plugin_gateway import call, load_receipt
    import claude_connector_gateway
    gateway_call = claude_connector_gateway.call if claude_connector_gateway.owns(plugin) else call
    outcome = gateway_call('lab', plugin, tool, arguments, purpose)
    stored = load_receipt(outcome['receipt']['receipt_id'], 'lab')
    result = receipt('plugin:'+plugin, {'tool':tool, 'arguments_sha256':outcome['receipt']['arguments_sha256']},
                     stored['result'], metadata={'plugin_receipt_id':outcome['receipt']['receipt_id'],
                     'coverage':'tool_defined', 'evidence':'connected_tool_output'})
    lab._append(os.path.join(lab.ROOT, 'source-receipts.jsonl'), result)
    lab._append(lab.COLLISION_ADAPTER, collision_descriptor(result))
    return {'plugin_receipt': outcome['receipt'], 'source_receipt': result}


def query_protein_design_mcp(spec):
    """One bounded local instrument call, returned as Lab provenance."""
    import chemistry_mcp
    outcome = chemistry_mcp.call(spec)
    result = receipt('protein_design_mcp',
                     {'tool': outcome['tool'], 'arguments_sha256': outcome.get('arguments_sha256'),
                      'source_receipt_ids': outcome['source_receipt_ids']},
                     {'summary': outcome['summary'], 'result_sha256': outcome['result_sha256']},
                     metadata={'artifact': outcome['artifact'],
                               **({'backend_receipt_id': outcome['backend_receipt_id']}
                                  if outcome.get('backend_receipt_id') else {}),
                               'evidence': 'local_model_prediction_not_experimental_validation'})
    lab._append(os.path.join(lab.ROOT, 'source-receipts.jsonl'), result)
    lab._append(lab.COLLISION_ADAPTER, collision_descriptor(result))
    return {'instrument_receipt': result, 'instrument_result': outcome}


def query(spec, *, client=None, question=''):
    if not lab.config().get('allow_public_database_reads'):
        raise RuntimeError('public database reads disabled')
    # One bounded request per source per minute; provider throttles get a longer hold.
    throttle_path = os.path.join(lab.ROOT, 'source-throttle.json')
    with lab._locked():
        throttle = lab._load(throttle_path, {})
        source = str(spec.get('source', 'unknown'))
        if time.time() < throttle.get(source, 0): raise RuntimeError('source_cooldown_active')
        throttle[source] = time.time()+60
        lab._atomic(throttle_path, throttle)
    try:
        result = (client or configured_sources()).query(spec)
    except Exception as exc:
        from urllib.error import HTTPError
        if isinstance(exc, HTTPError) and exc.code == 429:
            with lab._locked():
                throttle = lab._load(throttle_path, {})
                throttle[source] = time.time()+300
                lab._atomic(throttle_path, throttle)
        # The reason, not only its type: "RuntimeError" alone told nobody what failed (2026-09-29).
        raise RuntimeError('source_query_unavailable:'+type(exc).__name__
                           + (' %s' % exc.code if isinstance(exc, HTTPError) else '')
                           + (': ' + ' '.join(str(exc).split())[:200] if str(exc) and not isinstance(exc, HTTPError) else '')) from exc
    lab._ensure()
    lab._append(os.path.join(lab.ROOT, 'source-receipts.jsonl'), result)
    lab._append(lab.COLLISION_ADAPTER, collision_descriptor(result))
    names = (result.get('metadata') or {}).get('available_scorers') if result.get('source') == 'atlas' else None
    if names:   # Atlas's real scorer names, kept so the next question can name them
        lab._atomic(os.path.join(lab.ROOT, 'atlas-scorers.json'), list(names)[:40])
    import chemistry_frontier_bridge as bridge
    assessment = bridge.assess({'at': result['retrieved_at'], 'entry_id': 'SRC-'+result['receipt_id'][:16],
        'source_accessions': [result['receipt_id'][:32]],
        'factual_observation': json.dumps({'source': result['source'], 'query': result['query'],
                                          'receipt': result['receipt_id'], 'observations': result['records']})[:1000],
        'next_question': str(question)[:1000], 'speculative_reading': 'Prediction or source observation; not validation.'},
        source_query_succeeded=True)
    candidate = {'receipt_id': result['receipt_id'], 'question': question,
                 'assessment': assessment, 'followups': followups(result)}
    lab._append(os.path.join(lab.ROOT, 'source-candidates.jsonl'), candidate)
    return {'receipt': result, 'candidate': candidate}


_COMMON = frozenset("""what which how does do did are is was were the of in on to for and or with from by that this these those
their its into across under over between within specific specifically structural structure structures motif motifs
role roles mechanism mechanisms particular different various possible potential might could would there their
exhibit facilitate facilitates allow allows explain relate related relation environment environments
protein proteins architecture architectures diversity dictate dictates conserved across modular affect affects influence""".split())


def material_terms(inquiry):
    """The words a literature search needs: the protein he named, the organism, what he asks about."""
    inquiry = inquiry if isinstance(inquiry, dict) else {}
    chosen = [str(t).strip() for t in (inquiry.get('material_terms') or []) if isinstance(t, str) and t.strip()]
    if chosen: return chosen[:5]
    terms = [t.split(':', 1)[1].strip('"') for t in lab._intent_terms(inquiry.get('uniprot_query'))]
    sq = inquiry.get('source_query') if isinstance(inquiry.get('source_query'), dict) else {}
    terms += [str(sq[k]) for k in ('term', 'organism') if isinstance(sq.get(k), str) and sq.get(k)]
    question = str(inquiry.get('question') or '')
    terms += re.findall(r'\b[A-Z][a-z]+ [a-z]{4,}\b', question)[:1]          # a binomial: Saccharolobus solfataricus
    words = [w for w in re.findall(r'\b(?:[A-Z][A-Z0-9]{2,}[a-z]?|[A-Za-z][A-Za-z0-9-]{3,})\b', question)   # PKS, KaiC, MCR
             if w.lower() not in _COMMON]
    taken = ' '.join(terms).lower()
    words = [w for w in dict.fromkeys(words) if w.lower() not in taken]
    # Names first (KaiC, PFOR, S-layer), then the longest words, which carry the most meaning.
    terms += sorted(words, key=lambda w: (not re.search(r'[A-Z0-9-]', w[1:]), -len(w)))[:3]
    seen, out = set(), []
    for term in terms:
        if term.lower() not in seen and not any(term.lower() in o.lower() for o in out):
            seen.add(term.lower()); out.append(term)
    return out[:5]


def material(inquiry, *, client=None):
    """Published abstracts for his question, fetched by the Lab itself (Gloria, 2026-09-28: "Give him the
    material"). His own queries only ever returned identifiers and taxonomy lines; this is the reading."""
    if not lab.config().get('allow_public_database_reads'): return None
    terms = material_terms(inquiry)
    if not terms: return None
    throttle_path = os.path.join(lab.ROOT, 'source-throttle.json')
    with lab._locked():
        throttle = lab._load(throttle_path, {})
        if time.time() < throttle.get('pubmed_abstracts', 0): return None
        throttle['pubmed_abstracts'] = time.time() + 20
        lab._atomic(throttle_path, throttle)
    result = (client or configured_sources()).query({'source': 'pubmed_abstracts', 'terms': terms})
    lab._ensure()
    lab._append(os.path.join(lab.ROOT, 'source-receipts.jsonl'), result)
    return result

def report_packet(receipt_ids):
    """Exact, sourced input for a Forge report. Does not declare publication novelty."""
    if not isinstance(receipt_ids, list) or not 1 <= len(receipt_ids) <= 8:
        raise ValueError('choose 1..8 source receipts')
    rows = lab._jsonl(os.path.join(lab.ROOT, 'source-receipts.jsonl'))
    by_id = {r['receipt_id']: r for r in rows}
    if any(rid not in by_id for rid in receipt_ids): raise ValueError('unknown source receipt')
    selected = [by_id[rid] for rid in receipt_ids]
    from lab_sources import receipt
    bounded = []
    for row in selected:
        encoded = json.dumps(row['records'], sort_keys=True)
        if len(encoded) > 12000:
            row = receipt(row['source'], row['query'], {'excerpt': encoded[:12000], 'truncated': True},
                          metadata={**row['metadata'], 'full_receipt_id': row['receipt_id'],
                                    'full_response_sha256': row['response_sha256'], 'coverage': 'bounded_excerpt_only'})
        bounded.append(row)
    return {'kind': 'lab_research_report', 'source_receipts': bounded,
            'required_sections': ['sourced_observations', 'hypotheses', 'conflicting_evidence',
                                  'limitations', 'next_tests'],
            'novelty': 'not_established', 'commercial_use': 'not_authorized',
            'completion_means': 'documented_report_not_validated_discovery'}


REPORT_MAX_ATTEMPTS = 12            # a report that has failed this often is abandoned, not retried forever
REPORT_BACKOFF_CAP_S = 6 * 3600     # 1 min, 2, 4 ... never more than 6 hours between tries
REPORT_PAUSE_S = 30 * 60            # after the Forge says no, no report is offered for this long
REPORT_PAUSE = os.path.join(lab.ROOT, 'forge-report-pause.json')
# The Forge full (X-Forge-Refusal: four_unfinished) is not a fault to keep logging: the Lab loop logs the
# refusal once, the pause record keeps how many projects the Forge had open, and no report is offered again
# until that count changes (Vintos, 2026-10-08). Other refusals keep the timed pause.
REPORT_DONE = ('complete', 'cancelled', 'abandoned')
fetch_projects = None    # tests replace this; the Lab reads the Forge's keyless project list on the loop


def forge_open(cfg):
    """The Forge's open projects [{id, title, state}], or None when the Forge cannot be read."""
    rows = _forge_projects(cfg)
    if rows is None: return None
    return [{'id': r.get('id'), 'title': str(r.get('title') or r.get('name') or r.get('intent') or '')[:120],
             'state': r.get('state')} for r in rows if isinstance(r, dict) and r.get('state') not in REPORT_DONE]


def forge_unfinished(cfg):
    """How many Forge projects are still open, or None when the Forge cannot be read."""
    open_now = forge_open(cfg)
    return None if open_now is None else len(open_now)


def _forge_projects(cfg):
    try:
        if fetch_projects is not None:
            rows = fetch_projects()
        else:
            from urllib.parse import urlsplit
            from urllib.request import Request
            from lab_http import open_request
            parsed = urlsplit(cfg['url'])
            with open_request(Request('%s://%s/api/projects' % (parsed.scheme, parsed.netloc)), timeout=15) as response:
                rows = json.loads(response.read(1 << 20))
        return rows if isinstance(rows, list) else None
    except Exception:
        return None


def held(cfg):
    """Why a report may not be sent now, or '': the Forge said four_unfinished and its open count has not moved, or
    another refusal's timed pause has not run out. A changed count lifts the four_unfinished hold."""
    pause = lab._load(REPORT_PAUSE, {}) or {}
    if pause.get('guard') == 'four_unfinished':
        count = forge_unfinished(cfg)
        if count is None or count == pause.get('unfinished'):
            return 'four_unfinished'
        try: os.unlink(REPORT_PAUSE)
        except FileNotFoundError: pass
        return ''
    if pause.get('until', 0) > time.time():
        return pause.get('guard') or 'paused after HTTP %s' % pause.get('http_status')
    return ''


def offer_report(receipt_ids, question, *, send=None):
    """Explicit Lab configuration grants source-dossier creation, not a novelty claim."""
    cfg = lab.config().get('forge_report_intake')
    if not cfg: return {'state': 'not_configured'}
    from urllib.parse import urlsplit
    from urllib.request import Request
    from lab_http import open_request
    from forge_loop_runtime import secret
    endpoint = cfg['url']
    parsed = urlsplit(endpoint)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path != '/api/lab-intake':
        raise ValueError('Lab intake requires the dedicated local loop endpoint')
    key = hashlib.sha256(json.dumps(sorted(receipt_ids)).encode()).hexdigest()
    outbox_path = os.path.join(lab.ROOT, 'forge-report-outbox.json')
    with lab._locked():
        outbox = lab._load(outbox_path, {})
        prior = outbox.get(key)
        if prior and prior.get('state') == 'accepted': return {'id': prior['project_id'], 'replayed': True}
        if prior and prior.get('state') == 'abandoned': return {'state': 'abandoned', 'replayed': True}
    # A held Forge is not asked again by a new report either (2026-10-08: the reflect phase offered each new
    # instrument gap straight to a full Forge, a fresh 403 and a fresh fault each time). It waits in the outbox,
    # unattempted, for flush_reports to send once the hold lifts.
    why_held = held(cfg)
    if why_held:
        with lab._locked():
            outbox = lab._load(outbox_path, {})
            row = outbox.get(key) or {'receipt_ids': receipt_ids, 'question': question, 'attempts': 0}
            row.update(state='pending', held=why_held, next_attempt=0)
            outbox[key] = row
            lab._atomic(outbox_path, outbox)
        return {'state': 'held', 'guard': why_held}
    packet = report_packet(receipt_ids)
    body = {'source_packet': packet, 'intent': str(question)[:2000]}
    with lab._locked():
        outbox = lab._load(outbox_path, {})
        prior = outbox.get(key)
        attempts = int((prior or {}).get('attempts', 0)) + 1
        outbox[key] = {'receipt_ids': receipt_ids, 'question': question, 'state': 'pending', 'attempts': attempts,
                       'next_attempt': time.time() + min(REPORT_BACKOFF_CAP_S, 60 * 2 ** (attempts - 1))}
        lab._atomic(outbox_path, outbox)
    req = Request(endpoint, data=json.dumps(body).encode(), method='POST', headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer '+secret(cfg['token_file'])})
    try:
        with (send or open_request)(req, timeout=15) as response:
            result = json.loads(response.read(65536))
    except Exception as exc:
        # It used to retry every 60 s forever: 18,821 faults in one week (gap scan, 2026-09-24).
        # The Forge answers the same 403 for every refusal. Since 2026-10-05 it names the guard in an
        # X-Forge-Refusal header to the Lab alone (token, size, packet, receipt_hash, four_unfinished,
        # malformed); no header on a 403 means the intake token itself was not accepted, or the Forge
        # predates the header. The guard is kept on the report and in the Lab's fault line. Retrying is
        # unchanged: a refusal pauses ALL reports for a while, each report backs off on its own, and only
        # a report tried REPORT_MAX_ATTEMPTS times is abandoned.
        code = getattr(exc, 'code', None)
        named = None
        if code == 403:
            named = (getattr(exc, 'headers', None) or {}).get('X-Forge-Refusal') or 'not_named'
            try: exc.msg = '%s (Forge guard: %s)' % (exc.msg, named)
            except Exception: pass
        if isinstance(code, int) and 400 <= code < 500:
            pause = {'until': time.time() + REPORT_PAUSE_S, 'http_status': code, 'at': lab.now_iso()}
            if named == 'four_unfinished':   # held, not retried, until the Forge's open count changes
                open_now = forge_open(cfg)    # which ones: the blocker names what would clear it
                pause.update(guard=named, unfinished=None if open_now is None else len(open_now),
                             open=(open_now or [])[:8])
            lab._atomic(REPORT_PAUSE, pause)
        with lab._locked():
            outbox = lab._load(outbox_path, {})
            outbox[key].update(http_status=code, reason=str(exc)[:240])
            if named: outbox[key]['forge_guard'] = named
            if attempts >= REPORT_MAX_ATTEMPTS:
                outbox[key].update(state='abandoned', ended_at=lab.now_iso())
            lab._atomic(outbox_path, outbox)
        raise
    if not result.get('id'): raise RuntimeError('report intake not acknowledged')
    with lab._locked():
        outbox = lab._load(outbox_path, {})
        outbox[key].update(state='accepted', project_id=result['id'])
        lab._atomic(outbox_path, outbox)
    lab._append(os.path.join(lab.ROOT, 'forge-report-handoffs.jsonl'),
                {'at': lab.now_iso(), 'receipt_ids': receipt_ids, 'project_id': result['id'],
                 'state': 'accepted_by_atelier', 'novelty': 'not_established'})
    return result


def flush_reports():
    cfg = lab.config().get('forge_report_intake')
    if not cfg: return
    if held(cfg) == 'four_unfinished':
        return   # the Forge was full; the loop logged that once. Nothing is offered until its open count moves
    outbox_path = os.path.join(lab.ROOT, 'forge-report-outbox.json')
    with lab._locked():
        outbox = lab._load(outbox_path, {})
        # Only a genuinely missing limb goes to the Forge (Gloria, 2026-09-28). Write-ups of his questions
        # (2026-09-26) and laboratory equipment he could never operate — the cryo-EM "Feasibility Assessment"
        # projects — are withdrawn, not retried.
        prefix = 'The Lab needs an instrument it does not have: '
        stale = [row for row in outbox.values() if row.get('state') in ('pending', 'refused') and not (
                 str(row.get('question', '')).startswith(prefix)
                 and lab.missing_limb(str(row['question'])[len(prefix):].split('\nIt came up on this question:')[0]))]
        for row in stale: row.update(state='withdrawn', withdrawn_at=lab.now_iso())
        if stale: lab._atomic(outbox_path, outbox)
    if (lab._load(REPORT_PAUSE, {}) or {}).get('until', 0) > time.time(): return   # the Forge said no; wait
    for row in outbox.values():
        # 'refused' is only left by the 2026-09-24 build that took a capacity 403 as final; it is retried.
        if row.get('state') in ('pending', 'refused') and row.get('next_attempt', 0) <= time.time():
            offer_report(row['receipt_ids'], row['question'])
            return

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query_json', help='explicit source query JSON file; no generated commands')
    args = parser.parse_args()
    print(json.dumps(query(json.loads(Path(args.query_json).read_text())), indent=2))

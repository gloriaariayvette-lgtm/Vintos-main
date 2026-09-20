"""Shared background/frontier source execution, receipt ledger and report handoff."""
import json
import os
from pathlib import Path
import sys
import time
import hashlib

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path: sys.path.insert(0, HERE)
import chemistry_lab as lab
from lab_sources import Sources, AtlasProcess, collision_descriptor, followups


def configured_sources():
    cfg = lab.config()
    key_file = cfg.get('alphagenome_key_file')
    return Sources(atlas=AtlasProcess(key_file, cfg.get('alphagenome_python', sys.executable)) if key_file else None)


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
        raise RuntimeError('source_query_unavailable:'+type(exc).__name__) from exc
    lab._ensure()
    lab._append(os.path.join(lab.ROOT, 'source-receipts.jsonl'), result)
    lab._append(lab.COLLISION_ADAPTER, collision_descriptor(result))
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
    packet = report_packet(receipt_ids)
    body = {'source_packet': packet, 'intent': str(question)[:2000]}
    key = hashlib.sha256(json.dumps(sorted(receipt_ids)).encode()).hexdigest()
    outbox_path = os.path.join(lab.ROOT, 'forge-report-outbox.json')
    with lab._locked():
        outbox = lab._load(outbox_path, {})
        prior = outbox.get(key)
        if prior and prior.get('state') == 'accepted': return {'id': prior['project_id'], 'replayed': True}
        outbox[key] = {'receipt_ids': receipt_ids, 'question': question, 'state': 'pending', 'next_attempt': time.time()+60}
        lab._atomic(outbox_path, outbox)
    req = Request(endpoint, data=json.dumps(body).encode(), method='POST', headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer '+secret(cfg['token_file'])})
    with (send or open_request)(req, timeout=15) as response:
        result = json.loads(response.read(65536))
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
    if not lab.config().get('forge_report_intake'): return
    outbox = lab._load(os.path.join(lab.ROOT, 'forge-report-outbox.json'), {})
    for row in outbox.values():
        if row.get('state') == 'pending' and row.get('next_attempt', 0) <= time.time():
            offer_report(row['receipt_ids'], row['question'])
            break


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query_json', help='explicit source query JSON file; no generated commands')
    args = parser.parse_args()
    print(json.dumps(query(json.loads(Path(args.query_json).read_text())), indent=2))

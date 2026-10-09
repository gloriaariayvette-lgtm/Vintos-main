#!/usr/bin/env python3
"""Replay 9 Oct's unanswered SLC26A19 and Pendrin runs. No provider or network calls."""
import json, os, pathlib, socket, sys, tempfile
from urllib.parse import parse_qs, urlsplit
from datetime import datetime, timezone
REPO = pathlib.Path(__file__).resolve().parents[2]
HOME = tempfile.mkdtemp(prefix='lab-failed-runs-')
os.environ['HOME'] = HOME
os.environ['SPARK_WORKSPACE'] = HOME + '/workspace'
network = []
def no_network(*a, **kw):
    network.append(True)
    raise AssertionError('network forbidden')
socket.socket.connect = no_network
sys.path.insert(0, str(REPO / 'scripts'))
import chemistry_lab as lab
import lab_repeats as repeats
import lab_sources as sources
import chemistry_frontier_bridge as bridge
assert all(str(p).startswith(HOME) for p in (lab.ROOT, lab.NOTEBOOK, lab.SPENT, repeats.LOOKUPS, repeats.SESSIONS, bridge.INTEREST, bridge.SURFACES))
assert socket.socket.connect is no_network
calls = []
def model_stub(system, prompt, **kw):
    calls.append(prompt)
    return json.dumps({'answers_question': 'no; source does not answer this', 'factual_observation': 'A returned record', 'next_question': 'Retrieve the missing evidence'})
lab._ask = model_stub
assert lab._ask is model_stub
inq = {'question': 'What is the domain architecture of human SLC26A19?',
       'uniprot_query': 'reviewed:true AND (protein_name:SLC26A19 AND reviewed:true)'}
now = datetime.now(timezone.utc)
repeats.record(inq, now=now)
assert 'exact lookup' in repeats.repeat(dict(inq, question='Does this transporter have C-terminal scaffolding?'), now=now)
assert repeats.lookup_key(dict(inq, source_query={'source':'interpro','accession':'O43511'})) != repeats.lookup_key(inq)
assert not repeats.repeat(dict(inq, source_query={'source':'interpro','accession':'O43511'}), now=now)
routed=lab._inquiry(dict(inq, plugin_query={"plugin":"pubmed","tool":"search_articles",
                                            "arguments":{"term":"human SLC26A5 protein structure"}}))
assert routed['plugin_query'] is None
assert routed['source_query'] == {'source':'pubmed_abstracts','terms':['human SLC26A5 protein structure']}
# A completed but unanswered review used to reset the failure streak on every pass.
rows = []
for _ in range(3):
    rows += [{'kind':'inquiry', 'inquiry':inq}, {'kind':'reflection', 'answers_question':'no; no data for SLC26A19'}]
assert lab.dead_ends(rows)['count'] == 3 and 'SLC26A19' in lab.dead_ends(rows)['subjects']
assert lab.dead_ends(rows + [{'kind':'reflection','answers_question':'yes; measured sequence length'}])['count'] == 0
# Replay the PubMed zero-hit subject. Generic ERK papers must never replace it.
queries=[]
def search(url):
    q=parse_qs(urlsplit(url).query); term=q['term'][0]; queries.append(term)
    return {'esearchresult': {'count':'0' if 'SLC26A19' in term else '4',
                             'idlist':[] if 'SLC26A19' in term else ['31796593']}}, {}
def no_abstract(url): raise AssertionError('unrelated ERK abstract must not be fetched')
client=sources.Sources(fetch=search, fetch_record=no_abstract)
r=client.query({'source':'pubmed_abstracts','terms':['SLC26A19','human','protein structure']})
assert r['records'] == [] and 'SLC26A19' in r['query']['terms_matched']
assert all('SLC26A19' in q for q in queries if ' AND ' in q)
# A zero-record browse is not source success; explicit no is not a promoted finding.
failed={'kind':'reflection','at':now.isoformat(),'inquiry':inq,'source_accessions':['PMID-31796593'],
        'source_query_succeeded':True,'answers_question':'no; these records concern ERK, not SLC26A19',
        'factual_observation':'The literature concerns ERK','next_question':'Where is SLC26A19?'}
lab._append(lab.NOTEBOOK, failed)
a=bridge.assess(failed, source_query_succeeded=True)
assert not a['flagged_for_next_lab_session'] and 'unanswered_not_a_finding' in a['reason_for_score']
assert all(t['state'] != 'finding' for t in lab.journal_threads())
lab._append(lab.NOTEBOOK, dict(failed, entry_id='OLD-FAILED'))
lab._append(lab.NOTEBOOK, dict(failed, answers_question='yes', entry_id='LATER-ANSWERED'))
assert 'OLD-FAILED' in bridge._redirect_entry_ids()
for verdict in ('', 'The records do not provide the sequence', 'no'):
    assert not lab.review_answered(dict(failed, answers_question=verdict))
# Real UniProt O43511 captured read-only on Aegis 2026-10-09: 780 residues.
p=json.loads((REPO/'broker/tests/fixtures/pendrin-o43511.json').read_text())
assert len(p['sequence']) == p['length'] == 780
q={'question':'What is the primary sequence of residues 485-535 in human Pendrin?', 'why_now':'Resolve the missing interval'}
spans=lab.sequence_regions(q, {'records':[p]})
assert spans[0]['sequence'] == p['region_485_535'] == p['sequence'][484:535]
assert spans[0]['accession'] == 'O43511' and spans[0]['length'] == 51
assert lab.sequence_regions({'question':'residues 770-900'}, {'records':[p]}) == []
lab._reflect('replay', q, {'records':[p]})
assert p['region_485_535'] in calls[-1] and 'one-based inclusive' in calls[-1]
assert 'If no, leave speculative_reading empty' in calls[-1]
assert not network
print('PASS: failed-run replay, repeat recovery, PubMed subject preservation, finding gate, exact Pendrin interval; isolated')

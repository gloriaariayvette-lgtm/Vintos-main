#!/usr/bin/env python3
"""Replay the Oct 9 routing failures; scratch stores and no real senders."""
import json, os, pathlib, socket, sys, tempfile
HOME = tempfile.mkdtemp(prefix='lab-oct9-recovery-')
os.environ['HOME'] = HOME
os.environ['SPARK_WORKSPACE'] = HOME + '/workspace'
os.environ['VINTOS_SECRETS'] = HOME + '/secrets'
net = []
def no_net(*a, **k):
    net.append(True)
    raise AssertionError('network forbidden')
socket.socket.connect = no_net
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'scripts'))
import chemistry_lab as C
import lab_sources as S
import lab_repeats as R
assert all(str(p).startswith(HOME) for p in (C.ROOT,C.STATE,C.NOTEBOOK,C.SPENT,R.LOOKUPS,R.SESSIONS))
assert socket.socket.connect is no_net
# Two real runs escaped the direct route because they supplied a terms list.
terms = ['human SLC26A1','DRA','structural fold','STAS domain','SulP domain']
inq = C._inquiry({'question':'What is the structure of SLC26A1?', 'plugin_query':
    {'plugin':'pubmed','tool':'search_articles','arguments':{'terms':terms}}})
assert inq['plugin_query'] is None and inq['source_query'] == {'source':'pubmed_abstracts','terms':terms}
# Preserve requested limits; unknown actions are not rerouted into a different operation.
limited = C._inquiry({'plugin_query':{'plugin':'pubmed','tool':'search_articles','arguments':{'terms':terms,'limit':2}}})
assert limited['source_query']['limit'] == 2
unknown = C._inquiry({'plugin_query':{'plugin':'pubmed','tool':'other','arguments':{'terms':terms}}})
assert unknown['plugin_query'] and not unknown['source_query']
# Direct abstract reads also accept a single phrase without splitting away the subject.
calls = []
def fetch(url):
    calls.append(url)
    return {'esearchresult':{'count':'0','idlist':[]}}, {}
def no_record(url): raise AssertionError('no IDs returned; must not fetch')
client = S.Sources(fetch=fetch, fetch_record=no_record)
assert client.fetch is fetch and client.fetch_record is no_record
for key in ('term','query'):
    out = client.query({'source':'pubmed_abstracts',key:'human SLC26A1 STAS'})
    assert out['records'] == [] and out['query']['terms_matched'] == ['human SLC26A1 STAS']
# Unreviewed lookup must be satisfiable, not intersected with reviewed:true.
q = C._safe_query('protein_name:SLC26A18 AND taxonomy_id:9606 AND reviewed:false')
assert 'reviewed:false' in q and 'reviewed:true' not in q
# The explicit accession in the actual failed request controls the protein retrieval.
wrong = {'question':'Given residues 535-729 of human Pendrin (O43511), what is the spacing?',
         'uniprot_query':'protein_name:SLC26A3 AND taxonomy_id:9606'}
fixed = C._inquiry(wrong)
assert fixed['uniprot_query'] == 'accession:O43511'
assert 'SLC26A3' in fixed['query_resolution']['requested_query']
assert C._safe_query('accession:O43511').find('length:') == -1
# Comparing two accessions must not silently pick one of them.
pair = C._inquiry(dict(wrong, question='Compare O43511 and P40879'))
assert not pair.get('query_resolution')
# A different protein is not a repeat merely because STAS/architecture overlap.
first = {'question':'What is the documented domain architecture of SLC26A1 and its STAS domain?',
         'uniprot_query':'gene:SLC26A1'}
R.record(first)
second = dict(first,question=first['question'].replace('SLC26A1','SLC26A2'),uniprot_query='gene:SLC26A2')
assert R.repeat(second) == ''
assert 'exact lookup' in R.repeat(first)
# Same subject paraphrase remains a repeat even with a nonidentical retrieval.
assert R.repeat(dict(first,uniprot_query='gene:SLC26A1 AND reviewed:true'))
# Extra descriptors/incorrect aliases cannot prevent reading papers on the retained subject.
from urllib.parse import parse_qs, urlsplit
searches=[]
def subject_search(url):
    term=parse_qs(urlsplit(url).query)['term'][0]; searches.append(term)
    # Real ESearch shape; the subject exists, but conjunctions do not.
    return {'esearchresult':{'count':'1' if term == '(SLC26A1)' else '0',
                            'idlist':[]}}, {}
subject_client=S.Sources(fetch=subject_search,fetch_record=no_record)
r=subject_client.query({'source':'pubmed_abstracts','terms':['SLC26A1','DRA']})
assert r['query']['terms_matched'] == ['SLC26A1']
assert searches[-1] == '(SLC26A1)' and '(DRA)' != searches[-1]
# The provider cannot substitute a sibling even on an exact-accession route.
import urllib.request
class Response:
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,*args): return json.dumps({'results':[{'primaryAccession':'P40879'}]}).encode()
def urlopen(*args,**kwargs): return Response()
urllib.request.urlopen = urlopen
assert urllib.request.urlopen is urlopen
try:
    C._browse('accession:O43511',1)
    raise AssertionError('wrong record accepted')
except ValueError as error:
    assert 'source_accession_mismatch' in str(error)
assert calls and not net
print('PASS: recorded routing failures, exact identity, valid unreviewed query, subject-aware repeats; isolated')

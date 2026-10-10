#!/usr/bin/env python3
"""Real Oct 10 source shapes; every writer is scratch and every sender is stubbed."""
import os,sys,json,socket,tempfile,pathlib
from unittest.mock import patch
HOME=tempfile.mkdtemp(prefix='lab-oct10-test-')
os.environ['HOME']=HOME;os.environ['SPARK_WORKSPACE']=HOME+'/workspace';os.environ['VINTOS_SECRETS']=HOME+'/secrets'
def no_network(*a,**k): raise AssertionError('network forbidden')
socket.socket.connect=no_network
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
import chemistry_lab as C,chemistry_sources as CS,lab_sources as S,lab_repeats as R,lab_phage as P
import urllib.request
urllib.request.urlopen=no_network
assert all(str(x).startswith(HOME) for x in (C.ROOT,C.STATE,C.NOTEBOOK,C.SPENT,C.FAULTS,C.RECEIPTS,C.COLLISION_ADAPTER,R.LOOKUPS,R.SESSIONS,P.LEDGER))
assert socket.socket.connect is no_network and urllib.request.urlopen is no_network
FIX=pathlib.Path(__file__).parent/'fixtures'
replays=json.loads((FIX/'lab_oct10_structural_replays.json').read_text())
scope=json.loads((FIX/'lab_oct10_scope.json').read_text())
# Planning and saved requests dispatch to the same existing screen with a canonical receipt.
q=C._inquiry({'question':'Read the sourced locus','source_query':{'source':'ncbi_rt_locus_screen','accession':'NP_001503.1'}})
assert q['source_query']['source']=='rt_locus_screen'
def screen(client,spec):
 assert spec['source']=='rt_locus_screen';return S.receipt('rt_locus_screen',spec,[{'accession':spec['accession']}])
with patch.object(P,'screen',screen):
 client=S.Sources(fetch=no_network,fetch_record=no_network)
 assert P.screen is screen
 assert client.query({'source':'ncbi_rt_locus_screen','accession':'NP_001503.1'})['source']=='rt_locus_screen'
# No unrequested citation can replace the actual structure's cited article.
xml=(FIX/'lab_oct10_citation.xml').read_text()
calls=[]
def exact_record(url):calls.append(url);return xml
client=S.Sources(fetch=no_network,fetch_record=exact_record)
r=client.query({'source':'pubmed_abstracts','pmids':['27386547']})
assert r['records'][0]['pmid']=='27386547' and len(calls)==1 and 'esearch' not in calls[0]
try:client.query({'source':'pubmed_abstracts','pmids':['bad']})
except ValueError:pass
else:raise AssertionError('invalid PMID accepted')
# Real raw UniProt response from the diagnostic receipt: no fabricated API shape.
raw=scope['source_receipt']['records'];sent=[]
class Response:
 def __init__(self,value):self.value=value
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self,*args):return json.dumps(self.value).encode()
def fetch(req,**kwargs):
 from urllib.parse import urlsplit,parse_qs
 query=parse_qs(urlsplit(req.full_url).query)['query'][0];sent.append(query)
 return Response({'results':[] if '9606' in query else raw})
with patch.object(urllib.request,'urlopen',fetch):
 assert urllib.request.urlopen is fetch
 result=C._browse(scope['requested_query'],2)
 assert result['scope_resolution'] and '9606' not in result['executed_query']
 assert all(r['organism']!='Homo sapiens' for r in result['records'])
 assert result['source_receipt']['metadata']['scope_resolution']
assert '9606' in sent[0] and '9606' not in sent[-1]
# A blocked source changes to an unread actual PDB/InterPro route without another model call.
first=replays[0]['inquiry'];protein=replays[0]['after']['records'][0]
C._append(C.NOTEBOOK,{'kind':'source_read','source':'UniProtKB REST','requested_query':first['uniprot_query'],'records':[protein]})
R.record(first)
regulatory=dict(first,atlas_turn=True,question='What are the predicted regulatory effects of single-base variants in SLC26A2?')
assert C._strategy_change(regulatory,R) is None
assert C._strategy_change(dict(first,question='How does chromatin accessibility affect CASR expression?'),R) is None
assert C._strategy_change(dict(first,question='What is the genomic neighborhood of CASR?'),R) is None
with patch.object(C,'_ask',side_effect=AssertionError('no replanning needed')),patch.object(C,'_ground_inquiry',return_value={'status':'not_applicable'}):
 out,_=C._held_to_plan('s','t',first,{},None,None,R)
 assert not out.get('refused') and out['strategy_resolution']
 assert R.lookup_key(out)!=R.lookup_key(first)
 assert out['source_query']['source'] in ('pdb','interpro')
# The reviewer receives structure geometry, exact paper and source sequence, not embedding duplication.
for sample in replays:
 payload=sample['after'];visible=json.loads(C.observed(C.review_observations(sample['inquiry'],payload)))
 assert visible['additional_source']['records'][0]['geometry']
 assert visible['LITERATURE'][0]['pmid']==str(payload['additional_source']['receipt']['records'][0]['primary_citation']['pdbx_database_id_PubMed'])
# Inconsistent no + conjecture gets a bounded review validation; never force yes.
answers=iter([{'answers_question':'no','speculative_reading':'invented','next_question':'missing membrane orientation'},
              {'answers_question':'no: membrane orientation is not measured','speculative_reading':'invented','next_question':'obtain membrane orientation'}])
def ask(*a,**k):return json.dumps(next(answers))
with patch.object(C,'_ask',ask), patch.object(C,'_coverage_check',return_value=None):
 assert C._ask is ask
 result=C._reflect('',replays[1]['inquiry'],replays[1]['after'])
 assert result['answers_question']=='no' and result['speculative_reading']==''
 assert 'orientation' in result['missing_evidence']
assert socket.socket.connect is no_network and urllib.request.urlopen is no_network
print('PASS: canonical RT screen, exact citations, explicit scope correction, distinct evidence recovery, structured review data and truthful no; isolated')

# Exact public source quotes from the real CASR checker output can settle the
# original question; bracketed source paths resolve to the same actual strings.
coverage=json.loads((FIX/'lab_oct10_coverage.json').read_text())
positive=coverage['checker_responses'][0]
with patch.object(C,'_ask',return_value=json.dumps(positive)) as grader:
 result=C._coverage_check(coverage['inquiry'],coverage['evidence'])
 assert result and result['answered'] is True
 assert all(item['path'].startswith('evidence.') for item in result['supports'])
 assert all(item.get('source_citation','').startswith('PMID ') for item in result['supports'])
 grader.assert_called_once()
invalid=json.loads(json.dumps(positive));invalid['supports'][0]['quote']='An invented statement not present in the paper.'
with patch.object(C,'_ask',return_value=json.dumps(invalid)):
 assert C._coverage_check(coverage['inquiry'],coverage['evidence']) is None
# Coordinate contacts come from actual deposited atoms, with explicit measurement limits.
structure=replays[2]['after']['additional_source']['receipt']['records'][0]
assert structure['geometry']['inter_chain_contacts'][0]['ca_pair_count']==98
assert 'not proof' in structure['geometry']['method']
assert socket.socket.connect is no_network and urllib.request.urlopen is no_network
print('PASS: real checker quote paths, grounded affirmative coverage, invented quote refused, measured contacts; isolated')
# Real linked full text: pmcid (not pmc) is the current provider identity field.
from urllib.parse import urlsplit,parse_qs
pmc_calls=[]
def linked_article(url):
 query=parse_qs(urlsplit(url).query);pmc_calls.append(query['db'][0])
 return (FIX/('lab_oct10_slc26a6_pmc.xml' if query['db'][0]=='pmc' else 'lab_oct10_slc26a6_pubmed.xml')).read_text()
full_client=S.Sources(fetch=no_network,fetch_record=linked_article)
full=full_client.query({'source':'pubmed_abstracts','pmids':['37351578'],'include_full_text':True})
article=full['records'][0]
assert article['pmcid']=='PMC10328499' and pmc_calls==['pubmed','pmc']
assert any('cytoplasmic STAS domain' in p for p in article['full_text_excerpt'])
assert sum(map(len,article['full_text_excerpt']))<=6000 and len(article['full_text_excerpt'])<=4
assert socket.socket.connect is no_network and urllib.request.urlopen is no_network
print('PASS: real public full text supplies missing topology; exact article identity and bounded structural excerpts; isolated')
# Next pass after a refusal continues an existing self-authored next step before
# calling the planner again; it does not make the same failed choice a third time.
pathlib.Path(R.LOOKUPS).write_text('')
R.record(first)
C._append(C.NOTEBOOK,{'kind':'reflection','inquiry':first,'answers_question':'no',
                    'next_question':'What do the source annotations establish about CASR domain organization?'})
C._append(C.NOTEBOOK,{'kind':'inquiry_refused','inquiry':first,'why':'repeat'})
with patch.object(C,'_ask',side_effect=AssertionError('repeated planner must not run')), \
     patch.object(C,'_ground_inquiry',return_value={'status':'not_applicable'}), \
     patch.object(C,'atlas_turn_due',return_value=False), \
     patch.object(R,'frontier_step',return_value=None):
 recovered=C._orient('fixture')
 assert not recovered.get('refused') and recovered['strategy_resolution']['reason']=='continued_another_self_authored_unresolved_step'
 assert recovered['source_query']['source'] in ('pdb','interpro')
 assert R.lookup_key(recovered)!=R.lookup_key(first)
assert all(str(p).startswith(HOME) for p in (C.ROOT,C.NOTEBOOK,R.LOOKUPS))
print('PASS: refused pass resumes sourced pending work before replanning; isolated')

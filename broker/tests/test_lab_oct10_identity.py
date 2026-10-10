"""Offline regressions: no live workspace, providers, models, or device calls."""
import importlib, json, os, pathlib, socket, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

scratch = tempfile.TemporaryDirectory(prefix='lab-oct10-')
os.environ.update(HOME=scratch.name, SPARK_WORKSPACE=scratch.name+'/workspace',
                  VINTOS_SECRETS=scratch.name+'/secrets')
def forbidden(*a, **k): raise AssertionError('external operation forbidden')
socket.socket.connect = forbidden
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
import chemistry_lab as C
import lab_sources as S
import lab_repeats as R
C._ask = forbidden
assert socket.socket.connect is forbidden and C._ask is forbidden
assert all(str(p).startswith(scratch.name) for p in (C.ROOT,C.NOTEBOOK,C.STATE,C.SPENT,R.ROOT,R.LOOKUPS,R.SESSIONS))

class IdentityTests(unittest.TestCase):
    def setUp(self):
        pathlib.Path(R.ROOT).mkdir(parents=True,exist_ok=True)
        for name in ('lookups.jsonl','notebook.jsonl','source-receipts.jsonl','sessions.jsonl'):
            pathlib.Path(R.ROOT,name).write_text('')

    def test_pdb_tokens_do_not_call_gene_provider(self):
        class Client:
            human_gene_identity = forbidden
        for token in ('7W3O','7w3o','(7W3O),','7W3O:A','7W3O_A','7W3OX'):
            inquiry={'question':'Human protein structure in PDB '+token,
                     'uniprot_query':'accession:P00387','source_query':{'source':'pdb','entry_id':'7W3O'}}
            self.assertEqual(C._ground_inquiry(inquiry,Client()),{'status':'not_applicable'})
            self.assertEqual(S.uniprot_identity_symbols('protein_name:"'+token+'"'),[])
        self.assertEqual(C._human_question_symbols('human TP53 BRCA1 G6PD'),['TP53','BRCA1','G6PD'])
        self.assertEqual(S.uniprot_identity_symbols('gene:G6PD'),['G6PD'])

    def test_pdb_route_survives_admission(self):
        inquiry={'question':'Human protein structure PDB 7W3O:A',
                 'uniprot_query':'accession:P00387','source_query':{'source':'pdb','entry_id':'7W3O','operation':'structure_evidence'}}
        with patch.object(S.Sources,'human_gene_identity',side_effect=forbidden) as provider:
            admitted,_=C._held_to_plan('','',inquiry,{},None,None,R)
        provider.assert_not_called()
        self.assertNotIn('refused',admitted)
        self.assertEqual(admitted['source_query'],inquiry['source_query'])

    def test_beta_extraction_normalization_transport(self):
        for beta in ('β',r'$\beta$', '$\beta$', r'\x08eta'):
            query='protein_name:"'+beta+'-galactosidase" AND organism_id:9606 AND reviewed:true'
            normalized=C._safe_query(query)
            self.assertIn('β-galactosidase',normalized)
            self.assertIn('β-galactosidase',C._intent_terms(normalized)[0])
            outgoing=[]
            def fetch(url):
                outgoing.append(parse_qs(urlsplit(url).query)['query'][0])
                return {'results':[{'primaryAccession':'P16278','genes':[]}]},{}
            client=S.Sources(fetch=fetch,fetch_record=forbidden)
            client.query({'source':'uniprot','query':normalized})
            self.assertTrue(outgoing)
            self.assertIn('β-galactosidase',outgoing[0])
            self.assertIn('taxonomy_id:9606',outgoing[0])
            self.assertNotIn('x08',outgoing[0])
            for _,relaxed in S.uniprot_relaxations(normalized):
                self.assertIn('β-galactosidase',relaxed)
                self.assertIn('organism_id:9606',relaxed)
            self.assertIn('β-galactosidase',S.validate_uniprot(query))

    def inquiry(self, **updates):
        row={'question':'What is the human FAKE123 structural domain?',
             'uniprot_query':'accession:P00387','source_query':{'source':'pdb','entry_id':'1UMK','operation':'structure_evidence'}}
        row.update(updates); return row

    def reject(self, status='unresolved'):
        result={'status':status,'symbol':'FAKE123','reason':'fixture identity rejected','receipt_ids':['rejection-1']}
        with patch.object(C,'_ground_inquiry',return_value=result) as ground:
            refused,_=C._held_to_plan('','',self.inquiry(),{},None,None,R)
        self.assertEqual(ground.call_count,1)
        self.assertIn('refused',refused)
        return refused

    def test_semantic_rejection_persists_but_corrections_retry(self):
        self.reject()
        importlib.reload(R)
        same=self.inquiry(question='Describe domain topology of human FAKE123 now',attempt_id='new')
        same['source_query']=dict(same['source_query'],attempt_id='next')
        self.assertIn('unresolved',R.repeat(same))
        self.assertEqual(R.repeat(self.inquiry(question='Human TP53 structure')), '')
        self.assertEqual(R.repeat(self.inquiry(uniprot_query='accession:P04637')), '')
        self.assertEqual(R.repeat(self.inquiry(source_query={'source':'interpro','accession':'P00387'})), '')
        receipt=self.verified_receipt()
        pathlib.Path(R.ROOT,'source-receipts.jsonl').write_text(json.dumps(receipt)+'\n')
        self.assertEqual(R.repeat(same),'')

    def test_transient_identity_failure_retries(self):
        self.reject('unavailable')
        self.assertEqual(R.repeat(self.inquiry()),'')

    def test_recovery_advances_and_exhausts_without_redispatch(self):
        prior=self.inquiry(uniprot_query='gene:FAKE123 AND taxonomy_id:9606')
        source={'kind':'source_read','source':'UniProtKB REST','requested_query':prior['uniprot_query'],
                'records':[{'accession':'P00387','pdb_ids':['1UMK']}]}
        reflection={'kind':'reflection','inquiry':prior,'next_question':prior['question']}
        pathlib.Path(C.NOTEBOOK).write_text(json.dumps(source)+'\n'+json.dumps(reflection)+'\n')
        result={'status':'unresolved','symbol':'FAKE123','reason':'fixture identity rejected','receipt_ids':['rejection-1']}
        with patch.object(C,'_ground_inquiry',return_value=result) as ground:
            routes=[]
            for _ in range(5):
                candidate=C._next_evidence_work({},R,None,None)
                if candidate:
                    routes.append(candidate['source_query']['source'])
                    C._held_to_plan('','',candidate,{},None,None,R)
                importlib.reload(R) # new process-equivalent ledger read
        self.assertEqual(routes,['pdb','interpro'])
        self.assertEqual(ground.call_count,2)
        self.assertIsNone(C._next_evidence_work({},R,None,None))


    def verified_receipt(self, taxon=9606, symbol='FAKE123', aliases=None):
        return S.receipt('ncbi_gene_identity', {'symbol':'FAKE123','taxon_id':9606},
            [{'gene_id':'123','symbol':symbol,'taxon_id':taxon,'aliases':aliases or []}],
            metadata={'status':'verified','match_count':1,'service':'NCBI_Gene'})

    def test_stale_refusal_cannot_renew_expiry(self):
        refused=self.reject()
        original=R._tail(R.LOOKUPS)[-1]
        start=R._when(original)
        # An already-suppressed object retaining its identity_check is not validation.
        R.record(refused, now=start+timedelta(days=6), refused='repeat: unchanged')
        # Even a validation using the same cached receipt cannot renew the decision.
        R.record(refused, now=start+timedelta(days=6), refused='cached negative', identity_validated=True)
        decisions=[r for r in R._tail(R.LOOKUPS) if r.get('identity_refusal')]
        self.assertEqual([r['at'] for r in decisions],[original['at']])
        self.assertEqual(R.repeat(self.inquiry(),now=start+timedelta(days=8)), '')
        # A genuinely new validation receipt can start a new decision window.
        fresh=dict(refused,identity_check=dict(refused['identity_check'],receipt_ids=['rejection-2']))
        R.record(fresh,now=start+timedelta(days=8),refused='new negative',identity_validated=True)
        self.assertIn('unresolved',R.repeat(self.inquiry(),now=start+timedelta(days=8)))

    def test_legacy_refusal_needs_one_fresh_failure(self):
        legacy={'at':datetime.now(timezone.utc).isoformat(),'lookup':'','words':[],
                'question':self.inquiry()['question'],'refused':'old identity rejection'}
        pathlib.Path(R.LOOKUPS).write_text(json.dumps(legacy)+'\n')
        self.assertEqual(R.repeat(self.inquiry()),'')
        self.reject()  # asserts exactly one grounding call
        self.assertIn('unresolved',R.repeat(self.inquiry()))

    def test_release_requires_real_human_exact_receipt(self):
        self.reject()
        path=pathlib.Path(R.ROOT,'source-receipts.jsonl')
        cases=[{'source':'ncbi_gene_identity','query':{'symbol':'FAKE123'},
                'retrieved_at':datetime.now(timezone.utc).isoformat(),'metadata':{'status':'verified'}},
               self.verified_receipt(taxon=10090),self.verified_receipt(symbol='OTHER123')]
        tampered=self.verified_receipt();tampered['records'][0]['symbol']='OTHER123'
        cases.append(tampered)
        for receipt in cases:
            path.write_text(json.dumps(receipt)+'\n')
            self.assertIn('unresolved',R.repeat(self.inquiry()))
        valid=self.verified_receipt(symbol='CANONICAL1',aliases=['FAKE123'])
        self.assertTrue(S.verified_human_identity(valid,'FAKE123'))
        path.write_text(json.dumps(valid)+'\n')
        self.assertEqual(R.repeat(self.inquiry()),'')

    def test_beta_does_not_rewrite_longer_tokens(self):
        for text in (r'\betamax',r'\beta2',r'\beta_name',r'\x08etamax',
                     '\beta2',r'prefix\beta',r'\\beta'):
            self.assertEqual(S.normalize_protein_notation(text),text)
        for text in (r'$\beta$-galactosidase',r'\beta-galactosidase','\beta-galactosidase'):
            self.assertEqual(S.normalize_protein_notation(text),'β-galactosidase')

    def test_semantic_key_case_spacing_and_unicode(self):
        a=self.inquiry(uniprot_query='gene:FAKE123 AND organism_id:9606')
        b=self.inquiry(question=a['question'].lower(),
             uniprot_query=' GENE : fake123  and taxonomy_id : 9606 ',
             source_query={'source':'PDB','entry_id':' 1umk ','operation':'STRUCTURE_EVIDENCE'})
        self.assertEqual(R.identity_refusal_key(a),R.identity_refusal_key(b))
        a=self.inquiry(uniprot_query='protein_name:"café β-galactosidase" AND organism_id:9606')
        b=self.inquiry(uniprot_query='protein_name:"cafe\u0301 β-galactosidase" AND taxonomy_id:9606')
        self.assertEqual(R.identity_refusal_key(a),R.identity_refusal_key(b))

    def test_repeat_helpers_do_not_import_second_main(self):
        import builtins, types
        original=builtins.__import__
        def guarded(name,*a,**kw):
            if name=='chemistry_lab': raise AssertionError('second Lab module import')
            return original(name,*a,**kw)
        main=types.ModuleType('__main__');main.__file__='/installed/scripts/chemistry_lab.py'
        calls=[]
        def convert(*a): calls.append(a);return {'source':'uniprot','query':'gene:TP53'}
        main.uniprot_from_plugin=convert
        with patch.dict(sys.modules,{'__main__':main}),patch.object(builtins,'__import__',guarded):
            R.identity_refusal_key(self.inquiry())
            R.lookup_key({'plugin_query':{'plugin':'uniprot','arguments':{'gene':'TP53'}}})
        self.assertEqual(len(calls),1)


    def test_expired_same_receipt_revalidation_is_bounded(self):
        prior=self.inquiry(uniprot_query='gene:FAKE123 AND taxonomy_id:9606')
        source={'kind':'source_read','source':'UniProtKB REST','requested_query':prior['uniprot_query'],
                'records':[{'accession':'P00387','pdb_ids':['1UMK']}]}
        reflection={'kind':'reflection','inquiry':prior,'next_question':prior['question']}
        pathlib.Path(C.NOTEBOOK).write_text(json.dumps(source)+'\n'+json.dumps(reflection)+'\n')
        negative={'status':'unresolved','symbol':'FAKE123','reason':'same receipt rejection',
                  'receipt_ids':['unchanged-receipt']}
        old=datetime.now(timezone.utc)-timedelta(days=8)
        for spec in ({'source':'pdb','entry_id':'1UMK','operation':'structure_evidence'},
                     {'source':'interpro','accession':'P00387'}):
            R.record(self.inquiry(source_query=spec,identity_check=negative),now=old,
                     refused='old validation',identity_validated=True)
        routes=[]
        with patch.object(C,'_ground_inquiry',return_value=negative) as ground:
            for _ in range(4):
                candidate=C._next_evidence_work({},R,None,None)
                if candidate:
                    routes.append(candidate['source_query']['source'])
                    C._held_to_plan('','',candidate,{},None,None,R)
        self.assertEqual(routes,['pdb','interpro'])
        self.assertEqual(ground.call_count,2)
        self.assertIsNone(C._next_evidence_work({},R,None,None))

    def test_real_grounding_refreshes_eight_day_receipt(self):
        old=S.receipt('ncbi_gene_identity',{'symbol':'FAKE123','taxon_id':9606},[],
                      metadata={'status':'unresolved','match_count':0,'service':'NCBI_Gene'})
        old['retrieved_at']=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
        pathlib.Path(R.ROOT,'source-receipts.jsonl').write_text(json.dumps(old)+'\n')
        fresh=S.receipt('ncbi_gene_identity',{'symbol':'FAKE123','taxon_id':9606},[],
                        metadata={'status':'unresolved','match_count':0,'service':'NCBI_Gene'})
        with patch.object(S.Sources,'human_gene_identity',return_value=fresh) as provider:
            first=C._ground_inquiry(self.inquiry())
            second=C._ground_inquiry(self.inquiry())
        self.assertEqual(provider.call_count,1)
        self.assertEqual(first['receipt_ids'],[fresh['receipt_id']])
        self.assertEqual(second['receipt_ids'],[fresh['receipt_id']])
        self.assertNotEqual(first['receipt_ids'],[old['receipt_id']])

if __name__=='__main__': unittest.main()

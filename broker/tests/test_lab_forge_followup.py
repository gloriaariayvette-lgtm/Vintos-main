"""Observed question follows existing strict browse and coverage assessment; wrapper stays open."""
import copy,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_lab_forge_consumer as fixture
from test_lab_query_perimeter import C
import lab_forge_consumer as F
from lab_sources import receipt
from forge_lab_handback import ownership

class Followup(fixture.Consumer):
    def setUp(self):
        super().setUp()
        self.science='Does the SLC26A19 gene exist in the human genome, and what is its structural topology or functional context if it does?'
        self.original="The Lab needs an instrument it does not have: A genomic sequence database to verify SLC26A19.\nIt came up on this question: "+self.science+'\nBuild or connect this capability for him; do not write up the question and do not claim discovery.'
        owners=C._load(self.outbox,{});owners['owned']['question']=self.original
        self.row.update(original_request=self.original,ownership_sha256=ownership(owners['owned']))
        self.row['artifact']['lab_handback']['original_request']=self.original
        C._atomic(self.outbox,owners);C._atomic(self.ledger,{self.cycle:self.row})
    def test_unresolved_checkpoint_resumes_on_new_authoritative_evidence_then_executes_assessment(self):
        empty=receipt('ncbi_gene_identity',{'symbol':'SLC26A19','taxon_id':9606},[],metadata={'status':'unresolved'})
        verify=Mock(return_value=empty)
        F.consume_one(C,verify=verify)
        self.assertEqual(F.consume_one(C,verify=verify)['kind'],'forge_followup_blocked')
        self.assertIsNone(F.consume_one(C,verify=verify));verify.assert_called_once()
        # A numbered sibling is not resumption evidence.
        def evidence(symbol):return receipt('ncbi_gene_identity',{'symbol':symbol,'taxon_id':9606},
            [{'gene_id':'123','symbol':symbol,'taxon_id':9606,'aliases':[]}],
            metadata={'status':'verified','service':'NCBI_Gene','match_count':1})
        path=str(Path(C.ROOT)/'source-receipts.jsonl');C._append(path,evidence('SLC26A4'))
        self.assertIsNone(F.consume_one(C,verify=verify))
        C._append(path,evidence('SLC26A19'))
        query='gene:SLC26A19 AND taxonomy_id:9606'
        raw=[{'primaryAccession':'Q00000','organism':{'taxonId':9606},'genes':[{'geneName':{'value':'SLC26A19'}}]}]
        browse={'records':[{'accession':'Q00000','taxon_id':9606}],
            'source_receipt':receipt('uniprot',{'requested_query':query,'executed_query':query},raw)}
        with patch.object(C,'_browse',return_value=browse) as read,patch.object(C,'lab_context',return_value=({},{})), \
             patch.object(C,'_reflect',return_value={'evidence_status':'answered','coverage_check':{'answered':True}}) as assess:
            self.assertEqual(F.consume_one(C)['kind'],'forge_followup_assessment_pending')
            read.assert_called_once_with(query,4,allow_relaxation=False)
            self.assertEqual(F.consume_one(C)['kind'],'forge_followup_blocked')
            self.assertEqual(assess.call_args.args[1]['question'],self.science)
            self.assertIsNone(F.consume_one(C));read.assert_called_once();assess.assert_called_once()
        row=C._load(self.ledger,{})[self.cycle]
        self.assertTrue(row['continuation']['scientific_question_answered'])
        self.assertFalse(row['verification']['original_request_fulfilled'])
        self.assertFalse(row['continuation']['original_request_fulfilled'])
        self.assertIn('capability build/connect evidence',row['continuation']['blockers'])
        self.assertIn('sequence-handle binding',row['continuation']['blockers'])
    def test_real_strict_browse_does_not_relax_an_empty_target_lookup(self):
        import json
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps({'results':[]}).encode()
        with patch.object(C.urllib.request,'urlopen',return_value=Response()) as fetch:
            got=C._browse('gene:SLC26A19 AND taxonomy_id:9606',4,allow_relaxation=False)
        self.assertEqual(got['records'],[]);fetch.assert_called_once()

for name in list(fixture.Consumer.__dict__):
    if name.startswith('test_'):setattr(Followup,name,None)
if __name__=='__main__':unittest.main()

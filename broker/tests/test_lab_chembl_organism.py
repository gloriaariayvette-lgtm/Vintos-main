"""ChEMBL target search takes the organism the connector's schema offers (2026-10-13). The Lab refused any search
naming one ("unsupported ChEMBL target-search arguments"), every time, and the failure sat in his open intentions.
Isolation: HOME is throwaway; the fetch is a recorder; nothing is sent."""
import json,os,pathlib,sys,tempfile,unittest
scratch=tempfile.TemporaryDirectory(prefix='lab-chembl-')
os.environ.update(HOME=scratch.name,SPARK_WORKSPACE=scratch.name+'/workspace')
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'scripts'))
import chemistry_lab as C, lab_sources as S
def denied(*a,**k):raise AssertionError('network forbidden')
C.urllib.request.urlopen=denied

class Organism(unittest.TestCase):
    def test_plugin_call_with_organism_is_accepted(self):
        spec=C.chembl_from_plugin({'plugin':'chembl','tool':'chembl_search_targets',
                                   'arguments':{'target_name':'CFTR','organism':'Homo sapiens','limit':2}})
        self.assertEqual(spec['organism'],'Homo sapiens');self.assertEqual(spec['term'],'CFTR')
    def test_unknown_arguments_are_still_refused(self):
        with self.assertRaisesRegex(ValueError,'unsupported ChEMBL'):
            C.chembl_from_plugin({'plugin':'chembl','tool':'chembl_search_targets','arguments':{'target_name':'CFTR','species':'x'}})
    def test_the_filter_reaches_chembl(self):
        urls=[]
        def fetch(url):
            urls.append(url)
            return {'targets':[{'target_chembl_id':'CHEMBL4051','pref_name':'CFTR','organism':'Homo sapiens','target_type':'SINGLE PROTEIN'}],
                    'page_meta':{'total_count':1}},{}
        got=S.Sources(fetch=fetch).query({'source':'chembl','operation':'search_targets','term':'CFTR','organism':'Homo sapiens','limit':2})
        self.assertIn('organism__icontains=Homo+sapiens',urls[0])
        self.assertIn('CHEMBL4051',json.dumps(got))

if __name__=='__main__':unittest.main()

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

def plan(**args):
    return C.chembl_from_plugin({'plugin':'chembl','tool':'chembl_search_targets','arguments':args})

class QueryWords(unittest.TestCase):
    """The planner named the search word `term` (19 October, F-70cbe17adc): the whole Lab turn faulted, because only
    target_name was taken. The words PubMed and UniProt already take stand in for a missing target_name."""
    def test_the_usual_search_words_name_the_target(self):
        for key in ('term','query','q'):
            self.assertEqual(plan(**{key:'CFTR'})['term'],'CFTR',key)
    def test_a_target_name_wins_over_an_alias(self):
        self.assertEqual(plan(target_name='CFTR',term='KCNQ1')['term'],'CFTR')
    def test_aliases_go_in_their_existing_order(self):
        self.assertEqual(plan(term='KCNQ1',query='CFTR')['term'],'CFTR')   # query comes before term
    def test_a_blank_or_missing_target_name_falls_back(self):
        self.assertEqual(plan(target_name='  ',term='CFTR')['term'],'CFTR')
        self.assertEqual(plan(target_name=None,term='CFTR')['term'],'CFTR')
    def test_a_non_string_alias_is_passed_over_for_a_string_one(self):
        self.assertEqual(plan(query=['CFTR'],term='KCNQ1')['term'],'KCNQ1')
    def test_a_malformed_target_name_still_fails(self):
        for bad in (['CFTR'],7,True):
            with self.assertRaises(ValueError):plan(target_name=bad,term='KCNQ1')
    def test_no_name_at_all_still_fails(self):
        with self.assertRaises(ValueError):plan(term='')
        with self.assertRaises(ValueError):plan(limit=2)
    def test_an_unrelated_argument_is_still_named(self):
        with self.assertRaisesRegex(ValueError,'unsupported ChEMBL target-search arguments: species'):
            plan(term='CFTR',species='x')
    def test_limit_and_organism_are_still_checked(self):
        spec=plan(term='CFTR',organism='Homo sapiens',limit=2)
        self.assertEqual((spec['organism'],spec['limit']),('Homo sapiens',2))
        with self.assertRaises(ValueError):plan(term='CFTR',limit=99)
    def test_the_request_is_not_changed(self):
        args={'term':'CFTR','limit':2}
        C.chembl_from_plugin({'plugin':'chembl','tool':'chembl_search_targets','arguments':args})
        self.assertEqual(args,{'term':'CFTR','limit':2})

class Isolation(unittest.TestCase):
    def test_throwaway_home_and_no_network(self):
        self.assertTrue(C.WS.startswith(scratch.name))
        with self.assertRaises(AssertionError):C.urllib.request.urlopen('https://www.ebi.ac.uk/')

if __name__=='__main__':unittest.main()

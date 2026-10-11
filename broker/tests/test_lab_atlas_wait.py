"""Recorded Atlas hold must yield its slot without releasing scientific holds."""
from pathlib import Path
import copy,json,os,socket,subprocess,sys,tempfile,unittest
from unittest.mock import patch
scratch=tempfile.TemporaryDirectory(prefix='lab-atlas-wait-')
os.environ.update(HOME=scratch.name,SPARK_WORKSPACE=scratch.name+'/workspace',VINTOS_SECRETS=scratch.name+'/secrets')
def forbidden(*a,**k):raise AssertionError('External operation forbidden')
socket.socket.connect=forbidden;socket.create_connection=forbidden;subprocess.Popen=forbidden
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import chemistry_lab as C
C._ask=forbidden;C.urllib.request.urlopen=forbidden
assert C.ROOT.startswith(scratch.name)
fixture=json.loads((Path(__file__).parent/'fixtures/lab_oct11_atlas_wait.json').read_text())
def event(kind,atlas=False,source=None):
    return {'kind':kind,'atlas_turn':atlas,'inquiry':{'source_query':{'source':source} if source else {}}}
class AtlasWait(unittest.TestCase):
    def setUp(self):
        self.config=patch.object(C,'config',return_value={'alphagenome_key_file':'configured-not-read'});self.config.start();self.addCleanup(self.config.stop)
    def test_recorded_scheduled_wait_yields_without_mutation(self):
        before=copy.deepcopy(fixture);self.assertFalse(C.atlas_turn_due(fixture));self.assertEqual(fixture,before)
    def test_repeated_scheduled_waits_do_not_pin_slot(self):
        self.assertFalse(C.atlas_turn_due([event('inquiry')]*3+[event('evidence_wait',True)]*8))
    def test_unrelated_wait_does_not_spend_atlas_opportunity(self):
        self.assertTrue(C.atlas_turn_due([event('inquiry')]*3+[event('evidence_wait')]))
    def test_existing_refusal_cadence_unchanged(self):
        for n in range(4):self.assertEqual(C.atlas_turn_due([event('inquiry_refused',True)]+[event('inquiry')]*n),n>=2)
    def test_two_further_accepted_questions_restore_atlas(self):
        hist=[event('evidence_wait',True)]
        self.assertFalse(C.atlas_turn_due(hist+[event('inquiry')]))
        self.assertTrue(C.atlas_turn_due(hist+[event('inquiry')]*2))
    def test_atlas_source_wait_without_flag_yields(self):
        self.assertFalse(C.atlas_turn_due([event('inquiry')]*3+[event('evidence_wait',source='atlas')]))
    def test_no_atlas_configuration_disables_schedule(self):
        with patch.object(C,'config',return_value={}):self.assertFalse(C.atlas_turn_due([event('inquiry')]*3))
    def test_held_question_and_no_followup_policy_unchanged(self):
        hist=[event('inquiry')]*3+[dict(event('evidence_wait',True),inquiry={'atlas_turn':True,'coverage_deferred':True,'refused':'full evidence held','question':'SLC26A5 (Pendrin) original question'},evidence_gap={'automatic_followup':False})]
        before=copy.deepcopy(hist);self.assertFalse(C.atlas_turn_due(hist));self.assertEqual(hist,before)
if __name__=='__main__':unittest.main()

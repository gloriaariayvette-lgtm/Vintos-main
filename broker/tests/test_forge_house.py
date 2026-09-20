#!/usr/bin/env python3
"""Broad Forge intake: scratch stores, fake transport and model, no host effects."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import forge_house as house
import skill_forge as sf
from forge_loop import Controller
from forge_loop_runtime import Runtime, ReportBuilder
from forge_loop_atelier import AtelierProjection

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve(); self.owner='o'*40
        self.c=Controller(self.root/'loop.db',self.owner,'w'*40,'https://fixture.invalid')
        self.r=Runtime(self.c,AtelierProjection(self.root/'atelier'),ReportBuilder(self.model))
        for name,value in [('MEMORY',str(self.root)),('PROPOSALS',str(self.root/'proposals.json'))]:
            p=patch.object(sf,name,value);p.start();self.addCleanup(p.stop)
        p=patch.object(house,'request',self.request);p.start();self.addCleanup(p.stop)
        p=patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden'));p.start();self.addCleanup(p.stop)
        self.assertEqual(house.request,self.request)
        self.assertTrue(Path(sf.PROPOSALS).is_relative_to(self.root))
        self.assertTrue(self.c.path.is_relative_to(self.root))
        self.want={'id':'w1','source':'latent_thread','want':'I want to email a collaborator',
                   'steps':[{'capability':'web_search','note':'find public contact details','status':'completed'}],
                   'current_step_index':1}
        self.path=self.root/'current-wants.json';self.path.write_text(json.dumps([self.want]))
    def request(self,path,body):
        if path=='/api/wants-sync':return self.r.sync_wants(self.owner,body['rows'],body['inventory'])
        if path=='/api/gaps-sync':return self.r.sync_gaps(self.owner,body['rows'])
        raise AssertionError(path)
    def model(self,system,user):
        return {'missing':True,'capability':'send_email','note':'send the prepared message to the authorized collaborator',
                'execution':'external','expected_output':'provider delivery receipt','acceptance':'authorized fixture delivery',
                'reason':'Search can find a public address but cannot send a message'}
    def test_real_want_gap_proposal_no_fake_fulfillment_and_replay(self):
        house.sync(inventory=['web_search'])
        pid=self.c.ready_queue('w'*40)[0];self.r.step(pid)
        house.sync(inventory=['web_search'])
        want=json.loads(self.path.read_text())[0]
        self.assertEqual(want['want'],self.want['want'])
        self.assertFalse(want.get('fulfilled',False))
        self.assertEqual(want['steps'][0]['status'],'completed')
        self.assertEqual(want['steps'][1]['capability'],'send_email')
        self.assertEqual(want['blocked']['blocked_step'],'send_email')
        proposals=sf._load();self.assertEqual(len(proposals),1)
        self.assertEqual(proposals[0]['origin']['want_id'],'w1')
        self.assertIsNone(sf.approve(proposals[0]['id'])[0])
        house.sync(inventory=['web_search'])
        self.assertEqual(len(sf._load()),1)
        self.assertEqual(len(json.loads(self.path.read_text())[0]['steps']),2)
    def test_changed_want_invalidates_assessment(self):
        house.sync(inventory=['web_search'])
        pid=self.c.ready_queue('w'*40)[0];self.r.step(pid)
        self.want['want']='I want to write privately'
        self.path.write_text(json.dumps([self.want]))
        house.sync(inventory=['web_search'])
        self.assertEqual(sf._load(),[])
        self.assertNotIn('blocked',json.loads(self.path.read_text())[0])
        self.assertEqual(self.c.status(self.owner,pid)['state'],'cancelled')
    def test_installed_action_is_not_a_missing_capability(self):
        house.sync(inventory=['web_search','send_email'])
        pid=self.c.ready_queue('w'*40)[0]
        with self.assertRaises(ValueError):self.r.step(pid)
        self.assertEqual(sf._load(),[])
    def test_no_gap_completes_assessment_only(self):
        self.r.builder=ReportBuilder(lambda *a:{**self.model(*a),'missing':False,'capability':''})
        house.sync(inventory=['web_search']);pid=self.c.ready_queue('w'*40)[0];self.r.step(pid)
        self.assertEqual(self.c.status(self.owner,pid)['state'],'complete')
        self.assertFalse(json.loads(self.path.read_text())[0].get('fulfilled',False))

if __name__=='__main__':unittest.main()

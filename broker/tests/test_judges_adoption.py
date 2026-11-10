#!/usr/bin/env python3
"""Synthetic offline owner-answer contracts; no private records or real sender."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[2]

def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
CLI=ROOT/'experiments/nonllm-judges/adoption.py'
A=load('adoption_test',CLI)
FIX=load('adoption_fixture',ROOT/'broker/tests/test_nonllm_private_run.py')
R=FIX.P
KEY=bytes(range(32))  # Synthetic fixture only, never a configured signing credential.
END='2020-01-11';CUTOFF='2020-01-11T06:00:00Z';OBSERVED='2020-01-11T06:30:00Z';LATER='2020-02-01T00:00:00Z'


def fixture():
    bundle,_=FIX.fixture()
    bundle['numerical_evidence']['reference_ids']=[r['turn_id'] for r in bundle['rows'] if r['role']=='assistant' and int(r['turn_id'].split('-')[1])<6]
    for i,e in enumerate(bundle['embeddings']):e['vector']=[1.,0.] if i//2<6 else [-1.,0.]
    private,_=R.evaluate(bundle,None,CUTOFF)
    private['manifest']={'cutoff':R.P.stamp(CUTOFF)}
    return bundle,private,A.build(bundle,private,END)


def answers(digest,decision='growth',observed=OBSERVED):
    return dict(schema='adoption-answers-v1',digest_sha256=A.sha(A.canonical(digest)),answers=[dict(window_id=w['window_id'],actor='owner',decision=decision,observed_at=observed) for w in digest['windows']])


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base=fixture()
    def setUp(self):
        self.bundle,self.run,self.digest=copy.deepcopy(self.base)
        self.tmp=tempfile.TemporaryDirectory(prefix='adoption-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700);self.assertNotIn('.vintos',self.root.parts)
        self.sender=Mock(side_effect=AssertionError('network forbidden'))
        guard=patch.object(socket.socket,'connect',self.sender);guard.start();self.addCleanup(guard.stop)
        self.assertIs(socket.socket.connect,self.sender);self.addCleanup(self.sender.assert_not_called)
    def signed(self,decision='growth',observed=OBSERVED):return A.sign(self.digest,answers(self.digest,decision,observed),KEY)
    def project(self,decision='growth',cutoff=LATER):return A.project(self.digest,self.signed(decision),KEY,cutoff)
    def put(self,name,value):
        path=self.root/name;path.write_text(json.dumps(value));path.chmod(0o600);return path
    def cli(self,command,out,**options):
        args=[sys.executable,str(CLI),command,'--scratch',str(self.root),'--output',str(self.root/out)]
        args += [part for k,v in options.items() for part in ('--'+k.replace('_','-'),str(v))]
        return subprocess.run(args,capture_output=True,text=True,timeout=40,
            env=dict(os.environ,SPARK_WORKSPACE=str(self.root),PYTHONDONTWRITEBYTECODE='1'))
    def test_digest_recovers_entire_sustained_run_and_exact_members(self):
        self.assertEqual(len(self.digest['windows']),1);w=self.digest['windows'][0]
        self.assertEqual((w['start_date'],w['end_date']),('2020-01-07','2020-01-10'))
        self.assertEqual(len(w['members']),8)
        self.assertEqual(sum(d['sustained_shift'] for d in self.run['views']['primary_10s']['voice_drift_receipts']['drift']),1)
        expected={r['turn_id']:FIX.sha(r['content']) for r in self.bundle['rows'] if r['role']=='assistant'}
        self.assertTrue(all(expected[m['node_id']]==m['content_sha256'] for m in w['members']))
    def test_digest_phone_text_has_only_dates_scope_and_fixed_words(self):
        text=A.render(self.digest)
        for forbidden in ('reply-', 'sha256', 'synthetic', 'vector', 'reference_version', str(self.root)):
            self.assertNotIn(forbidden,text)
        self.assertIn('everyday/avatar: his voice moved',text)
        self.assertIn('Growth · Not him · Not sure',text)
        before=copy.deepcopy(self.bundle);A.build(self.bundle,self.run,END);self.assertEqual(before,self.bundle)
    def test_counts_only_cannot_build_or_forge_private_flags(self):
        with self.assertRaises((ValueError,KeyError)):A.build(self.bundle,{'schema':'numerical-counts-v1'},END)
        self.run['views']['primary_10s']['voice_drift_receipts']['drift'][-1]['sustained_shift']=False
        with self.assertRaises(ValueError):A.build(self.bundle,self.run,END)
    def test_changed_cache_and_unknown_ancestry_refuse_stale_run(self):
        self.bundle['embeddings'][15]['vector']=[1.,0.]
        with self.assertRaises(ValueError):A.build(self.bundle,self.run,END)
        self.bundle=copy.deepcopy(self.base[0]);self.bundle['numerical_evidence']['nodes'][-15]['complete']=False
        with self.assertRaises(ValueError):A.build(self.bundle,self.run,END)
    def test_wrong_week_and_unknown_view_refused(self):
        for end,view in [('2020-01-12','primary_10s'),(END,'all')]:
            with self.assertRaises(ValueError):A.build(self.bundle,self.run,end,view)
        other=A.build(self.bundle,self.run,END,'window30')
        with self.assertRaises(ValueError):A.project(other,self.signed(),KEY,LATER)
    def test_no_shift_empty_digest_has_no_fabricated_answers(self):
        for e in self.bundle['embeddings']:e['vector']=[1.,0.]
        private,_=R.evaluate(self.bundle,None,CUTOFF);private['manifest']={'cutoff':R.P.stamp(CUTOFF)}
        digest=A.build(self.bundle,private,END);self.assertFalse(digest['windows'])
        self.assertIn('No sustained change',A.render(digest));self.assertFalse(A.sign(digest,answers(digest),KEY)['receipts'])
    def test_growth_only_and_no_answer_defaults(self):
        for choice,n in [('growth',1),('not him',0),('not sure',0)]:
            projection,counts=self.project(choice);self.assertEqual(len(projection['adoptions']),n)
            text=json.dumps(counts)
            for private in ('reply-','sha256','2020-',KEY.hex(),'avatar','score','vector'):self.assertNotIn(private,text)
        empty=answers(self.digest);empty['answers']=[]
        self.assertFalse(A.sign(self.digest,empty,KEY)['receipts'])
    def test_unknown_automatic_duplicate_and_unbound_answers_refused(self):
        for key,val in [('decision','adopt'),('actor','automatic'),('window_id','0'*64),('observed_at','2020-01-10T12:00:00Z'),('observed_at','2020-01-11T12:00:00')]:
            a=answers(self.digest);a['answers'][0][key]=val
            with self.assertRaises(ValueError):A.sign(self.digest,a,KEY)
        a=answers(self.digest);a['answers']*=2
        with self.assertRaises(ValueError):A.sign(self.digest,a,KEY)
        a=answers(self.digest);a['digest_sha256']='0'*64
        with self.assertRaises(ValueError):A.sign(self.digest,a,KEY)
    def test_signature_wrong_key_and_every_bound_field_tamper_refused(self):
        with self.assertRaises(ValueError):A.project(self.digest,self.signed(),b'x'*32,LATER)
        for field,value in [('decision','not him'),('observed_at','2020-01-12T00:00:00Z'),('view','window30'),('timezone','UTC'),('eligible_from_day','2020-01-11'),('actor','automatic'),('digest_sha256','0'*64)]:
            signed=self.signed();signed['receipts'][0]['payload'][field]=value
            with self.assertRaises(ValueError):A.project(self.digest,signed,KEY,LATER)
        signed=self.signed();signed['receipts'][0]['payload']['window']['members'][0]['content_sha256']='0'*64
        with self.assertRaises(ValueError):A.project(copy.deepcopy(self.base[2]),signed,KEY,LATER)
    def test_even_valid_mac_cannot_bypass_bound_window_or_time(self):
        for field,value in [('decision','automatic'),('observed_at','2020-01-09T00:00:00Z'),('eligible_from_day','2020-01-11')]:
            signed=self.signed();r=signed['receipts'][0];r['payload'][field]=value;r['signature']=A.signature(r['payload'],KEY)
            with self.assertRaises(ValueError):A.project(self.digest,signed,KEY,LATER)
    def test_duplicate_receipt_idempotent_conflicting_answer_refuses(self):
        signed=self.signed();signed['receipts']*=2
        out,counts=A.project(self.digest,signed,KEY,LATER)
        self.assertEqual(len(out['adoptions']),1);self.assertEqual(counts['counts']['duplicate_receipts'],1)
        signed['receipts'].append(self.signed('not him')['receipts'][0])
        with self.assertRaises(ValueError):A.project(self.digest,signed,KEY,LATER)
    def test_cutoff_and_next_local_day_not_utc_day(self):
        signed=self.signed(observed='2020-01-12T05:59:59Z')
        p=signed['receipts'][0]['payload'];self.assertEqual(p['eligible_from_day'],'2020-01-12')
        for cutoff in ['2020-01-12T05:59:59Z','2020-01-12T05:59:59.999Z']:
            self.assertFalse(A.project(self.digest,signed,KEY,cutoff)[0]['adoptions'])
        self.assertEqual(len(A.project(self.digest,signed,KEY,'2020-01-12T06:00:00Z')[0]['adoptions']),1)
    def test_review_day_across_dst_transition_is_calendar_based(self):
        for observed,expected in [('2020-11-01T01:30:00-05:00','2020-11-02'),
                                  ('2020-11-01T01:30:00-06:00','2020-11-02'),
                                  ('2020-03-08T01:30:00-06:00','2020-03-09')]:
            receipt=self.signed(observed=observed)['receipts'][0]
            self.assertEqual(receipt['payload']['eligible_from_day'],expected)

    def test_real_offline_replay_same_day_unchanged_later_day_only(self):
        adoptions=self.project()[0]['adoptions']
        _,_,_,sup,ev,nodes,fe,encoder,_,_=R.adapt(self.bundle,LATER)
        _,before=R.V.analyze(ev,nodes,fe,encoder,sup['reference_ids'],LATER,zone=self.bundle['timezone'])
        report,after=R.V.analyze(ev,nodes,fe,encoder,sup['reference_ids'],LATER,zone=self.bundle['timezone'],adoptions=adoptions*2)
        self.assertEqual(report['drift']['reference_revisions'],1)
        self.assertEqual(after['revisions'][0]['effective_day'],'2020-01-12')
        self.assertEqual([r for r in before['voice'] if r['day']<='2020-01-11'],[r for r in after['voice'] if r['day']<='2020-01-11'])
        for choice in ('not him','not sure'):
            _,unchanged=R.V.analyze(ev,nodes,fe,encoder,sup['reference_ids'],LATER,zone=self.bundle['timezone'],adoptions=self.project(choice)[0]['adoptions'])
            self.assertEqual(before,unchanged)
    def test_digest_members_dates_overlap_and_bounds_validate(self):
        for mutate in ('hash','missing','overlap','scope','date','extra','bound'):
            d=copy.deepcopy(self.digest);w=d['windows'][0]
            if mutate=='hash':w['members'][0]['content_sha256']='0'*64
            elif mutate=='missing':w['members']=w['members'][2:]
            elif mutate=='overlap':d['windows'].append(copy.deepcopy(w))
            elif mutate=='scope':w['mode']='unknown'
            elif mutate=='date':w['end_date']='2020-01-11'
            elif mutate=='extra':w['text']='SYNTHETIC_PRIVATE'
            else:d['windows']*=513
            with self.assertRaises(ValueError):A.validate_digest(d)
    def test_cli_roundtrip_private_modes_counts_and_unchanged_inputs(self):
        b=self.put('input.json',self.bundle);r=self.put('run.json',self.run)
        result=self.cli('digest','digest-out',input=b,run=r,week_end=END)
        self.assertEqual(result.returncode,0,result.stderr)
        d=self.root/'digest-out/digest.json';self.assertEqual(json.loads(d.read_text()),self.digest)
        a=self.put('answers.json',answers(self.digest));k=self.put('key.json',dict(schema='adoption-signing-key-v1',key_hex=KEY.hex()))
        snapshots={p:p.read_bytes() for p in (b,r,d,a,k)}
        result=self.cli('sign','sign-out',digest=d,answers=a,key=k);self.assertEqual(result.returncode,0,result.stderr)
        signed=self.root/'sign-out/receipts.json'
        result=self.cli('verify','verify-out',digest=d,receipts=signed,key=k,cutoff=LATER)
        self.assertEqual(result.returncode,0,result.stderr);self.assertNotIn(KEY.hex(),result.stdout+result.stderr)
        self.assertEqual(json.loads((self.root/'verify-out/projection.json').read_text()),self.project()[0])
        for folder in ('digest-out','sign-out','verify-out'):
            self.assertEqual((self.root/folder).stat().st_mode&0o777,0o700)
            for p in (self.root/folder).iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)
        for p,data in snapshots.items():self.assertEqual(p.read_bytes(),data)
        self.assertNotEqual(self.cli('sign','sign-out',digest=d,answers=a,key=k).returncode,0)
    def test_cli_refuses_symlink_key_and_bad_permissions_sanitizes_errors(self):
        d=self.put('digest.json',self.digest);a=self.put('answers.json',answers(self.digest));k=self.put('key.json',dict(schema='adoption-signing-key-v1',key_hex=KEY.hex()))
        link=self.root/'linked-key';link.symlink_to(k)
        for candidate in (link,k):
            if candidate==k:k.chmod(0o644)
            res=self.cli('sign','refused',digest=d,answers=a,key=candidate)
            self.assertNotEqual(res.returncode,0);self.assertEqual(res.stderr.strip(),'adoption_refused')
            self.assertFalse((self.root/'refused').exists());self.assertNotIn(KEY.hex(),res.stdout+res.stderr)
    def test_cli_duplicate_json_and_outside_output_refused(self):
        d=self.put('digest.json',self.digest);d.write_text('{"schema":1,"schema":2}')
        k=self.put('key.json',dict(schema='adoption-signing-key-v1',key_hex=KEY.hex()));a=self.put('answers.json',answers(self.digest))
        self.assertNotEqual(self.cli('sign','refused',digest=d,answers=a,key=k).returncode,0)
        self.assertNotEqual(self.cli('sign','../outside-adoption',digest=d,answers=a,key=k).returncode,0)
    def test_key_schema_and_short_keys_refused(self):
        for k in ({'schema':'other','key_hex':KEY.hex()},{'schema':'adoption-signing-key-v1','key_hex':'00'}):
            with self.assertRaises(ValueError):A.key_bytes(k)
        with self.assertRaises(ValueError):A.sign(self.digest,answers(self.digest),b'short')


if __name__=='__main__':unittest.main()

#!/usr/bin/env python3
"""Synthetic authorized-snapshot projector tests; no real private store or sender."""
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
CLI=ROOT/'experiments/nonllm-judges/landings_project.py'
P=load('landings_project_test',CLI)
CUTOFF='2020-02-01T00:00:00Z'

def row(kind='message',ref='synthetic-ref',rating='landed',rid='synthetic-rating',at='2020-01-10T12:00:01Z',text='A synthetic complete piece.'):
    return dict(id=rid,at=at,surface=kind,ref=ref,rating=rating,why='SYNTHETIC_PRIVATE_WHY',before='SYNTHETIC_PRIVATE_BEFORE',
        piece=dict(type=kind,text=text),made={P.TEXT.get(kind,'prompt'):text},lead_up=[dict(gloria='SYNTHETIC_PRIVATE_CONTEXT')])
def binding(r,node='synthetic-node',at='2020-01-10T12:00:00Z'):
    return dict(surface=r['surface'],ref=r['ref'],node_id=node,content_sha256=P.sha(r['piece']['text']),finalized_at=at,identity_source_sha256=P.sha('synthetic identity receipt'))
def bindings(items):return dict(schema='landings-item-bindings-v1',items=items)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='landings-project-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.assertNotIn('.vintos',self.root.parts)
        self.sender=Mock(side_effect=AssertionError('network forbidden'))
        guard=patch.object(socket.socket,'connect',self.sender);guard.start();self.addCleanup(guard.stop)
        self.assertIs(socket.socket.connect,self.sender);self.addCleanup(self.sender.assert_not_called)
    def project(self,rows,items=None,zone=None):
        return P.project(rows,bindings(items if items is not None else [binding(rows[0])]),CUTOFF,zone)
    def test_three_text_kinds_exact_output_contract_no_private_words(self):
        rows=[row(kind=k,ref=k,rid=k) for k in P.TEXT]
        out,summary=self.project(rows,[binding(r,node='synthetic-'+r['surface']) for r in rows])
        self.assertEqual(len(out['anchors']),3)
        self.assertEqual(len({a['evidence_id'] for a in out['anchors']}),3)
        for a in out['anchors']:
            self.assertEqual(set(a),{'evidence_id','node_id','content_sha256','actor','witnessed','observed_at','source','value','link','source_record_sha256'})
            self.assertEqual((a['actor'],a['witnessed'],a['source'],a['value']),('owner',True,'landings','landed'))
        for value in (out,summary):
            text=json.dumps(value);self.assertNotIn('SYNTHETIC_PRIVATE',text);self.assertNotIn('A synthetic complete piece.',text)
        self.assertNotIn('synthetic-node',json.dumps(summary))
    def test_latest_nonpositive_supersedes_old_positive(self):
        for rating in ('partly','missed','unknown'):
            first=row();last=row(rating=rating,rid='second',at='2020-01-11T12:00:00Z')
            out,summary=self.project([first,last]);self.assertEqual(out['anchors'],[])
            self.assertEqual(summary['counts']['superseded_records'],1)
            self.assertEqual(summary['counts']['not_landed'],1)
    def test_latest_landed_after_nonpositive_uses_latest_identity(self):
        first=row(rating='missed');last=row(rid='second',at='2020-01-11T12:00:00Z')
        out,_=self.project([first,last]);self.assertEqual(len(out['anchors']),1)
        self.assertEqual(out['anchors'][0]['evidence_id'],'landings-'+P.sha('second'))
    def test_exact_and_future_cutoff_do_not_replace_historical_rating(self):
        for at in (CUTOFF,'2020-03-01T00:00:00Z'):
            out,summary=self.project([row(),row(rid='future',rating='missed',at=at)])
            self.assertEqual(len(out['anchors']),1);self.assertEqual(summary['counts']['at_or_after_cutoff'],1)
    def test_unknown_or_backward_order_cannot_resurrect_positive(self):
        for at in ('bad','2020-01-09T12:00:00Z','2020-01-11T12:00:00'):
            out,_=self.project([row(),row(rid='second',rating='missed',at=at)])
            self.assertFalse(out['anchors'])
    def test_naive_time_needs_reviewed_zone_and_dst_is_not_guessed(self):
        r=row(at='2020-01-10T06:00:01')
        self.assertFalse(self.project([r])[0]['anchors'])
        self.assertEqual(len(self.project([r],zone='America/Chicago')[0]['anchors']),1)
        for at in ('2020-11-01T01:30:00','2020-03-08T02:30:00'):
            with self.assertRaises(ValueError):P.instant(at,'America/Chicago')
    def test_frozen_full_text_hash_ref_and_kind_are_all_required(self):
        r=row();good=binding(r)
        for field,value in [('ref','another'),('content_sha256','0'*64),('surface','joke')]:
            b=dict(good);b[field]=value
            self.assertFalse(self.project([r],[b])[0]['anchors'])
        for change in ('missing','edited','made_mismatch','truncated'):
            r=row()
            if change=='missing':r.pop('piece')
            elif change=='edited':r['piece']['text']+='!'
            elif change=='made_mismatch':r['made']['message']='different'
            else:r['piece']['text']=r['piece']['text'][:5];r['made']['message']=r['piece']['text']
            self.assertFalse(self.project([r],[good])[0]['anchors'])
    def test_no_binding_or_unknown_identity_receipt(self):
        self.assertFalse(self.project([row()],[])[0]['anchors'])
        b=binding(row());b.pop('identity_source_sha256')
        with self.assertRaises(ValueError):self.project([row()],[b])
    def test_rating_before_act_no_media_or_empty_explanation(self):
        b=binding(row(),at='2020-01-11T12:00:00Z')
        self.assertFalse(self.project([row()],[b])[0]['anchors'])
        for k in ('image','song','video'):
            out,summary=self.project([row(kind=k)],[]);self.assertFalse(out['anchors'])
            self.assertEqual(summary['counts']['unsupported_media_or_kind'],1)
        r=row();r['why']=' ';self.assertFalse(self.project([r])[0]['anchors'])
    def test_duplicate_records_deduplicate_conflicting_identity_refuses(self):
        r=row();out,summary=self.project([r,r]);self.assertEqual(len(out['anchors']),1)
        self.assertEqual(summary['counts']['duplicate_records'],1)
        other=copy.deepcopy(r);other['rating']='missed'
        with self.assertRaises(ValueError):self.project([r,other])
    def test_conflicting_binding_and_aliases_refuse(self):
        b=binding(row());other=dict(b,node_id='other')
        with self.assertRaises(ValueError):self.project([row()],[b,other])
        other=dict(b,ref='another')
        with self.assertRaises(ValueError):self.project([row()],[b,other])
    def test_actual_downstream_taste_accepts_projected_anchors(self):
        F=load('landings_fixture',ROOT/'broker/tests/test_nonllm_private_run.py')
        bundle,_=F.fixture();rows=[];items=[]
        for index,r in enumerate([r for r in bundle['rows'] if r['role']=='assistant'][:8:2]):
            at=datetime.fromtimestamp(r['timestamp'],timezone.utc)
            observed=datetime.fromtimestamp(r['timestamp']+10,timezone.utc).isoformat()
            native=row(ref='synthetic-'+str(index),rid='synthetic-'+str(index),at=observed,text=r['content'])
            rows.append(native);items.append(binding(native,node=r['turn_id'],at=at.isoformat()))
        out,summary=self.project(rows,items)
        _,counts=F.P.evaluate(bundle,out,CUTOFF)
        self.assertEqual(summary['counts']['projected_positive_anchors'],4)
        self.assertEqual(counts['views']['window30']['facets']['taste']['positive_acts'],4)
    def command(self):
        self.source=self.root/'snapshot.jsonl';self.source.write_text(json.dumps(row())+'\n');self.source.chmod(0o600)
        self.mapping=self.root/'bindings.json';self.mapping.write_text(json.dumps(bindings([binding(row())])));self.mapping.chmod(0o600)
        self.output=self.root/'projected/landings-projection.json'
        return [sys.executable,str(CLI),'--scratch',str(self.root),'--snapshot',str(self.source),'--bindings',str(self.mapping),'--cutoff',CUTOFF,'--output',str(self.output)]
    def run_cli(self,args):return subprocess.run(args,capture_output=True,text=True,timeout=20,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    def test_cli_private_output_inputs_unchanged_no_overwrite(self):
        args=self.command();before=(self.source.read_bytes(),self.mapping.read_bytes())
        res=self.run_cli(args);self.assertEqual(res.returncode,0,res.stderr)
        self.assertEqual(json.loads(res.stdout)['counts']['projected_positive_anchors'],1)
        self.assertNotIn('synthetic-node',res.stdout);self.assertNotIn('SYNTHETIC_PRIVATE',self.output.read_text())
        self.assertEqual(self.output.stat().st_mode&0o777,0o600);self.assertEqual(self.output.parent.stat().st_mode&0o777,0o700)
        self.assertEqual(before,(self.source.read_bytes(),self.mapping.read_bytes()))
        content=self.output.read_bytes();res=self.run_cli(args)
        self.assertNotEqual(res.returncode,0);self.assertEqual(self.output.read_bytes(),content)
    def test_cli_symlink_permissions_and_duplicate_json_keys_refused(self):
        for issue in ('mode','symlink','duplicate','invalid_line'):
            args=self.command()
            if issue=='mode':self.source.chmod(0o644)
            elif issue=='symlink':
                target=self.root/'SYNTHETIC_PRIVATE';self.source.rename(target);self.source.symlink_to(target)
            elif issue=='duplicate':self.source.write_text('{"id":"one","id":"two"}\n')
            else:self.source.write_text(json.dumps(row())+'\nnot-json\n')
            res=self.run_cli(args);self.assertNotEqual(res.returncode,0)
            self.assertEqual(res.stderr.strip(),'landings_projection_refused');self.assertFalse(res.stdout)
            self.assertFalse(self.output.exists());self.source.unlink()
    def test_cli_output_outside_scratch_or_existing_parent_refuses(self):
        args=self.command();args[-1]=str(self.root/'landings-projection.json')
        res=self.run_cli(args);self.assertNotEqual(res.returncode,0)
        args=self.command();args[-1]=str(self.root.parent/'landings-projection.json')
        res=self.run_cli(args);self.assertNotEqual(res.returncode,0)
    def test_cron_proposal_generator_preserves_other_jobs_and_refuses_ambiguity(self):
        doc=(ROOT/'experiments/nonllm-judges/VALUE-MAP-CAPTURE.md').read_text()
        script=doc.split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
        before=self.root/'cron.before';after=self.root/'cron.proposed'
        original='MAILTO=""\n37 3,11,19 * * * /bin/bash /synthetic/value-map-update.sh >> /synthetic/log 2>&1\n0 * * * * /synthetic/unrelated.sh\n'
        before.write_text(original)
        args=[sys.executable,'-c',script,'/synthetic/capture.json',str(before),str(after)]
        result=self.run_cli(args);self.assertEqual(result.returncode,0,result.stderr)
        expected=original.replace('/bin/bash /synthetic/value-map-update.sh',"JUDGES_CAPTURE_CONFIG='/synthetic/capture.json' /bin/bash /synthetic/value-map-update.sh")
        self.assertEqual(after.read_text(),expected);self.assertEqual(before.read_text(),original)
        self.assertEqual(after.stat().st_mode&0o777,0o600)
        after.unlink();before.write_text(original+original)
        self.assertNotEqual(self.run_cli(args).returncode,0);self.assertFalse(after.exists())
        before.write_text(expected)
        self.assertNotEqual(self.run_cli(args).returncode,0);self.assertFalse(after.exists())
        before.write_text(original);args[3]='/synthetic/bad%path'
        self.assertNotEqual(self.run_cli(args).returncode,0);self.assertFalse(after.exists())
    def test_bounds_and_invalid_native_records_fail_closed(self):
        with self.assertRaises(ValueError):self.project([row()]*(P.LIMIT+1))
        with self.assertRaises(ValueError):self.project([dict(row(),id=None)])
        r=row();r['piece']['text']='x'*10001;r['made']['message']=r['piece']['text']
        self.assertFalse(self.project([r])[0]['anchors'])


if __name__=='__main__':unittest.main()

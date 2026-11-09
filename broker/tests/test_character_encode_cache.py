#!/usr/bin/env python3
"""Scratch-only producer tests with an injected tiny encoder, never real weights."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
F=load('cache_fixture',ROOT/'broker/tests/test_numerical_evidence_builder.py')
E=load('cache_producer',ROOT/'experiments/character-reference/encode_cache.py')
CLI=ROOT/'experiments/character-reference/encode_cache.py'
DRIVER=r'''
import importlib.util,json,os,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('producer',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
action=os.environ.get('STUB_ACTION','normal');calls=[]
class Encoder:
    runtime={'name':'synthetic-encoder','version':'test-1','native_version':None}
    def __init__(self,path,settings):
        assert path.name=='encoder-copy.gguf'
        assert path.read_bytes().startswith(b'GGUFsynthetic')
        assert path.stat().st_mode&0o777==0o400
        self.path=path
        if action=='network':
            import socket
            socket.socket().connect(('127.0.0.1',1))
        if action=='process':
            import subprocess
            subprocess.run([sys.executable,'-c','pass'])
        if action=='exception':
            os.write(2,b'PRIVATE-CANARY native message\n')
            raise ValueError('PRIVATE-CANARY')
    def encode(self,text):
        calls.append(text)
        if action=='mutate':
            self.path.chmod(0o600);self.path.write_bytes(b'GGUFchanged')
        if action=='samebytes':
            raw=self.path.read_bytes();self.path.chmod(0o600);self.path.write_bytes(raw);self.path.chmod(0o400)
        if action=='zero':return [0.,0.,0.]
        if action=='nan':return [float('nan'),1.,2.]
        if action=='nested':return [[1.,2.,3.]]
        if action=='dimension' and len(calls)>1:return [1.,2.]
        return [float(len(text)),1.,2.]
    def close(self):pass
try:
    m.run(sys.argv[2:],factory=Encoder)
    out=Path(sys.argv[sys.argv.index('--output')+1])
    (out/'stub-calls.json').write_text(json.dumps(calls))
except Exception:
    print(json.dumps({'written':False,'error':'cache_production_failed'}),file=sys.stderr);sys.exit(1)
'''


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='character-cache-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.sender=Mock(side_effect=AssertionError('network forbidden'))
        guard=patch.object(socket.socket,'connect',self.sender);guard.start();self.addCleanup(guard.stop);self.addCleanup(self.sender.assert_not_called)
        self.assertNotIn('.vintos',self.root.parts);self.assertIsInstance(socket.socket.connect,Mock)
        self.bundle,self.graph,_,_=F.fixture();self.original=self.root/'source.gguf';self.original.write_bytes(b'GGUFsynthetic file bytes')
        self.inp=self.root/'input.json';self.out=self.root/'encoded';self.driver=self.root/'driver.py';self.driver.write_text(DRIVER)

    def run_cli(self,action='normal',**changes):
        self.inp.write_text(json.dumps(self.bundle))
        options=dict(gguf=self.original,input=self.inp,scratch=self.root,output=self.out,cutoff=F.CUTOFF,pooling='mean')
        options.update(changes)
        args=[sys.executable,str(self.driver),str(CLI)]+[part for k,v in options.items() for part in ('--'+k,str(v))]
        return subprocess.run(args,env=dict(os.environ,SPARK_WORKSPACE=str(self.root),STUB_ACTION=action,PYTHONDONTWRITEBYTECODE='1'),
            capture_output=True,text=True,timeout=30)

    def test_full_pipeline_copy_hash_metadata_and_permissions(self):
        result=self.run_cli();self.assertEqual(result.returncode,0,result.stderr)
        projection=json.loads((self.out/'character-input.json').read_text());metadata=json.loads((self.out/'cache-metadata.json').read_text())
        self.assertEqual(projection['rows'],self.bundle['rows']);self.assertEqual(json.loads(self.inp.read_text()),self.bundle)
        self.assertEqual(self.original.read_bytes(),(self.out/'encoder-copy.gguf').read_bytes())
        manifest=projection['cache_producer'];self.assertEqual(manifest['artifact_sha256'],hashlib.sha256(self.original.read_bytes()).hexdigest())
        self.assertEqual(manifest['runtime']['version'],'test-1');self.assertFalse(manifest['historical_backfill'])
        self.assertEqual((self.out/'encoder-copy.gguf').stat().st_mode&0o777,0o400)
        for name in ('character-input.json','cache.json','cache-metadata.json','counts.json'):self.assertEqual((self.out/name).stat().st_mode&0o777,0o600)
        self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        for entry in metadata['entries']:
            self.assertEqual(entry['input_sha256'],entry['reply_sha256']);self.assertTrue(entry['reply_ids'])
            self.assertGreaterEqual(entry['reply_encoding']['started_at'],manifest['frozen_at'])
            self.assertEqual(entry['encoder_id'],projection['encoder']['id'])
        built,coverage=F.B.build(projection,self.graph,metadata['entries'],[],F.CUTOFF)
        self.assertFalse(coverage['encoder_metadata_available'])
        self.assertEqual(coverage['per_field_reason_counts']['encoder_pin']['recorded'],32)
        self.assertEqual(coverage['per_field_reason_counts']['encoder_freeze']['missing_invalid_or_late_freeze'],32)
        self.assertNotIn('encoder_frozen_at',built['numerical_evidence'])

    def test_exact_full_strings_no_prefix_truncation(self):
        row=next(r for r in self.bundle['rows'] if r['role']=='assistant')
        row['content']='Synthetic full string Ω '+('z'*2400);row['context']='Exact context Ω'
        # Attribution uses retained serving labels; old witness hash is not rewritten.
        self.assertEqual(self.run_cli().returncode,0)
        calls=json.loads((self.out/'stub-calls.json').read_text())
        self.assertIn(row['content'],calls);self.assertIn(row['context'],calls);self.assertEqual(len(calls),len(set(calls)))
        metadata=json.loads((self.out/'cache-metadata.json').read_text())
        entry=next(e for e in metadata['entries'] if row['turn_id'] in e['reply_ids'])
        self.assertEqual(entry['reply_sha256'],hashlib.sha256(row['content'].encode()).hexdigest())

    def test_late_freeze_not_backdated_to_source_mtime(self):
        os.utime(self.original,(1,1));self.assertEqual(self.run_cli().returncode,0)
        manifest=json.loads((self.out/'character-input.json').read_text())['cache_producer']
        self.assertGreater(manifest['frozen_at'],1_700_000_000)
        counts=json.loads((self.out/'counts.json').read_text());self.assertEqual(counts['replies_predating_freeze'],32)

    def test_changed_copy_refuses_cache(self):
        self.assertNotEqual(self.run_cli('mutate').returncode,0);self.assertFalse((self.out/'cache.json').exists())

    def test_restored_bytes_still_detect_change(self):
        self.assertNotEqual(self.run_cli('samebytes').returncode,0);self.assertFalse((self.out/'cache.json').exists())

    def test_existing_copy_or_output_refused(self):
        self.out.mkdir();target=self.out/'encoder-copy.gguf';target.write_bytes(b'untouched')
        self.assertNotEqual(self.run_cli().returncode,0);self.assertEqual(target.read_bytes(),b'untouched')

    def test_network_forbidden(self):
        self.assertNotEqual(self.run_cli('network').returncode,0);self.assertFalse((self.out/'cache.json').exists())

    def test_subprocess_forbidden(self):
        self.assertNotEqual(self.run_cli('process').returncode,0);self.assertFalse((self.out/'cache.json').exists())

    def test_native_and_exception_output_sanitized(self):
        result=self.run_cli('exception');self.assertNotEqual(result.returncode,0)
        self.assertNotIn('PRIVATE-CANARY',result.stderr+result.stdout);self.assertNotIn(str(self.root),result.stderr+result.stdout)

    def test_zero_vector_refused(self):self.assertNotEqual(self.run_cli('zero').returncode,0)
    def test_nonfinite_vector_refused(self):self.assertNotEqual(self.run_cli('nan').returncode,0)
    def test_unpooled_vector_refused(self):self.assertNotEqual(self.run_cli('nested').returncode,0)
    def test_dimension_mismatch_refused(self):self.assertNotEqual(self.run_cli('dimension').returncode,0)

    def test_old_cache_not_relabelled_or_reused(self):
        before=copy.deepcopy(self.bundle['embeddings']);self.assertEqual(self.run_cli().returncode,0)
        fresh=json.loads((self.out/'character-input.json').read_text())
        self.assertNotEqual(fresh['embeddings'],before);self.assertEqual(json.loads(self.inp.read_text())['embeddings'],before)
        self.assertNotEqual(fresh['encoder']['id'],self.bundle['encoder']['id'])

    def test_controls_require_separate_production(self):
        self.bundle['controls']=[{'synthetic':'old'}];self.assertNotEqual(self.run_cli().returncode,0);self.assertFalse(self.out.exists())

    def test_output_repository_and_nonprivate_scratch_refused(self):
        self.assertNotEqual(self.run_cli(output=ROOT/'never-create-cache').returncode,0)
        self.root.chmod(0o755);self.assertNotEqual(self.run_cli().returncode,0)

    def test_source_and_output_symlinks_refused(self):
        alias=self.root/'alias.gguf';alias.symlink_to(self.original)
        self.assertNotEqual(self.run_cli(gguf=alias).returncode,0)
        self.out.symlink_to(self.root,target_is_directory=True);self.assertNotEqual(self.run_cli().returncode,0)

    def test_conflicting_contexts_refused(self):
        r=copy.deepcopy(next(r for r in self.bundle['rows'] if r['role']=='assistant'));r['turn_id']='synthetic-other';r['context']='different'
        self.bundle['rows'].append(r);self.assertNotEqual(self.run_cli().returncode,0);self.assertFalse(self.out.exists())

    def test_real_adapter_arguments_with_stub_module(self):
        calls={}
        class Model:
            def __init__(self,**kwargs):calls.update(kwargs)
            def pooling_type(self):return 1
            def embed(self,text,**kwargs):calls['embed']=(text,kwargs);return [3.,4.]
            def close(self):calls['closed']=True
        module=types.SimpleNamespace(__version__='synthetic-api-1',LLAMA_POOLING_TYPE_MEAN=1,Llama=Model)
        with patch.dict(sys.modules,{'llama_cpp':module}):
            runtime=E.LocalEncoder(self.original,dict(pooling='mean',context_tokens=8192,threads=2));self.assertEqual(runtime.encode('exact'),[3.,4.]);runtime.close()
        self.assertEqual(calls['model_path'],str(self.original));self.assertTrue(calls['embedding']);self.assertEqual(calls['n_gpu_layers'],0)
        self.assertFalse(calls['use_mmap']);self.assertEqual(calls['embed'],('exact',dict(normalize=False,truncate=False)))
        self.assertEqual(calls['n_batch'],calls['n_ctx']);self.assertTrue(calls['closed'])
        self.assertFalse(calls['offload_kqv']);self.assertFalse(calls['op_offload']);self.assertFalse(calls['flash_attn'])

if __name__=='__main__':unittest.main()

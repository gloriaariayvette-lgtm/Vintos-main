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
clock_state={'wall':1800000000.,'mono':100.,'wall_calls':0}
if action=='stepping-clock':
    import types
    def wall():
        clock_state['wall_calls']+=1
        return clock_state['wall']
    def mono():
        clock_state['mono']+=.125
        return clock_state['mono']
    m.time=types.SimpleNamespace(time=wall,monotonic=mono)

if os.environ.get('STUB_PINS'):
    pins=m.Q.validate_registry(json.loads(os.environ['STUB_PINS']))
    m.Q.load_pins=lambda:pins
class Encoder:
    runtime={'name':'synthetic-encoder','version':'test-1','native_version':None}
    def __init__(self,path,settings):
        assert path.name=='encoder-copy.gguf'
        assert path.read_bytes().startswith(b'GGUFsynthetic')
        assert path.stat().st_mode&0o777==0o400
        self.path=path
        (path.parent/'stub-loaded').write_text('synthetic')
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
        if action=='stepping-clock':clock_state['wall']-=2.8
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
    if action=='missing-runtime':sys.modules['llama_cpp']=None
    m.run(sys.argv[2:],factory=m.LocalEncoder if action=='missing-runtime' or action.startswith('runtime-') else Encoder)
    out=Path(sys.argv[sys.argv.index('--output')+1])
    (out/'stub-calls.json').write_text(json.dumps(calls))
    if action=='stepping-clock':(out/'stub-clock.json').write_text(json.dumps(clock_state))
except Exception as exc:
    print(json.dumps(m.error_payload(exc)),file=sys.stderr);sys.exit(1)
'''


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='character-cache-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.sender=Mock(side_effect=AssertionError('network forbidden'))
        guard=patch.object(socket.socket,'connect',self.sender);guard.start();self.addCleanup(guard.stop);self.addCleanup(self.sender.assert_not_called)
        self.assertNotIn('.vintos',self.root.parts);self.assertIsInstance(socket.socket.connect,Mock)
        self.bundle,self.graph,_,_=F.fixture();self.original=self.root/'source.gguf';self.original.write_bytes(b'GGUFsynthetic file bytes')
        self.pins=None
        self.inp=self.root/'input.json';self.out=self.root/'encoded';self.driver=self.root/'driver.py';self.driver.write_text(DRIVER)

    def run_cli(self,action='normal',**changes):
        self.inp.write_text(json.dumps(self.bundle))
        options=dict(gguf=self.original,input=self.inp,scratch=self.root,output=self.out,cutoff=F.CUTOFF,pooling='mean')
        options.update(changes)
        args=[sys.executable,str(self.driver),str(CLI)]+[part for k,v in options.items() for part in ('--'+k,str(v))]
        return subprocess.run(args,env=dict(os.environ,SPARK_WORKSPACE=str(self.root),STUB_ACTION=action,STUB_PINS=json.dumps(self.pins) if self.pins else '',PYTHONDONTWRITEBYTECODE='1'),
            capture_output=True,text=True,timeout=30)

    def published(self,**changes):
        pin=dict(id='synthetic-pin',publisher='synthetic-publisher',repo='synthetic/repository',filename='fixture.gguf',
            revision='a'*40,revision_at='2019-01-01T00:00:00Z',artifact_sha256=hashlib.sha256(self.original.read_bytes()).hexdigest(),
            artifact_kind='external_pretrained',trained_on_subject_data=False,reviewed=True)
        pin.update(changes);self.pins={'schema':'published-encoder-pins-v1','pins':[pin]}
        return pin

    def published_cli(self,**changes):
        options={'freeze-source':'published_artifact','artifact-kind':'external_pretrained','published-pin':'synthetic-pin'}
        options.update(changes);return self.run_cli(**options)

    def test_published_freeze_producer_builder_runner(self):
        pin=self.published();result=self.published_cli();self.assertEqual(result.returncode,0,result.stderr)
        projection=json.loads((self.out/'character-input.json').read_text())
        metadata=json.loads((self.out/'cache-metadata.json').read_text())['entries']
        counts=json.loads((self.out/'counts.json').read_text())
        receipt=projection['cache_producer']['freeze_receipt']
        self.assertEqual(receipt['frozen_at'],E.Q.instant(pin['revision_at']))
        self.assertGreater(receipt['copy_completed_at'],receipt['frozen_at'])
        self.assertEqual(receipt['published_pin'],pin)
        self.assertEqual(counts['encoder_freeze_sources']['published_artifact'],32)
        self.assertEqual(counts['encoder_freeze_sources']['copy_time'],0)
        for entry in metadata:
            self.assertEqual(entry['freeze_receipt'],receipt)
            self.assertGreaterEqual(entry['reply_encoding']['started_at'],receipt['copy_completed_at'])
        pins=E.Q.validate_registry(self.pins)
        with patch.object(F.B.Q,'load_pins',return_value=pins):
            built,coverage=F.B.build(projection,self.graph,metadata,[],F.CUTOFF)
            private,public=F.B.R.evaluate(built,None,F.CUTOFF)
        self.assertTrue(coverage['encoder_metadata_available'])
        self.assertEqual(coverage['encoder_freeze_sources']['published_artifact'],32)
        self.assertEqual(public['encoder_freeze_sources']['published_artifact'],32)
        self.assertEqual(public['views']['window30']['admitted_original_acts'],32)
        self.assertGreater(sum(s['voice_scored'] for s in public['views']['window30']['per_mode_surface']),0)
        self.assertEqual(private['encoder_freeze_receipt'],receipt)
        self.assertEqual(built['rows'],self.bundle['rows'])
        for word in ('synthetic-pin','sha256','vector','fixture.gguf','synthetic/repository'):
            self.assertNotIn(word,json.dumps(public))
        # Recheck the checked-in pin at both downstream boundaries, not only production.
        with self.assertRaises(ValueError):F.B.build(projection,self.graph,metadata,[],F.CUTOFF)
        with self.assertRaises(ValueError):F.B.R.evaluate(built,None,F.CUTOFF)
        with patch.object(F.B.Q,'load_pins',return_value=pins):
            built['numerical_evidence']['encoder_frozen_at']-=1
            with self.assertRaises(ValueError):F.B.R.evaluate(built,None,F.CUTOFF)

    def test_published_hash_mismatch_refused(self):
        self.published(artifact_sha256='0'*64)
        self.assertNotEqual(self.published_cli().returncode,0);self.assertFalse((self.out/'cache.json').exists());self.assertFalse((self.out/'stub-loaded').exists())

    def test_published_missing_pin_refused(self):
        self.assertNotEqual(self.published_cli().returncode,0);self.assertFalse((self.out/'cache.json').exists())

    def test_published_local_trained_refused(self):
        self.published()
        self.assertNotEqual(self.published_cli(**{'artifact-kind':'local_trained'}).returncode,0)
        self.assertFalse((self.out/'cache.json').exists())

    def test_published_subject_trained_pin_refused(self):
        self.published(trained_on_subject_data=True);self.assertNotEqual(self.published_cli().returncode,0)

    def test_published_unreviewed_pin_refused(self):
        self.published(reviewed=False);self.assertNotEqual(self.published_cli().returncode,0)

    def test_published_future_revision_refused(self):
        self.published(revision_at='2099-01-01T00:00:00Z');self.assertNotEqual(self.published_cli().returncode,0)

    def test_unused_pin_with_copy_time_refused(self):
        self.published();self.assertNotEqual(self.published_cli(**{'freeze-source':'copy_time'}).returncode,0)

    def test_copy_source_and_legacy_separate(self):
        self.assertEqual(self.run_cli().returncode,0)
        projection=json.loads((self.out/'character-input.json').read_text())
        receipt=projection['cache_producer']['freeze_receipt']
        self.assertEqual(receipt['frozen_at'],receipt['copy_completed_at']);self.assertIsNone(receipt['published_pin'])
        self.assertEqual(receipt['artifact_kind'],'local_trained')
        self.assertEqual(json.loads((self.out/'counts.json').read_text())['encoder_freeze_sources']['copy_time'],32)
        b,g,c,h=F.fixture();built,summary=F.B.build(b,g,c,h,F.CUTOFF)
        self.assertEqual(summary['encoder_freeze_sources']['legacy_unknown'],32)
        self.assertEqual(F.B.R.evaluate(built,None,F.CUTOFF)[1]['encoder_freeze_sources']['legacy_unknown'],32)

    def test_published_revision_after_acts_stays_unscored(self):
        self.published(revision_at='2021-01-01T00:00:00Z');self.assertEqual(self.published_cli().returncode,0)
        projection=json.loads((self.out/'character-input.json').read_text())
        metadata=json.loads((self.out/'cache-metadata.json').read_text())['entries']
        with patch.object(F.B.Q,'load_pins',return_value=E.Q.validate_registry(self.pins)):
            built,counts=F.B.build(projection,self.graph,metadata,[],F.CUTOFF)
        self.assertFalse(counts['encoder_metadata_available'])
        self.assertEqual(counts['per_field_reason_counts']['encoder_freeze']['missing_invalid_or_late_freeze'],32)
        self.assertNotIn('encoder_frozen_at',built['numerical_evidence'])

    def test_mixed_freeze_sources_not_collapsed(self):
        b,g,c,h=F.fixture();entry=c[0]
        entry['freeze_source']='copy_time'
        entry['freeze_receipt']=F.B.Q.qualify(entry['artifact_sha256'],entry['frozen_at'])
        built,counts=F.B.build(b,g,c,h,F.CUTOFF)
        self.assertFalse(counts['encoder_metadata_available'])
        self.assertEqual(counts['encoder_freeze_sources']['copy_time'],1)
        self.assertEqual(counts['encoder_freeze_sources']['legacy_unknown'],31)
        self.assertNotIn('encoder_frozen_at',built['numerical_evidence'])

    def test_qualifier_without_receipt_refused(self):
        b,g,c,h=F.fixture();c[0]['freeze_source']='published_artifact'
        with self.assertRaises(ValueError):F.B.build(b,g,c,h,F.CUTOFF)
        b,g,c,h=F.fixture();built,_=F.B.build(b,g,c,h,F.CUTOFF)
        built['numerical_evidence']['encoder_freeze_source']='published_artifact'
        with self.assertRaises(ValueError):F.B.R.evaluate(built,None,F.CUTOFF)

    def test_checked_in_reviewed_pin_parses(self):
        pins=E.Q.load_pins()
        pin=pins['nomic-embed-text-v1.5-Q4_K_M']
        self.assertRegex(pin['artifact_sha256'],r'^[0-9a-f]{64}$')
        self.assertEqual(pin['size_bytes'],84106624)
        self.assertEqual(pin['revision'],'0188c9bf409793f810680a5a431e7b899c46104c')
        self.assertEqual(pin['revision_at'],'2025-04-28T20:14:53+00:00')
        self.assertTrue(pin['reviewed']);self.assertFalse(pin['trained_on_subject_data'])
        self.assertIn('local sha256',pin['reviewer'])
        receipt=E.Q.qualify(pin['artifact_sha256'],1800000000,'published_artifact','external_pretrained',pin['id'])
        self.assertEqual(receipt['published_pin'],pin)
        for field,value in [('size_bytes',True),('size_bytes',-1),('reviewer',''),('reviewer',None)]:
            bad=copy.deepcopy(pin);bad[field]=value
            with self.assertRaises(ValueError):E.Q.validate_registry({'schema':'published-encoder-pins-v1','pins':[bad]})

    def test_registry_validation_and_receipt_tampering(self):
        pin=self.published();registry=copy.deepcopy(self.pins)
        for field,value in [('reviewed',1),('trained_on_subject_data',0),('artifact_kind','local_trained'),
                            ('revision','main'),('revision_at','2019-01-01'),('publisher',''),('artifact_sha256','x'*64)]:
            with self.subTest(field=field):
                bad=copy.deepcopy(registry);bad['pins'][0][field]=value
                with self.assertRaises(ValueError):E.Q.validate_registry(bad)
        duplicate=copy.deepcopy(registry);duplicate['pins'].append(pin)
        with self.assertRaises(ValueError):E.Q.validate_registry(duplicate)
        with self.assertRaises(ValueError):E.Q.pairs([('schema','a'),('schema','b')])
        with patch.object(E.Q,'load_pins',return_value=E.Q.validate_registry(registry)):
            receipt=E.Q.qualify(pin['artifact_sha256'],1700000000,'published_artifact','external_pretrained',pin['id'])
            for field,value in [('copy_completed_at',0),('artifact_sha256','0'*64),('pin_sha256','0'*64),('artifact_kind','local_trained')]:
                bad=dict(receipt);bad[field]=value
                with self.assertRaises(ValueError):E.Q.verify(bad,pin['artifact_sha256'],receipt['frozen_at'],'published_artifact')

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

    def test_missing_local_runtime_has_typed_private_refusal(self):
        result=self.run_cli('missing-runtime');self.assertNotEqual(result.returncode,0)
        error=json.loads(result.stderr)
        self.assertEqual(error['error'],'encoder_runtime_unavailable')
        self.assertEqual(error['dependency'],'llama-cpp-python')
        self.assertIn('owner approval',error['hint'])
        self.assertNotIn(str(self.root),result.stderr)
        self.assertFalse((self.out/'cache.json').exists())
        self.assertFalse((self.out/'stub-loaded').exists())

    def runtime_stub(self, opening):
        # Import happens inside the producer guard, using only this synthetic module.
        text="""import os
__version__='fixture-runtime'
LLAMA_POOLING_TYPE_MEAN=1
"""+opening+"""
class Llama:
    def __init__(self, **kw):
        assert kw['n_batch']==kw['n_ctx']==kw['n_ubatch']==8192
        assert kw['n_gpu_layers']==0 and kw['use_mmap'] is False
    def pooling_type(self):return 1
    def embed(self,text,normalize,truncate):
        assert normalize is False and truncate is False
        return [len(text),1.,2.]
    def close(self):pass
"""
        (self.root/'llama_cpp.py').write_text(text)

    def test_runtime_import_can_open_only_real_devnull_for_writing(self):
        self.runtime_stub("with open(os.devnull,'w') as f:f.write('synthetic discard')\n")
        result=self.run_cli('runtime-null');self.assertEqual(result.returncode,0,result.stderr)
        manifest=json.loads((self.out/'character-input.json').read_text())['cache_producer']
        self.assertEqual(manifest['runtime']['version'],'fixture-runtime')
        self.assertEqual(manifest['settings']['n_ubatch'],8192)

    def test_runtime_import_outside_output_write_remains_forbidden(self):
        self.runtime_stub("with open(os.path.join(os.path.dirname(__file__),'escape.txt'),'w') as f:f.write('denied')\n")
        result=self.run_cli('runtime-outside');self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.root/'escape.txt').exists());self.assertFalse((self.out/'cache.json').exists())

    def test_runtime_import_null_alias_remains_forbidden(self):
        (self.root/'null-alias').symlink_to(os.devnull)
        self.runtime_stub("with open(os.path.join(os.path.dirname(__file__),'null-alias'),'w') as f:f.write('denied')\n")
        self.assertNotEqual(self.run_cli('runtime-null-alias').returncode,0)

    def test_local_adapter_microbatch_matches_context_at_other_sizes(self):
        for size in (1024,16384):
            constructor=Mock(return_value=types.SimpleNamespace(pooling_type=lambda:1,close=lambda:None))
            module=types.SimpleNamespace(__version__='synthetic',LLAMA_POOLING_TYPE_MEAN=1,Llama=constructor)
            with patch.dict(sys.modules,llama_cpp=module):
                model=E.LocalEncoder(self.original,dict(pooling='mean',context_tokens=size,threads=2));model.close()
            self.assertEqual(constructor.call_args.kwargs['n_ubatch'],size)
            self.assertEqual(constructor.call_args.kwargs['n_batch'],size)
            self.assertEqual(constructor.call_args.kwargs['n_ctx'],size)

    def test_stepping_wall_clock_preserves_real_monotonic_order_and_anchor(self):
        result=self.run_cli('stepping-clock');self.assertEqual(result.returncode,0,result.stderr)
        manifest=json.loads((self.out/'character-input.json').read_text())['cache_producer']
        metadata=json.loads((self.out/'cache-metadata.json').read_text())['entries']
        state=json.loads((self.out/'stub-clock.json').read_text())
        anchor=manifest['clock_receipt'];self.assertEqual(anchor['wall_at_anchor'],1800000000.)
        self.assertEqual(state['wall_calls'],1);self.assertLess(state['wall'],anchor['wall_at_anchor']-3)
        self.assertEqual(anchor['cross_process_order'],'not_attested')
        copied=manifest['copy_completed_elapsed_seconds']
        self.assertAlmostEqual(manifest['copy_completed_at'],anchor['wall_at_anchor']+copied)
        self.assertEqual(manifest['freeze_receipt']['copy_completed_at'],manifest['copy_completed_at'])
        for row in metadata:
            self.assertEqual(row['clock_receipt'],anchor)
            for label in ('reply_encoding','context_encoding'):
                c=row[label];self.assertEqual(c['clock_source'],'anchored_monotonic')
                self.assertGreaterEqual(c['started_elapsed_seconds'],copied)
                self.assertGreaterEqual(c['finished_elapsed_seconds'],c['started_elapsed_seconds'])
                self.assertAlmostEqual(c['started_at'],anchor['wall_at_anchor']+c['started_elapsed_seconds'])
                self.assertAlmostEqual(c['finished_at'],anchor['wall_at_anchor']+c['finished_elapsed_seconds'])

    def test_invalid_monotonic_clock_refuses_instead_of_clamping(self):
        clock=E.AnchoredClock(wall=lambda:1000.,monotonic=iter([10.,10.1,11.,10.9]).__next__)
        self.assertGreater(clock.sample()['at'],1000.)
        with self.assertRaises(ValueError):clock.sample()
        for value in (float('nan'),float('inf'),-1,True):
            with self.assertRaises(ValueError):E.AnchoredClock(wall=lambda:value,monotonic=lambda:10.)

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
